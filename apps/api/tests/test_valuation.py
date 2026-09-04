"""Valuation engine tests.

Each test states the input, the comparables it produces and the expected
outcome, so a failing test points at a methodology change rather than at a
mystery number.
"""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

from echte_auto_waarde.domain.comparables import (
    ComparableCandidate,
    ComparableCriteria,
    select_comparables,
)
from echte_auto_waarde.domain.deals import DealClassification, classify_deal
from echte_auto_waarde.domain.fingerprint import VehicleFingerprint
from echte_auto_waarde.domain.valuation import (
    ALGORITHM_VERSION,
    DEFAULT_CONFIG,
    ValuationConfig,
    value_vehicle,
)
from echte_auto_waarde.models.enums import BodyType, Drivetrain, FuelType, Transmission

NOW = datetime(2026, 6, 1, tzinfo=UTC)

TARGET = VehicleFingerprint(
    make="BMW",
    model="3 Serie",
    generation="G20",
    body_type=BodyType.SEDAN,
    fuel_type=FuelType.PLUGIN_HYBRID,
    transmission=Transmission.AUTOMATIC,
    drivetrain=Drivetrain.RWD,
    engine_description="330e",
    power_hp=292,
    year=2021,
    mileage_km=80_000,
    trim="M Sport",
    option_keys=frozenset({"panoramic_roof", "adaptive_cruise_control"}),
)

LOOSE = ComparableCriteria(min_similarity=0.3, min_comparables=1)


def _candidate(
    index: int,
    price_cents: int,
    fingerprint: VehicleFingerprint | None = None,
    observed_days_ago: int = 5,
) -> ComparableCandidate:
    return ComparableCandidate(
        listing_id=index,
        fingerprint=fingerprint or TARGET,
        asking_price_cents=price_cents,
        last_seen_at=NOW - timedelta(days=observed_days_ago),
        source_quality=0.9,
    )


def _selection(candidates: list[ComparableCandidate], criteria: ComparableCriteria = LOOSE):
    return select_comparables(TARGET, candidates, criteria)


def _identical_market(prices: list[int]) -> list[ComparableCandidate]:
    """A market of cars identical to the target, so only price varies."""
    return [_candidate(index, price) for index, price in enumerate(prices)]


def test_identical_market_values_the_car_at_the_market_median() -> None:
    prices = [2_600_000, 2_700_000, 2_800_000, 2_900_000, 3_000_000]
    result = value_vehicle(TARGET, _selection(_identical_market(prices)), now=NOW)

    assert result.sufficient_data
    assert result.market_basis_cents == 2_800_000
    # Nothing differs from the group, so no adjustment is applied.
    assert result.adjustments == []
    assert result.estimated_market_value_cents == 2_800_000
    assert result.algorithm_version == ALGORITHM_VERSION


def test_too_few_comparables_produce_no_valuation() -> None:
    result = value_vehicle(TARGET, _selection(_identical_market([2_700_000, 2_800_000])), now=NOW)

    assert not result.sufficient_data
    assert result.estimated_market_value_cents is None
    assert result.insufficient_data_reason is not None
    assert "at least 3" in result.insufficient_data_reason


def test_an_extreme_listing_does_not_dominate_the_valuation() -> None:
    normal = [2_600_000, 2_700_000, 2_800_000, 2_900_000, 3_000_000]
    with_outlier = _identical_market([*normal, 9_500_000])

    result = value_vehicle(TARGET, _selection(with_outlier), now=NOW)

    assert result.statistics.outliers_removed == 1
    assert result.removed_outlier_listing_ids == [5]
    assert result.estimated_market_value_cents == 2_800_000


def test_more_similar_comparables_weigh_more() -> None:
    # Three cheap but loosely matching cars outnumber two close matches, so the
    # plain median sits low while the weighted market basis follows the cars
    # that actually resemble the target.
    loose = replace(
        TARGET,
        mileage_km=200_000,
        trim="Executive",
        year=2019,
        body_type=BodyType.STATIONWAGON,
        option_keys=frozenset(),
    )
    candidates = [
        _candidate(1, 2_500_000, loose),
        _candidate(2, 2_550_000, loose),
        _candidate(3, 2_600_000, loose),
        _candidate(4, 2_950_000),
        _candidate(5, 3_000_000),
    ]

    result = value_vehicle(TARGET, _selection(candidates), now=NOW)

    assert result.statistics.outliers_removed == 0
    assert result.market_basis_cents > result.statistics.median_price_cents


