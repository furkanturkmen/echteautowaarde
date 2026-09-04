"""Numeric grounding check.

The system prompt tells the model not to invent amounts. This verifies it did
not, because a prompt is a request and this product's whole claim is that its
numbers are checkable.

This is a numeric check and only a numeric check. It reads euro amounts, not
meaning: an answer whose every figure is ours can still describe a relationship
between those figures incorrectly — calling an asking price "within" an advice
range it sits above, say. `grounded=True` means the numbers came from this
valuation, never that the answer was verified.

Every euro amount in an answer is matched against the amounts the valuation
actually produced. An amount that appears nowhere in the context was invented,
and the answer is flagged so the interface can say so rather than presenting a
fabricated figure as the product's own advice.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from echte_auto_waarde.domain.ai_context import ValuationAiContext

# "€ 21.633", "€21.633,50", "21.633 euro". Dutch grouping uses a dot.
_AMOUNT_PATTERN = re.compile(
    r"(?:€\s?|\bEUR\s?)(\d{1,3}(?:[.\s]\d{3})*(?:,\d{1,2})?|\d+(?:,\d{1,2})?)"
    r"|(\d{1,3}(?:[.\s]\d{3})+(?:,\d{1,2})?)\s?euro",
    re.IGNORECASE,
)

# Prose rounds: "ongeveer € 21.600" for € 21.633 is a restatement, not an
# invention. The tolerance is relative so it behaves the same on a € 8.000 car
# as on a € 80.000 one, with a floor and a ceiling to keep it sane at both ends.
#
# The bias is deliberate: a near-miss of a real figure is left alone, because
# crying wolf over a rounded number would train people to ignore the warning.
# Only amounts that match nothing in the valuation are flagged.
TOLERANCE_RATIO = 0.01
MIN_TOLERANCE_CENTS = 25_00
MAX_TOLERANCE_CENTS = 500_00


def _tolerance_for(amount_cents: int) -> int:
    return max(
        MIN_TOLERANCE_CENTS, min(MAX_TOLERANCE_CENTS, int(abs(amount_cents) * TOLERANCE_RATIO))
    )


@dataclass
class GroundingResult:
    grounded: bool
    unknown_amounts_cents: list[int] = field(default_factory=list)
    checked_amounts: int = 0

    @property
    def note(self) -> str | None:
        """Dutch caution for the interface, when something failed the check."""
        if self.grounded:
            return None
        return (
            "Dit antwoord noemt een bedrag dat niet uit deze waardering komt. "
            "Ga uit van de cijfers in de waardering hierboven."
        )


def _parse_amount_to_cents(raw: str) -> int | None:
    """Parse a Dutch-formatted amount into cents."""
    cleaned = raw.replace(" ", "").replace(".", "")
    if "," in cleaned:
        whole, _, fraction = cleaned.partition(",")
        fraction = (fraction + "00")[:2]
    else:
        whole, fraction = cleaned, "00"
    if not whole.isdigit():
        return None
    return int(whole) * 100 + int(fraction)


def extract_amounts_cents(text: str) -> list[int]:
    """Every euro amount mentioned in a piece of text, in cents."""
    amounts: list[int] = []
    for match in _AMOUNT_PATTERN.finditer(text):
        raw = match.group(1) or match.group(2)
        if raw is None:
            continue
        parsed = _parse_amount_to_cents(raw)
        if parsed is not None:
            amounts.append(parsed)
    return amounts


def check_answer(answer: str, context: ValuationAiContext) -> GroundingResult:
    """Verify that every amount in `answer` came from the valuation."""
    known = context.known_amounts_cents
    mentioned = extract_amounts_cents(answer)

    unknown = [
        amount
        for amount in mentioned
        if not any(abs(amount - candidate) <= _tolerance_for(candidate) for candidate in known)
    ]

    return GroundingResult(
        grounded=not unknown,
        unknown_amounts_cents=sorted(set(unknown)),
        checked_amounts=len(mentioned),
    )
