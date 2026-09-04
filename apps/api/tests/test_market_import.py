"""Market import: the CSV contract, the lifecycle, and the evidence policy.

Nothing here touches the network. Files are written to a temporary directory,
and the only market that exists is the one the test builds.

Most of these tests are about restraint: what an import must *not* do. It must
not apply half a file, must not retire a listing it was never asked about, must
not call a disappearance a sale, and must not quietly value a real car against
invented listings.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from echte_auto_waarde.data_sources.csv_import import CsvContractError, CsvImportDataSource
from echte_auto_waarde.data_sources.synthetic import SyntheticDataSource
from echte_auto_waarde.domain.evidence import (
    IMPORTED_DISCLAIMER,
    SYNTHETIC_DISCLAIMER,
    MarketMode,
    describe_evidence,
    evidence_source_types,
)
from echte_auto_waarde.models.enums import (
    BodyType,
    DataSourceType,
    FuelType,
    ImportMode,
    ImportRunStatus,
    ListingStatus,
    Transmission,
)
from echte_auto_waarde.models.import_run import ImportRun
from echte_auto_waarde.models.listing import Listing
from echte_auto_waarde.models.vehicle import Vehicle
from echte_auto_waarde.services.import_market import import_market_file
from echte_auto_waarde.services.ingestion import ingest

HEADER = (
    "external_reference,make,model,variant,trim,registration_year,mileage_km,"
    "asking_price_eur,fuel,transmission,body_type,power_hp,seller_type,seller_city,"
    "options,observed_at"
)


def row(
    reference: str,
    price: str = "27.500",
    mileage: str = "68500",
    year: str = "2020",
    observed: str = "2026-09-01",
    trim: str = "M Sport",
) -> str:
    # A decimal comma has to be quoted, as in any CSV file.
    cell = f'"{price}"' if "," in price else price
    return (
        f"{reference},BMW,3 Serie,330e,{trim},{year},{mileage},{cell},"
        f"Plug-in hybride,Automaat,Sedan,292,DEALER,Voorbeeldstad,Panoramadak,{observed}"
    )


def write_csv(tmp_path: Path, *rows: str, name: str = "market.csv") -> Path:
    path = tmp_path / name
    path.write_text("\n".join([HEADER, *rows]) + "\n", encoding="utf-8")
    return path


def source_for(path: Path, key: str = "import:test") -> CsvImportDataSource:
    return CsvImportDataSource(path=path, key=key, name="Test import")


# --- 1-6. The CSV contract ---------------------------------------------------


def test_a_valid_file_becomes_normalized_listings(session: Session, tmp_path: Path) -> None:
    path = write_csv(tmp_path, row("A-1"), row("A-2", price="24.950", mileage="94200"))

    report = import_market_file(session, source_for(path), scope="bmw-3-serie")
    session.commit()

    assert report.succeeded
    assert (report.rows_read, report.listings_created, report.listings_updated) == (2, 2, 0)

    listings = session.scalars(select(Listing)).all()
    assert {listing.external_reference for listing in listings} == {"A-1", "A-2"}
    vehicle = listings[0].vehicle
    # Source wording is normalized by the existing layer, not by the importer.
    assert vehicle.make == "BMW"
    assert vehicle.fuel_type is FuelType.PLUGIN_HYBRID
    assert vehicle.transmission is Transmission.AUTOMATIC
    assert vehicle.body_type is BodyType.SEDAN
    assert listings[0].asking_price_cents == 2_750_000


@pytest.mark.parametrize("column", ["external_reference", "make", "model", "asking_price_eur"])
def test_a_missing_required_value_rejects_the_file(
    session: Session, tmp_path: Path, column: str
) -> None:
    fields = HEADER.split(",")
    values = row("A-1").split(",")
    values[fields.index(column)] = ""
    path = write_csv(tmp_path, ",".join(values))

    report = import_market_file(session, source_for(path), scope="s")

    assert not report.succeeded
    assert any(column in problem for problem in report.validation_errors)
    assert session.scalars(select(Listing)).first() is None


def test_a_missing_required_column_rejects_the_file(tmp_path: Path) -> None:
    path = tmp_path / "bad.csv"
    path.write_text("make,model\nBMW,3 Serie\n", encoding="utf-8")

    with pytest.raises(CsvContractError) as error:
        list(source_for(path).fetch_listings())

    assert any("external_reference" in problem for problem in error.value.problems)


@pytest.mark.parametrize("price", ["twintigduizend", "-500", "0", "1.000.000.000"])
def test_malformed_prices_are_rejected(session: Session, tmp_path: Path, price: str) -> None:
    path = write_csv(tmp_path, row("A-1", price=price))

    report = import_market_file(session, source_for(path), scope="s")

    assert not report.succeeded
    assert any("asking_price_eur" in problem for problem in report.validation_errors)


@pytest.mark.parametrize(
    ("written", "expected_cents"),
    [("27500", 2_750_000), ("27.500", 2_750_000), ("27500,50", 2_750_050), ("€ 27.500", 2_750_000)],
)
def test_euro_conventions_are_understood(tmp_path: Path, written: str, expected_cents: int) -> None:
    path = write_csv(tmp_path, row("A-1", price=written))

    listings = list(source_for(path).fetch_listings())

    assert listings[0].asking_price_cents == expected_cents


@pytest.mark.parametrize("observed", ["gisteren", "01-09-2026", "2026-13-01", ""])
def test_malformed_dates_are_rejected(session: Session, tmp_path: Path, observed: str) -> None:
    path = write_csv(tmp_path, row("A-1", observed=observed))

    report = import_market_file(session, source_for(path), scope="s")

    assert not report.succeeded
    assert any("observed_at" in problem for problem in report.validation_errors)


def test_unknown_values_normalize_to_unknown_rather_than_a_guess(
    session: Session, tmp_path: Path
) -> None:
    """A value we cannot map lowers confidence; it never becomes an invention."""
    line = (
        row("A-1").replace("Plug-in hybride", "Vliegtuigbrandstof").replace("Sedan", "Ruimteschip")
    )
    path = write_csv(tmp_path, line)

    import_market_file(session, source_for(path), scope="s")
    session.commit()

    vehicle = session.scalars(select(Vehicle)).one()
    assert vehicle.fuel_type is FuelType.UNKNOWN
    assert vehicle.body_type is BodyType.UNKNOWN


def test_a_duplicate_reference_within_one_file_is_rejected(
    session: Session, tmp_path: Path
) -> None:
    """Identity must be unambiguous, so the file is refused rather than guessed."""
    path = write_csv(tmp_path, row("A-1"), row("A-1", price="24.000"))

    report = import_market_file(session, source_for(path), scope="s")

    assert not report.succeeded
    assert any("already used" in problem for problem in report.validation_errors)
    assert session.scalars(select(Listing)).first() is None


# --- 7-8. Repeated imports and history ---------------------------------------


def test_reimporting_updates_the_same_listing(session: Session, tmp_path: Path) -> None:
    first = write_csv(tmp_path, row("A-1"), name="first.csv")
    import_market_file(session, source_for(first), scope="s")
    session.commit()

    second = write_csv(tmp_path, row("A-1", price="26.000", observed="2026-09-08"), name="2.csv")
    report = import_market_file(session, source_for(second), scope="s")
    session.commit()

    assert (report.listings_created, report.listings_updated) == (0, 1)
    listing = session.scalars(select(Listing)).one()
    assert listing.asking_price_cents == 2_600_000


def test_a_price_change_is_recorded_as_history(session: Session, tmp_path: Path) -> None:
    first = write_csv(tmp_path, row("A-1", price="27.500"), name="first.csv")
    import_market_file(session, source_for(first), scope="s")
    session.commit()

    second = write_csv(tmp_path, row("A-1", price="26.000", observed="2026-09-08"), name="2.csv")
    import_market_file(session, source_for(second), scope="s")
    session.commit()

    listing = session.scalars(select(Listing)).one()
    prices = [snapshot.asking_price_cents for snapshot in listing.snapshots]
    # Both observations survive: history is append-only, never overwritten.
    assert prices == [2_750_000, 2_600_000]


# --- 9-15. Lifecycle: what absence may and may not mean ----------------------


def _import_two_then(
    session: Session, tmp_path: Path, mode: ImportMode, scope: str = "s", key: str = "import:test"
):
    first = write_csv(tmp_path, row("A-1"), row("A-2"), name="first.csv")
    import_market_file(session, source_for(first, key), scope="s")
    session.commit()

    second = write_csv(tmp_path, row("A-1", price="26.000"), name="second.csv")
    report = import_market_file(session, source_for(second, key), scope=scope, mode=mode)
    session.commit()
    return report


def test_incremental_import_never_removes_an_unseen_listing(
    session: Session, tmp_path: Path
) -> None:
    """An incremental file says nothing about what it does not contain."""
    report = _import_two_then(session, tmp_path, ImportMode.INCREMENTAL)

    assert report.listings_removed == 0
    absent = session.scalars(select(Listing).where(Listing.external_reference == "A-2")).one()
    assert absent.status is ListingStatus.ACTIVE


def test_a_completed_full_snapshot_retires_unseen_listings(
    session: Session, tmp_path: Path
) -> None:
    report = _import_two_then(session, tmp_path, ImportMode.FULL_SNAPSHOT)

    assert report.listings_removed == 1
    absent = session.scalars(select(Listing).where(Listing.external_reference == "A-2")).one()
    assert absent.status is ListingStatus.REMOVED
    seen = session.scalars(select(Listing).where(Listing.external_reference == "A-1")).one()
    assert seen.status is ListingStatus.ACTIVE


def test_a_rejected_full_snapshot_removes_nothing(session: Session, tmp_path: Path) -> None:
    """Validation failure must not be a way to empty a market."""
    first = write_csv(tmp_path, row("A-1"), row("A-2"), name="first.csv")
    import_market_file(session, source_for(first), scope="s")
    session.commit()

    broken = write_csv(tmp_path, row("A-1", price="niet-een-getal"), name="broken.csv")
    report = import_market_file(
        session, source_for(broken), scope="s", mode=ImportMode.FULL_SNAPSHOT
    )

    assert not report.succeeded
    assert report.listings_removed == 0
    statuses = {listing.status for listing in session.scalars(select(Listing)).all()}
    assert statuses == {ListingStatus.ACTIVE}


def test_a_full_snapshot_of_another_scope_removes_nothing(session: Session, tmp_path: Path) -> None:
    """A snapshot describes its own scope and draws no conclusions beyond it."""
    report = _import_two_then(session, tmp_path, ImportMode.FULL_SNAPSHOT, scope="other-scope")

    assert report.listings_removed == 0
    assert all(
        listing.status is ListingStatus.ACTIVE for listing in session.scalars(select(Listing)).all()
    )


def test_a_full_snapshot_of_another_source_removes_nothing(
    session: Session, tmp_path: Path
) -> None:
    first = write_csv(tmp_path, row("A-1"), row("A-2"), name="first.csv")
    import_market_file(session, source_for(first, "import:one"), scope="s")
    session.commit()

    second = write_csv(tmp_path, row("B-1"), name="second.csv")
    import_market_file(
        session, source_for(second, "import:two"), scope="s", mode=ImportMode.FULL_SNAPSHOT
    )
    session.commit()

    original = session.scalars(
        select(Listing).where(Listing.external_reference.in_(["A-1", "A-2"]))
    ).all()
    assert {listing.status for listing in original} == {ListingStatus.ACTIVE}


def test_a_removed_listing_is_never_treated_as_sold(session: Session, tmp_path: Path) -> None:
    """REMOVED means "not observed", and nothing more.

    No sale is recorded, no sale price is stored, and a retired listing stops
    being market evidence rather than becoming evidence of a transaction.
    """
    _import_two_then(session, tmp_path, ImportMode.FULL_SNAPSHOT)

    removed = session.scalars(select(Listing).where(Listing.external_reference == "A-2")).one()
    assert removed.status is ListingStatus.REMOVED
    assert removed.status is not ListingStatus.LIKELY_SOLD
    # The observations that remain are asking prices, unchanged by removal.
    assert [snapshot.asking_price_cents for snapshot in removed.snapshots] == [2_750_000]
    assert not hasattr(removed, "sale_price_cents")


def test_the_import_run_records_what_happened(session: Session, tmp_path: Path) -> None:
    _import_two_then(session, tmp_path, ImportMode.FULL_SNAPSHOT)

    runs = session.scalars(select(ImportRun).order_by(ImportRun.id)).all()
    assert [run.status for run in runs] == [ImportRunStatus.COMPLETED, ImportRunStatus.COMPLETED]
    latest = runs[-1]
    assert latest.mode is ImportMode.FULL_SNAPSHOT
    assert (latest.listings_seen, latest.listings_updated, latest.listings_removed) == (1, 1, 1)
    assert latest.finished_at is not None


def test_a_rejected_import_writes_no_run_and_no_listings(session: Session, tmp_path: Path) -> None:
    """Validation precedes mutation, so a bad file leaves no trace at all."""
    path = write_csv(tmp_path, row("A-1", price="kapot"))

    report = import_market_file(session, source_for(path), scope="s")
    session.commit()

    assert not report.succeeded
    assert session.scalars(select(ImportRun)).first() is None
    assert session.scalars(select(Listing)).first() is None


def test_a_dry_run_validates_and_writes_nothing(session: Session, tmp_path: Path) -> None:
    path = write_csv(tmp_path, row("A-1"), row("A-2"))

    report = import_market_file(session, source_for(path), scope="s", dry_run=True)
    session.commit()

    assert report.succeeded and report.rows_read == 2
    assert session.scalars(select(Listing)).first() is None
    assert session.scalars(select(ImportRun)).first() is None


# --- 16-20. Demo data must not become market evidence ------------------------


def test_the_evidence_policy_keeps_the_two_markets_apart() -> None:
    assert evidence_source_types(MarketMode.DEMO, target_is_demo=True) == {DataSourceType.SYNTHETIC}
    assert evidence_source_types(MarketMode.REAL, target_is_demo=True) == {DataSourceType.SYNTHETIC}

    real = evidence_source_types(MarketMode.REAL, target_is_demo=False)
    assert DataSourceType.SYNTHETIC not in real
    assert DataSourceType.CSV_IMPORT in real


def _mixed_market(session: Session, tmp_path: Path) -> None:
    """A database holding both an invented market and an imported one."""
    ingest(session, SyntheticDataSource())
    rows = [
        row(f"REAL-{index}", price=f"2{index}.000", mileage=f"{60000 + index * 1000}")
        for index in range(1, 9)
    ]
    import_market_file(session, source_for(write_csv(tmp_path, *rows)), scope="bmw-3-serie")
    session.commit()


def test_a_real_vehicle_is_valued_on_imported_evidence_only(
    session: Session, tmp_path: Path, monkeypatch
) -> None:
    from echte_auto_waarde import config
    from echte_auto_waarde.data_sources.base import RawVehicle
    from echte_auto_waarde.models.listing import DataSource
    from echte_auto_waarde.services.comparables import find_comparables
    from echte_auto_waarde.services.vehicles import create_manual_vehicle

    _mixed_market(session, tmp_path)
    _use_market_mode(monkeypatch, config, MarketMode.REAL)

    target = create_manual_vehicle(
        session,
        RawVehicle(make="BMW", model="3 Serie", year=2020, mileage_km=70_000, trim="M Sport"),
    )
    session.commit()

    selection = find_comparables(session, target)
    assert selection.comparables

    sources = set()
    for item in selection.comparables:
        listing = session.get(Listing, item.candidate.listing_id)
        sources.add(session.get(DataSource, listing.data_source_id).source_type)
    assert sources == {DataSourceType.CSV_IMPORT}


def test_a_demo_vehicle_is_still_valued_on_the_demo_market(
    session: Session, tmp_path: Path, monkeypatch
) -> None:
    from echte_auto_waarde import config
    from echte_auto_waarde.models.listing import DataSource
    from echte_auto_waarde.services.comparables import find_comparables

    _mixed_market(session, tmp_path)
    _use_market_mode(monkeypatch, config, MarketMode.REAL)

    demo = session.scalars(
        select(Vehicle).join(Listing).join(DataSource).where(DataSource.key == "synthetic")
    ).first()

    selection = find_comparables(session, demo)

    sources = set()
    for item in selection.comparables:
        listing = session.get(Listing, item.candidate.listing_id)
        sources.add(session.get(DataSource, listing.data_source_id).source_type)
    assert sources == {DataSourceType.SYNTHETIC}


def test_a_shortage_of_real_evidence_is_not_filled_with_demo_listings(
    session: Session, monkeypatch
) -> None:
    """The honest answer to "we have no real data" is insufficient data."""
    from echte_auto_waarde import config
    from echte_auto_waarde.data_sources.base import RawVehicle
    from echte_auto_waarde.services.valuation import valuate_vehicle
    from echte_auto_waarde.services.vehicles import create_manual_vehicle

    ingest(session, SyntheticDataSource())  # a full demo market, and nothing real
    _use_market_mode(monkeypatch, config, MarketMode.REAL)

    target = create_manual_vehicle(
        session,
        RawVehicle(make="BMW", model="3 Serie", year=2020, mileage_km=70_000, trim="M Sport"),
    )
    session.commit()

    result = valuate_vehicle(session, target)

    assert result.sufficient_data is False
    assert result.estimated_market_value_cents is None


def test_provenance_describes_the_evidence_that_was_used() -> None:
    assert describe_evidence({DataSourceType.SYNTHETIC}) == SYNTHETIC_DISCLAIMER
    assert describe_evidence({DataSourceType.CSV_IMPORT}) == IMPORTED_DISCLAIMER
    mixed = describe_evidence({DataSourceType.CSV_IMPORT, DataSourceType.SYNTHETIC})
    assert "demogegevens" in mixed
    assert "verkoopprijzen" in IMPORTED_DISCLAIMER


def test_the_valuation_response_reports_imported_provenance(
    session: Session, tmp_path: Path, monkeypatch
) -> None:
    from echte_auto_waarde import config
    from echte_auto_waarde.api.mapping import to_valuation_read
    from echte_auto_waarde.data_sources.base import RawVehicle
    from echte_auto_waarde.services.comparables import find_comparables
    from echte_auto_waarde.services.valuation import valuate_vehicle
    from echte_auto_waarde.services.vehicles import create_manual_vehicle

    _mixed_market(session, tmp_path)
    _use_market_mode(monkeypatch, config, MarketMode.REAL)

    target = create_manual_vehicle(
        session,
        RawVehicle(make="BMW", model="3 Serie", year=2020, mileage_km=70_000, trim="M Sport"),
    )
    session.commit()

    result = valuate_vehicle(session, target)
    read = to_valuation_read(session, target, result, find_comparables(session, target))

    assert read.data_disclaimer == IMPORTED_DISCLAIMER
    assert "demomarkt" not in read.data_disclaimer


def _use_market_mode(monkeypatch, config_module, mode: MarketMode) -> None:
    """Switch market mode for one test, cache included."""
    settings = config_module.get_settings()
    monkeypatch.setattr(settings, "market_mode", mode)


# --- Scope is immutable within a source --------------------------------------
#
# A listing keeps the scope it was first imported under. Moving one between
# scopes would make full-snapshot removal unsound: a snapshot of one scope could
# retire a listing that never belonged to it.


def test_a_new_listing_receives_the_import_scope(session: Session, tmp_path: Path) -> None:
    path = write_csv(tmp_path, row("A-1"))

    import_market_file(session, source_for(path), scope="bmw-3-serie")
    session.commit()

    listing = session.scalars(select(Listing)).one()
    assert listing.source_scope == "bmw-3-serie"


def test_reimporting_under_the_same_scope_succeeds(session: Session, tmp_path: Path) -> None:
    first = write_csv(tmp_path, row("A-1"), name="first.csv")
    import_market_file(session, source_for(first), scope="bmw-3-serie")
    session.commit()

    second = write_csv(tmp_path, row("A-1", price="26.000"), name="second.csv")
    report = import_market_file(session, source_for(second), scope="bmw-3-serie")
    session.commit()

    assert report.succeeded
    listing = session.scalars(select(Listing)).one()
    assert listing.source_scope == "bmw-3-serie"
    assert listing.asking_price_cents == 2_600_000


def test_a_listing_without_a_scope_adopts_one_once(session: Session, tmp_path: Path) -> None:
    """Covers rows imported before scopes existed."""
    path = write_csv(tmp_path, row("A-1"))
    import_market_file(session, source_for(path), scope="bmw-3-serie")
    session.commit()

    legacy = session.scalars(select(Listing)).one()
    legacy.source_scope = None
    session.commit()

    report = import_market_file(session, source_for(path), scope="bmw-3-serie-2026")
    session.commit()

    assert report.succeeded
    assert session.scalars(select(Listing)).one().source_scope == "bmw-3-serie-2026"


def test_the_same_reference_under_a_different_scope_is_rejected(
    session: Session, tmp_path: Path
) -> None:
    first = write_csv(tmp_path, row("A-1"), name="first.csv")
    import_market_file(session, source_for(first), scope="scope-a")
    session.commit()

    second = write_csv(tmp_path, row("A-1", price="26.000"), name="second.csv")
    report = import_market_file(session, source_for(second), scope="scope-b")

    assert not report.succeeded
    assert any("already belongs to scope" in problem for problem in report.validation_errors)


def test_a_scope_conflict_changes_nothing_at_all(session: Session, tmp_path: Path) -> None:
    """No listing moved, no observation appended, no run recorded, nothing retired."""
    first = write_csv(tmp_path, row("A-1"), row("A-2"), name="first.csv")
    import_market_file(session, source_for(first), scope="scope-a")
    session.commit()
    snapshots_before = len(session.scalars(select(Listing)).all()[0].snapshots)

    conflicting = write_csv(tmp_path, row("A-1", price="26.000"), name="second.csv")
    report = import_market_file(
        session, source_for(conflicting), scope="scope-b", mode=ImportMode.FULL_SNAPSHOT
    )
    session.commit()

    assert not report.succeeded
    listings = {listing.external_reference: listing for listing in session.scalars(select(Listing))}
    assert listings["A-1"].source_scope == "scope-a"
    assert listings["A-1"].asking_price_cents == 2_750_000
    assert len(listings["A-1"].snapshots) == snapshots_before
    assert {listing.status for listing in listings.values()} == {ListingStatus.ACTIVE}
    # Only the first, successful run exists.
    assert [run.scope for run in session.scalars(select(ImportRun))] == ["scope-a"]


def test_a_snapshot_of_one_scope_never_retires_another_scopes_listing(
    session: Session, tmp_path: Path
) -> None:
    a = write_csv(tmp_path, row("A-1"), name="a.csv")
    import_market_file(session, source_for(a), scope="scope-a")
    session.commit()

    b = write_csv(tmp_path, row("B-1"), name="b.csv")
    import_market_file(session, source_for(b), scope="scope-b")
    session.commit()

    # A complete snapshot of scope B that contains nothing at all from scope A.
    b_again = write_csv(tmp_path, row("B-1", price="26.000"), name="b2.csv")
    report = import_market_file(
        session, source_for(b_again), scope="scope-b", mode=ImportMode.FULL_SNAPSHOT
    )
    session.commit()

    assert report.succeeded
    assert report.listings_removed == 0
    scope_a = session.scalars(select(Listing).where(Listing.external_reference == "A-1")).one()
    assert scope_a.status is ListingStatus.ACTIVE
    assert scope_a.source_scope == "scope-a"


def test_the_evidence_policy_is_unchanged_by_scope_handling() -> None:
    """Scope governs lifecycle, never which market a valuation may use."""
    assert evidence_source_types(MarketMode.DEMO, target_is_demo=False) == {
        DataSourceType.SYNTHETIC
    }
    real = evidence_source_types(MarketMode.REAL, target_is_demo=False)
    assert DataSourceType.SYNTHETIC not in real and DataSourceType.CSV_IMPORT in real
    assert evidence_source_types(MarketMode.REAL, target_is_demo=True) == {DataSourceType.SYNTHETIC}
