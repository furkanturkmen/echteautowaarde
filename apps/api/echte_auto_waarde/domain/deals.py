"""Deal classification.

The domain layer owns this decision. Thresholds live here and nowhere else — the
frontend only maps a returned code to its Dutch consumer label, so backend and
frontend can never disagree about what counts as a good deal.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class DealClassification(StrEnum):
    EXCELLENT_DEAL = "EXCELLENT_DEAL"
    GOOD_DEAL = "GOOD_DEAL"
    FAIR_PRICE = "FAIR_PRICE"
    EXPENSIVE = "EXPENSIVE"
    VERY_EXPENSIVE = "VERY_EXPENSIVE"


@dataclass(frozen=True)
class DealThresholds:
    """Upper bounds on asking price / estimated market value.

    The band around 1.0 is deliberately wide: comparable asking prices carry
    real spread, so small deviations are normal market noise rather than a
    signal worth flagging to a consumer.
    """

    excellent_deal_max_ratio: float = 0.92
    good_deal_max_ratio: float = 0.97
    fair_price_max_ratio: float = 1.04
    expensive_max_ratio: float = 1.12


DEFAULT_DEAL_THRESHOLDS = DealThresholds()


def classify_deal(
    asking_price_cents: int,
    estimated_market_value_cents: int,
    thresholds: DealThresholds = DEFAULT_DEAL_THRESHOLDS,
) -> DealClassification:
    """Classify an asking price against the estimated market value."""
    if estimated_market_value_cents <= 0:
        raise ValueError("estimated market value must be positive to classify a deal")

    ratio = asking_price_cents / estimated_market_value_cents

    if ratio <= thresholds.excellent_deal_max_ratio:
        return DealClassification.EXCELLENT_DEAL
    if ratio <= thresholds.good_deal_max_ratio:
        return DealClassification.GOOD_DEAL
    if ratio <= thresholds.fair_price_max_ratio:
        return DealClassification.FAIR_PRICE
    if ratio <= thresholds.expensive_max_ratio:
        return DealClassification.EXPENSIVE
    return DealClassification.VERY_EXPENSIVE
