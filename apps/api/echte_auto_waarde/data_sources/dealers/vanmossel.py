"""Van Mossel public inventory (vanmossel.nl), read from published structured data.

Two properties of this site make a small, careful sample possible.

Its sitemap encodes make, model, fuel and year in every listing URL, so the
segment can be selected *before* fetching anything: one sitemap request, then a
detail request only for listings that already match. Nothing is fetched
speculatively.

Its listing pages publish schema.org `Car` data — the same block search engines
read — carrying make, model, first registration, mileage, fuel, body type and
the asking price. That is read instead of the page markup: it states facts, and
it does not depend on layout.

Photographs, descriptions, dealer contact details and the VIN are present in
that block and are deliberately not read.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass, field

from echte_auto_waarde.data_sources.base import RawListing, RawSeller, RawSnapshot, RawVehicle
from echte_auto_waarde.data_sources.dealers import segment
from echte_auto_waarde.data_sources.dealers.collector import (
    DEFAULT_LISTING_LIMIT,
    DealerCollectionError,
    PoliteFetcher,
    build_fetcher,
    clamp_limit,
    observed_now,
)
from echte_auto_waarde.data_sources.dealers.structured import read_car
from echte_auto_waarde.models.enums import DataSourceType, ListingStatus

logger = logging.getLogger(__name__)

SOURCE_KEY = "dealer:vanmossel"
BASE_URL = "https://www.vanmossel.nl"
SITEMAP_URL = f"{BASE_URL}/__sitemap__/nl-NL.xml"

# The segment is defined once, in `segment`, so every source collects the same
# thing. This site is unusual in stating fuel and year in the URL, which is why
# it can filter before fetching at all.
SEGMENT_FUEL = "benzine"

_LISTING_URL = re.compile(r"<loc>(https://www\.vanmossel\.nl/voorraad/[^<]+)</loc>")
# .../voorraad/812337-1-volkswagen-golf-variant-15-etsi-...-benzine-2023
_REFERENCE = re.compile(r"/voorraad/(\d+)-")
_FUEL_AND_YEAR = re.compile(r"-(benzine|diesel|elektrisch|hybride|lpg)-(\d{4})$", re.I)


@dataclass
class VanMosselDataSource:
    """A `DataSourceAdapter` over one dealer group's public listings."""

    key: str = SOURCE_KEY
    source_type: DataSourceType = DataSourceType.DEALER_SITE
    name: str = "Openbare dealeradvertenties"
    # One group's stock is real evidence, but it is one seller's pricing policy
    # rather than a market.
    quality: float = 0.55
    limit: int = DEFAULT_LISTING_LIMIT
    fetcher: PoliteFetcher = field(default_factory=build_fetcher)

    discovered: int = 0
    rejected: int = 0
    _collected: list[RawListing] | None = None

    @property
    def origin(self) -> str:
        return SITEMAP_URL

    def fetch_listings(self) -> Iterable[RawListing]:
        """The sample, fetched once per run.

        One request for the sitemap, then at most `limit` detail requests — and
        only for listings whose URL already says they are in the segment.
        """
        if self._collected is not None:
            return self._collected

        urls = self.select_segment(self.fetcher.get(SITEMAP_URL))
        listings: list[RawListing] = []
        for url in urls[: clamp_limit(self.limit)]:
            try:
                listing = self.parse_listing(self.fetcher.get(url), url)
            except DealerCollectionError:
                # Blocked, challenged or disallowed: stop the whole source
                # rather than pressing on.
                raise
            if listing is None:
                self.rejected += 1
                continue
            listings.append(listing)

        self._collected = listings
        return listings

    # -- Discovery ------------------------------------------------------------

    def select_segment(self, sitemap: str) -> list[str]:
        """Listing URLs already in the segment, in a deterministic order.

        The filtering happens here, on the sitemap, precisely so that pages
        outside the segment are never requested at all.
        """
        matches: list[str] = []
        for url in _LISTING_URL.findall(sitemap):
            slug = url.rsplit("/", 1)[-1].lower()
            if not segment.slug_could_match(slug):
                continue
            found = _FUEL_AND_YEAR.search(slug)
            if found is None:
                continue
            fuel, year = found.group(1).lower(), int(found.group(2))
            if fuel != SEGMENT_FUEL:
                continue
            if not segment.FIRST_YEAR <= year <= segment.LAST_YEAR:
                continue
            matches.append(url)

        self.discovered = len(matches)
        logger.info("%d listing(s) in segment before the cap is applied", len(matches))
        return sorted(set(matches))

    # -- Parsing --------------------------------------------------------------

    def parse_listing(self, html: str, url: str) -> RawListing | None:
        """One listing, from the structured data the page publishes."""
        car = read_car(html)
        if car is None:
            return None
        if car.asking_price_cents is None or car.mileage_km is None:
            # Without a price there is no market observation, and without a
            # mileage the comparison would be worth little.
            return None

        reference = _REFERENCE.search(url)
        if reference is None:
            return None

        observed_at = observed_now()
        return RawListing(
            # The dealer's own stock number from the canonical URL.
            external_reference=reference.group(1),
            vehicle=RawVehicle(
                make=car.make,
                model=car.model,
                year=car.year,
                mileage_km=car.mileage_km,
                first_registration_date=car.first_registration,
                engine_description=car.variant,
                body_type=car.body_type,
                fuel_type=car.fuel,
                transmission=car.transmission,
                doors=car.doors,
                option_texts=(),
            ),
            asking_price_cents=car.asking_price_cents,
            first_seen_at=observed_at,
            last_seen_at=observed_at,
            # Seller type only: no name, no address, no contact details.
            seller=RawSeller(seller_type="DEALER", name=None, city=None),
            url=url,
            status=ListingStatus.ACTIVE,
            snapshots=(
                RawSnapshot(
                    observed_at=observed_at,
                    asking_price_cents=car.asking_price_cents,
                    mileage_km=car.mileage_km,
                    status=ListingStatus.ACTIVE,
                ),
            ),
        )
