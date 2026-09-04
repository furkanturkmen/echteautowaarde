"""Van Mossel: segment selection and published structured data.

This source differs from the other two in both halves of its job. It selects its
segment on the sitemap, so listings outside the segment are never requested at
all, and it reads the schema.org block the site publishes rather than the page
markup.

Nothing here touches the network. The fixtures are hand-written: a sitemap of
one in-segment listing per near-miss case, and one listing page carrying the
photographs, description, VIN and dealer telephone number that must not survive.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from echte_auto_waarde.data_sources.dealers import DEALER_SOURCES
from echte_auto_waarde.data_sources.dealers.collector import CollectionBlocked, RobotsDecision
from echte_auto_waarde.data_sources.dealers.structured import read_car
from echte_auto_waarde.data_sources.dealers.vanmossel import VanMosselDataSource
from echte_auto_waarde.models.enums import (
    DataSourceType,
    FuelType,
    ImportMode,
    ListingStatus,
    Transmission,
)
from echte_auto_waarde.models.listing import Listing
from echte_auto_waarde.services.import_market import import_market_file

FIXTURES = Path(__file__).parent / "fixtures"

LISTING_URL = "https://www.vanmossel.nl/voorraad/812337-1-volkswagen-golf-15-etsi-life-benzine-2022"


def read_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@dataclass
class SequenceFetcher:
    """Answers a planned sequence of pages; anything more is a test failure."""

    pages: list[str] = field(default_factory=list)
    error: Exception | None = None
    requests_made: int = 0

    def check_robots(self, url: str) -> RobotsDecision:
        return RobotsDecision(allowed=True, detail="stubbed", robots_found=True)

    def get(self, url: str) -> str:
        if self.requests_made >= len(self.pages):
            if self.error is not None:
                raise self.error
            raise AssertionError("unexpected request for " + url)
        page = self.pages[self.requests_made]
        self.requests_made += 1
        return page


def source(fetcher: SequenceFetcher | None = None, limit: int = 20) -> VanMosselDataSource:
    return VanMosselDataSource(fetcher=fetcher or SequenceFetcher(), limit=limit)  # type: ignore[arg-type]


# --- Selecting the segment before fetching -----------------------------------


def test_the_segment_is_selected_on_the_sitemap() -> None:
    collector = source()

    urls = collector.select_segment(read_fixture("vanmossel_sitemap.xml"))

    assert [url.rsplit("/", 1)[-1] for url in urls] == [
        "812337-1-volkswagen-golf-15-etsi-life-benzine-2022",
        "812338-1-volkswagen-golf-variant-15-etsi-style-benzine-2023",
    ]
    assert collector.discovered == 2


@pytest.mark.parametrize(
    ("slug", "why"),
    [
        ("812339-1-volkswagen-golf-20-tdi-life-diesel-2022", "diesel"),
        ("812340-1-volkswagen-golf-14-tsi-comfortline-benzine-2015", "before the band"),
        ("812341-1-volkswagen-golf-15-etsi-r-line-benzine-2025", "after the band"),
        ("812342-1-volkswagen-golf-sportsvan-14-tsi-benzine-2022", "Sportsvan"),
        ("812343-1-volkswagen-polo-10-tsi-life-benzine-2022", "not a Golf"),
        ("812344-1-volkswagen-golf-15-ehybrid-style-hybride-2022", "plug-in hybrid"),
    ],
)
def test_out_of_segment_listings_are_never_requested(slug: str, why: str) -> None:
    urls = source().select_segment(read_fixture("vanmossel_sitemap.xml"))

    assert not any(slug in url for url in urls), why


def test_only_capped_detail_pages_are_requested() -> None:
    """One sitemap request, then at most `limit` listing requests."""
    fetcher = SequenceFetcher(
        [read_fixture("vanmossel_sitemap.xml")] + [read_fixture("vanmossel_listing.html")] * 5
    )

    listings = list(source(fetcher, limit=1).fetch_listings())

    assert len(listings) == 1
    assert fetcher.requests_made == 2


def test_the_sample_is_fetched_once_per_run() -> None:
    fetcher = SequenceFetcher(
        [read_fixture("vanmossel_sitemap.xml"), read_fixture("vanmossel_listing.html")]
    )
    collector = source(fetcher, limit=1)

    first = list(collector.fetch_listings())
    second = list(collector.fetch_listings())

    assert first == second
    assert fetcher.requests_made == 2


def test_a_block_during_collection_stops_the_source() -> None:
    fetcher = SequenceFetcher(
        [read_fixture("vanmossel_sitemap.xml")], error=CollectionBlocked("challenge")
    )

    with pytest.raises(CollectionBlocked):
        list(source(fetcher, limit=5).fetch_listings())


# --- Reading the published structured data -----------------------------------


def test_a_listing_is_read_from_its_published_structured_data() -> None:
    listing = source().parse_listing(read_fixture("vanmossel_listing.html"), LISTING_URL)

    assert listing is not None
    assert listing.external_reference == "812337"
    assert listing.url == LISTING_URL
    assert (listing.vehicle.make, listing.vehicle.model) == ("Volkswagen", "Golf")
    assert listing.vehicle.year == 2022
    assert listing.vehicle.first_registration_date == date(2022, 4, 14)
    assert listing.vehicle.mileage_km == 41_250
    assert listing.asking_price_cents == 2_790_000
    assert listing.vehicle.fuel_type == "Benzine"
    assert listing.vehicle.transmission == "Automaat"
    assert listing.vehicle.body_type == "hatchback"
    assert listing.vehicle.doors == 5


def test_the_variant_drops_the_equipment_prose() -> None:
    listing = source().parse_listing(read_fixture("vanmossel_listing.html"), LISTING_URL)

    assert listing is not None
    assert listing.vehicle.engine_description == "1.5 eTSI Life Business AUTOMAAT"


def test_mileage_in_miles_is_refused_rather_than_misread() -> None:
    html = read_fixture("vanmossel_listing.html").replace('"KMT"', '"SMI"')

    car = read_car(html)

    assert car is not None
    assert car.mileage_km is None


def test_a_price_in_another_currency_is_refused() -> None:
    html = read_fixture("vanmossel_listing.html").replace('"EUR"', '"USD"')

    car = read_car(html)

    assert car is not None
    assert car.asking_price_cents is None


def test_photographs_descriptions_and_contact_details_are_not_collected() -> None:
    """The published block carries all of these; none may reach storage."""
    listing = source().parse_listing(read_fixture("vanmossel_listing.html"), LISTING_URL)
    stored = repr(listing)

    for unwanted in (
        "photo-1.webp",
        "prachtige auto",
        "+31 900",
        "Voorbeeld Dealer",
        "WVWZZZCD6RW820609",
    ):
        assert unwanted not in stored, unwanted
    assert listing is not None and listing.seller is not None
    assert listing.seller.name is None
    assert listing.seller.seller_type == "DEALER"


@pytest.mark.parametrize("field_name", ["offers", "mileageFromOdometer"])
def test_a_listing_without_a_price_or_mileage_is_rejected(field_name: str) -> None:
    """No price means no observation; no mileage means little worth comparing."""
    html = re.sub(
        '"' + field_name + r'":\s*\{[^}]*\}[^,]*,', "", read_fixture("vanmossel_listing.html")
    )

    assert source().parse_listing(html, LISTING_URL) is None


def test_a_page_without_structured_data_is_rejected_rather_than_guessed() -> None:
    assert source().parse_listing("<html><body>27.900</body></html>", LISTING_URL) is None


# --- Lifecycle and provenance ------------------------------------------------


def test_collection_can_never_run_as_a_full_snapshot(session: Session) -> None:
    fetcher = SequenceFetcher(
        [read_fixture("vanmossel_sitemap.xml"), read_fixture("vanmossel_listing.html")]
    )

    report = import_market_file(
        session, source(fetcher, limit=1), scope="golf-mk8", mode=ImportMode.FULL_SNAPSHOT
    )

    assert not report.succeeded
    assert any("partial by design" in problem for problem in report.validation_errors)
    assert session.scalars(select(Listing)).first() is None


def test_listings_import_as_real_dealer_evidence(session: Session) -> None:
    fetcher = SequenceFetcher(
        [read_fixture("vanmossel_sitemap.xml"), read_fixture("vanmossel_listing.html")]
    )

    report = import_market_file(session, source(fetcher, limit=1), scope="golf-mk8")
    session.commit()

    assert report.succeeded and report.listings_created == 1
    listing = session.scalars(select(Listing)).one()
    assert listing.data_source.source_type is DataSourceType.DEALER_SITE
    assert listing.vehicle.fuel_type is FuelType.PETROL
    assert listing.vehicle.transmission is Transmission.AUTOMATIC
    assert listing.status is ListingStatus.ACTIVE


def test_the_source_is_registered_in_the_allowlist() -> None:
    assert DEALER_SOURCES["vanmossel"] is VanMosselDataSource


def test_inzoeven_manual_wording_now_normalizes() -> None:
    """Phase 14 found Inzoeven writes "Handmatig"; we knew only "handgeschakeld"."""
    from echte_auto_waarde.domain import normalization

    assert normalization.normalize_transmission("Handmatig") is Transmission.MANUAL
