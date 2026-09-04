"""Normalization of raw vehicle text into canonical values.

Normalization runs before anything else in the pipeline: the comparable engine
can only match vehicles that describe themselves the same way. Every function
here is pure and deterministic, and callers are expected to keep the raw source
text alongside the canonical value for traceability.

Unknown input is never guessed at. It falls back to a cleaned-up form (or the
UNKNOWN enum member), so a missing mapping shows up as missing data rather than
as a silently wrong match.
"""

from __future__ import annotations

import re
import unicodedata

from echte_auto_waarde.models.enums import BodyType, Drivetrain, FuelType, Transmission

_WHITESPACE_RE = re.compile(r"\s+")
_PLATE_STRIP_RE = re.compile(r"[^A-Z0-9]")


def collapse_whitespace(value: str) -> str:
    return _WHITESPACE_RE.sub(" ", value).strip()


def _lookup_key(value: str) -> str:
    """Aggressively simplified key used for alias lookups.

    Lowercased, accent-stripped, with punctuation removed, so "B.M.W.",
    "bmw" and "B M W" all reduce to "bmw".
    """
    decomposed = unicodedata.normalize("NFKD", value)
    without_accents = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]", "", without_accents.lower())


def normalize_license_plate(value: str | None) -> str | None:
    """Dutch plates are stored without separators, e.g. "K-123-AB" -> "K123AB"."""
    if not value:
        return None
    plate = _PLATE_STRIP_RE.sub("", value.upper())
    return plate or None


# --- Make ------------------------------------------------------------------

_MAKE_ALIASES: dict[str, str] = {
    "bmw": "BMW",
    "volkswagen": "Volkswagen",
    "vw": "Volkswagen",
    "mercedesbenz": "Mercedes-Benz",
    "mercedes": "Mercedes-Benz",
    "audi": "Audi",
    "tesla": "Tesla",
    "toyota": "Toyota",
    "volvo": "Volvo",
    "peugeot": "Peugeot",
    "renault": "Renault",
    "skoda": "Škoda",
    "kia": "Kia",
    "hyundai": "Hyundai",
    "ford": "Ford",
    "opel": "Opel",
}


def normalize_make(value: str | None) -> str:
    if not value:
        return "Unknown"
    canonical = _MAKE_ALIASES.get(_lookup_key(value))
    return canonical or collapse_whitespace(value).title()


# --- Model -----------------------------------------------------------------

# Keyed by (normalized make, alias key). Model stays the model line; the engine
# variant ("330e") belongs in engine_description, and the appearance package
# ("M Sport") in trim.
_MODEL_ALIASES: dict[tuple[str, str], str] = {
    ("BMW", "3serie"): "3 Serie",
    ("BMW", "3series"): "3 Serie",
    ("BMW", "serie3"): "3 Serie",
    ("BMW", "3er"): "3 Serie",
    ("Volkswagen", "golf"): "Golf",
    ("Mercedes-Benz", "cklasse"): "C-Klasse",
    ("Mercedes-Benz", "cclass"): "C-Klasse",
    ("Mercedes-Benz", "cklass"): "C-Klasse",
    ("Audi", "a4"): "A4",
    ("Tesla", "model3"): "Model 3",
}

# Engine variants that are frequently written as if they were the model name.
_MODEL_FROM_VARIANT: dict[tuple[str, str], str] = {
    ("BMW", "320i"): "3 Serie",
    ("BMW", "320d"): "3 Serie",
    ("BMW", "330i"): "3 Serie",
    ("BMW", "330e"): "3 Serie",
    ("Mercedes-Benz", "c200"): "C-Klasse",
    ("Mercedes-Benz", "c220d"): "C-Klasse",
    ("Mercedes-Benz", "c300e"): "C-Klasse",
}


def normalize_model(make: str, value: str | None) -> str:
    if not value:
        return "Unknown"
    key = _lookup_key(value)
    canonical = _MODEL_ALIASES.get((make, key)) or _MODEL_FROM_VARIANT.get((make, key))
    return canonical or collapse_whitespace(value)


# --- Trim ------------------------------------------------------------------

# Appearance/equipment packages. These influence value and similarity, but a
# package is never a performance model: "330e M Sport" is not an "M3".
_TRIM_ALIASES: dict[str, str] = {
    "msport": "M Sport",
    "mpakket": "M Sport",
    "msportpakket": "M Sport",
    "msportpro": "M Sport",
    "amgline": "AMG Line",
    "amgpakket": "AMG Line",
    "sline": "S line",
    "slinecompetition": "S line",
    "rline": "R-Line",
    "gtline": "GT Line",
    "businessedition": "Business Edition",
    "business": "Business Edition",
    "executive": "Executive",
    "advantage": "Advantage",
    "luxuryline": "Luxury Line",
    "avantgarde": "Avantgarde",
    "style": "Style",
    "longrange": "Long Range",
    "performance": "Performance",
    "standardrangeplus": "Standard Range Plus",
    "highline": "Highline",
    "comfortline": "Comfortline",
    "lifeplus": "Life Plus",
    "life": "Life",
}


