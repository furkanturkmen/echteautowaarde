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
    # Performance designations. They are trim rather than model, and they move
    # the price far more than any other package.
    "gti": "GTI",
    "gte": "GTE",
    "golfr": "R",
}


def normalize_trim(value: str | None) -> str | None:
    if not value:
        return None
    canonical = _TRIM_ALIASES.get(_lookup_key(value))
    return canonical or collapse_whitespace(value)


# The longest package name in the taxonomy is three words ("Standard Range
# Plus"), so windows wider than that cannot match anything.
_MAX_TRIM_WORDS = 3


def find_trim(text: str | None) -> str | None:
    """The trim named inside a longer description, if there is one.

    Dealer listings state the trim as part of a title — "1.5 eTSI Life Business
    Automaat" — rather than in a field of its own, so the package has to be
    recognised within the text. Longer names are tried first, so "Business
    Edition" is not read as "Business", and the leftmost match wins, because a
    title names the trim before it lists the equipment.

    Only names already in the taxonomy are recognised. Unknown wording returns
    nothing rather than a guess, which leaves the vehicle without a trim and
    lowers its confidence instead of inventing a package.
    """
    if not text:
        return None

    words = collapse_whitespace(text).split(" ")
    for start in range(len(words)):
        for width in range(min(_MAX_TRIM_WORDS, len(words) - start), 0, -1):
            candidate = _TRIM_ALIASES.get(_lookup_key(" ".join(words[start : start + width])))
            if candidate:
                return candidate
    return None


# --- Engine designation ----------------------------------------------------

# The engine families used on the Dutch market, written as they appear in
# listing titles. Longer names come first so "eTSI" is not read as "TSI".
_ENGINE_FAMILIES = (
    "etsi",
    "tfsi",
    "tsi",
    "tdi",
    "cdti",
    "cdi",
    "hdi",
    "dci",
    "crdi",
    "thp",
    "vti",
    "bluehdi",
    "ecoboost",
    "skyactiv",
    "mhev",
)

_ENGINE_DESIGNATION = re.compile(
    r"(?<![\d.,])(\d[.,]\d)\s*-?\s*(" + "|".join(_ENGINE_FAMILIES) + r")\b",
    re.IGNORECASE,
)

# "110pk", "110 PK", "150 pk". Kilowatts are written the same way but are a
# different quantity, so only horsepower is read here.
_POWER_HP = re.compile(r"\b(\d{2,4})\s*-?\s*pk\b", re.IGNORECASE)

# Outside this band the number is not a power figure — small hybrids start
# around 60 hp and nothing this product values reaches four figures.
_POWER_HP_RANGE = (40, 999)


def find_engine_designation(text: str | None) -> str | None:
    """The engine named inside a listing title, as "1.5 eTSI".

    Dealer titles run "1.0 eTSI 110pk DSG Life" or "Variant 1.5 eTSI R-Line
    Business 150 PK": the same engine, described differently by each dealer.
    Comparing those strings whole makes identical engines look unrelated, so
    the comparison uses the displacement and the engine family — the part that
    says what the engine is — and leaves the package, the gearbox and the
    equipment prose to the fields that already carry them.

    Unrecognised wording returns nothing, which leaves the engine unknown
    rather than inventing a designation.
    """
    if not text:
        return None

    match = _ENGINE_DESIGNATION.search(text)
    if match is None:
        return None
    displacement = match.group(1).replace(",", ".")
    family = match.group(2).lower()
    return f"{displacement} {_ENGINE_FAMILY_CASING.get(family, family.upper())}"


# Written the way the manufacturers write them, so the value can be displayed.
_ENGINE_FAMILY_CASING = {
    "etsi": "eTSI",
    "bluehdi": "BlueHDi",
    "ecoboost": "EcoBoost",
    "skyactiv": "SkyActiv",
    "mhev": "mHEV",
}


def find_power_hp(text: str | None) -> int | None:
    """The horsepower figure stated in a listing title, if there is one.

    Titles state it often enough to be worth reading — "110pk", "150 PK" — and
    it is the one thing that separates two cars carrying the same engine
    designation.
    """
    if not text:
        return None

    match = _POWER_HP.search(text)
    if match is None:
        return None
    power = int(match.group(1))
    low, high = _POWER_HP_RANGE
    return power if low <= power <= high else None


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
    "handmatig": Transmission.MANUAL,
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
