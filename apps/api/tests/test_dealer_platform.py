"""The shared-platform adapter: five dealers, one parser.

Nothing here touches the network. The fixtures are hand-written: a vehicle
sitemap and two listing pages carrying the schema.org block the platform
publishes, one inside the segment and one outside it.

The behaviour that matters is what the adapter refuses. It opens only listings
whose slug could match, it caps *requests* rather than accepted listings, and it
drops anything that turns out to be the wrong year or the wrong fuel once read —
because this platform's URLs, unlike Van Mossel's, do not say.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from echte_auto_waarde.data_sources.dealers import DEALER_SOURCES
from echte_auto_waarde.data_sources.dealers import segment as segment_module
from echte_auto_waarde.data_sources.dealers.collector import MAX_LISTING_LIMIT, RobotsDecision
from echte_auto_waarde.data_sources.dealers.platform import (
    PLATFORM_DEALERS,
    PlatformDataSource,
    build_platform_source,
)
from echte_auto_waarde.models.enums import (
    DataSourceType,
    FuelType,
    ImportMode,
    ListingStatus,
)
from echte_auto_waarde.models.listing import Listing
from echte_auto_waarde.services.import_market import import_market_file

FIXTURES = Path(__file__).parent / "fixtures"

IN_SEGMENT_URL = "https://www.nefkens.nl/p/volkswagen-golf-15-etsi-life-54283911-25"
OUT_OF_SEGMENT_URL = "https://www.nefkens.nl/p/volkswagen-golf-14-tsi-comfortline-11112222-25"


def read_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@dataclass
class SequenceFetcher:
    pages: list[str] = field(default_factory=list)
    requested: list[str] = field(default_factory=list)
    requests_made: int = 0

    def check_robots(self, url: str) -> RobotsDecision:
        return RobotsDecision(allowed=True, detail="stubbed", robots_found=True)

    def get(self, url: str) -> str:
        self.requested.append(url)
        if self.requests_made >= len(self.pages):
            raise AssertionError("unexpected request for " + url)
        page = self.pages[self.requests_made]
        self.requests_made += 1
        return page


def source(fetcher: SequenceFetcher, slug: str = "nefkens", limit: int = 20) -> PlatformDataSource:
    return build_platform_source(slug, fetcher=fetcher, limit=limit)  # type: ignore[arg-type]


# --- The allowlist -----------------------------------------------------------


def test_five_dealers_share_one_adapter() -> None:
    assert sorted(PLATFORM_DEALERS) == [
        "ekris",
        "hoogenboom",
        "nefkens",
        "pouw",
        "vandenbrug",
    ]
    for slug in PLATFORM_DEALERS:
        assert DEALER_SOURCES[slug] is not None


def test_each_dealer_keeps_its_own_identity() -> None:
    """Sharing code is not sharing a source key, a cap or permission."""
    keys = {slug: build_platform_source(slug, fetcher=None).key for slug in PLATFORM_DEALERS}

    assert keys["nefkens"] == "dealer:nefkens"
    assert keys["hoogenboom"] == "dealer:hoogenboom"
    assert len(set(keys.values())) == len(PLATFORM_DEALERS)


def test_every_dealer_reads_its_own_sitemap() -> None:
    origins = {build_platform_source(slug, fetcher=None).origin for slug in PLATFORM_DEALERS}

    assert len(origins) == len(PLATFORM_DEALERS)
    assert all(origin.endswith("/sitemaps/vehicle-1.xml") for origin in origins)


# --- Discovery and the request cap -------------------------------------------


def test_only_listings_that_could_match_are_opened() -> None:
    collector = source(SequenceFetcher())

    candidates = collector.select_candidates(read_fixture("platform_sitemap.xml"))

    slugs = [url.rsplit("/", 1)[-1] for url in candidates]
    assert all("volkswagen-golf" in slug for slug in slugs)
    assert not any("sportsvan" in slug for slug in slugs)
    assert not any("polo" in slug for slug in slugs)


def test_the_cap_is_on_requests_not_on_accepted_listings() -> None:
    """The slug cannot state year or fuel, so some opened pages miss the segment.

    The honest response is a smaller sample, never more requests.
    """
    fetcher = SequenceFetcher(
        [read_fixture("platform_sitemap.xml")] + [read_fixture("platform_out_of_segment.html")] * 3
    )

    listings = list(source(fetcher, limit=3).fetch_listings())

    assert listings == []
    # One sitemap plus exactly three listing pages, and no retry to fill the gap.
    assert fetcher.requests_made == 4


@pytest.mark.parametrize(("asked", "expected_requests"), [(1, 2), (2, 3)])
def test_the_limit_bounds_the_listing_requests(asked: int, expected_requests: int) -> None:
    fetcher = SequenceFetcher(
        [read_fixture("platform_sitemap.xml")] + [read_fixture("platform_listing.html")] * 5
    )

    list(source(fetcher, limit=asked).fetch_listings())

    assert fetcher.requests_made == expected_requests


def test_the_hard_maximum_still_applies() -> None:
    fetcher = SequenceFetcher(
        [read_fixture("platform_sitemap.xml")] + [read_fixture("platform_listing.html")] * 40
    )

    list(source(fetcher, limit=999).fetch_listings())

    assert fetcher.requests_made <= MAX_LISTING_LIMIT + 1


def test_the_sample_is_fetched_once_per_run() -> None:
    fetcher = SequenceFetcher(
        [read_fixture("platform_sitemap.xml"), read_fixture("platform_listing.html")]
    )
    collector = source(fetcher, limit=1)

    assert list(collector.fetch_listings()) == list(collector.fetch_listings())
    assert fetcher.requests_made == 2


# --- Reading, and refusing what is out of segment ----------------------------


def test_a_listing_is_read_from_its_published_structured_data() -> None:
    listing = source(SequenceFetcher()).parse_listing(
        read_fixture("platform_listing.html"), IN_SEGMENT_URL
    )

    assert listing is not None
    assert listing.external_reference == "54283911"
    assert (listing.vehicle.make, listing.vehicle.model) == ("Volkswagen", "Golf")
    assert listing.vehicle.year == 2022
    assert listing.vehicle.mileage_km == 38_500
    assert listing.asking_price_cents == 2_649_000
    assert listing.vehicle.fuel_type == "Benzine"


def test_the_trim_is_taken_from_the_listing_title() -> None:
    listing = source(SequenceFetcher()).parse_listing(
        read_fixture("platform_listing.html"), IN_SEGMENT_URL
    )

    assert listing is not None
    assert listing.vehicle.trim == "Life"


def test_a_listing_outside_the_year_band_is_dropped_after_reading() -> None:
    listing = source(SequenceFetcher()).parse_listing(
        read_fixture("platform_out_of_segment.html"), OUT_OF_SEGMENT_URL
    )

    assert listing is None


def test_the_segment_rule_is_shared_with_the_other_sources() -> None:
    assert segment_module.matches("Golf", 2022, "petrol") is True
    assert segment_module.matches("Golf", 2015, "petrol") is False
    assert segment_module.matches("Golf", 2022, "diesel") is False
    assert segment_module.matches("Golf Sportsvan", 2022, "petrol") is False
    assert segment_module.matches("Polo", 2022, "petrol") is False


# --- Lifecycle and provenance ------------------------------------------------


def test_listings_import_as_real_dealer_evidence(session: Session) -> None:
    fetcher = SequenceFetcher(
        [read_fixture("platform_sitemap.xml"), read_fixture("platform_listing.html")]
    )

    report = import_market_file(session, source(fetcher, limit=1), scope="golf-mk8")
    session.commit()

    assert report.succeeded and report.listings_created == 1
    listing = session.scalars(select(Listing)).one()
    assert listing.data_source.key == "dealer:nefkens"
    assert listing.data_source.source_type is DataSourceType.DEALER_SITE
    assert listing.vehicle.fuel_type is FuelType.PETROL
    assert listing.status is ListingStatus.ACTIVE


def test_collection_can_never_run_as_a_full_snapshot(session: Session) -> None:
    fetcher = SequenceFetcher(
        [read_fixture("platform_sitemap.xml"), read_fixture("platform_listing.html")]
    )

    report = import_market_file(
        session, source(fetcher, limit=1), scope="golf-mk8", mode=ImportMode.FULL_SNAPSHOT
    )

    assert not report.succeeded
    assert any("partial by design" in problem for problem in report.validation_errors)


def test_contact_details_and_media_are_not_collected() -> None:
    listing = source(SequenceFetcher()).parse_listing(
        read_fixture("platform_listing.html"), IN_SEGMENT_URL
    )
    stored = repr(listing)

    for unwanted in ("photo", ".webp", "+31", "verkoopadviseur", "WVWZZZ"):
        assert unwanted not in stored, unwanted
    assert listing is not None and listing.seller is not None
    assert listing.seller.name is None


def test_plug_in_hybrids_are_recognised_from_the_slug() -> None:
    """A dealer whose Golf stock is mostly GTE would otherwise burn its budget.

    The fuel rule already excludes plug-in hybrids; reading it from the slug
    only avoids opening pages that are certain to be rejected.
    """
    for slug in (
        "volkswagen-golf-1-4-ehybrid-gte-56251034-347",
        "volkswagen-golf-1-5-ehybrid-style-55847403-313",
        "volkswagen-golf-gte-54205344-313",
    ):
        assert segment_module.slug_could_match(slug) is False

    for slug in (
        "volkswagen-golf-15-etsi-life-54283911-25",
        "volkswagen-golf-variant-10-tsi-style-54283912-25",
        "volkswagen-golf-20-tsi-gti-49035328-47",
    ):
        assert segment_module.slug_could_match(slug) is True


def test_the_budget_now_reaches_petrol_listings() -> None:
    """With the hybrids filtered out, a small budget finds real candidates."""
    sitemap = read_fixture("platform_sitemap.xml").replace(
        "<url><loc>https://www.nefkens.nl/p/volkswagen-golf-15-etsi-life-54283911-25</loc></url>",
        "\n".join(
            "<url><loc>https://www.nefkens.nl/p/volkswagen-golf-1-4-ehybrid-gte-"
            f"9999{index}-25</loc></url>"
            for index in range(5)
        )
        + "\n<url><loc>https://www.nefkens.nl/p/volkswagen-golf-15-etsi-life-54283911-25</loc></url>",
    )
    collector = source(SequenceFetcher())

    candidates = collector.select_candidates(sitemap)

    assert not any("ehybrid" in url for url in candidates)
    assert any("54283911" in url for url in candidates)
