"""The deterministic valuation engine.

Pipeline:

    comparables -> outlier removal -> similarity-weighted market basis
    -> transparent adjustments -> estimated market value
    -> recommended purchase range -> confidence -> deal classification

Every euro of difference between the market basis and the final estimate is
accounted for by a structured adjustment carrying its own reason. No step
consults a language model, and no number is invented: if the evidence is too
thin, the engine says so instead of producing a confident-looking figure.

All amounts are EUR cents.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from statistics import mean, median
from typing import Any

from echte_auto_waarde.domain.comparables import ComparableSelection, ScoredComparable
from echte_auto_waarde.domain.confidence import ConfidenceResult, calculate_confidence
from echte_auto_waarde.domain.deals import (
    DEFAULT_DEAL_THRESHOLDS,
    DealClassification,
    DealThresholds,
    classify_deal,
)
from echte_auto_waarde.domain.fingerprint import VehicleFingerprint
from echte_auto_waarde.domain.options import OPTIONS_BY_KEY
from echte_auto_waarde.domain.statistics import (
    detect_outliers,
    percentile,
    relative_dispersion,
    weighted_median,
)

ALGORITHM_VERSION = "valuation-v0.1"

# Appearance/equipment packages that carry real used-market value.
PACKAGE_TRIMS = frozenset({"M Sport", "AMG Line", "S line", "R-Line", "GTE"})


@dataclass(frozen=True)
class ValuationConfig:
    """Every tunable number in the valuation, in one place.

    The adjustment constants are deliberately conservative. Comparable prices
    already contain most of the effect of age and equipment, so adjustments only
    correct for how this particular car differs from its comparable group. Each
    one is capped, because a large correction on thin evidence is a worse answer
    than a smaller one.
    """

    minimum_comparables: int = 3

    # Effect of one kilometre of difference from the group median. Around 6 cents
    # per km for a mainstream Dutch used car; deliberately flat for now, and a
    # documented assumption rather than a measured figure.
    mileage_cents_per_km: int = 6
    # A mileage correction may never move the value more than this share.
    mileage_adjustment_cap_ratio: float = 0.15

    # Share of value one model year is worth. Comparable prices already reflect
    # depreciation, so this only corrects the residual difference in age.
    year_value_ratio: float = 0.025
    year_adjustment_cap_ratio: float = 0.10

    # Used-market value of an option at importance 1.0. Well below what the
    # option cost new: used buyers pay for equipment, but not retail prices.
    option_value_scale_cents: int = 60_000
    option_adjustment_cap_ratio: float = 0.08

    # Used-market value of a full appearance package versus a base trim.
    package_trim_value_cents: int = 80_000

    # The recommended purchase range sits below the estimated market value: it
    # answers "what should I try to pay", not "what is it listed for". The range
    # reflects the negotiation room typical of Dutch asking prices.
    buy_range_low_ratio: float = 0.94
    buy_range_high_ratio: float = 0.98

    deal_thresholds: DealThresholds = DEFAULT_DEAL_THRESHOLDS


DEFAULT_CONFIG = ValuationConfig()


@dataclass
class Adjustment:
    type: str
    amount_cents: int
    reason: str
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "amountCents": self.amount_cents,
            "reason": self.reason,
            **({"detail": self.detail} if self.detail else {}),
        }


@dataclass
class MarketStatistics:
    comparable_count: int
    min_price_cents: int
    max_price_cents: int
    median_price_cents: int
    weighted_median_price_cents: int
    p25_price_cents: int
    p75_price_cents: int
    relative_dispersion: float
    average_mileage_km: int | None
    average_year: float | None
    average_similarity: float
    min_similarity: float
    max_similarity: float
    outliers_removed: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "comparableCount": self.comparable_count,
            "minPriceCents": self.min_price_cents,
            "maxPriceCents": self.max_price_cents,
            "medianPriceCents": self.median_price_cents,
            "weightedMedianPriceCents": self.weighted_median_price_cents,
            "p25PriceCents": self.p25_price_cents,
            "p75PriceCents": self.p75_price_cents,
            "relativeDispersion": round(self.relative_dispersion, 4),
            "averageMileageKm": self.average_mileage_km,
            "averageYear": self.average_year,
            "averageSimilarity": round(self.average_similarity, 4),
            "minSimilarity": round(self.min_similarity, 4),
            "maxSimilarity": round(self.max_similarity, 4),
            "outliersRemoved": self.outliers_removed,
        }


@dataclass
class ValuationResult:
    """A complete valuation, or a documented refusal to produce one."""

    sufficient_data: bool
    algorithm_version: str = ALGORITHM_VERSION
    estimated_market_value_cents: int | None = None
    recommended_buy_price_low_cents: int | None = None
    recommended_buy_price_high_cents: int | None = None
    market_basis_cents: int | None = None
    asking_price_cents: int | None = None
    deal_classification: DealClassification | None = None
    confidence: ConfidenceResult | None = None
    statistics: MarketStatistics | None = None
    adjustments: list[Adjustment] = field(default_factory=list)
    comparables: list[ScoredComparable] = field(default_factory=list)
    removed_outlier_listing_ids: list[int] = field(default_factory=list)
    widening_level: int = 0
    insufficient_data_reason: str | None = None


def _cap(amount: int, basis: int, ratio: float) -> int:
    limit = int(abs(basis) * ratio)
    return max(-limit, min(limit, amount))


def _option_importance_sum(option_keys: frozenset[str]) -> float:
    return sum(OPTIONS_BY_KEY[key].importance for key in option_keys if key in OPTIONS_BY_KEY)


def value_vehicle(
    target: VehicleFingerprint,
    selection: ComparableSelection,
    asking_price_cents: int | None = None,
    config: ValuationConfig = DEFAULT_CONFIG,
    source_quality: float = 0.5,
    option_data_complete: bool = True,
    now: datetime | None = None,
) -> ValuationResult:
    """Produce a valuation from a set of scored comparables."""
    comparables = selection.comparables

    if len(comparables) < config.minimum_comparables:
        return ValuationResult(
            sufficient_data=False,
            asking_price_cents=asking_price_cents,
            widening_level=selection.widening_level,
            comparables=comparables,
            insufficient_data_reason=(
                f"Only {len(comparables)} comparable listings met the similarity threshold; "
                f"at least {config.minimum_comparables} are required for a valuation."
            ),
        )

    prices = [float(item.asking_price_cents) for item in comparables]
    outliers = detect_outliers(prices)
    kept = [comparables[index] for index in outliers.kept_indexes]
    removed_ids = [comparables[index].candidate.listing_id for index in outliers.removed_indexes]

    kept_prices = [float(item.asking_price_cents) for item in kept]
    weights = [max(item.score, 0.01) for item in kept]

    market_basis = int(round(weighted_median(kept_prices, weights)))

    adjustments = _build_adjustments(target, kept, market_basis, config)
    estimated = market_basis + sum(adjustment.amount_cents for adjustment in adjustments)
    # Round to whole euros: cent-level precision would imply accuracy the
    # evidence does not support.
    estimated = int(round(estimated / 100) * 100)

    statistics = _build_statistics(kept, kept_prices, weights, len(outliers.removed_indexes))

    observation_dates = [
        item.candidate.last_seen_at for item in kept if item.candidate.last_seen_at
    ]
    missing_fields = target.missing_fields()
    confidence = calculate_confidence(
        comparable_count=len(kept),
        average_similarity=statistics.average_similarity,
        price_dispersion=statistics.relative_dispersion,
        observation_dates=observation_dates,
        missing_field_count=len(missing_fields),
        total_field_count=len(VehicleFingerprint.REQUIRED_FOR_CONFIDENCE),
        option_data_complete=option_data_complete,
        source_quality=source_quality,
        widening_level=selection.widening_level,
        now=now,
    )

    buy_low = int(round(estimated * config.buy_range_low_ratio / 100) * 100)
    buy_high = int(round(estimated * config.buy_range_high_ratio / 100) * 100)

    deal = (
        classify_deal(asking_price_cents, estimated, config.deal_thresholds)
        if asking_price_cents
        else None
    )

    return ValuationResult(
        sufficient_data=True,
        estimated_market_value_cents=estimated,
        recommended_buy_price_low_cents=buy_low,
        recommended_buy_price_high_cents=buy_high,
        market_basis_cents=market_basis,
        asking_price_cents=asking_price_cents,
        deal_classification=deal,
        confidence=confidence,
        statistics=statistics,
        adjustments=adjustments,
        comparables=kept,
        removed_outlier_listing_ids=removed_ids,
        widening_level=selection.widening_level,
    )


def _build_adjustments(
    target: VehicleFingerprint,
    kept: list[ScoredComparable],
    market_basis: int,
    config: ValuationConfig,
) -> list[Adjustment]:
    """Correct the market basis for how the target differs from its group."""
    adjustments: list[Adjustment] = []

    # --- Mileage ---
    mileages = [
        item.candidate.fingerprint.mileage_km
        for item in kept
        if item.candidate.fingerprint.mileage_km is not None
    ]
    if target.mileage_km is not None and mileages:
        median_mileage = int(median(mileages))
        delta_km = target.mileage_km - median_mileage
        if abs(delta_km) >= 1_000:
            amount = _cap(
                -delta_km * config.mileage_cents_per_km,
                market_basis,
                config.mileage_adjustment_cap_ratio,
            )
            direction = "more" if delta_km > 0 else "fewer"
            adjustments.append(
                Adjustment(
                    type="MILEAGE",
                    amount_cents=amount,
                    reason=(
                        f"Vehicle has approximately {abs(delta_km):,} km {direction} than the "
                        f"comparable group median of {median_mileage:,} km."
                    ),
                    detail={
                        "targetMileageKm": target.mileage_km,
                        "comparableMedianMileageKm": median_mileage,
                        "deltaKm": delta_km,
                    },
                )
            )

    # --- Age ---
    years = [
        item.candidate.fingerprint.year
        for item in kept
        if item.candidate.fingerprint.year is not None
    ]
    if target.year is not None and years:
        median_year = median(years)
        delta_years = target.year - median_year
        if abs(delta_years) >= 0.5:
            amount = _cap(
                int(market_basis * config.year_value_ratio * delta_years),
                market_basis,
                config.year_adjustment_cap_ratio,
            )
            direction = "newer" if delta_years > 0 else "older"
            adjustments.append(
                Adjustment(
                    type="AGE",
                    amount_cents=amount,
                    reason=(
                        f"Vehicle is {abs(delta_years):.1f} model years {direction} than the "
                        f"comparable group median of {median_year:.0f}."
                    ),
                    detail={
                        "targetYear": target.year,
                        "comparableMedianYear": median_year,
                        "deltaYears": delta_years,
                    },
                )
            )

    # --- Options ---
    group_importance = [
        _option_importance_sum(item.candidate.fingerprint.option_keys) for item in kept
    ]
    if group_importance:
        target_importance = _option_importance_sum(target.option_keys)
        median_importance = median(group_importance)
        delta_importance = target_importance - median_importance
        if abs(delta_importance) >= 0.1:
            amount = _cap(
                int(delta_importance * config.option_value_scale_cents),
                market_basis,
                config.option_adjustment_cap_ratio,
            )
            direction = "better" if delta_importance > 0 else "less well"
            adjustments.append(
                Adjustment(
                    type="OPTIONS",
                    amount_cents=amount,
                    reason=(
                        f"Vehicle is {direction} equipped than the comparable group; option "
                        f"importance differs by {delta_importance:+.2f}."
                    ),
                    detail={
                        "targetOptionImportance": round(target_importance, 2),
                        "comparableMedianOptionImportance": round(median_importance, 2),
                        "targetOptions": sorted(target.option_keys),
                    },
                )
            )

    # --- Trim / package ---
    target_has_package = bool(target.trim and target.trim in PACKAGE_TRIMS)
    group_package_share = mean(
        [1.0 if (item.candidate.fingerprint.trim or "") in PACKAGE_TRIMS else 0.0 for item in kept]
    )
    if target_has_package and group_package_share < 0.95:
        amount = int(config.package_trim_value_cents * (1 - group_package_share))
        adjustments.append(
            Adjustment(
                type="TRIM",
                amount_cents=amount,
                reason=(
                    f"Vehicle has the {target.trim} package, which only "
                    f"{group_package_share:.0%} of the comparable group has."
                ),
                detail={"trim": target.trim, "comparableShareWithPackage": group_package_share},
            )
        )
    elif not target_has_package and group_package_share > 0.05:
        amount = -int(config.package_trim_value_cents * group_package_share)
        adjustments.append(
            Adjustment(
                type="TRIM",
                amount_cents=amount,
                reason=(
                    f"{group_package_share:.0%} of the comparable group has a sport/appearance "
                    "package that this vehicle does not have."
                ),
                detail={"trim": target.trim, "comparableShareWithPackage": group_package_share},
            )
        )

    return adjustments


def _build_statistics(
    kept: list[ScoredComparable],
    prices: list[float],
    weights: list[float],
    outliers_removed: int,
) -> MarketStatistics:
    similarities = [item.score for item in kept]
    mileages = [
        item.candidate.fingerprint.mileage_km
        for item in kept
        if item.candidate.fingerprint.mileage_km is not None
    ]
    years = [
        item.candidate.fingerprint.year
        for item in kept
        if item.candidate.fingerprint.year is not None
    ]

    return MarketStatistics(
        comparable_count=len(kept),
        min_price_cents=int(min(prices)),
        max_price_cents=int(max(prices)),
        median_price_cents=int(median(prices)),
        weighted_median_price_cents=int(round(weighted_median(prices, weights))),
        p25_price_cents=int(percentile(prices, 0.25)),
        p75_price_cents=int(percentile(prices, 0.75)),
        relative_dispersion=relative_dispersion(prices),
        average_mileage_km=int(mean(mileages)) if mileages else None,
        average_year=round(mean(years), 1) if years else None,
        average_similarity=mean(similarities),
        min_similarity=min(similarities),
        max_similarity=max(similarities),
        outliers_removed=outliers_removed,
    )
