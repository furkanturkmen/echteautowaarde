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
from echte_auto_waarde.domain.normalization import find_engine_designation
from echte_auto_waarde.domain.options import OPTIONS_BY_KEY
from echte_auto_waarde.models.enums import BodyType, FuelType


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

# A characteristic neither vehicle states is dropped from the average rather
# than scored, so the comparison rests on what is actually known about both
# cars. This floor stops that from rewarding an empty description: when less
# than half the weight can be evaluated, the missing half still counts
# against the score.
MINIMUM_EVALUABLE_WEIGHT = 0.5


@dataclass
class SimilarityBreakdown:
    """Full result of one comparison, including why it scored the way it did."""

    score: float
    components: dict[str, float] = field(default_factory=dict)
    # Characteristics one or both vehicles do not state, and which therefore
    # took no part in the score. Kept so the shortfall can be explained.
    unevaluated: tuple[str, ...] = ()
    reasons: list[dict[str, Any]] = field(default_factory=list)
    differences: list[dict[str, Any]] = field(default_factory=list)


def _linear_closeness(delta: float, tolerance: float) -> float:
    return max(0.0, 1.0 - abs(delta) / tolerance)


def _fuel_score(target: FuelType, candidate: FuelType) -> float | None:
    if FuelType.UNKNOWN in (target, candidate):
        return None
    if target is candidate:
        return 1.0
    return _RELATED_FUELS.get(frozenset({target, candidate}), 0.0)


def _option_score(target: frozenset[str], candidate: frozenset[str]) -> float | None:
    """Importance-weighted overlap of equipment.

    An option both cars have counts fully; an option only one has counts against
    the match in proportion to how much that option matters.

    Two vehicles that both list nothing are not a perfect match on equipment —
    they are a comparison that cannot be made, because sources that publish no
    options look exactly like cars that have none.
    """
    if not target and not candidate:
        return None

    def importance(key: str) -> float:
        definition = OPTIONS_BY_KEY.get(key)
        return definition.importance if definition else 0.3

    shared = sum(importance(key) for key in target & candidate)
    union = sum(importance(key) for key in target | candidate)
    return shared / union if union else 1.0


def _engine_score(target: str | None, candidate: str | None) -> float | None:
    """How far two engine descriptions describe the same engine.

    Dealers write the same engine differently — "1.0 eTSI 110pk DSG Life" and
    "Variant 1.0 eTSI Life" are one engine in two titles — so where both sides
    name a displacement and an engine family, those are compared and the
    surrounding package and equipment wording is left to the fields that
    already carry it. Descriptions that carry no such designation ("330e",
    "45 TFSI quattro") are compared whole, as before.
    """
    if not target or not candidate:
        return None

    target_engine = find_engine_designation(target)
    candidate_engine = find_engine_designation(candidate)
    if target_engine and candidate_engine:
        return 1.0 if target_engine == candidate_engine else 0.0
    return 1.0 if target == candidate else 0.0


def unstated_factors(
    target: VehicleFingerprint,
    weights: SimilarityWeights = DEFAULT_WEIGHTS,
) -> tuple[str, ...]:
    """Scored characteristics the target does not state, heaviest first.

    A factor the target leaves blank can never be evaluated, whatever the
    candidate says about itself, so it caps how similar any comparable can be.
    Naming those factors turns "no comparable was close enough" into something
    the person can act on.
    """
    stated = {
        "generation": target.generation is not None,
        "body_type": target.body_type is not BodyType.UNKNOWN,
        "fuel_type": target.fuel_type is not FuelType.UNKNOWN,
        "engine": target.engine_description is not None,
        "power": target.power_hp is not None,
        "transmission": target.transmission.name != "UNKNOWN",
        "drivetrain": target.drivetrain.name != "UNKNOWN",
        "year": target.year is not None,
        "mileage": target.mileage_km is not None,
        "trim": target.trim is not None,
        "options": bool(target.option_keys),
    }
    missing = [name for name, known in stated.items() if not known]
    return tuple(sorted(missing, key=lambda name: -getattr(weights, name)))


