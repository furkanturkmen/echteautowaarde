"""The offline evaluation framework.

Two kinds of test. The statistics are checked against hand-computed numbers, so
a silent change in a percentile or a share is caught. The evaluation itself is
checked for the properties that make it meaningful: a listing never values
itself, demo data never takes part, and running it changes nothing.

The fixtures stand in for imported real data. They are `CSV_IMPORT` listings so
they behave exactly like a lawful import would, and no test touches the network.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from echte_auto_waarde.data_sources.csv_import import CsvImportDataSource
from echte_auto_waarde.data_sources.synthetic import SyntheticDataSource
from echte_auto_waarde.domain.evaluation import (
    ListingEvaluation,
    comparable_count_band,
    confidence_band,
    largest_deviations,
    percentile,
    segment_by,
    summarise,
)
from echte_auto_waarde.models.enums import DataSourceType
from echte_auto_waarde.models.listing import DataSource, Listing
from echte_auto_waarde.models.valuation import Valuation
from echte_auto_waarde.services.evaluation import (
    EvaluationFilters,
    evaluate_listing,
    evaluate_market,
    select_targets,
)
from echte_auto_waarde.services.import_market import import_market_file
from echte_auto_waarde.services.ingestion import ingest

HEADER = (
    "external_reference,make,model,variant,trim,registration_year,mileage_km,"
    "asking_price_eur,fuel,transmission,body_type,power_hp,seller_type,seller_city,"
    "options,observed_at"
)


def listing_row(
    reference: str,
    price: int,
    mileage: int,
    year: int = 2020,
    make: str = "BMW",
    model: str = "3 Serie",
) -> str:
    return (
        f"{reference},{make},{model},330e,M Sport,{year},{mileage},{price},"
        "Plug-in hybride,Automaat,Sedan,292,DEALER,Voorbeeldstad,Panoramadak,2026-09-01"
    )


def import_rows(
    session: Session,
    tmp_path: Path,
    rows: list[str],
    key: str = "import:test",
    scope: str = "bmw-3-serie",
    name: str = "market.csv",
) -> None:
    path = tmp_path / name
    path.write_text("\n".join([HEADER, *rows]) + "\n", encoding="utf-8")
    source = CsvImportDataSource(path=path, key=key, name="Test import")
    report = import_market_file(session, source, scope=scope)
    assert report.succeeded, report.validation_errors
    session.commit()


@pytest.fixture
def imported_market(session: Session, tmp_path: Path) -> None:
    """Ten comparable imported listings around a coherent price level."""
    rows = [
        listing_row(f"REAL-{index:02d}", 26_000 + index * 400, 60_000 + index * 3_000)
        for index in range(1, 11)
    ]
    import_rows(session, tmp_path, rows)


def evaluation(
    listing_id: int = 1,
    ask: int = 2_000_000,
    estimate: int | None = 2_000_000,
    confidence: float | None = 0.7,
    comparables: int = 8,
    sufficient: bool = True,
    **overrides: object,
) -> ListingEvaluation:
    defaults = dict(
        listing_id=listing_id,
        external_reference=f"REF-{listing_id}",
        source_key="import:test",
        scope="scope",
        make="BMW",
        model="3 Serie",
        year=2020,
        mileage_km=70_000,
        trim="M Sport",
        fuel_type="PLUGIN_HYBRID",
        transmission="AUTOMATIC",
        body_type="SEDAN",
        observed_asking_price_cents=ask,
        estimated_market_value_cents=estimate,
        sufficient_data=sufficient,
        comparable_count=comparables,
        confidence_score=confidence,
    )
    defaults.update(overrides)
    return ListingEvaluation(**defaults)  # type: ignore[arg-type]


# --- Statistics --------------------------------------------------------------


def test_euro_and_percentage_deviation_are_measured_against_the_asking_price() -> None:
    item = evaluation(ask=2_000_000, estimate=1_800_000)

    assert item.deviation_cents == -200_000
    assert item.deviation_ratio == pytest.approx(-0.10)

    higher = evaluation(ask=2_000_000, estimate=2_300_000)
    assert higher.deviation_cents == 300_000
    assert higher.deviation_ratio == pytest.approx(0.15)


def test_signed_bias_separates_over_and_under_estimation() -> None:
    items = [
        evaluation(1, estimate=2_200_000),  # +10%
        evaluation(2, estimate=2_200_000),  # +10%
        evaluation(3, estimate=1_800_000),  # -10%
        evaluation(4, estimate=2_000_000),  # 0%
    ]

    metrics = summarise(items)

    # Mean signed deviation keeps direction; the absolute median does not.
    assert metrics.mean_signed_deviation_ratio == pytest.approx(0.025)
    assert metrics.median_absolute_deviation_ratio == pytest.approx(0.10)
    assert metrics.median_absolute_deviation_cents == 200_000
    assert metrics.share_estimated_above_ask == pytest.approx(0.5)
    assert metrics.share_estimated_below_ask == pytest.approx(0.25)


@pytest.mark.parametrize(
    ("fraction", "expected"),
    [(0.0, 1.0), (0.5, 3.0), (0.75, 4.0), (0.9, 4.6), (1.0, 5.0)],
)
def test_percentiles_interpolate_predictably(fraction: float, expected: float) -> None:
    assert percentile([1.0, 2.0, 3.0, 4.0, 5.0], fraction) == pytest.approx(expected)


def test_percentiles_of_nothing_are_nothing() -> None:
    assert percentile([], 0.5) is None
    assert percentile([2.5], 0.9) == 2.5


def test_insufficient_evidence_is_counted_and_excluded_from_deviations() -> None:
    items = [
        evaluation(1, estimate=2_200_000),
        evaluation(2, estimate=None, sufficient=False),
        evaluation(3, estimate=None, sufficient=False),
    ]

    metrics = summarise(items)

    assert metrics.evaluated_count == 3
    assert metrics.insufficient_evidence_count == 2
    # Only the valued listing contributes a deviation.
    assert metrics.median_absolute_deviation_ratio == pytest.approx(0.10)


def test_groups_below_the_minimum_size_are_not_reported() -> None:
    """A median over two listings describes the sample, not the market."""
    items = [evaluation(index, comparables=2) for index in range(1, 4)]
    items += [evaluation(index, comparables=10) for index in range(4, 10)]

    segments = segment_by(items, comparable_count_band, minimum_size=5)

    assert [segment.label for segment in segments] == ["8-15 comparables"]
    assert segments[0].metrics.evaluated_count == 6


def test_confidence_bands_group_as_documented() -> None:
    assert confidence_band(evaluation(confidence=0.31)) == "confidence <40%"
    assert confidence_band(evaluation(confidence=0.55)) == "confidence 40-60%"
    assert confidence_band(evaluation(confidence=0.79)) == "confidence 60-80%"
    assert confidence_band(evaluation(confidence=0.95)) == "confidence 80%+"
    assert confidence_band(evaluation(confidence=None)) is None


def test_largest_deviations_are_ordered_and_deterministic() -> None:
    items = [
        evaluation(1, estimate=2_100_000),  # +5%
        evaluation(2, estimate=2_600_000),  # +30%
        evaluation(3, estimate=1_600_000),  # -20%
        evaluation(4, estimate=None, sufficient=False),
    ]

    outliers = largest_deviations(items, limit=2)

    assert [item.listing_id for item in outliers] == [2, 3]
    # Nothing is dropped from the metrics because it is an outlier.
    assert summarise(items).evaluated_count == 4


# --- Evaluation against the real engine --------------------------------------


def test_a_listing_is_never_evidence_for_its_own_valuation(
    session: Session, imported_market: None
) -> None:
    target = session.scalars(select(Listing).order_by(Listing.id)).first()

    result = evaluate_listing(session, target)

    assert target.external_reference not in result.comparable_references
    assert result.comparable_count > 0


def test_only_imported_evidence_takes_part(
    session: Session, tmp_path: Path, imported_market: None
) -> None:
    """A synthetic demo market alongside it must not reach the evaluation."""
    ingest(session, SyntheticDataSource())
    session.commit()

    synthetic_references = {
        listing.external_reference
        for listing in session.scalars(
            select(Listing)
            .join(DataSource)
            .where(DataSource.source_type == DataSourceType.SYNTHETIC)
        )
    }
    target = session.scalars(select(Listing).order_by(Listing.id)).first()

    result = evaluate_listing(session, target)

    assert result.comparable_count > 0
    assert not set(result.comparable_references) & synthetic_references


def test_synthetic_listings_are_never_evaluated(
    session: Session, tmp_path: Path, imported_market: None
) -> None:
    ingest(session, SyntheticDataSource())
    session.commit()

    targets = select_targets(session, EvaluationFilters())

    assert targets
    assert all(listing.data_source.source_type is DataSourceType.CSV_IMPORT for listing in targets)


def test_a_report_describes_the_imported_market(session: Session, imported_market: None) -> None:
    report = evaluate_market(session)

    assert report.listing_count == 10
    assert report.overall.evaluated_count == 10
    assert report.overall.median_absolute_deviation_ratio is not None
    # The fixture is a coherent price ladder, so deviations should be modest.
    assert report.overall.median_absolute_deviation_ratio < 0.25


def test_running_an_evaluation_creates_no_consumer_valuations(
    session: Session, imported_market: None
) -> None:
    """A backtest must not appear in anyone's valuation history."""
    before = session.scalars(select(Valuation)).all()

    evaluate_market(session)

    assert session.scalars(select(Valuation)).all() == before
    assert before == []


