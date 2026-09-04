"""Structured context handed to the AI layer.

This is the only thing the model ever sees about a valuation. It is built on the
server from the stored valuation, never from client input, and it is a plain
value object rather than an ORM graph: the model must not be able to reach
anything the backend did not deliberately put in front of it.

The context is also the definition of what "grounded" means. Every euro amount
the assistant is allowed to mention appears in `known_amounts_cents`; anything
else in an answer is, by definition, invented.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# A model that has to weigh twenty listings answers worse than one given the
# strongest handful, and the prompt stays comfortably bounded.
MAX_CONTEXT_COMPARABLES = 6
# Guards against a pathological option list blowing up the prompt.
MAX_CONTEXT_OPTIONS = 12


@dataclass(frozen=True)
class ComparableContext:
    similarity: float
    make: str
    model: str
    year: int | None
    mileage_km: int | None
    trim: str | None
    engine_description: str | None
    asking_price_cents: int
    price_difference_cents: int | None
    seller_type: str | None
    reasons: list[str]
    differences: list[str]


@dataclass(frozen=True)
class AdjustmentContext:
    type: str
    amount_cents: int
    reason: str
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ConfidenceFactorContext:
    code: str
    impact: str
    score: float
    detail: dict[str, Any]


@dataclass(frozen=True)
class ValuationAiContext:
    """Everything the assistant may talk about, and nothing else."""

    valuation_id: int
    algorithm_version: str

    # Vehicle identity
    make: str
    model: str
    year: int | None
    mileage_km: int | None
    trim: str | None
    engine_description: str | None
    fuel_type: str
    transmission: str
    body_type: str
    power_hp: int | None
    license_plate: str | None
    options: list[str]

    # Money
    estimated_market_value_cents: int
    recommended_buy_price_low_cents: int
    recommended_buy_price_high_cents: int
    market_basis_cents: int | None
    asking_price_cents: int | None
    deal_classification: str | None

    # Evidence
    confidence_score: float
    confidence_factors: list[ConfidenceFactorContext]
    comparable_count: int
    widening_level: int
    market_statistics: dict[str, Any]
    adjustments: list[AdjustmentContext]
    comparables: list[ComparableContext]

    # Provenance
    data_is_synthetic: bool
    data_disclaimer: str

    @property
    def known_amounts_cents(self) -> set[int]:
        """Every euro amount the assistant may quote.

        Anything outside this set in an answer was not produced by the
        valuation engine, which is exactly what the grounding check looks for.
        """
        amounts: set[int] = {
            self.estimated_market_value_cents,
            self.recommended_buy_price_low_cents,
            self.recommended_buy_price_high_cents,
        }
        if self.market_basis_cents is not None:
            amounts.add(self.market_basis_cents)
            # What the corrections did in total. Asked to list them, models add
            # them up and get it wrong; the engine already knows the answer.
            amounts.add(abs(self.estimated_market_value_cents - self.market_basis_cents))
        if self.asking_price_cents is not None:
            amounts.add(self.asking_price_cents)
            # The gap between asking price and advice is the one comparison the
            # interface itself makes, so quoting it is grounded.
            amounts.add(abs(self.asking_price_cents - self.estimated_market_value_cents))
            amounts.add(abs(self.asking_price_cents - self.recommended_buy_price_high_cents))
            amounts.add(abs(self.asking_price_cents - self.recommended_buy_price_low_cents))

        for adjustment in self.adjustments:
            amounts.add(abs(adjustment.amount_cents))

        for comparable in self.comparables:
            amounts.add(comparable.asking_price_cents)
            if comparable.price_difference_cents is not None:
                amounts.add(abs(comparable.price_difference_cents))

        for key, value in self.market_statistics.items():
            if key.endswith("Cents") and isinstance(value, int):
                amounts.add(value)

        return amounts

    @property
    def total_adjustment_cents(self) -> int | None:
        """The net effect of every correction, as the engine computed it.

        Not the sum of the listed adjustments: capping and rounding can leave
        those a euro apart from the real difference, and the difference is what
        actually happened to the market basis.
        """
        if self.market_basis_cents is None:
            return None
        return self.estimated_market_value_cents - self.market_basis_cents

    def supported_questions(self) -> list[str]:
        """Example questions the current data can actually answer.

        A question is only offered when the evidence behind it exists, so the
        interface never invites a question whose honest answer would be "that
        is not in this valuation".
        """
        questions: list[str] = []

        if self.asking_price_cents is not None:
            questions.append("Wat zou jij voor deze auto betalen?")
            if self.asking_price_cents > self.estimated_market_value_cents:
                questions.append("Waarom ligt de marktwaarde lager dan de vraagprijs?")
            questions.append("Is deze auto duur ten opzichte van de markt?")
        else:
            questions.append("Wat zegt deze waardering over wat ik zou moeten betalen?")

        confidence_percentage = round(self.confidence_score * 100)
        questions.append(f"Waarom is de betrouwbaarheid maar {confidence_percentage}%?")

        if self.comparables:
            questions.append("Welke vergelijkbare auto weegt het zwaarst mee?")
            questions.append("Welke verschillen zijn het belangrijkst?")

        mileage = next((a for a in self.adjustments if a.type == "MILEAGE"), None)
        if mileage is not None:
            questions.append("Waarom is de kilometercorrectie zo groot?")

        if self.widening_level > 0:
            questions.append("Waarom is de zoekopdracht verbreed?")

        return questions


@dataclass
class ContextBuildResult:
    context: ValuationAiContext
    # Kept separate from the context so prompt construction stays pure.
    notes: list[str] = field(default_factory=list)
