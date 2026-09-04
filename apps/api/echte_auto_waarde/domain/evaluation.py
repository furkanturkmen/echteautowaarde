"""Measuring how a valuation sits relative to observed asking prices.

**This is not accuracy.** An asking price is what somebody was asking, not what
a car sold for and not what it was worth. A dealer's optimistic price and a
private seller's quick-sale price are both legitimate observations, and an
estimate that differs from either is not thereby wrong.

So everything here is deliberately called *deviation from the observed asking
price*. It measures whether the valuation is consistent with the market it was
given — a valuation that sits far from most asking prices deserves a look, and
one that tracks them closely is at least coherent. Neither is a claim about
truth, and no number here should ever be presented as one.

Pure functions: no database, no valuation logic, nothing to keep in sync with
the engine it measures.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from statistics import fmean, median

# Below this a group's statistics say more about the sample than the market.
MIN_SEGMENT_SIZE = 5

# How many of the largest deviations to surface for engineering diagnosis.
DEFAULT_OUTLIER_COUNT = 10


@dataclass(frozen=True)
class ListingEvaluation:
    """One listing valued against every other listing but itself."""

    listing_id: int
    external_reference: str
    source_key: str
    scope: str | None
    make: str
    model: str
    year: int | None
    mileage_km: int | None
    trim: str | None
    fuel_type: str
    transmission: str
    body_type: str

    observed_asking_price_cents: int
    estimated_market_value_cents: int | None
    sufficient_data: bool

    comparable_count: int = 0
    widening_level: int = 0
    confidence_score: float | None = None
    mean_similarity: float | None = None
    comparable_references: tuple[str, ...] = ()
    adjustments: tuple[tuple[str, int], ...] = ()
    insufficient_data_reason: str | None = None

    @property
    def deviation_cents(self) -> int | None:
        """Estimate minus observed asking price. Positive: estimated higher."""
        if self.estimated_market_value_cents is None:
            return None
        return self.estimated_market_value_cents - self.observed_asking_price_cents

    @property
    def deviation_ratio(self) -> float | None:
        """The same difference relative to the observed asking price."""
        deviation = self.deviation_cents
        if deviation is None or self.observed_asking_price_cents <= 0:
            return None
        return deviation / self.observed_asking_price_cents


@dataclass(frozen=True)
class DeviationMetrics:
    """Descriptive statistics over a set of evaluations.

    Every name says "deviation from the observed asking price" because that is
    what was measured. None of these is an error rate.
    """

    evaluated_count: int
    insufficient_evidence_count: int
    median_absolute_deviation_cents: int | None = None
    median_absolute_deviation_ratio: float | None = None
    p75_absolute_deviation_ratio: float | None = None
    p90_absolute_deviation_ratio: float | None = None
    mean_signed_deviation_ratio: float | None = None
    share_estimated_above_ask: float | None = None
    share_estimated_below_ask: float | None = None


def percentile(values: Sequence[float], fraction: float) -> float | None:
    """Linear-interpolated percentile over a sorted copy of `values`.

    Written out rather than imported so the behaviour on the small samples this
    framework will actually see is explicit and testable.
    """
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]

    position = (len(ordered) - 1) * max(0.0, min(1.0, fraction))
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def summarise(evaluations: Sequence[ListingEvaluation]) -> DeviationMetrics:
    """Describe how a set of valuations sat relative to their asking prices."""
    valued = [item for item in evaluations if item.deviation_ratio is not None]
    insufficient = sum(1 for item in evaluations if not item.sufficient_data)

    if not valued:
        return DeviationMetrics(
            evaluated_count=len(evaluations), insufficient_evidence_count=insufficient
        )

    signed_ratios = [item.deviation_ratio for item in valued if item.deviation_ratio is not None]
    absolute_ratios = [abs(ratio) for ratio in signed_ratios]
    absolute_cents = [
        abs(item.deviation_cents) for item in valued if item.deviation_cents is not None
    ]

    above = sum(1 for ratio in signed_ratios if ratio > 0)
    below = sum(1 for ratio in signed_ratios if ratio < 0)

    return DeviationMetrics(
        evaluated_count=len(evaluations),
        insufficient_evidence_count=insufficient,
        median_absolute_deviation_cents=int(median(absolute_cents)),
        median_absolute_deviation_ratio=median(absolute_ratios),
        p75_absolute_deviation_ratio=percentile(absolute_ratios, 0.75),
        p90_absolute_deviation_ratio=percentile(absolute_ratios, 0.90),
        mean_signed_deviation_ratio=fmean(signed_ratios),
        share_estimated_above_ask=above / len(signed_ratios),
        share_estimated_below_ask=below / len(signed_ratios),
    )


@dataclass(frozen=True)
class Segment:
    """One group of evaluations, large enough to say something about."""

    label: str
    metrics: DeviationMetrics


def segment_by(
    evaluations: Sequence[ListingEvaluation],
    key: Callable[[ListingEvaluation], str | None],
    minimum_size: int = MIN_SEGMENT_SIZE,
) -> list[Segment]:
    """Group evaluations and summarise every group that is big enough.

    Groups below `minimum_size` are dropped rather than reported: a median over
    two listings is noise wearing a statistic's clothes.
    """
    groups: dict[str, list[ListingEvaluation]] = {}
    for item in evaluations:
        label = key(item)
        if label is None:
            continue
        groups.setdefault(label, []).append(item)

    return [
        Segment(label=label, metrics=summarise(members))
        for label, members in sorted(groups.items())
        if len(members) >= minimum_size
    ]


# -- Standard groupings -------------------------------------------------------


def mileage_band(evaluation: ListingEvaluation) -> str | None:
    if evaluation.mileage_km is None:
        return None
    step = 50_000
    lower = (evaluation.mileage_km // step) * step
    return f"{lower // 1000}-{(lower + step) // 1000}k km"


def comparable_count_band(evaluation: ListingEvaluation) -> str:
    count = evaluation.comparable_count
    if count <= 3:
        return "1-3 comparables"
    if count <= 7:
        return "4-7 comparables"
    if count <= 15:
        return "8-15 comparables"
    return "16+ comparables"


def _band(value: float | None, edges: Sequence[float], labels: Sequence[str]) -> str | None:
    if value is None:
        return None
    for edge, label in zip(edges, labels, strict=True):
        if value < edge:
            return label
    return labels[-1]


def confidence_band(evaluation: ListingEvaluation) -> str | None:
    return _band(
        evaluation.confidence_score,
        (0.4, 0.6, 0.8, 1.01),
        ("confidence <40%", "confidence 40-60%", "confidence 60-80%", "confidence 80%+"),
    )


def similarity_band(evaluation: ListingEvaluation) -> str | None:
    return _band(
        evaluation.mean_similarity,
        (0.6, 0.75, 0.9, 1.01),
        ("similarity <60%", "similarity 60-75%", "similarity 75-90%", "similarity 90%+"),
    )


STANDARD_SEGMENTS: dict[str, Callable[[ListingEvaluation], str | None]] = {
    "model": lambda item: f"{item.make} {item.model}",
    "model_year": lambda item: str(item.year) if item.year else None,
    "mileage_band": mileage_band,
    "transmission": lambda item: item.transmission,
    "fuel": lambda item: item.fuel_type,
    "body_type": lambda item: item.body_type,
    "trim": lambda item: item.trim,
    "comparable_count": comparable_count_band,
    "similarity": similarity_band,
    "confidence": confidence_band,
}


def largest_deviations(
    evaluations: Sequence[ListingEvaluation], limit: int = DEFAULT_OUTLIER_COUNT
) -> list[ListingEvaluation]:
    """The widest deviations, for engineering diagnosis.

    Nothing is excluded from the metrics because of this: an outlier is
    something to understand, not something to hide. Ordering is deterministic,
    with the listing id breaking ties.
    """
    valued = [item for item in evaluations if item.deviation_ratio is not None]
    return sorted(
        valued,
        key=lambda item: (-abs(item.deviation_ratio or 0.0), item.listing_id),
    )[:limit]


@dataclass(frozen=True)
class EvaluationReport:
    """Everything one evaluation run found. Never persisted as a valuation."""

    dataset: str
    listing_count: int
    overall: DeviationMetrics
    segments: dict[str, list[Segment]] = field(default_factory=dict)
    outliers: list[ListingEvaluation] = field(default_factory=list)
    minimum_segment_size: int = MIN_SEGMENT_SIZE

    @property
    def confidence_is_directionally_sound(self) -> bool | None:
        """Whether higher confidence went with tighter asking-price deviation.

        A weak signal on purpose: it compares the lowest and highest confidence
        bands that have enough members, and says nothing when the data cannot
        support even that. It is a prompt to investigate, never a calibration.
        """
        bands = [
            segment
            for segment in self.segments.get("confidence", [])
            if segment.metrics.median_absolute_deviation_ratio is not None
        ]
        if len(bands) < 2:
            return None
        lowest, highest = bands[0], bands[-1]
        assert lowest.metrics.median_absolute_deviation_ratio is not None
        assert highest.metrics.median_absolute_deviation_ratio is not None
        return (
            highest.metrics.median_absolute_deviation_ratio
            <= lowest.metrics.median_absolute_deviation_ratio
        )
