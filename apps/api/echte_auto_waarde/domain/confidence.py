"""Confidence scoring.

Confidence is a measurement of the evidence, not an opinion about the car and
certainly not something a model invents. It combines factors that can each be
computed and explained:

| Factor            | Weight | Rationale                                        |
|-------------------|--------|--------------------------------------------------|
| comparable count  | 0.30   | More evidence is the single strongest signal      |
| average similarity| 0.25   | Loosely matching cars support a weaker conclusion |
| price dispersion  | 0.20   | A tight market pins a value down; a wide one does not |
| observation age   | 0.10   | Stale asking prices describe a past market        |
| data completeness | 0.10   | Unknown specification or options weaken the match |
| source quality    | 0.05   | Synthetic data cannot support high confidence     |

The result is then reduced when the comparable engine had to widen its filters,
because a widened search means the strict evidence was not there.

Each factor also produces a human-readable entry so the interface and the AI can
say *why* confidence is what it is.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

# Enough comparables that more listings stop meaningfully improving certainty.
STRONG_COMPARABLE_COUNT = 20
# Similarity at or below this contributes nothing: barely-comparable cars.
SIMILARITY_FLOOR = 0.5
# Relative IQR at or above this is treated as a fully dispersed market.
DISPERSION_CEILING = 0.30
# Observations older than this are treated as stale evidence.
FRESHNESS_HORIZON_DAYS = 60
# Each widening level costs this much confidence, multiplicatively.
WIDENING_PENALTY_PER_LEVEL = 0.12

WEIGHTS: dict[str, float] = {
    "comparable_count": 0.30,
    "average_similarity": 0.25,
    "price_dispersion": 0.20,
    "observation_age": 0.10,
    "data_completeness": 0.10,
    "source_quality": 0.05,
}

# Below this, the interface should tell the user the estimate is weakly supported.
LOW_CONFIDENCE_THRESHOLD = 0.55


@dataclass
class ConfidenceResult:
    score: float
    factors: list[dict[str, Any]] = field(default_factory=list)

    @property
    def is_low(self) -> bool:
        return self.score < LOW_CONFIDENCE_THRESHOLD


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _factor(code: str, value: float, positive: bool, detail: dict[str, Any]) -> dict[str, Any]:
    return {
        "code": code,
        "impact": "POSITIVE" if positive else "NEGATIVE",
        "score": round(value, 3),
        "weight": WEIGHTS.get(code, 0.0),
        **detail,
    }


def calculate_confidence(
    comparable_count: int,
    average_similarity: float,
    price_dispersion: float,
    observation_dates: list[datetime] | None = None,
    missing_field_count: int = 0,
    total_field_count: int = 5,
    option_data_complete: bool = True,
    source_quality: float = 0.5,
    widening_level: int = 0,
    now: datetime | None = None,
) -> ConfidenceResult:
    """Compute a confidence score in 0..1 with structured factors."""
    now = now or datetime.now(UTC)
    factors: list[dict[str, Any]] = []

    count_score = _clamp(comparable_count / STRONG_COMPARABLE_COUNT)
    factors.append(
        _factor(
            "comparable_count",
            count_score,
            positive=comparable_count >= STRONG_COMPARABLE_COUNT / 2,
            detail={"comparable_count": comparable_count},
        )
    )

    similarity_score = _clamp((average_similarity - SIMILARITY_FLOOR) / (1 - SIMILARITY_FLOOR))
    factors.append(
        _factor(
            "average_similarity",
            similarity_score,
            positive=average_similarity >= 0.75,
            detail={"average_similarity": round(average_similarity, 3)},
        )
    )

    dispersion_score = _clamp(1 - price_dispersion / DISPERSION_CEILING)
    factors.append(
        _factor(
            "price_dispersion",
            dispersion_score,
            positive=price_dispersion <= DISPERSION_CEILING / 2,
            detail={"relative_dispersion": round(price_dispersion, 3)},
        )
    )

    if observation_dates:
        ages = [max((now - _as_utc(observed)).days, 0) for observed in observation_dates]
        fresh = sum(1 for age in ages if age <= FRESHNESS_HORIZON_DAYS)
        freshness_score = fresh / len(ages)
        median_age = sorted(ages)[len(ages) // 2]
    else:
        freshness_score = 0.5
        median_age = None
    factors.append(
        _factor(
            "observation_age",
            freshness_score,
            positive=freshness_score >= 0.7,
            detail={"median_observation_age_days": median_age},
        )
    )

    completeness_score = _clamp(1 - missing_field_count / max(total_field_count, 1))
    if not option_data_complete:
        completeness_score *= 0.8
    factors.append(
        _factor(
            "data_completeness",
            completeness_score,
            positive=missing_field_count == 0 and option_data_complete,
            detail={
                "missing_field_count": missing_field_count,
                "option_data_complete": option_data_complete,
            },
        )
    )

    quality_score = _clamp(source_quality)
    factors.append(
        _factor(
            "source_quality",
            quality_score,
            positive=source_quality >= 0.7,
            detail={"source_quality": round(source_quality, 3)},
        )
    )

    weighted = sum(WEIGHTS[factor["code"]] * factor["score"] for factor in factors)
    score = _clamp(weighted * (1 - WIDENING_PENALTY_PER_LEVEL) ** widening_level)

    if widening_level > 0:
        factors.append(
            {
                "code": "search_widened",
                "impact": "NEGATIVE",
                "score": round((1 - WIDENING_PENALTY_PER_LEVEL) ** widening_level, 3),
                "weight": 0.0,
                "widening_level": widening_level,
            }
        )

    return ConfidenceResult(score=round(score, 3), factors=factors)


def _as_utc(value: datetime) -> datetime:
    """SQLite returns naive datetimes; treat those as the UTC they were written as."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
