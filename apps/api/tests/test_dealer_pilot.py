"""The public dealer pilot: parsing, limits, and the refusals.

The fixtures are hand-written minimal markup that reproduces the *shape* of each
dealer's inventory card — the elements the parsers rely on — rather than copies
of their pages. Nothing here reaches the network: the fetcher is either stubbed
or bypassed entirely by calling `parse` directly.

Much of this file tests what the collector must refuse to do: exceed its cap,
continue past a robots disallow, work around a challenge, store a telephone
number, or ever run as a full snapshot.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from echte_auto_waarde.data_sources.dealers import DEALER_SOURCES
from echte_auto_waarde.data_sources.dealers.autoxl import AutoXlDataSource
from echte_auto_waarde.data_sources.dealers.collector import (
    MAX_LISTING_LIMIT,
    CollectionBlocked,
    DealerCollectionError,
    PoliteFetcher,
    RobotsDisallowed,
    clamp_limit,
    clean_variant,
    parse_euro,
)
from echte_auto_waarde.data_sources.dealers.inzoeven import InzoevenDataSource
from echte_auto_waarde.domain.evidence import (
    DEALER_DISCLAIMER,
    REAL_SOURCE_TYPES,
    MarketMode,
    describe_evidence,
    evidence_source_types,
)
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


def read_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@dataclass
class StubFetcher:
    """Stands in for the network. Records what would have been requested."""

    body: str = ""
    error: Exception | None = None
    requests_made: int = 0
    requested: list[str] | None = None

    def __post_init__(self) -> None:
        self.requested = []

    def check_robots(self, url: str):  # noqa: ANN201 - mirrors PoliteFetcher
        from echte_auto_waarde.data_sources.dealers.collector import RobotsDecision

        return RobotsDecision(allowed=True, detail="stubbed", robots_found=True)

    def get(self, url: str) -> str:
        assert self.requested is not None
        self.requested.append(url)
        self.requests_made += 1
        if self.error is not None:
            raise self.error
        return self.body


# --- Parsing -----------------------------------------------------------------


def test_inzoeven_inventory_parsing() -> None:
    source = InzoevenDataSource(fetcher=StubFetcher())  # type: ignore[arg-type]

    listings = list(source.parse(read_fixture("inzoeven_inventory.html")))

    assert len(listings) == 2
    first = listings[0]
    assert first.external_reference == "6758539"
    assert first.url == "https://inzoeven.nl/aanbod/audi-a5-coupe-6758539"
    assert (first.vehicle.make, first.vehicle.model) == ("Audi", "A5 Coupe")
    assert first.vehicle.year == 2018
    assert first.vehicle.mileage_km == 98_413
    assert first.asking_price_cents == 5_999_500
    assert first.vehicle.fuel_type == "Benzine"
    assert first.vehicle.transmission == "Automaat"


def test_autoxl_inventory_parsing() -> None:
    source = AutoXlDataSource(fetcher=StubFetcher())  # type: ignore[arg-type]

    listings = list(source.parse(read_fixture("autoxl_inventory.html")))

    assert len(listings) == 2
    first = listings[0]
    assert first.external_reference == "21219173"
    assert first.url.endswith("/voertuigen/bmw-i4-edrive40-21219173-awd")
    assert (first.vehicle.make, first.vehicle.model) == ("BMW", "i4")
    assert first.vehicle.year == 2022
    assert first.vehicle.mileage_km == 41_250
    assert first.vehicle.fuel_type == "Elektrisch"
    assert first.vehicle.transmission == "Automaat"


def test_a_monthly_lease_figure_is_never_taken_as_an_asking_price() -> None:
    """Both prices sit in the same card; only the purchase price is an ask."""
    source = AutoXlDataSource(fetcher=StubFetcher())  # type: ignore[arg-type]

    listings = list(source.parse(read_fixture("autoxl_inventory.html")))

    assert listings[0].asking_price_cents == 3_894_000  # the "Kopen" price
    assert all(listing.asking_price_cents > 100_000 for listing in listings)


@pytest.mark.parametrize(
    ("text", "expected"),
    [("€ 59.995", 5_999_500), ("€ 12.940", 1_294_000), ("€ 8.950,50", 895_050), ("geen", None)],
)
def test_price_normalization(text: str, expected: int | None) -> None:
    assert parse_euro(text) == expected


def test_variant_keeps_the_specification_and_drops_the_sales_pitch() -> None:
    assert clean_variant("2.9 TFSI RS 5 quattro, 6 maanden garantie") == "2.9 TFSI RS 5 quattro"
    assert clean_variant("eDrive40 M-Sport 84 kWh") == "eDrive40 M-Sport 84 kWh"
    assert clean_variant("Rijklaar, inruil mogelijk") is None


def test_normalization_turns_source_wording_into_domain_values(
    session: Session, tmp_path: Path
) -> None:
    """The existing normalization layer does this; the adapter only supplies text."""
    source = InzoevenDataSource(fetcher=StubFetcher(read_fixture("inzoeven_inventory.html")))  # type: ignore[arg-type]

    report = import_market_file(session, source, scope="inzoeven")  # type: ignore[arg-type]
    session.commit()

    assert report.succeeded
    listing = session.scalars(select(Listing).order_by(Listing.id)).first()
    assert listing.vehicle.fuel_type is FuelType.PETROL
    assert listing.vehicle.transmission is Transmission.AUTOMATIC
    assert listing.vehicle.make == "Audi"


def test_a_malformed_card_is_skipped_and_counted() -> None:
    source = InzoevenDataSource(fetcher=StubFetcher())  # type: ignore[arg-type]

    listings = list(source.parse(read_fixture("inzoeven_broken.html")))

    assert len(listings) == 1
    assert source.discovered == 3
    assert source.rejected == 2


def test_a_listing_without_a_price_is_not_collected() -> None:
    source = InzoevenDataSource(fetcher=StubFetcher())  # type: ignore[arg-type]

    listings = list(source.parse(read_fixture("inzoeven_broken.html")))

    assert all(listing.asking_price_cents > 0 for listing in listings)


# --- The cap -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("asked", "expected"), [(None, 20), (5, 5), (25, 25), (26, 25), (10_000, 25), (0, 1)]
)
def test_the_hard_limit_cannot_be_exceeded(asked: int | None, expected: int) -> None:
    assert clamp_limit(asked) == expected
    assert MAX_LISTING_LIMIT == 25


def test_a_source_stops_at_its_limit() -> None:
    source = InzoevenDataSource(fetcher=StubFetcher(), limit=1)  # type: ignore[arg-type]

    listings = list(source.parse(read_fixture("inzoeven_inventory.html")))

    assert len(listings) == 1


# --- What is never stored ----------------------------------------------------


def test_contact_details_and_page_content_are_not_collected() -> None:
    """The fixture carries a phone link, an image and a description; none survive."""
    source = InzoevenDataSource(fetcher=StubFetcher())  # type: ignore[arg-type]

    listing = next(iter(source.parse(read_fixture("inzoeven_inventory.html"))))
    stored = repr(listing)

    for unwanted in ("wa.me", "31634789380", "media-cdn", ".webp", "info@", "Bel ons"):
        assert unwanted not in stored
    assert listing.seller is not None
    assert listing.seller.name is None
    assert listing.seller.seller_type == "DEALER"
    # No field exists to hold a description or a photograph.
    assert not hasattr(listing, "description")
    assert not hasattr(listing, "images")


# --- robots, blocking, challenges --------------------------------------------


def _fetcher_with(monkeypatch, body: str, status: int = 200, robots: str = "") -> PoliteFetcher:
    def fake_get(url, headers=None, timeout=None, follow_redirects=None):  # noqa: ANN001
        if url.endswith("/robots.txt"):
            return httpx.Response(200, text=robots or "User-agent: *\nAllow: /\n")
        return httpx.Response(status, text=body)

    monkeypatch.setattr(httpx, "get", fake_get)
    return PoliteFetcher(user_agent="TestPilot/1.0", delay_seconds=0.0, timeout_seconds=5.0)


def test_robots_allowing_the_path_permits_collection(monkeypatch) -> None:
    fetcher = _fetcher_with(monkeypatch, "<html>ok</html>")

    decision = fetcher.check_robots("https://example.test/aanbod")

    assert decision.allowed is True
    assert decision.robots_found is True


def test_an_explicit_robots_disallow_stops_collection(monkeypatch) -> None:
    fetcher = _fetcher_with(
        monkeypatch, "<html>ok</html>", robots="User-agent: *\nDisallow: /aanbod\n"
    )

    assert fetcher.check_robots("https://example.test/aanbod").allowed is False
    with pytest.raises(RobotsDisallowed):
        fetcher.get("https://example.test/aanbod")


def test_a_missing_robots_file_is_not_treated_as_permission(monkeypatch) -> None:
    def fake_get(url, headers=None, timeout=None, follow_redirects=None):  # noqa: ANN001
        if url.endswith("/robots.txt"):
            return httpx.Response(404, text="")
        return httpx.Response(200, text="<html>ok</html>")

    monkeypatch.setattr(httpx, "get", fake_get)
    fetcher = PoliteFetcher(user_agent="TestPilot/1.0", delay_seconds=0.0, timeout_seconds=5.0)

    decision = fetcher.check_robots("https://example.test/aanbod")

    assert decision.allowed is True
    assert decision.robots_found is False
    assert "not permission" in decision.detail


@pytest.mark.parametrize("status", [403, 429, 451])
def test_a_blocking_response_stops_the_source(monkeypatch, status: int) -> None:
    fetcher = _fetcher_with(monkeypatch, "<html>no</html>", status=status)

    with pytest.raises(CollectionBlocked):
        fetcher.get("https://example.test/aanbod")


def test_a_challenge_page_stops_rather_than_being_solved(monkeypatch) -> None:
    fetcher = _fetcher_with(monkeypatch, "<html><title>Just a moment...</title></html>")

    with pytest.raises(CollectionBlocked) as error:
        fetcher.get("https://example.test/aanbod")

    assert "challenge" in str(error.value)


def test_an_http_failure_stops_safely(monkeypatch) -> None:
    fetcher = _fetcher_with(monkeypatch, "", status=500)

    with pytest.raises(DealerCollectionError):
        fetcher.get("https://example.test/aanbod")


def test_robots_is_fetched_once_per_site(monkeypatch) -> None:
    calls: list[str] = []

    def fake_get(url, headers=None, timeout=None, follow_redirects=None):  # noqa: ANN001
        calls.append(url)
        if url.endswith("/robots.txt"):
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        return httpx.Response(200, text="<html>ok</html>")

    monkeypatch.setattr(httpx, "get", fake_get)
    fetcher = PoliteFetcher(user_agent="TestPilot/1.0", delay_seconds=0.0, timeout_seconds=5.0)

    fetcher.get("https://example.test/a")
    fetcher.get("https://example.test/b")

    assert calls.count("https://example.test/robots.txt") == 1


# --- Lifecycle and provenance ------------------------------------------------


def test_dealer_collection_can_never_run_as_a_full_snapshot(
    session: Session, tmp_path: Path
) -> None:
    """A partial sample must not be able to retire anything, ever."""
    source = InzoevenDataSource(fetcher=StubFetcher(read_fixture("inzoeven_inventory.html")))  # type: ignore[arg-type]

    report = import_market_file(session, source, scope="inzoeven", mode=ImportMode.FULL_SNAPSHOT)

    assert not report.succeeded
    assert any("partial by design" in problem for problem in report.validation_errors)
    assert session.scalars(select(Listing)).first() is None


def test_a_listing_absent_from_a_later_sample_stays_active(
    session: Session, tmp_path: Path
) -> None:
    first = InzoevenDataSource(fetcher=StubFetcher(read_fixture("inzoeven_inventory.html")))  # type: ignore[arg-type]
    import_market_file(session, first, scope="inzoeven")  # type: ignore[arg-type]
    session.commit()

    # A later run that happens to show only one of the two cars.
    smaller = InzoevenDataSource(
        fetcher=StubFetcher(read_fixture("inzoeven_inventory.html")),  # type: ignore[arg-type]
        limit=1,
    )
    import_market_file(session, smaller, scope="inzoeven")  # type: ignore[arg-type]
    session.commit()

    statuses = {listing.status for listing in session.scalars(select(Listing))}
    assert statuses == {ListingStatus.ACTIVE}
    assert ListingStatus.REMOVED not in statuses


def test_dealer_evidence_counts_as_real_and_is_described_honestly() -> None:
    assert DataSourceType.DEALER_SITE in REAL_SOURCE_TYPES
    assert DataSourceType.DEALER_SITE in evidence_source_types(
        MarketMode.REAL, target_is_demo=False
    )

    wording = describe_evidence({DataSourceType.DEALER_SITE})
    assert wording == DEALER_DISCLAIMER
    assert "openbare dealeradvertenties" in wording
    # No claim of partnership, endorsement, official access or sale prices.
    for forbidden in ("partner", "officieel", "samenwerking", "verkoopprijzen zijn"):
        assert forbidden not in wording.lower()


def test_synthetic_listings_stay_out_of_real_valuations() -> None:
    real = evidence_source_types(MarketMode.REAL, target_is_demo=False)

    assert DataSourceType.SYNTHETIC not in real


def test_only_allowlisted_dealers_are_supported() -> None:
    """Adding a source is a deliberate act with its own robots and terms review."""
    assert sorted(DEALER_SOURCES) == [
        "autoxl",
        "ekris",
        "hoogenboom",
        "inzoeven",
        "nefkens",
        "pouw",
        "vandenbrug",
        "vanmossel",
    ]


def test_a_trim_that_looks_like_a_sales_word_survives() -> None:
    """ "Pro Line Plus" is a trim level; the offer after it is not."""
    assert (
        clean_variant("2.0 TDI quattro Design Pro Line Plus incl. 6 maanden garantie")
        == "2.0 TDI quattro Design Pro Line Plus"
    )


def test_the_inventory_page_is_fetched_once_per_run() -> None:
    """The pipeline asks twice; a website must not be asked twice."""
    fetcher = StubFetcher(read_fixture("inzoeven_inventory.html"))
    source = InzoevenDataSource(fetcher=fetcher)  # type: ignore[arg-type]

    first = list(source.fetch_listings())
    second = list(source.fetch_listings())

    assert fetcher.requests_made == 1
    assert first == second


# --- Transmission wording ----------------------------------------------------
#
# The live pilot showed the card states the gearbox beside the category
# ("Automaat 8 versnellingen"), which normalization did not recognise, so 15 of
# 20 vehicles arrived with an unknown transmission.


def test_the_transmission_category_is_extracted_from_the_gearbox_wording() -> None:
    source = InzoevenDataSource(fetcher=StubFetcher())  # type: ignore[arg-type]

    listings = list(source.parse(read_fixture("inzoeven_transmission.html")))

    assert [listing.vehicle.transmission for listing in listings] == [
        "Automaat",  # from "Automaat 8 versnellingen"
        "Handgeschakeld",  # from "Handgeschakeld 6 versnellingen"
        "Automaat",  # already bare
        None,  # "Sequentieel schakelsysteem" is not a wording we claim to know
    ]


def test_extracted_transmissions_normalize_and_unknown_wording_stays_unknown(
    session: Session,
) -> None:
    source = InzoevenDataSource(
        fetcher=StubFetcher(read_fixture("inzoeven_transmission.html")),  # type: ignore[arg-type]
    )

    report = import_market_file(session, source, scope="inzoeven")  # type: ignore[arg-type]
    session.commit()

    assert report.succeeded
    stored = {
        listing.external_reference: listing.vehicle.transmission
        for listing in session.scalars(select(Listing))
    }
    assert stored["6431589"] is Transmission.AUTOMATIC
    assert stored["1111111"] is Transmission.MANUAL
    assert stored["2222222"] is Transmission.AUTOMATIC
    # Unknown wording lowers confidence rather than inventing a gearbox.
    assert stored["3333333"] is Transmission.UNKNOWN


def test_a_semi_automatic_is_not_read_as_an_automatic() -> None:
    """Word order matters: "semi-automaat" contains "automaat"."""
    from echte_auto_waarde.data_sources.dealers.inzoeven import _transmission_category

    assert _transmission_category(["Semi-automaat"]) == "Semi-automaat"
    assert _transmission_category(["Automaat 8 versnellingen"]) == "Automaat"
    assert _transmission_category(["Handgeschakeld"]) == "Handgeschakeld"
    assert _transmission_category(["Onbekend"]) is None


# --- Fetch-once lifecycle ----------------------------------------------------


def test_a_second_collection_run_fetches_fresh_inventory() -> None:
    """The cache lives on the adapter, and each run builds a new adapter.

    One operation must not fetch twice; a later independent run must not be
    served yesterday's page.
    """
    first_fetcher = StubFetcher("<html></html>")
    first = InzoevenDataSource(fetcher=first_fetcher)  # type: ignore[arg-type]
    list(first.fetch_listings())
    list(first.fetch_listings())

    second_fetcher = StubFetcher(read_fixture("inzoeven_inventory.html"))
    second = DEALER_SOURCES["inzoeven"](fetcher=second_fetcher)
    listings = list(second.fetch_listings())

    # One page per operation...
    assert first_fetcher.requests_made == 1
    assert second_fetcher.requests_made == 1
    # ...and the new run saw the new page, not the previous run's result.
    assert len(listings) == 2
    assert first._collected == []  # type: ignore[attr-defined]


def test_the_cache_is_per_adapter_and_not_shared_between_instances() -> None:
    one = InzoevenDataSource(fetcher=StubFetcher(read_fixture("inzoeven_inventory.html")))  # type: ignore[arg-type]
    two = InzoevenDataSource(fetcher=StubFetcher("<html></html>"))  # type: ignore[arg-type]

    assert len(list(one.fetch_listings())) == 2
    assert list(two.fetch_listings()) == []
