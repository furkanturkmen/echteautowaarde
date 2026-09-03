import pytest

from echte_auto_waarde.domain.statistics import (
    detect_outliers,
    median_absolute_deviation,
    percentile,
    relative_dispersion,
    weighted_median,
)


def test_weighted_median_with_equal_weights_is_the_median() -> None:
    values = [10.0, 20.0, 30.0, 40.0, 50.0]
    assert weighted_median(values, [1.0] * len(values)) == 30.0


def test_weighted_median_follows_the_heavier_values() -> None:
    values = [10.0, 20.0, 30.0]
    # The most similar comparable (weight 10) pulls the centre towards itself.
    assert weighted_median(values, [1.0, 1.0, 10.0]) == 30.0
    assert weighted_median(values, [10.0, 1.0, 1.0]) == 10.0


def test_weighted_median_rejects_mismatched_input() -> None:
    with pytest.raises(ValueError):
        weighted_median([1.0, 2.0], [1.0])
    with pytest.raises(ValueError):
        weighted_median([], [])


def test_outlier_detection_removes_a_clearly_detached_price() -> None:
    prices = [25_000.0, 25_500.0, 26_000.0, 26_500.0, 27_000.0, 120_000.0]
    result = detect_outliers(prices)

    assert result.removed_indexes == [5]
    assert len(result.kept_indexes) == 5
    assert result.method == "mad"
    assert result.removed_scores[5] > 3.5


def test_outlier_detection_leaves_a_normal_spread_alone() -> None:
    prices = [24_000.0, 25_000.0, 26_000.0, 27_000.0, 28_000.0, 29_000.0]
    result = detect_outliers(prices)

    assert result.removed_indexes == []


def test_outlier_detection_never_removes_most_of_the_group() -> None:
    # Two tight clusters far apart: the method must not delete an entire half.
    prices = [10_000.0, 10_100.0, 10_200.0, 90_000.0, 91_000.0, 92_000.0]
    result = detect_outliers(prices)

    assert len(result.kept_indexes) >= len(prices) * 0.75


def test_tiny_groups_are_never_trimmed() -> None:
    prices = [20_000.0, 21_000.0, 95_000.0]
    result = detect_outliers(prices)

    assert result.removed_indexes == []
    assert result.method == "none"


def test_identical_prices_are_not_treated_as_outliers() -> None:
    prices = [25_000.0] * 6
    result = detect_outliers(prices)

    assert result.removed_indexes == []
    assert result.method == "mad-degenerate"


def test_median_absolute_deviation() -> None:
    assert median_absolute_deviation([10.0, 12.0, 14.0, 16.0, 18.0]) == 2.0
    assert median_absolute_deviation([]) == 0.0


def test_percentile_interpolates() -> None:
    values = [10.0, 20.0, 30.0, 40.0]
    assert percentile(values, 0.0) == 10.0
    assert percentile(values, 1.0) == 40.0
    assert percentile(values, 0.5) == 25.0


def test_relative_dispersion_reflects_market_spread() -> None:
    tight = [25_000.0, 25_200.0, 25_400.0, 25_600.0]
    wide = [15_000.0, 22_000.0, 30_000.0, 40_000.0]

    assert relative_dispersion(tight) < relative_dispersion(wide)
    assert relative_dispersion([25_000.0]) == 0.0
