from datetime import UTC, datetime, timedelta

from echte_auto_waarde.domain.confidence import (
    LOW_CONFIDENCE_THRESHOLD,
    calculate_confidence,
)

NOW = datetime(2026, 6, 1, tzinfo=UTC)


def _strong(**overrides):
    arguments = {
        "comparable_count": 25,
        "average_similarity": 0.9,
        "price_dispersion": 0.05,
        "observation_dates": [NOW - timedelta(days=5)] * 25,
        "missing_field_count": 0,
        "option_data_complete": True,
        "source_quality": 0.9,
        "widening_level": 0,
        "now": NOW,
    }
    arguments.update(overrides)
    return calculate_confidence(**arguments)


def test_strong_evidence_produces_high_confidence() -> None:
    assert _strong().score > 0.85


def test_confidence_is_bounded() -> None:
    assert 0.0 <= _strong().score <= 1.0
    assert 0.0 <= _strong(comparable_count=0, average_similarity=0.0).score <= 1.0


def test_few_comparables_reduce_confidence() -> None:
    assert _strong(comparable_count=3).score < _strong(comparable_count=25).score


def test_weak_similarity_reduces_confidence() -> None:
    assert _strong(average_similarity=0.55).score < _strong(average_similarity=0.9).score


def test_a_widely_dispersed_market_reduces_confidence() -> None:
    assert _strong(price_dispersion=0.4).score < _strong(price_dispersion=0.05).score


def test_stale_observations_reduce_confidence() -> None:
    stale = [NOW - timedelta(days=200)] * 25
    assert _strong(observation_dates=stale).score < _strong().score


def test_missing_vehicle_data_reduces_confidence() -> None:
    assert _strong(missing_field_count=3).score < _strong(missing_field_count=0).score


def test_incomplete_option_data_reduces_confidence() -> None:
    assert _strong(option_data_complete=False).score < _strong(option_data_complete=True).score


def test_synthetic_source_quality_reduces_confidence() -> None:
    assert _strong(source_quality=0.35).score < _strong(source_quality=0.9).score


def test_widening_the_search_reduces_confidence() -> None:
    level_zero = _strong(widening_level=0).score
    level_one = _strong(widening_level=1).score
    level_two = _strong(widening_level=2).score

    assert level_two < level_one < level_zero


def test_thin_evidence_is_flagged_as_low_confidence() -> None:
    result = _strong(
        comparable_count=3,
        average_similarity=0.58,
        price_dispersion=0.35,
        source_quality=0.35,
        widening_level=2,
    )

    assert result.score < LOW_CONFIDENCE_THRESHOLD
    assert result.is_low


def test_factors_explain_the_score() -> None:
    result = _strong(comparable_count=4, average_similarity=0.6)
    codes = {factor["code"] for factor in result.factors}

    assert {
        "comparable_count",
        "average_similarity",
        "price_dispersion",
        "observation_age",
        "data_completeness",
        "source_quality",
    } <= codes

    count_factor = next(f for f in result.factors if f["code"] == "comparable_count")
    assert count_factor["impact"] == "NEGATIVE"
    assert count_factor["comparable_count"] == 4


def test_widening_is_reported_as_its_own_factor() -> None:
    factors = _strong(widening_level=2).factors
    widening = next(f for f in factors if f["code"] == "search_widened")

    assert widening["impact"] == "NEGATIVE"
    assert widening["widening_level"] == 2


def test_confidence_is_deterministic() -> None:
    assert _strong().score == _strong().score