def score_similarity(
    target: VehicleFingerprint,
    candidate: VehicleFingerprint,
    weights: SimilarityWeights = DEFAULT_WEIGHTS,
) -> SimilarityBreakdown:
    """Score how comparable `candidate` is to `target`, with an explanation.

    A characteristic neither vehicle states cannot tell the two apart, so it is
    left out of the average rather than scored as a half match. Counting it
    used to drag every comparison towards the middle: dealer listings publish
    no generation, power or drivetrain, which capped even two identical cars
    well below a full match and left far too little room between a genuine
    match and a loose one.

    The divisor never drops below `MINIMUM_EVALUABLE_WEIGHT`, so a vehicle
    described by only one or two fields cannot reach a high score by having
    almost nothing to compare.
    """
    components: dict[str, float] = {}
    unevaluated: list[str] = []
    reasons: list[dict[str, Any]] = []
    differences: list[dict[str, Any]] = []

    def record(field_name: str, score: float | None) -> None:
        if score is None:
            unevaluated.append(field_name)
        else:
            components[field_name] = score

    # --- Generation ---
    if target.generation and candidate.generation:
        same_generation = target.generation == candidate.generation
        record("generation", 1.0 if same_generation else 0.0)
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
        record("generation", None)

    # --- Body type ---
    if BodyType.UNKNOWN in (target.body_type, candidate.body_type):
        record("body_type", None)
    elif target.body_type is candidate.body_type:
        record("body_type", 1.0)
        reasons.append(
            {"code": "SAME_BODY_TYPE", "field": "body_type", "value": candidate.body_type.value}
        )
    else:
        record("body_type", 0.2)
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
    record("fuel_type", fuel_score)
    if fuel_score == 1.0:
        reasons.append(
            {"code": "SAME_POWERTRAIN", "field": "fuel_type", "value": candidate.fuel_type.value}
        )
    elif fuel_score is not None and target.fuel_type is not candidate.fuel_type:
        differences.append(
            {
                "code": "DIFFERENT_POWERTRAIN",
                "field": "fuel_type",
                "value": candidate.fuel_type.value,
                "target_value": target.fuel_type.value,
            }
        )

    # --- Engine variant ---
    engine_score = _engine_score(target.engine_description, candidate.engine_description)
    record("engine", engine_score)
    if engine_score == 1.0:
        reasons.append(
            {"code": "SAME_ENGINE", "field": "engine", "value": candidate.engine_description}
        )
    elif engine_score is not None:
        differences.append(
            {
                "code": "DIFFERENT_ENGINE",
                "field": "engine",
                "value": candidate.engine_description,
                "target_value": target.engine_description,
            }
        )

    # --- Power ---
    if target.power_hp and candidate.power_hp:
        delta_hp = candidate.power_hp - target.power_hp
        record("power", _linear_closeness(delta_hp, POWER_TOLERANCE_HP))
        if delta_hp:
            differences.append({"code": "POWER_DIFFERENCE", "field": "power_hp", "delta": delta_hp})
    else:
        record("power", None)

    # --- Transmission ---
    if target.transmission.name == "UNKNOWN" or candidate.transmission.name == "UNKNOWN":
        record("transmission", None)
    elif target.transmission is candidate.transmission:
        record("transmission", 1.0)
        reasons.append(
            {
                "code": "SAME_TRANSMISSION",
                "field": "transmission",
                "value": candidate.transmission.value,
            }
        )
    else:
        record("transmission", 0.0)
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
        record("drivetrain", None)
    elif target.drivetrain is candidate.drivetrain:
        record("drivetrain", 1.0)
    else:
        record("drivetrain", 0.25)
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
        record("year", _linear_closeness(delta_years, YEAR_TOLERANCE))
        if delta_years == 0:
            reasons.append({"code": "SAME_YEAR", "field": "year", "value": candidate.year})
        else:
            differences.append({"code": "YEAR_DIFFERENCE", "field": "year", "delta": delta_years})
    else:
        record("year", None)

    # --- Mileage ---
    if target.mileage_km is not None and candidate.mileage_km is not None:
        delta_km = candidate.mileage_km - target.mileage_km
        record("mileage", _linear_closeness(delta_km, MILEAGE_TOLERANCE_KM))
        if abs(delta_km) < 5_000:
            reasons.append({"code": "SIMILAR_MILEAGE", "field": "mileage_km", "delta": delta_km})
        else:
            differences.append(
                {"code": "MILEAGE_DIFFERENCE", "field": "mileage_km", "delta": delta_km}
            )
    else:
        record("mileage", None)

    # --- Trim ---
    if target.trim and candidate.trim:
        same_trim = target.trim == candidate.trim
        record("trim", 1.0 if same_trim else 0.2)
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
        record("trim", None)

    # --- Options ---
    record("options", _option_score(target.option_keys, candidate.option_keys))
    for key in sorted(candidate.option_keys - target.option_keys):
        differences.append({"code": "EXTRA_OPTION", "field": "option", "value": key})
    for key in sorted(target.option_keys - candidate.option_keys):
        differences.append({"code": "MISSING_OPTION", "field": "option", "value": key})
    for key in sorted(target.option_keys & candidate.option_keys):
        reasons.append({"code": "SHARED_OPTION", "field": "option", "value": key})

    evaluated_weight = sum(getattr(weights, name) for name in components)
    weighted = sum(score * getattr(weights, name) for name, score in components.items())
    divisor = max(evaluated_weight, MINIMUM_EVALUABLE_WEIGHT)
    score = round(weighted / divisor, 4) if divisor else 0.0

    return SimilarityBreakdown(
        score=score,
        components=components,
        unevaluated=tuple(unevaluated),
        reasons=reasons,
        differences=differences,
    )