def test_higher_mileage_than_the_group_lowers_the_estimate() -> None:
    group = [_candidate(index, 2_800_000, replace(TARGET, mileage_km=60_000)) for index in range(5)]
    high_mileage_target = replace(TARGET, mileage_km=100_000)

    result = value_vehicle(
        high_mileage_target, select_comparables(high_mileage_target, group, LOOSE), now=NOW
    )

    mileage = next(a for a in result.adjustments if a.type == "MILEAGE")
    assert mileage.amount_cents < 0
    # 40.000 km more than the group median at 6 cents/km.
    assert mileage.amount_cents == -40_000 * DEFAULT_CONFIG.mileage_cents_per_km
    assert "40,000 km more" in mileage.reason
    assert result.estimated_market_value_cents < result.market_basis_cents


def test_lower_mileage_than_the_group_raises_the_estimate() -> None:
    group = [
        _candidate(index, 2_800_000, replace(TARGET, mileage_km=120_000)) for index in range(5)
    ]
    low_mileage_target = replace(TARGET, mileage_km=60_000)

    result = value_vehicle(
        low_mileage_target, select_comparables(low_mileage_target, group, LOOSE), now=NOW
    )

    mileage = next(a for a in result.adjustments if a.type == "MILEAGE")
    assert mileage.amount_cents > 0
    assert result.estimated_market_value_cents > result.market_basis_cents


def test_mileage_adjustment_is_capped() -> None:
    group = [_candidate(index, 2_000_000, replace(TARGET, mileage_km=20_000)) for index in range(5)]
    extreme_target = replace(TARGET, mileage_km=400_000)

    result = value_vehicle(
        extreme_target, select_comparables(extreme_target, group, LOOSE), now=NOW
    )

    mileage = next(a for a in result.adjustments if a.type == "MILEAGE")
    cap = int(result.market_basis_cents * DEFAULT_CONFIG.mileage_adjustment_cap_ratio)
    assert mileage.amount_cents == -cap


def test_a_newer_car_than_the_group_is_worth_more() -> None:
    group = [_candidate(index, 2_800_000, replace(TARGET, year=2019)) for index in range(5)]
    newer_target = replace(TARGET, year=2022)

    result = value_vehicle(newer_target, select_comparables(newer_target, group, LOOSE), now=NOW)

    age = next(a for a in result.adjustments if a.type == "AGE")
    assert age.amount_cents > 0
    assert "newer" in age.reason


def test_age_adjustment_stays_conservative() -> None:
    group = [_candidate(index, 2_800_000, replace(TARGET, year=2019)) for index in range(5)]
    # Five model years newer would be worth 12.5% on the raw ratio.
    newer_target = replace(TARGET, year=2024)

    result = value_vehicle(newer_target, select_comparables(newer_target, group, LOOSE), now=NOW)

    age = next(a for a in result.adjustments if a.type == "AGE")
    cap = int(result.market_basis_cents * DEFAULT_CONFIG.year_adjustment_cap_ratio)
    # Comparable prices already carry depreciation, so the correction is capped.
    assert age.amount_cents == cap


def test_better_equipped_than_the_group_raises_the_estimate() -> None:
    plain = replace(TARGET, option_keys=frozenset())
    group = [_candidate(index, 2_800_000, plain) for index in range(5)]

    result = value_vehicle(TARGET, select_comparables(TARGET, group, LOOSE), now=NOW)

    options = next(a for a in result.adjustments if a.type == "OPTIONS")
    assert options.amount_cents > 0
    assert options.detail["targetOptions"] == ["adaptive_cruise_control", "panoramic_roof"]


def test_option_adjustment_is_well_below_retail_prices() -> None:
    plain = replace(TARGET, option_keys=frozenset())
    group = [_candidate(index, 2_800_000, plain) for index in range(5)]

    result = value_vehicle(TARGET, select_comparables(TARGET, group, LOOSE), now=NOW)
    options = next(a for a in result.adjustments if a.type == "OPTIONS")

    # A panoramic roof and adaptive cruise cost thousands new; used-market value
    # is a fraction of that.
    assert options.amount_cents < 120_000


def test_a_sport_package_the_group_lacks_raises_the_estimate() -> None:
    plain = replace(TARGET, trim="Business Edition")
    group = [_candidate(index, 2_800_000, plain) for index in range(5)]

    result = value_vehicle(TARGET, select_comparables(TARGET, group, LOOSE), now=NOW)

    trim = next(a for a in result.adjustments if a.type == "TRIM")
    assert trim.amount_cents == DEFAULT_CONFIG.package_trim_value_cents
    assert "M Sport" in trim.reason


def test_lacking_a_package_the_group_has_lowers_the_estimate() -> None:
    plain_target = replace(TARGET, trim="Business Edition")
    group = [_candidate(index, 2_800_000, TARGET) for index in range(5)]

    result = value_vehicle(plain_target, select_comparables(plain_target, group, LOOSE), now=NOW)

    trim = next(a for a in result.adjustments if a.type == "TRIM")
    assert trim.amount_cents < 0


