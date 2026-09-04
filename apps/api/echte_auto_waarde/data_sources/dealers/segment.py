"""The vehicle segment the dealer pilot collects.

Kept in one place so every source agrees on what is in scope, and stated as
constants rather than configuration: a pilot that can be pointed at anything is
no longer a pilot.

The segment exists because of what Phase 14 measured. Dealer websites carry
almost no 2013-2017 petrol Golfs — the largest group in the country had three,
all of them a different body style — because official dealers trade those cars
away rather than retail them. Recent Golfs, by contrast, are everywhere. The
segment follows the supply rather than wishing it were elsewhere.
"""

from __future__ import annotations

import re

MAKE = "Volkswagen"
MODEL = "Golf"

# Mk8 and late Mk7.5: the years dealer stock actually covers.
FIRST_YEAR = 2020
LAST_YEAR = 2024

# Petrol only. A plug-in hybrid Golf prices differently enough that mixing the
# two would measure the mix rather than the market.
FUEL_WORDS = frozenset({"benzine", "petrol", "gasoline"})

# The Sportsvan is a different body style wearing the same name.
EXCLUDED_WORDS = ("sportsvan",)

# Engine designations that state the powertrain in the URL. A Golf slug saying
# eHybrid or GTE is a plug-in hybrid, which the fuel rule excludes anyway — so
# recognising it saves opening the page rather than adding a rule.
#
# This matters more than it sounds. One dealer's Golf stock is 36 plug-in
# hybrids out of 49, and because candidates are read in order, a run spent its
# entire request budget on cars it was always going to reject.
_SLUG_EXCLUSIONS = re.compile(r"sportsvan|e-?hybrid|-gte(?:[-0-9]|$)", re.IGNORECASE)


def slug_could_match(slug: str) -> bool:
    """Whether a listing URL is worth opening at all.

    Deliberately generous: a slug names the model but rarely the year or the
    fuel, so this rules out only what is certainly wrong. Anything it lets
    through is checked properly once the page has been read.
    """
    lowered = slug.lower()
    if f"{MAKE.lower()}-{MODEL.lower()}" not in lowered:
        return False
    return not _SLUG_EXCLUSIONS.search(lowered)


def matches(model: str | None, year: int | None, fuel: str | None) -> bool:
    """Whether a listing that has been read is in the segment."""
    if not model or MODEL.lower() not in model.lower():
        return False
    if any(word in model.lower() for word in EXCLUDED_WORDS):
        return False
    if year is None or not FIRST_YEAR <= year <= LAST_YEAR:
        return False
    return fuel is not None and fuel.strip().lower() in FUEL_WORDS


def describe() -> str:
    return f"{MAKE} {MODEL} {FIRST_YEAR}-{LAST_YEAR}, petrol"