def test_the_same_database_produces_the_same_report(
    session: Session, imported_market: None
) -> None:
    first = evaluate_market(session)
    second = evaluate_market(session)

    assert first.overall == second.overall
    assert [item.listing_id for item in first.outliers] == [
        item.listing_id for item in second.outliers
    ]


def test_filtering_by_source_scope_make_and_model(session: Session, tmp_path: Path) -> None:
    import_rows(
        session,
        tmp_path,
        [listing_row(f"BMW-{index}", 26_000 + index * 400, 60_000) for index in range(1, 7)],
        key="import:one",
        scope="scope-a",
        name="one.csv",
    )
    import_rows(
        session,
        tmp_path,
        [
            listing_row(
                f"VW-{index}", 18_000 + index * 300, 90_000, make="Volkswagen", model="Golf"
            )
            for index in range(1, 7)
        ],
        key="import:two",
        scope="scope-b",
        name="two.csv",
    )

    by_source = select_targets(session, EvaluationFilters(source_key="import:one"))
    by_scope = select_targets(session, EvaluationFilters(scope="scope-b"))
    by_model = select_targets(session, EvaluationFilters(make="Volkswagen", model="Golf"))
    by_year = select_targets(session, EvaluationFilters(year_from=2021))

    assert {listing.external_reference[:3] for listing in by_source} == {"BMW"}
    assert {listing.external_reference[:2] for listing in by_scope} == {"VW"}
    assert len(by_model) == 6
    # Every fixture listing is a 2020 car.
    assert by_year == []