def test_every_euro_of_the_estimate_is_accounted_for() -> None:
    group = [
        _candidate(
            index, 2_800_000, replace(TARGET, mileage_km=60_000, year=2019, trim="Executive")
        )
        for index in range(6)
    ]

    result = value_vehicle(TARGET, select_comparables(TARGET, group, LOOSE), now=NOW)
    total_adjustments = sum(a.amount_cents for a in result.adjustments)

    # Rounding to whole euros is the only unexplained difference.
    assert (
        abs(result.estimated_market_value_cents - (result.market_basis_cents + total_adjustments))
        < 100
    )


def test_recommended_purchase_range_sits_below_the_estimate() -> None:
    result = value_vehicle(TARGET, _selection(_identical_market([2_800_000] * 5)), now=NOW)

    assert (
        result.recommended_buy_price_low_cents
        < result.recommended_buy_price_high_cents
        <= result.estimated_market_value_cents
    )


def test_deal_classification_compares_asking_price_with_the_estimate() -> None:
    market = _identical_market([2_800_000] * 5)

    cheap = value_vehicle(TARGET, _selection(market), asking_price_cents=2_400_000, now=NOW)
    fair = value_vehicle(TARGET, _selection(market), asking_price_cents=2_800_000, now=NOW)
    steep = value_vehicle(TARGET, _selection(market), asking_price_cents=3_400_000, now=NOW)

    assert cheap.deal_classification is DealClassification.EXCELLENT_DEAL
    assert fair.deal_classification is DealClassification.FAIR_PRICE
    assert steep.deal_classification is DealClassification.VERY_EXPENSIVE


def test_no_asking_price_means_no_deal_classification() -> None:
    result = value_vehicle(TARGET, _selection(_identical_market([2_800_000] * 5)), now=NOW)
    assert result.deal_classification is None


def test_deal_thresholds_are_configurable() -> None:
    strict = ValuationConfig(
        deal_thresholds=replace(DEFAULT_CONFIG.deal_thresholds, fair_price_max_ratio=1.001)
    )
    result = value_vehicle(
        TARGET,
        _selection(_identical_market([2_800_000] * 5)),
        asking_price_cents=2_850_000,
        config=strict,
        now=NOW,
    )

    assert result.deal_classification is DealClassification.EXPENSIVE


def test_market_statistics_describe_the_evidence() -> None:
    prices = [2_500_000, 2_650_000, 2_800_000, 2_950_000, 3_100_000]
    result = value_vehicle(TARGET, _selection(_identical_market(prices)), now=NOW)
    statistics = result.statistics

    assert statistics.comparable_count == 5
    assert statistics.min_price_cents == 2_500_000
    assert statistics.max_price_cents == 3_100_000
    assert statistics.median_price_cents == 2_800_000
    assert statistics.p25_price_cents < statistics.median_price_cents < statistics.p75_price_cents
    assert statistics.average_mileage_km == TARGET.mileage_km
    assert statistics.average_year == TARGET.year
    assert 0.0 <= statistics.average_similarity <= 1.0


def test_valuation_is_deterministic() -> None:
    market = _identical_market([2_600_000, 2_700_000, 2_800_000, 2_900_000, 3_000_000])
    first = value_vehicle(TARGET, _selection(market), now=NOW)
    second = value_vehicle(TARGET, _selection(market), now=NOW)

    assert first.estimated_market_value_cents == second.estimated_market_value_cents
    assert first.confidence.score == second.confidence.score


def test_a_widened_search_lowers_confidence_for_the_same_prices() -> None:
    market = _identical_market([2_800_000] * 6)
    strict = _selection(market)
    widened = _selection(market)
    widened.widening_level = 2

    strict_result = value_vehicle(TARGET, strict, now=NOW)
    widened_result = value_vehicle(TARGET, widened, now=NOW)

    assert widened_result.confidence.score < strict_result.confidence.score


def test_deal_classification_requires_a_positive_estimate() -> None:
    try:
        classify_deal(2_500_000, 0)
    except ValueError as error:
        assert "positive" in str(error)
    else:  # pragma: no cover - guard must raise
        raise AssertionError("expected a ValueError")


def test_a_refusal_names_what_the_vehicle_does_not_state() -> None:
    """ "No comparable was close enough" is not actionable on its own."""
    from echte_auto_waarde.domain.comparables import ComparableSelection

    thin = VehicleFingerprint(make="BMW", model="3 Serie", year=2020, mileage_km=70_000)
    empty = ComparableSelection(comparables=[], widening_level=2, widening_description="broadest")

    result = value_vehicle(thin, empty)

    assert result.sufficient_data is False
    assert "fuel_type" in result.unstated_target_fields
    assert result.insufficient_data_reason is not None
    assert "states no" in result.insufficient_data_reason
