"""Reading listings from the structured data a dealer already publishes.

Some dealer sites embed schema.org `Car` data in their pages — the same data
they hand to search engines. Where that exists it is the better source: it is
published deliberately for machines, it states facts rather than presentation,
and it does not break when a designer moves a `<div>`.

Only the factual fields a valuation needs are taken. The blocks also carry
photographs, descriptions, dealer contact details and a VIN; none of that is
read, because none of it is market evidence.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import date
from typing import Any

from echte_auto_waarde.domain.normalization import find_trim

logger = logging.getLogger(__name__)

_JSON_LD = re.compile(
    r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.S | re.I
)

# schema.org fuel wording, mapped to the words our normalization already knows.
_FUEL_WORDS = {
    "petrol": "Benzine",
    "gasoline": "Benzine",
    "diesel": "Diesel",
    "electric": "Elektrisch",
    "hybrid": "Hybride",
    "plugin_hybrid": "Plug-in hybride",
    "plug-in hybrid": "Plug-in hybride",
    "lpg": "LPG",
    "cng": "CNG",
}

# Transmission is rarely a schema.org field; when it appears at all it is a word
# inside the listing title. Only these exact words are recognised.
_TRANSMISSION_WORDS = ("handgeschakeld", "handmatig", "automaat", "dsg", "tiptronic")


@dataclass(frozen=True)
class StructuredCar:
    """The subset of a schema.org `Car` node this product has a use for."""

    make: str
    model: str
    variant: str | None
    trim: str | None
    first_registration: date | None
    year: int | None
    mileage_km: int | None
    asking_price_cents: int | None
    fuel: str | None
    transmission: str | None
    body_type: str | None
    doors: int | None


def iter_json_ld(html: str) -> list[dict[str, Any]]:
    """Every JSON-LD node in a page, `@graph` entries included."""
    nodes: list[dict[str, Any]] = []
    for block in _JSON_LD.findall(html):
        try:
            parsed = json.loads(block)
        except ValueError:
            # A malformed block is skipped, not fatal: pages carry several.
            continue
        candidates = parsed if isinstance(parsed, list) else [parsed]
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            graph = candidate.get("@graph")
            if isinstance(graph, list):
                nodes.extend(node for node in graph if isinstance(node, dict))
            else:
                nodes.append(candidate)
    return nodes


def find_car(html: str) -> dict[str, Any] | None:
    """The first node that describes a vehicle."""
    for node in iter_json_ld(html):
        types = node.get("@type")
        names = types if isinstance(types, list) else [types]
        if any(str(name) in ("Car", "Vehicle") for name in names):
            return node
    return None


def read_car(html: str) -> StructuredCar | None:
    """Turn a page's structured data into the facts we keep, or nothing."""
    node = find_car(html)
    if node is None:
        return None

    make = _text(node.get("manufacturer")) or _text(node.get("brand")) or ""
    model = _text(node.get("model"))
    if not make or not model:
        return None

    registration = _date(node.get("dateVehicleFirstRegistered"))
    year = registration.year if registration else _int(node.get("vehicleModelDate"), 1950, 2100)

    variant = _variant(node, make, model)
    return StructuredCar(
        make=make,
        model=model,
        variant=variant,
        # Listings name the package inside the title rather than in a field of
        # its own, and an unrecognised name stays absent rather than becoming a
        # guess.
        trim=find_trim(variant),
        first_registration=registration,
        year=year,
        mileage_km=_quantity(node.get("mileageFromOdometer"), 0, 2_000_000),
        asking_price_cents=_price_cents(node.get("offers")),
        fuel=_fuel(node),
        transmission=_transmission(node),
        body_type=_text(node.get("bodyType")) or None,
        doors=_int(node.get("numberOfDoors"), 1, 9),
    )


# -- Field helpers ------------------------------------------------------------


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        return _text(value.get("name") or value.get("@value"))
    if isinstance(value, list) and value:
        return _text(value[0])
    return ""


def _int(value: Any, low: int, high: int) -> int | None:
    try:
        number = int(str(_text(value) or value).strip())
    except (TypeError, ValueError):
        return None
    return number if low <= number <= high else None


def _quantity(value: Any, low: int, high: int) -> int | None:
    """A schema.org QuantitativeValue, in its own unit."""
    if isinstance(value, dict):
        unit = str(value.get("unitCode", "")).upper()
        if unit and unit not in {"KMT", "SMI"}:
            return None
        if unit == "SMI":  # miles, which Dutch stock should not use
            return None
        return _int(value.get("value"), low, high)
    return _int(value, low, high)


def _price_cents(offers: Any) -> int | None:
    """The asking price from an Offer. Money stays integer cents."""
    if isinstance(offers, list):
        offers = offers[0] if offers else None
    if not isinstance(offers, dict):
        return None
    if str(offers.get("priceCurrency", "EUR")).upper() not in {"EUR", ""}:
        return None

    raw = offers.get("price")
    if raw is None:
        specification = offers.get("priceSpecification")
        if isinstance(specification, dict):
            raw = specification.get("price")
    try:
        amount = float(str(raw).replace(",", "."))
    except (TypeError, ValueError):
        return None
    return int(round(amount * 100)) if amount > 0 else None


def _fuel(node: dict[str, Any]) -> str | None:
    raw = _text(node.get("fuelType"))
    if not raw:
        engine = node.get("vehicleEngine")
        if isinstance(engine, dict):
            raw = _text(engine.get("fuelType"))
    if not raw:
        return None
    return _FUEL_WORDS.get(raw.strip().lower(), raw.strip())


def _transmission(node: dict[str, Any]) -> str | None:
    stated = _text(node.get("vehicleTransmission"))
    haystack = (stated or _text(node.get("name"))).lower()
    for word in _TRANSMISSION_WORDS:
        if word in haystack:
            return word.capitalize()
    return None


def _variant(node: dict[str, Any], make: str, model: str) -> str | None:
    """The engine and trim designation, without the marketing tail.

    Titles run "Golf Variant 1.5 eTSI R-Line Business AUTOMAAT | PANORAMADAK |
    ...". Everything from the first pipe is equipment prose, and the make and
    model are already stored separately.
    """
    name = _text(node.get("name"))
    if not name:
        return None
    variant = name.split("|")[0]
    for prefix in (f"{make} {model}", make, model):
        if prefix and variant.lower().startswith(prefix.lower()):
            variant = variant[len(prefix) :]
    variant = re.sub(r"\s+", " ", variant).strip(" -–—")
    return variant[:80] or None


def _date(value: Any) -> date | None:
    text = _text(value)
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None
