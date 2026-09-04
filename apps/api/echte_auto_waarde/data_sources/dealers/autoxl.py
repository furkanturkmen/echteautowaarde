"""AutoXL public inventory (autoxl.nl).

The inventory cards carry accessibility labels — "Bouwjaar:", "Kilometerstand:",
"Transmissie:", "Brandstof:" — so the facts are read by their label rather than
by position, which is both more robust and less dependent on presentation.

One request reads the sample; no detail page is opened. All knowledge of this
site's markup stops at this module.
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

SOURCE_KEY = "dealer:autoxl"
BASE_URL = "https://autoxl.nl"
INVENTORY_URL = f"{BASE_URL}/voertuigen"

_CARD_SPLIT = re.compile(r'(?=id="car-main-\d+")')
_LISTING_HREF = re.compile(r'href="(/voertuigen/([a-z0-9-]+))"')
# The dealer's numeric id sits in the slug, before an optional drivetrain tag.
_REFERENCE = re.compile(r"-(\d{6,})(?:-[a-z]+)?$")
_HEADING = re.compile(r'<p class="text-lg font-bold[^"]*">(.*?)</p>', re.S)
_SUBTITLE = re.compile(r'<p class="text-md[^"]*">(.*?)</p>', re.S)
_LABELLED = re.compile(r'<span class="sr-only">([^<]+)</span>\s*<span[^>]*>([^<]*)</span>', re.S)
# Two prices appear per card. Only the purchase price is an asking price; the
# monthly lease figure must never be mistaken for one.
_PURCHASE_PRICE = re.compile(r"Kopen.*?€\s*([\d.,\s]+)", re.S)


@dataclass
class AutoXlDataSource:
    """A `DataSourceAdapter` over one dealer's public inventory page."""

    key: str = SOURCE_KEY
    source_type: DataSourceType = DataSourceType.DEALER_SITE
    name: str = "Openbare dealeradvertenties"
    quality: float = 0.55
    limit: int = DEFAULT_LISTING_LIMIT
    fetcher: PoliteFetcher = field(default_factory=build_fetcher)

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
        heading = _HEADING.search(card)
        if not (href and heading):
            return None

        path, slug = href.groups()
        # The dealer's own id where the URL carries one; otherwise the canonical
        # URL itself. Never the price, the mileage or the position on the page.
        reference = _REFERENCE.search(slug)
        external_reference = path if reference is None else reference.group(1)

        price_match = _PURCHASE_PRICE.search(re.sub(r"\s+", " ", card))
        asking_price_cents = parse_euro(f"€ {price_match.group(1)}") if price_match else None
        if asking_price_cents is None:
            return None

        make, _, model = text_of(heading.group(1)).partition(" ")
        if not make or not model:
            return None

        subtitle = _SUBTITLE.search(card)
        variant = clean_variant(text_of(subtitle.group(1))) if subtitle else None

        facts = {
            label.strip().rstrip(":").lower(): text_of(value)
            for label, value in _LABELLED.findall(card)
        }
        observed_at = observed_now()

        return RawListing(
            external_reference=external_reference,
            vehicle=RawVehicle(
                make=make,
                model=model,
                year=parse_int(facts.get("bouwjaar", ""), 1950, 2100),
                mileage_km=parse_int(facts.get("kilometerstand", ""), 0, 2_000_000),
                engine_description=variant,
                fuel_type=facts.get("brandstof") or None,
                transmission=facts.get("transmissie") or None,
                option_texts=(),
            ),
            asking_price_cents=asking_price_cents,
            first_seen_at=observed_at,
            last_seen_at=observed_at,
            seller=RawSeller(seller_type="DEALER", name=None, city=None),
            url=f"{BASE_URL}{path}",
            status=ListingStatus.ACTIVE,
            snapshots=(
                RawSnapshot(
                    observed_at=observed_at,
                    asking_price_cents=asking_price_cents,
                    mileage_km=parse_int(facts.get("kilometerstand", ""), 0, 2_000_000),
                    status=ListingStatus.ACTIVE,
                ),
            ),
        )
