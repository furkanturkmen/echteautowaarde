import pytest

from echte_auto_waarde.domain.options import (
    OPTION_TAXONOMY,
    OPTIONS_BY_KEY,
    resolve_option,
    split_option_texts,
)
from echte_auto_waarde.models.enums import OptionCategory


@pytest.mark.parametrize(
    "raw",
    [
        "Adaptive Cruise Control",
        "adaptieve cruise control",
        "adaptieve cruise",
        "ACC",
        "adaptive-cruise",
    ],
)
def test_option_aliases_resolve_to_one_canonical_option(raw: str) -> None:
    definition = resolve_option(raw)
    assert definition is not None
    assert definition.key == "adaptive_cruise_control"


@pytest.mark.parametrize(
    ("raw", "expected_key"),
    [
        ("panoramadak", "panoramic_roof"),
        ("Panorama schuifdak", "panoramic_roof"),
        ("Harman Kardon", "premium_audio"),
        ("Burmester", "premium_audio"),
        ("HUD", "head_up_display"),
        ("trekhaak", "tow_bar"),
        ("Matrix LED", "matrix_led"),
    ],
)
def test_option_resolution_across_wordings(raw: str, expected_key: str) -> None:
    definition = resolve_option(raw)
    assert definition is not None
    assert definition.key == expected_key


def test_unknown_option_text_is_not_force_fitted() -> None:
    # Unresolved text must surface as missing data, never as a wrong match.
    assert resolve_option("achterbank verwarmde bekerhouder") is None
    assert resolve_option("") is None
    assert resolve_option(None) is None


def test_options_are_not_equally_important() -> None:
    panoramic = OPTIONS_BY_KEY["panoramic_roof"]
    parking_sensors = OPTIONS_BY_KEY["parking_sensors"]
    assert panoramic.importance > parking_sensors.importance


def test_every_option_has_a_usable_importance() -> None:
    for definition in OPTION_TAXONOMY:
        assert 0.0 < definition.importance <= 1.0
        assert definition.label_nl


def test_option_keys_are_unique() -> None:
    keys = [definition.key for definition in OPTION_TAXONOMY]
    assert len(keys) == len(set(keys))


def test_split_separates_trim_packages_from_equipment() -> None:
    options, trims, unresolved = split_option_texts(
        ["M Sport", "panoramadak", "ACC", "iets onbekends"]
    )

    option_keys = [definition.key for definition, _ in options]
    assert option_keys == ["panoramic_roof", "adaptive_cruise_control"]
    # A package belongs on the trim field, not in the option list: counting it in
    # both places would let one package influence the valuation twice.
    assert trims == ["M Sport"]
    assert unresolved == ["iets onbekends"]
    assert all(definition.category is not OptionCategory.TRIM_PACKAGE for definition, _ in options)


def test_split_keeps_the_raw_text_that_produced_each_option() -> None:
    options, _, _ = split_option_texts(["adaptieve cruise"])
    definition, raw_text = options[0]
    assert definition.key == "adaptive_cruise_control"
    assert raw_text == "adaptieve cruise"


def test_split_deduplicates_repeated_wordings() -> None:
    options, _, _ = split_option_texts(["ACC", "adaptive cruise control"])
    assert len(options) == 1
