"""Robust statistics for small comparable groups.

Comparable groups are small (often 8-30 listings) and contain the occasional
mispriced or mis-specified advertisement, so the mean is a poor central measure:
a single outlier moves it noticeably. Everything here is therefore built on
medians.

Outlier detection uses the median absolute deviation (MAD). Compared with the
IQR it stays meaningful on very small groups, and it does not assume a normal
distribution. Removal is capped so the method can never quietly discard most of
the evidence — if a group looks like it is mostly "outliers", that is a signal
about the group, not a licence to delete it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from statistics import median

# Modified z-score above which a listing is treated as an outlier. 3.5 is the
# conventional threshold; it flags clearly detached prices without touching the
# ordinary spread of a healthy market.
OUTLIER_THRESHOLD = 3.5
# Consistency constant that puts MAD on the same scale as a standard deviation.
MAD_SCALE = 0.6745
# Never remove more than this share of a comparable group.
MAX_OUTLIER_SHARE = 0.25


@dataclass
class OutlierResult:
    kept_indexes: list[int] = field(default_factory=list)
    removed_indexes: list[int] = field(default_factory=list)
    method: str = "mad"
    threshold: float = OUTLIER_THRESHOLD
    # Kept for debugging: why each removed value was considered detached.
    removed_scores: dict[int, float] = field(default_factory=dict)


def weighted_median(values: Sequence[float], weights: Sequence[float]) -> float:
    """Median where each value carries a weight.

    The weighted median is the value at which cumulative weight reaches half of
    the total, which makes more similar comparables count for more without
    letting any single listing dominate the way a weighted mean would.
    """
    if not values:
        raise ValueError("weighted_median requires at least one value")
    if len(values) != len(weights):
        raise ValueError("values and weights must have the same length")

    pairs = sorted(zip(values, weights, strict=True), key=lambda pair: pair[0])
    total_weight = sum(weight for _, weight in pairs)
    if total_weight <= 0:
        return float(median(values))

    cumulative = 0.0
    for value, weight in pairs:
        cumulative += weight
        if cumulative >= total_weight / 2:
            return float(value)
    return float(pairs[-1][0])


def median_absolute_deviation(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    center = median(values)
    return float(median([abs(value - center) for value in values]))


def detect_outliers(values: Sequence[float]) -> OutlierResult:
    """Flag detached prices using the modified z-score.

    Groups smaller than four are never trimmed: with so little evidence there is
    no way to tell an outlier from the market.
    """
    indexes = list(range(len(values)))
    if len(values) < 4:
        return OutlierResult(kept_indexes=indexes, method="none")

    center = median(values)
    mad = median_absolute_deviation(values)

    if mad == 0:
        # Identical or near-identical prices: nothing is detached.
        return OutlierResult(kept_indexes=indexes, method="mad-degenerate")

    scores = {index: abs(MAD_SCALE * (value - center) / mad) for index, value in enumerate(values)}
    flagged = sorted(
        (index for index, score in scores.items() if score > OUTLIER_THRESHOLD),
        key=lambda index: scores[index],
        reverse=True,
    )

    max_removable = int(len(values) * MAX_OUTLIER_SHARE)
    removed = set(flagged[:max_removable])

    return OutlierResult(
        kept_indexes=[index for index in indexes if index not in removed],
        removed_indexes=sorted(removed),
        method="mad",
        removed_scores={index: round(scores[index], 3) for index in sorted(removed)},
    )


def percentile(values: Sequence[float], fraction: float) -> float:
    """Linear-interpolation percentile, used for the market spread."""
    if not values:
        raise ValueError("percentile requires at least one value")
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])

    position = fraction * (len(ordered) - 1)
    lower_index = int(position)
    upper_index = min(lower_index + 1, len(ordered) - 1)
    weight = position - lower_index
    return float(ordered[lower_index] * (1 - weight) + ordered[upper_index] * weight)


def relative_dispersion(values: Sequence[float]) -> float:
    """Spread of the group as a share of its median (0 = identical prices).

    Based on the interquartile range rather than the standard deviation so a
    single extreme listing cannot make a tight market look volatile.
    """
    if len(values) < 2:
        return 0.0
    center = median(values)
    if center == 0:
        return 0.0
    spread = percentile(values, 0.75) - percentile(values, 0.25)
    return spread / center
