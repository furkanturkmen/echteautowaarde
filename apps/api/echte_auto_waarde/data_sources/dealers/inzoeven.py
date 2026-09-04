"""Inzoeven public inventory (inzoeven.nl).

Everything a valuation needs is on the inventory page itself, so one request
reads the whole sample and no detail page is opened.

All knowledge of this site's markup lives here. Nothing downstream — ingestion,
normalization, comparables, valuation — knows this dealer exists.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass, field

from echte_auto_waarde.data_sources.base import RawListing, RawSeller, RawSnapshot, RawVehicle
from echte_auto_waarde.data_sources.dealers.collector import (
    DEFAULT_LISTING_LIMIT,
    PoliteFetcher,
    build_fetcher,
    clamp_limit,
    clean_variant,
    observed_now,
    parse_euro,
    parse_int,
    text_of,
    unescape,
)
from echte_auto_waarde.models.enums import DataSourceType, ListingStatus

logger = logging.getLogger(__name__)

SOURCE_KEY = "dealer:inzoeven"
BASE_URL = "https://inzoeven.nl"
INVENTORY_URL = f"{BASE_URL}/aanbod"

# One card per vehicle on the inventory page.
_CARD_SPLIT = re.compile(r'(?=<div class="bg-white rounded-xl shadow-sm)')
_LISTING_HREF = re.compile(r'href="(/aanbod/([a-z0-9-]+?)-(\d+))"')
_TITLE = re.compile(r"<h3[^>]*>(.*?)</h3>", re.S)
_SUBTITLE = re.compile(r"<p class=\"text-slate-500[^\"]*\">(.*?)</p>", re.S)
_FACT_SPANS = re.compile(r"<span>(.*?)</span>", re.S)
_PRICE = re.compile(r'<div class="text-2xl[^"]*">(.*?)</div>', re.S)

_FUEL_WORDS = ("benzine", "diesel", "elektrisch", "hybride", "lpg", "cng", "waterstof")

# The card states the gearbox as well as the category — "Automaat 8
# versnellingen" — and normalization expects the category alone. Only these
# exact words are recognised; anything else stays unknown rather than guessed.
# Order matters: the longer wording is checked first so "semi-automaat" is not
# read as "automaat".
_TRANSMISSION_WORDS = ("semi-automaat", "handgeschakeld", "handmatig", "automaat")


@dataclass
class InzoevenDataSource:
    """A `DataSourceAdapter` over one dealer's public inventory page."""

    key: str = SOURCE_KEY
    source_type: DataSourceType = DataSourceType.DEALER_SITE
    name: str = "Openbare dealeradvertenties"
    # A single dealer's stock is real evidence, but it is one seller's pricing
    # policy rather than a market, so it is trusted less than a broad import.
    quality: float = 0.55
    limit: int = DEFAULT_LISTING_LIMIT
    fetcher: PoliteFetcher = field(default_factory=build_fetcher)

    # Rows seen, parsed and rejected, for the run report.
    discovered: int = 0
    rejected: int = 0
    # Populated by the first fetch and reused for the rest of the run.
    _collected: list[RawListing] | None = None

    @property
    def origin(self) -> str:
        return INVENTORY_URL

    def fetch_listings(self) -> Iterable[RawListing]:
        """The sample, fetched once.

        The import pipeline asks twice — once to validate, once to ingest — and
        a website should not be asked twice for the same page. Holding the
        result also guarantees both passes see identical data.
        """
        if self._collected is None:
            self._collected = list(self.parse(self.fetcher.get(INVENTORY_URL)))
        return self._collected

    def parse(self, html: str) -> Iterable[RawListing]:
        """Read listing cards out of an inventory page.

        A card that cannot be understood is skipped and counted; one bad card
        never ends the run.
        """
        cards = _CARD_SPLIT.split(html)[1:]
        self.discovered = len(cards)
        listings: list[RawListing] = []

        for card in cards:
            if len(listings) >= clamp_limit(self.limit):
                break
            listing = self._parse_card(card)
            if listing is None:
                self.rejected += 1
                continue
            listings.append(listing)

        return listings

    def _parse_card(self, card: str) -> RawListing | None:
        card = unescape(card)
        href = _LISTING_HREF.search(card)
        title = _TITLE.search(card)
        price = _PRICE.search(card)
        if not (href and title):
            return None

        path, _slug, listing_id = href.groups()
        asking_price_cents = parse_euro(text_of(price.group(1))) if price else None
        if asking_price_cents is None:
            return None

        # "Audi<!-- --> <!-- -->A5 Coupe" -> make "Audi", model "A5 Coupe".
        heading = text_of(title.group(1))
        make, _, model = heading.partition(" ")
        if not make or not model:
            return None

        subtitle = _SUBTITLE.search(card)
        variant = clean_variant(text_of(subtitle.group(1))) if subtitle else None

        facts = [text_of(span) for span in _FACT_SPANS.findall(card)]
        year = next((parse_int(fact, 1950, 2100) for fact in facts if _is_year(fact)), None)
        mileage = next(
            (parse_int(fact, 0, 2_000_000) for fact in facts if "km" in fact.lower()), None
        )
        fuel = _first_word(facts, _FUEL_WORDS)
        transmission = _transmission_category(facts)

        observed_at = observed_now()
        return RawListing(
            # The dealer's own numeric id from the canonical URL: stable, and
            # derived from nothing that changes.
            external_reference=listing_id,
            vehicle=RawVehicle(
                make=make,
                model=model,
                year=year,
                mileage_km=mileage,
                engine_description=variant,
                fuel_type=fuel,
                transmission=transmission,
                option_texts=(),
            ),
            asking_price_cents=asking_price_cents,
            first_seen_at=observed_at,
            last_seen_at=observed_at,
            # The dealer as a seller type only. No name, telephone or address:
            # this pilot collects market evidence, not contact details.
            seller=RawSeller(seller_type="DEALER", name=None, city=None),
            url=f"{BASE_URL}{path}",
            status=ListingStatus.ACTIVE,
            snapshots=(
                RawSnapshot(
                    observed_at=observed_at,
                    asking_price_cents=asking_price_cents,
                    mileage_km=mileage,
                    status=ListingStatus.ACTIVE,
                ),
            ),
        )


def _transmission_category(facts: list[str]) -> str | None:
    """The transmission category, without the gearbox detail beside it.

    The card writes "Automaat 8 versnellingen"; normalization recognises
    "Automaat". Only the exact words in `_TRANSMISSION_WORDS` are matched — a
    wording we do not know is left alone so it normalizes to UNKNOWN, which
    lowers confidence rather than inventing a gearbox.
    """
    for fact in facts:
        lowered = fact.lower()
        for word in _TRANSMISSION_WORDS:
            if word in lowered:
                return word.capitalize()
    return None


def _is_year(fact: str) -> bool:
    digits = re.sub(r"[^\d]", "", fact)
    return len(digits) == 4 and digits.startswith(("19", "20"))


def _first_word(facts: list[str], words: tuple[str, ...]) -> str | None:
    """The fact that mentions one of `words`, without its decorative icon.

    The page prefixes each fact with an emoji; normalization expects a word.
    """
    for fact in facts:
        lowered = fact.lower()
        for word in words:
            if word in lowered:
                return re.sub(r"^[^\w]+", "", fact).strip() or None
    return None
