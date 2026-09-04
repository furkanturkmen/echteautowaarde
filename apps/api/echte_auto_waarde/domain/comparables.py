"""Comparable candidate selection.

Hard filters first, then scoring — and when strict filters would leave too few
comparables, the engine widens in explicit documented levels rather than quietly
accepting anything. The level actually used travels with the result, because
widening is exactly the kind of thing a consumer deserves to be told about (and
it lowers confidence).

Nothing here touches the database: the service layer loads candidates, the
domain decides which ones count.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime

from echte_auto_waarde.domain.fingerprint import VehicleFingerprint
from echte_auto_waarde.domain.similarity import (
    DEFAULT_WEIGHTS,
    SimilarityBreakdown,
    SimilarityWeights,
    score_similarity,
)
from echte_auto_waarde.models.enums import FuelType, SellerType, Transmission

# Widening levels, from strictest to broadest.
WIDENING_LEVELS: tuple[tuple[int, str], ...] = (
    (0, "same model, generation, powertrain and transmission, within 3 model years"),
    (1, "same model and generation, related powertrain, within 4 model years"),
    (2, "same model, any generation, within 5 model years"),
)
MAX_WIDENING_LEVEL = WIDENING_LEVELS[-1][0]


@dataclass(frozen=True)
class ComparableCriteria:
    """What counts as a usable comparable.

    `required_option_keys` and the `require_*` flags exist so a user can later
    say what matters to them ("must have a tow bar", "transmission must match")
    without the engine being redesigned.
    """

    # Raised from 0.55 when similarity stopped scoring unstated
    # characteristics as half matches: the old cutoff sat mid-range on a
    # compressed scale, and on the repaired one it admitted cars sharing
    # little more than a body type. Measured by leave-one-out on both
    # datasets, 0.65 lowered deviation at every percentile while still
    # producing a valuation for all but one car in each. See
    # docs/valuation.md.
    min_similarity: float = 0.65
    min_comparables: int = 8
    max_comparables: int = 40
    max_year_gap: int = 5
    weights: SimilarityWeights = DEFAULT_WEIGHTS
    required_option_keys: frozenset[str] = frozenset()
    require_same_transmission: bool = False
    require_same_engine: bool = False


DEFAULT_CRITERIA = ComparableCriteria()


@dataclass(frozen=True)
class ComparableCandidate:
    """One market listing considered as evidence."""

    listing_id: int
    fingerprint: VehicleFingerprint
    asking_price_cents: int
    last_seen_at: datetime | None = None
    seller_type: SellerType | None = None
    source_quality: float = 0.5


@dataclass
class ScoredComparable:
    candidate: ComparableCandidate
    similarity: SimilarityBreakdown

    @property
    def score(self) -> float:
        return self.similarity.score

    @property
    def asking_price_cents(self) -> int:
        return self.candidate.asking_price_cents


@dataclass
class ComparableSelection:
    comparables: list[ScoredComparable] = field(default_factory=list)
    widening_level: int = 0
    widening_description: str = WIDENING_LEVELS[0][1]
    candidates_considered: int = 0
    rejected_below_threshold: int = 0
    rejected_by_requirements: int = 0

    @property
    def count(self) -> int:
        return len(self.comparables)


def _fuel_is_related(target: FuelType, candidate: FuelType) -> bool:
    """Powertrains close enough to compare when the strict level found too few."""
    if target is candidate:
        return True
    related = {
        frozenset({FuelType.HYBRID, FuelType.PLUGIN_HYBRID}),
        frozenset({FuelType.PETROL, FuelType.HYBRID}),
        frozenset({FuelType.PETROL, FuelType.LPG}),
    }
    return frozenset({target, candidate}) in related


def passes_filters(
    target: VehicleFingerprint,
    candidate: VehicleFingerprint,
    level: int,
    criteria: ComparableCriteria,
) -> bool:
    """Hard filters for one widening level."""
    if target.model_line != candidate.model_line:
        return False

    if criteria.require_same_engine and target.engine_description != candidate.engine_description:
        return False
    if criteria.require_same_transmission and target.transmission is not candidate.transmission:
        return False
    if criteria.required_option_keys - candidate.option_keys:
        return False

    year_gap = (
        abs((target.year or 0) - (candidate.year or 0)) if target.year and candidate.year else 0
    )

    if level == 0:
        if target.generation and candidate.generation and target.generation != candidate.generation:
            return False
        if target.fuel_type is not candidate.fuel_type:
            return False
        if (
            Transmission.UNKNOWN not in (target.transmission, candidate.transmission)
            and target.transmission is not candidate.transmission
        ):
            return False
        return year_gap <= 3

    if level == 1:
        if target.generation and candidate.generation and target.generation != candidate.generation:
            return False
        if not _fuel_is_related(target.fuel_type, candidate.fuel_type):
            return False
        return year_gap <= 4

    return year_gap <= criteria.max_year_gap


def select_comparables(
    target: VehicleFingerprint,
    candidates: Sequence[ComparableCandidate],
    criteria: ComparableCriteria = DEFAULT_CRITERIA,
) -> ComparableSelection:
    """Select comparables, widening only as far as necessary.

    The first level that yields enough comparables wins. If no level does, the
    attempt with the most evidence is returned (ties go to the stricter level),
    and when nothing matched anywhere the broadest attempt is returned so its
    rejection counts can explain why the search came up empty.
    """
    attempts: list[ComparableSelection] = []

    for level, description in WIDENING_LEVELS:
        scored: list[ScoredComparable] = []
        rejected_below_threshold = 0
        rejected_by_requirements = 0

        for candidate in candidates:
            if not passes_filters(target, candidate.fingerprint, level, criteria):
                rejected_by_requirements += 1
                continue
            similarity = score_similarity(target, candidate.fingerprint, criteria.weights)
            if similarity.score < criteria.min_similarity:
                rejected_below_threshold += 1
                continue
            scored.append(ScoredComparable(candidate=candidate, similarity=similarity))

        scored.sort(key=lambda item: item.score, reverse=True)
        selection = ComparableSelection(
            comparables=scored[: criteria.max_comparables],
            widening_level=level,
            widening_description=description,
            candidates_considered=len(candidates),
            rejected_below_threshold=rejected_below_threshold,
            rejected_by_requirements=rejected_by_requirements,
        )

        if selection.count >= criteria.min_comparables:
            return selection
        attempts.append(selection)

    best = max(attempts, key=lambda attempt: attempt.count)
    if best.count == 0:
        # Nothing matched at any level: report the broadest attempt, because its
        # counters are what explain the shortage to the user.
        return attempts[-1]
    return best
