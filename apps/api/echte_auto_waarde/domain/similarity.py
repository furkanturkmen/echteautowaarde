"""Similarity scoring between two normalized vehicles.

Similarity is expressed on a 0.00-1.00 scale everywhere in the system.

Every weight below is configuration, not a magic constant: the defaults reflect
what actually separates two otherwise identical Dutch used cars in price, and
they are documented in docs/valuation.md. `SimilarityWeights` can be replaced
per search, which is the mechanism a future "what matters to me" UI will use.

Scoring is deliberately explainable: alongside the score, each comparison
returns structured reasons (what matches) and differences (what does not), which
the frontend renders as Overeenkomsten and Verschillen. Codes are English and
stable; the Dutch wording is a frontend concern.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from echte_auto_waarde.domain.fingerprint import VehicleFingerprint
from echte_auto_waarde.domain.options import OPTIONS_BY_KEY
from echte_auto_waarde.models.enums import FuelType


@dataclass(frozen=True)
class SimilarityWeights:
    """Relative weight of each characteristic. The weights sum to 1.0."""

    generation: float = 0.12
    body_type: float = 0.08
    fuel_type: float = 0.15
    engine: float = 0.12
    power: float = 0.05
    transmission: float = 0.07
    drivetrain: float = 0.05
    year: float = 0.12
    mileage: float = 0.14
    trim: float = 0.06
    options: float = 0.04

    def total(self) -> float:
        return (
            self.generation
            + self.body_type
            + self.fuel_type
            + self.engine
            + self.power
            + self.transmission
            + self.drivetrain
            + self.year
            + self.mileage
            + self.trim
            + self.options
        )


DEFAULT_WEIGHTS = SimilarityWeights()

# A five-year gap makes two cars incomparable on age alone; anything closer
# scores proportionally.
YEAR_TOLERANCE = 5
# Dutch cars drive roughly 15.000 km/year, so 60.000 km is about four years of
# average use — beyond that, mileage alone dominates the price difference.
MILEAGE_TOLERANCE_KM = 60_000
# Power differences matter, but only up to a point: 100 hp apart is a different
# car regardless of the exact figure.
POWER_TOLERANCE_HP = 100

# Powertrains that are not identical but still partly comparable. A plug-in
# hybrid is closer to a full hybrid than to a diesel, but never equivalent.
_RELATED_FUELS: dict[frozenset[FuelType], float] = {
    frozenset({FuelType.HYBRID, FuelType.PLUGIN_HYBRID}): 0.45,
    frozenset({FuelType.PETROL, FuelType.HYBRID}): 0.35,
    frozenset({FuelType.PETROL, FuelType.PLUGIN_HYBRID}): 0.25,
    frozenset({FuelType.PETROL, FuelType.LPG}): 0.5,
    frozenset({FuelType.ELECTRIC, FuelType.PLUGIN_HYBRID}): 0.2,
}

# Score used when a value is missing on either side: an unknown is neither a
# match nor a mismatch, and must not be rewarded like a match.
UNKNOWN_SCORE = 0.4


@dataclass
class SimilarityBreakdown:
    """Full result of one comparison, including why it scored the way it did."""

    score: float
    components: dict[str, float] = field(default_factory=dict)
    reasons: list[dict[str, Any]] = field(default_factory=list)
    differences: list[dict[str, Any]] = field(default_factory=list)


def _linear_closeness(delta: float, tolerance: float) -> float:
    return max(0.0, 1.0 - abs(delta) / tolerance)


def _fuel_score(target: FuelType, candidate: FuelType) -> float:
    if FuelType.UNKNOWN in (target, candidate):
        return UNKNOWN_SCORE
    if target is candidate:
        return 1.0
    return _RELATED_FUELS.get(frozenset({target, candidate}), 0.0)


def _option_score(target: frozenset[str], candidate: frozenset[str]) -> float:
    """Importance-weighted overlap of equipment.

    An option both cars have counts fully; an option only one has counts against
    the match in proportion to how much that option matters.
    """
    if not target and not candidate:
        return 1.0

    def importance(key: str) -> float:
        definition = OPTIONS_BY_KEY.get(key)
        return definition.importance if definition else 0.3

    shared = sum(importance(key) for key in target & candidate)
    union = sum(importance(key) for key in target | candidate)
    return shared / union if union else 1.0


def score_similarity(
    target: VehicleFingerprint,
    candidate: VehicleFingerprint,
    weights: SimilarityWeights = DEFAULT_WEIGHTS,
) -> SimilarityBreakdown:
    """Score how comparable `candidate` is to `target`, with an explanation."""
    components: dict[str, float] = {}
    reasons: list[dict[str, Any]] = []
    differences: list[dict[str, Any]] = []

    # --- Generation ---
    if target.generation and candidate.generation:
        same_generation = target.generation == candidate.generation
        components["generation"] = 1.0 if same_generation else 0.0
        if same_generation:
            reasons.append(
                {"code": "SAME_GENERATION", "field": "generation", "value": candidate.generation}
            )
        else:
            differences.append(
                {
                    "code": "DIFFERENT_GENERATION",
                    "field": "generation",
                    "value": candidate.generation,
                    "target_value": target.generation,
                }
            )
    else:
        components["generation"] = UNKNOWN_SCORE

    # --- Body type ---
    if target.body_type is candidate.body_type:
        components["body_type"] = 1.0
        reasons.append(
            {"code": "SAME_BODY_TYPE", "field": "body_type", "value": candidate.body_type.value}
        )
    else:
        components["body_type"] = 0.2
        differences.append(
            {
                "code": "DIFFERENT_BODY_TYPE",
                "field": "body_type",
                "value": candidate.body_type.value,
                "target_value": target.body_type.value,
            }
        )

    # --- Fuel / powertrain ---
    fuel_score = _fuel_score(target.fuel_type, candidate.fuel_type)
    components["fuel_type"] = fuel_score
    if fuel_score == 1.0:
        reasons.append(
            {"code": "SAME_POWERTRAIN", "field": "fuel_type", "value": candidate.fuel_type.value}
        )
    elif target.fuel_type is not candidate.fuel_type:
        differences.append(
            {
                "code": "DIFFERENT_POWERTRAIN",
                "field": "fuel_type",
                "value": candidate.fuel_type.value,
                "target_value": target.fuel_type.value,
            }
        )

    # --- Engine variant ---
    if target.engine_description and candidate.engine_description:
        same_engine = target.engine_description == candidate.engine_description
        components["engine"] = 1.0 if same_engine else 0.0
        if same_engine:
            reasons.append(
                {"code": "SAME_ENGINE", "field": "engine", "value": candidate.engine_description}
            )
        else:
            differences.append(
                {
                    "code": "DIFFERENT_ENGINE",
                    "field": "engine",
                    "value": candidate.engine_description,
                    "target_value": target.engine_description,
                }
            )
    else:
        components["engine"] = UNKNOWN_SCORE

    # --- Power ---
    if target.power_hp and candidate.power_hp:
        delta_hp = candidate.power_hp - target.power_hp
        components["power"] = _linear_closeness(delta_hp, POWER_TOLERANCE_HP)
        if delta_hp:
            differences.append({"code": "POWER_DIFFERENCE", "field": "power_hp", "delta": delta_hp})
    else:
        components["power"] = UNKNOWN_SCORE

    # --- Transmission ---
    if target.transmission.name == "UNKNOWN" or candidate.transmission.name == "UNKNOWN":
        components["transmission"] = UNKNOWN_SCORE
    elif target.transmission is candidate.transmission:
        components["transmission"] = 1.0
        reasons.append(
            {
                "code": "SAME_TRANSMISSION",
                "field": "transmission",
                "value": candidate.transmission.value,
            }
        )
    else:
        components["transmission"] = 0.0
        differences.append(
            {
                "code": "DIFFERENT_TRANSMISSION",
                "field": "transmission",
                "value": candidate.transmission.value,
                "target_value": target.transmission.value,
            }
        )

    # --- Drivetrain ---
    if target.drivetrain.name == "UNKNOWN" or candidate.drivetrain.name == "UNKNOWN":
        components["drivetrain"] = UNKNOWN_SCORE
    elif target.drivetrain is candidate.drivetrain:
        components["drivetrain"] = 1.0
    else:
        components["drivetrain"] = 0.25
        differences.append(
            {
                "code": "DIFFERENT_DRIVETRAIN",
                "field": "drivetrain",
                "value": candidate.drivetrain.value,
                "target_value": target.drivetrain.value,
            }
        )

    # --- Year ---
    if target.year and candidate.year:
        delta_years = candidate.year - target.year
        components["year"] = _linear_closeness(delta_years, YEAR_TOLERANCE)
        if delta_years == 0:
            reasons.append({"code": "SAME_YEAR", "field": "year", "value": candidate.year})
        else:
            differences.append({"code": "YEAR_DIFFERENCE", "field": "year", "delta": delta_years})
    else:
        components["year"] = UNKNOWN_SCORE

    # --- Mileage ---
    if target.mileage_km is not None and candidate.mileage_km is not None:
        delta_km = candidate.mileage_km - target.mileage_km
        components["mileage"] = _linear_closeness(delta_km, MILEAGE_TOLERANCE_KM)
        if abs(delta_km) < 5_000:
            reasons.append({"code": "SIMILAR_MILEAGE", "field": "mileage_km", "delta": delta_km})
        else:
            differences.append(
                {"code": "MILEAGE_DIFFERENCE", "field": "mileage_km", "delta": delta_km}
            )
    else:
        components["mileage"] = UNKNOWN_SCORE

    # --- Trim ---
    if target.trim and candidate.trim:
        same_trim = target.trim == candidate.trim
        components["trim"] = 1.0 if same_trim else 0.2
        if same_trim:
            reasons.append({"code": "SAME_TRIM", "field": "trim", "value": candidate.trim})
        else:
            differences.append(
                {
                    "code": "DIFFERENT_TRIM",
                    "field": "trim",
                    "value": candidate.trim,
                    "target_value": target.trim,
                }
            )
    else:
        components["trim"] = UNKNOWN_SCORE

    # --- Options ---
    components["options"] = _option_score(target.option_keys, candidate.option_keys)
    for key in sorted(candidate.option_keys - target.option_keys):
        differences.append({"code": "EXTRA_OPTION", "field": "option", "value": key})
    for key in sorted(target.option_keys - candidate.option_keys):
        differences.append({"code": "MISSING_OPTION", "field": "option", "value": key})
    for key in sorted(target.option_keys & candidate.option_keys):
        reasons.append({"code": "SHARED_OPTION", "field": "option", "value": key})

    weighted = (
        components["generation"] * weights.generation
        + components["body_type"] * weights.body_type
        + components["fuel_type"] * weights.fuel_type
        + components["engine"] * weights.engine
        + components["power"] * weights.power
        + components["transmission"] * weights.transmission
        + components["drivetrain"] * weights.drivetrain
        + components["year"] * weights.year
        + components["mileage"] * weights.mileage
        + components["trim"] * weights.trim
        + components["options"] * weights.options
    )
    total_weight = weights.total()
    score = round(weighted / total_weight, 4) if total_weight else 0.0

    return SimilarityBreakdown(
        score=score, components=components, reasons=reasons, differences=differences
    )