def normalize_trim(value: str | None) -> str | None:
    if not value:
        return None
    canonical = _TRIM_ALIASES.get(_lookup_key(value))
    return canonical or collapse_whitespace(value)


# --- Enumerated attributes -------------------------------------------------

_BODY_TYPE_ALIASES: dict[str, BodyType] = {
    "hatchback": BodyType.HATCHBACK,
    "hatch": BodyType.HATCHBACK,
    "sedan": BodyType.SEDAN,
    "limousine": BodyType.SEDAN,
    "saloon": BodyType.SEDAN,
    "stationwagon": BodyType.STATIONWAGON,
    "stationwagen": BodyType.STATIONWAGON,
    "station": BodyType.STATIONWAGON,
    "touring": BodyType.STATIONWAGON,
    "estate": BodyType.STATIONWAGON,
    "avant": BodyType.STATIONWAGON,
    "variant": BodyType.STATIONWAGON,
    "combi": BodyType.STATIONWAGON,
    "suv": BodyType.SUV,
    "crossover": BodyType.SUV,
    "coupe": BodyType.COUPE,
    "cabriolet": BodyType.CABRIOLET,
    "cabrio": BodyType.CABRIOLET,
    "convertible": BodyType.CABRIOLET,
    "mpv": BodyType.MPV,
}

_FUEL_TYPE_ALIASES: dict[str, FuelType] = {
    "benzine": FuelType.PETROL,
    "petrol": FuelType.PETROL,
    "gasoline": FuelType.PETROL,
    "diesel": FuelType.DIESEL,
    "hybride": FuelType.HYBRID,
    "hybrid": FuelType.HYBRID,
    "fullhybrid": FuelType.HYBRID,
    "pluginhybride": FuelType.PLUGIN_HYBRID,
    "pluginhybrid": FuelType.PLUGIN_HYBRID,
    "phev": FuelType.PLUGIN_HYBRID,
    "stekkerhybride": FuelType.PLUGIN_HYBRID,
    "elektrisch": FuelType.ELECTRIC,
    "electric": FuelType.ELECTRIC,
    "ev": FuelType.ELECTRIC,
    "lpg": FuelType.LPG,
    # Wording used by the Dutch vehicle register.
    "elektriciteit": FuelType.ELECTRIC,
    "waterstof": FuelType.ELECTRIC,
    "cng": FuelType.LPG,
    "lng": FuelType.LPG,
    "aardgas": FuelType.LPG,
}

_TRANSMISSION_ALIASES: dict[str, Transmission] = {
    "automaat": Transmission.AUTOMATIC,
    "automatic": Transmission.AUTOMATIC,
    "auto": Transmission.AUTOMATIC,
    "automatisch": Transmission.AUTOMATIC,
    "dsg": Transmission.AUTOMATIC,
    "steptronic": Transmission.AUTOMATIC,
    "tiptronic": Transmission.AUTOMATIC,
    "stronic": Transmission.AUTOMATIC,
    "handgeschakeld": Transmission.MANUAL,
    "handbak": Transmission.MANUAL,
    "manual": Transmission.MANUAL,
    "manueel": Transmission.MANUAL,
    "schakel": Transmission.MANUAL,
}

_DRIVETRAIN_ALIASES: dict[str, Drivetrain] = {
    "fwd": Drivetrain.FWD,
    "voorwielaandrijving": Drivetrain.FWD,
    "voorwiel": Drivetrain.FWD,
    "rwd": Drivetrain.RWD,
    "achterwielaandrijving": Drivetrain.RWD,
    "achterwiel": Drivetrain.RWD,
    "awd": Drivetrain.AWD,
    "4wd": Drivetrain.AWD,
    "vierwielaandrijving": Drivetrain.AWD,
    "quattro": Drivetrain.AWD,
    "xdrive": Drivetrain.AWD,
    "4matic": Drivetrain.AWD,
    "4motion": Drivetrain.AWD,
    "dualmotor": Drivetrain.AWD,
}


def normalize_body_type(value: str | None) -> BodyType:
    if not value:
        return BodyType.UNKNOWN
    return _BODY_TYPE_ALIASES.get(_lookup_key(value), BodyType.UNKNOWN)


def normalize_fuel_type(value: str | None) -> FuelType:
    if not value:
        return FuelType.UNKNOWN
    return _FUEL_TYPE_ALIASES.get(_lookup_key(value), FuelType.UNKNOWN)


def normalize_transmission(value: str | None) -> Transmission:
    if not value:
        return Transmission.UNKNOWN
    return _TRANSMISSION_ALIASES.get(_lookup_key(value), Transmission.UNKNOWN)


def normalize_drivetrain(value: str | None) -> Drivetrain:
    if not value:
        return Drivetrain.UNKNOWN
    return _DRIVETRAIN_ALIASES.get(_lookup_key(value), Drivetrain.UNKNOWN)


def normalize_engine_description(value: str | None) -> str | None:
    """Engine/variant designation, e.g. "330e", "2.0 TDI", "Long Range"."""
    if not value:
        return None
    return collapse_whitespace(value)
