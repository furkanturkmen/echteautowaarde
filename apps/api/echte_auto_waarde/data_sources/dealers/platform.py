"""Dealers running the same inventory platform.

Five dealer groups publish their stock through one platform: the same
`/sitemaps/vehicle-1.xml`, the same `/p/<slug>-<id>` listing URLs, the same
`Disallow: /vehicle/` in robots.txt, and the same complete schema.org `Car`
block on every listing. One adapter therefore reads all of them, and adding the
sixth is a line in a table rather than a new parser.

That is a consequence of how the trade works: a dealer enters a car once into a
stock system, which renders it to their own website and pushes it to the
marketplaces. The website is an output of the feed, so dealers sharing a
platform publish identically.

Each dealer is still its own source with its own key, its own robots check and
its own cap. Sharing code is not sharing permission.
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
    PoliteFetcher,
    build_fetcher,
    clamp_limit,
    observed_now,
)
from echte_auto_waarde.data_sources.dealers.structured import read_car
from echte_auto_waarde.models.enums import DataSourceType, ListingStatus

logger = logging.getLogger(__name__)

SITEMAP_PATH = "/sitemaps/vehicle-1.xml"

_LISTING_URL = re.compile(r"<loc>(https?://[^<]+/p/[^<]+)</loc>")
# .../p/volkswagen-golf-variant-10-tsi-life-54283911-25 -> stock number 54283911
_REFERENCE = re.compile(r"-(\d{6,})-\d+/?$")


@dataclass(frozen=True)
class PlatformDealer:
    """One dealer on the shared platform."""

    slug: str
    domain: str
    key: str

    @property
    def sitemap_url(self) -> str:
        return f"https://{self.domain}{SITEMAP_PATH}"


# Each was checked individually: robots.txt read, listing path confirmed
# permitted, and structured data sampled. Adding a dealer here means doing that
# again for the new one, not assuming it because the platform matches.
PLATFORM_DEALERS: dict[str, PlatformDealer] = {
    dealer.slug: dealer
    for dealer in (
        PlatformDealer("nefkens", "www.nefkens.nl", "dealer:nefkens"),
        PlatformDealer("ekris", "www.ekris.nl", "dealer:ekris"),
        PlatformDealer("pouw", "www.pouw.nl", "dealer:pouw"),
        PlatformDealer("vandenbrug", "vandenbrug.nl", "dealer:vandenbrug"),
        PlatformDealer("hoogenboom", "www.autohoogenboom.nl", "dealer:hoogenboom"),
    )
}


@dataclass
class PlatformDataSource:
    """A `DataSourceAdapter` over one dealer on the shared platform."""

    dealer: PlatformDealer
    key: str = ""
    source_type: DataSourceType = DataSourceType.DEALER_SITE
    name: str = "Openbare dealeradvertenties"
    quality: float = 0.55
    limit: int = DEFAULT_LISTING_LIMIT
    fetcher: PoliteFetcher = field(default_factory=build_fetcher)

    # Listing pages opened, of which some turn out to be outside the segment.
    discovered: int = 0
    rejected: int = 0
    _collected: list[RawListing] | None = None

    def __post_init__(self) -> None:
        self.key = self.key or self.dealer.key

    @property
    def origin(self) -> str:
        return self.dealer.sitemap_url

    def fetch_listings(self) -> Iterable[RawListing]:
        """The sample, fetched once per run.

        One sitemap request, then at most `limit` listing requests. The cap is
        on **requests**, not on accepted listings: this platform's URLs do not
        state the year or the fuel, so some pages turn out to be outside the
        segment once read, and the honest response is a smaller sample rather
        than more requests.
        """
        if self._collected is not None:
            return self._collected

        candidates = self.select_candidates(self.fetcher.get(self.dealer.sitemap_url))
        budget = clamp_limit(self.limit)

        listings: list[RawListing] = []
        for url in candidates[:budget]:
            listing = self.parse_listing(self.fetcher.get(url), url)
            if listing is None:
                self.rejected += 1
                continue
            listings.append(listing)

        logger.info(
            "%s: %d candidate(s), %d opened, %d in segment (%s)",
            self.dealer.slug,
            self.discovered,
            min(len(candidates), budget),
            len(listings),
            segment.describe(),
        )
        self._collected = listings
        return listings

    # -- Discovery ------------------------------------------------------------

    def select_candidates(self, sitemap: str) -> list[str]:
        """Listing URLs that could be in the segment, deterministically ordered.

        The slug names the model but not the year or the fuel, so this narrows
        by model only. Everything it lets through is verified after reading.
        """
        candidates = sorted(
            {
                url
                for url in _LISTING_URL.findall(sitemap)
                if segment.slug_could_match(url.rsplit("/", 1)[-1])
            }
        )
        self.discovered = len(candidates)
        return candidates

    # -- Parsing --------------------------------------------------------------

    def parse_listing(self, html: str, url: str) -> RawListing | None:
        """One listing, from the structured data the page publishes."""
        car = read_car(html)
        if car is None:
            return None
        if not segment.matches(car.model, car.year, car.fuel):
            return None
        if car.asking_price_cents is None or car.mileage_km is None:
            # No price is no observation; no mileage leaves little to compare.
            return None

        reference = _REFERENCE.search(url)
        if reference is None:
            return None

        observed_at = observed_now()
        return RawListing(
            external_reference=reference.group(1),
            vehicle=RawVehicle(
                make=car.make,
                model=car.model,
                year=car.year,
                mileage_km=car.mileage_km,
                first_registration_date=car.first_registration,
                engine_description=car.variant,
                trim=car.trim,
                body_type=car.body_type,
                fuel_type=car.fuel,
                transmission=car.transmission,
                power_hp=car.power_hp,
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


def build_platform_source(slug: str, **kwargs: object) -> PlatformDataSource:
    """A source for one dealer on the platform, by its short name."""
    return PlatformDataSource(dealer=PLATFORM_DEALERS[slug], **kwargs)  # type: ignore[arg-type]
