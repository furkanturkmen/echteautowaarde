from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from echte_auto_waarde.data_sources.base import RawListing, RawSeller, RawSnapshot, RawVehicle
from echte_auto_waarde.data_sources.synthetic import SyntheticDataSource
from echte_auto_waarde.models.enums import (
    BodyType,
    DataSourceType,
    FuelType,
    ListingStatus,
    SellerType,
    Transmission,
)
from echte_auto_waarde.models.listing import DataSource, Listing, ListingSnapshot, Seller
from echte_auto_waarde.models.vehicle import Vehicle
from echte_auto_waarde.services.ingestion import ingest, sync_option_definitions

NOW = datetime(2026, 6, 1, tzinfo=UTC)


class _StubSource:
    """Minimal adapter returning source wording that still needs normalizing."""

    key = "stub"
    source_type = DataSourceType.SYNTHETIC
    name = "Stub"
    quality = 0.4

    def __init__(self, listings: list[RawListing]) -> None:
        self._listings = listings

    def fetch_listings(self) -> list[RawListing]:
        return self._listings


def _raw_listing(reference: str = "STUB-1", price_cents: int = 2_750_000) -> RawListing:
    return RawListing(
        external_reference=reference,
        vehicle=RawVehicle(
            make="bmw",
            model="3-serie",
            year=2021,
            mileage_km=82_000,
            trim="m-sport",
            generation="G20",
            body_type="Touring",
            fuel_type="Plug-in hybride",
            transmission="Automaat",
            drivetrain="Achterwielaandrijving",
            engine_description="330e",
            power_kw=215,
            power_hp=292,
            license_plate="K-123-AB",
            option_texts=("panoramadak", "ACC", "onbekende optie"),
        ),
        asking_price_cents=price_cents,
        first_seen_at=NOW,
        last_seen_at=NOW,
        seller=RawSeller(seller_type="DEALER", name="Demo Autobedrijf", city="Utrecht"),
    )


def test_ingestion_normalizes_raw_source_wording(session: Session) -> None:
    ingest(session, _StubSource([_raw_listing()]))

    vehicle = session.scalars(select(Vehicle)).one()
    assert vehicle.make == "BMW"
    assert vehicle.model == "3 Serie"
    assert vehicle.trim == "M Sport"
    assert vehicle.body_type is BodyType.STATIONWAGON
    assert vehicle.fuel_type is FuelType.PLUGIN_HYBRID
    assert vehicle.transmission is Transmission.AUTOMATIC
    assert vehicle.license_plate == "K123AB"


def test_ingestion_keeps_raw_values_for_traceability(session: Session) -> None:
    ingest(session, _StubSource([_raw_listing()]))

    vehicle = session.scalars(select(Vehicle)).one()
    assert vehicle.make_raw == "bmw"
    assert vehicle.model_raw == "3-serie"
    assert vehicle.trim_raw == "m-sport"

    option_texts = {option.raw_text for option in vehicle.options}
    assert option_texts == {"panoramadak", "ACC"}


def test_unresolved_option_text_is_reported_not_guessed(session: Session) -> None:
    result = ingest(session, _StubSource([_raw_listing()]))

    assert result.unresolved_option_texts == 1
    vehicle = session.scalars(select(Vehicle)).one()
    assert {option.definition.key for option in vehicle.options} == {
        "panoramic_roof",
        "adaptive_cruise_control",
    }


def test_ingestion_is_idempotent_and_appends_history(session: Session) -> None:
    source = _StubSource([_raw_listing()])
    first = ingest(session, source)
    assert first.listings_created == 1
    assert first.snapshots_created == 1

    # The same listing observed again at a lower price.
    later = datetime(2026, 6, 20, tzinfo=UTC)
    reduced = RawListing(
        external_reference="STUB-1",
        vehicle=_raw_listing().vehicle,
        asking_price_cents=2_650_000,
        first_seen_at=NOW,
        last_seen_at=later,
        seller=RawSeller(seller_type="DEALER", name="Demo Autobedrijf", city="Utrecht"),
        status=ListingStatus.PRICE_REDUCED,
        snapshots=(
            RawSnapshot(observed_at=NOW, asking_price_cents=2_750_000),
            RawSnapshot(
                observed_at=later,
                asking_price_cents=2_650_000,
                status=ListingStatus.PRICE_REDUCED,
            ),
        ),
    )
    second = ingest(session, _StubSource([reduced]))

    assert second.listings_created == 0
    assert second.listings_updated == 1
    assert session.scalar(select(func.count()).select_from(Listing)) == 1

    listing = session.scalars(select(Listing)).one()
    assert listing.asking_price_cents == 2_650_000
    assert listing.status is ListingStatus.PRICE_REDUCED

    snapshots = session.scalars(select(ListingSnapshot).order_by(ListingSnapshot.observed_at)).all()
    # Original observation preserved: history is appended, never rewritten.
    assert [snapshot.asking_price_cents for snapshot in snapshots] == [2_750_000, 2_650_000]


def test_identical_sellers_are_reused(session: Session) -> None:
    ingest(
        session,
        _StubSource([_raw_listing("STUB-1"), _raw_listing("STUB-2", price_cents=2_800_000)]),
    )

    sellers = session.scalars(select(Seller)).all()
    assert len(sellers) == 1
    assert sellers[0].seller_type is SellerType.DEALER


def test_seeding_the_synthetic_market_produces_a_usable_dataset(session: Session) -> None:
    result = ingest(session, SyntheticDataSource())

    assert result.listings_created == 100
    assert result.unresolved_option_texts == 0
    assert session.scalar(select(func.count()).select_from(Vehicle)) == 100

    data_source = session.scalars(select(DataSource)).one()
    assert data_source.source_type is DataSourceType.SYNTHETIC

    # Every listing carries at least one observation, so market history exists
    # from the very first import.
    assert session.scalar(select(func.count()).select_from(ListingSnapshot)) >= 100


def test_option_definitions_are_synced_from_the_taxonomy(session: Session) -> None:
    count = sync_option_definitions(session)
    assert count > 0

    # Re-syncing must update rather than duplicate.
    sync_option_definitions(session)
    from echte_auto_waarde.models.option import VehicleOptionDefinition

    assert session.scalar(select(func.count()).select_from(VehicleOptionDefinition)) == count
