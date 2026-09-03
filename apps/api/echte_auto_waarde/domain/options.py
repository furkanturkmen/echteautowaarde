"""Option taxonomy and alias resolution.

Listings describe the same feature in many ways ("Adaptive Cruise Control",
"ACC", "adaptieve cruise"). Everything resolves to one canonical option here, so
similarity and valuation compare equipment rather than wording.

`importance` (0..1) expresses how much an option matters for similarity and for
the option adjustment. The values are deliberate starting points based on how
strongly Dutch used-car buyers tend to seek each feature, not measured market
data — they are configuration, and are expected to be tuned once real market
observations exist.

Trim packages (M Sport, AMG Line, …) live in this taxonomy so that raw listing
text resolves, but they belong on the vehicle's `trim` field rather than in its
option list: see `split_option_texts`. Keeping them out of the option list is
what prevents a package from being counted twice in the valuation.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from echte_auto_waarde.models.enums import OptionCategory


@dataclass(frozen=True)
class OptionDefinition:
    key: str
    label_nl: str
    category: OptionCategory
    importance: float
    aliases: tuple[str, ...] = field(default_factory=tuple)


OPTION_TAXONOMY: tuple[OptionDefinition, ...] = (
    # --- Trim / appearance packages -------------------------------------
    OptionDefinition(
        key="m_sport",
        label_nl="M Sport",
        category=OptionCategory.TRIM_PACKAGE,
        importance=0.8,
        aliases=("m sport", "m-sport", "m sportpakket", "m pakket", "msport"),
    ),
    OptionDefinition(
        key="amg_line",
        label_nl="AMG Line",
        category=OptionCategory.TRIM_PACKAGE,
        importance=0.8,
        aliases=("amg line", "amg-line", "amg pakket", "amgline"),
    ),
    OptionDefinition(
        key="s_line",
        label_nl="S line",
        category=OptionCategory.TRIM_PACKAGE,
        importance=0.8,
        aliases=("s line", "s-line", "sline"),
    ),
    OptionDefinition(
        key="r_line",
        label_nl="R-Line",
        category=OptionCategory.TRIM_PACKAGE,
        importance=0.8,
        aliases=("r line", "r-line", "rline"),
    ),
    # --- Comfort ---------------------------------------------------------
    OptionDefinition(
        key="panoramic_roof",
        label_nl="Panoramadak",
        category=OptionCategory.COMFORT,
        importance=0.7,
        aliases=(
            "panoramadak",
            "panorama dak",
            "panoramisch dak",
            "panoramic roof",
            "panorama schuifdak",
            "glazen schuifdak",
        ),
    ),
    OptionDefinition(
        key="leather_interior",
        label_nl="Lederen bekleding",
        category=OptionCategory.COMFORT,
        importance=0.6,
        aliases=("leder", "leer", "lederen bekleding", "leather", "leather interior", "nappa"),
    ),
    OptionDefinition(
        key="heated_seats",
        label_nl="Stoelverwarming",
        category=OptionCategory.COMFORT,
        importance=0.45,
        aliases=("stoelverwarming", "verwarmde stoelen", "heated seats", "seat heating"),
    ),
    OptionDefinition(
        key="ventilated_seats",
        label_nl="Stoelventilatie",
        category=OptionCategory.COMFORT,
        importance=0.4,
        aliases=("stoelventilatie", "geventileerde stoelen", "ventilated seats"),
    ),
    OptionDefinition(
        key="electric_seats",
        label_nl="Elektrisch verstelbare stoelen",
        category=OptionCategory.COMFORT,
        importance=0.35,
        aliases=(
            "elektrisch verstelbare stoelen",
            "elektrische stoelen",
            "electric seats",
            "power seats",
        ),
    ),
    OptionDefinition(
        key="memory_seats",
        label_nl="Memory stoelen",
        category=OptionCategory.COMFORT,
        importance=0.3,
        aliases=("memory stoelen", "geheugenstoelen", "memory seats"),
    ),
    OptionDefinition(
        key="climate_control",
        label_nl="Climate control",
        category=OptionCategory.COMFORT,
        importance=0.2,
        aliases=("climate control", "climatronic", "airco automatisch", "clima"),
    ),
    # --- Safety / driver assistance --------------------------------------
    OptionDefinition(
        key="adaptive_cruise_control",
        label_nl="Adaptieve cruise control",
        category=OptionCategory.SAFETY,
        importance=0.6,
        aliases=(
            "adaptive cruise control",
            "adaptieve cruise control",
            "adaptieve cruise",
            "acc",
            "adaptive cruise",
        ),
    ),
    OptionDefinition(
        key="camera_360",
        label_nl="360 camera",
        category=OptionCategory.SAFETY,
        importance=0.5,
        aliases=("360 camera", "360-camera", "surround view", "rondomzicht camera"),
    ),
    OptionDefinition(
        key="reversing_camera",
        label_nl="Achteruitrijcamera",
        category=OptionCategory.SAFETY,
        importance=0.35,
        aliases=("achteruitrijcamera", "achteruitrij camera", "reversing camera", "rear camera"),
    ),
    OptionDefinition(
        key="parking_sensors",
        label_nl="Parkeersensoren",
        category=OptionCategory.SAFETY,
        importance=0.25,
        aliases=("parkeersensoren", "pdc", "parking sensors", "park distance control"),
    ),
    OptionDefinition(
        key="blind_spot_monitor",
        label_nl="Dodehoekdetectie",
        category=OptionCategory.SAFETY,
        importance=0.35,
        aliases=("dodehoekdetectie", "dode hoek", "blind spot", "blind spot monitor"),
    ),
    # --- Infotainment -----------------------------------------------------
    OptionDefinition(
        key="premium_audio",
        label_nl="Premium audio",
        category=OptionCategory.INFOTAINMENT,
        importance=0.45,
        aliases=(
            "premium audio",
            "harman kardon",
            "bang & olufsen",
            "bang en olufsen",
            "burmester",
            "bowers & wilkins",
            "premium sound",
        ),
    ),
    OptionDefinition(
        key="head_up_display",
        label_nl="Head-up display",
        category=OptionCategory.INFOTAINMENT,
        importance=0.45,
        aliases=("head-up display", "head up display", "hud"),
    ),
    OptionDefinition(
        key="navigation",
        label_nl="Navigatie",
        category=OptionCategory.INFOTAINMENT,
        importance=0.25,
        aliases=("navigatie", "navigation", "navi", "nav systeem"),
    ),
    OptionDefinition(
        key="apple_carplay",
        label_nl="Apple CarPlay",
        category=OptionCategory.INFOTAINMENT,
        importance=0.3,
        aliases=("apple carplay", "carplay", "android auto"),
    ),
    # --- Exterior ---------------------------------------------------------
    OptionDefinition(
        key="matrix_led",
        label_nl="Matrix LED-koplampen",
        category=OptionCategory.EXTERIOR,
        importance=0.55,
        aliases=(
            "matrix led",
            "matrix-led",
            "adaptive led",
            "adaptieve led",
            "laserlight",
            "led matrix",
        ),
    ),
    OptionDefinition(
        key="adaptive_suspension",
        label_nl="Adaptief onderstel",
        category=OptionCategory.EXTERIOR,
        importance=0.45,
        aliases=(
            "adaptief onderstel",
            "adaptive suspension",
            "adaptief demping",
            "adaptive drive",
            "luchtvering",
        ),
    ),
    OptionDefinition(
        key="sport_wheels_19",
        label_nl="19 inch velgen",
        category=OptionCategory.EXTERIOR,
        importance=0.3,
        aliases=("19 inch", '19"', "19 inch velgen", "19 inch lichtmetaal"),
    ),
    # --- Towing -----------------------------------------------------------
    OptionDefinition(
        key="tow_bar",
        label_nl="Trekhaak",
        category=OptionCategory.TOWING,
        importance=0.5,
        aliases=("trekhaak", "tow bar", "towbar", "afneembare trekhaak"),
    ),
)


def _lookup_key(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    without_accents = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]", "", without_accents.lower())


_ALIAS_INDEX: dict[str, OptionDefinition] = {}
for _definition in OPTION_TAXONOMY:
    for _alias in (_definition.key, _definition.label_nl, *_definition.aliases):
        _ALIAS_INDEX.setdefault(_lookup_key(_alias), _definition)

OPTIONS_BY_KEY: dict[str, OptionDefinition] = {
    definition.key: definition for definition in OPTION_TAXONOMY
}


def resolve_option(raw_text: str | None) -> OptionDefinition | None:
    """Resolve raw option text to a canonical definition, or None if unknown.

    Unknown text is never force-fitted to the nearest option: a missing mapping
    should surface as incomplete option data (which lowers confidence) rather
    than as a wrong equipment match.
    """
    if not raw_text:
        return None
    return _ALIAS_INDEX.get(_lookup_key(raw_text))


def split_option_texts(
    raw_texts: list[str],
) -> tuple[list[tuple[OptionDefinition, str]], list[str], list[str]]:
    """Split raw option texts into equipment options, trim packages and leftovers.

    Returns (options, trim_labels, unresolved), where each option is paired with
    the raw text that produced it so the mapping stays traceable. Trim packages
    are returned separately because they belong on the vehicle's trim field;
    counting them as equipment as well would let one package influence the
    valuation twice.
    """
    options: list[tuple[OptionDefinition, str]] = []
    trim_labels: list[str] = []
    unresolved: list[str] = []
    seen: set[str] = set()

    for raw_text in raw_texts:
        definition = resolve_option(raw_text)
        if definition is None:
            unresolved.append(raw_text)
            continue
        if definition.key in seen:
            continue
        seen.add(definition.key)
        if definition.category is OptionCategory.TRIM_PACKAGE:
            trim_labels.append(definition.label_nl)
        else:
            options.append((definition, raw_text))

    return options, trim_labels, unresolved