def test_an_evaluation_never_labels_an_asking_price_as_a_sale_price(
    session: Session, imported_market: None
) -> None:
    """Terminology is part of the contract, not decoration.

    The framework measures deviation from what sellers were asking. Nothing it
    produces may be read as a sale price, ground truth, or an accuracy score.
    """
    from echte_auto_waarde import evaluate_market as cli
    from echte_auto_waarde.domain import evaluation as metrics_module

    report = evaluate_market(session)
    item = report.outliers[0]

    # The observed field says what it is, and no sale-price field exists.
    assert item.observed_asking_price_cents > 0
    assert not any("sale" in name for name in vars(item))
    assert not any("truth" in name for name in vars(item))

    fields = vars(metrics_module.DeviationMetrics(evaluated_count=0, insufficient_evidence_count=0))
    assert not any("accuracy" in name or "error" in name for name in fields)

    payload_path = Path(cli.__file__)
    text = payload_path.read_text(encoding="utf-8")
    assert "not accuracy against sale prices" in text


def test_insufficient_evidence_is_reported_rather_than_hidden(
    session: Session, tmp_path: Path
) -> None:
    """A lone listing has nothing to be compared with, and that is the answer."""
    import_rows(session, tmp_path, [listing_row("LONELY-1", 26_000, 60_000)])

    report = evaluate_market(session)

    assert report.listing_count == 1
    assert report.overall.insufficient_evidence_count == 1
    assert report.overall.median_absolute_deviation_ratio is None
