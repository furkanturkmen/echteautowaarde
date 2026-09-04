import pytest

from echte_auto_waarde.domain import normalization
from echte_auto_waarde.models.enums import BodyType, Drivetrain, FuelType, Transmission


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("BMW", "BMW"),
        ("bmw", "BMW"),
        ("B.M.W.", "BMW"),
        ("  b m w ", "BMW"),
        ("VW", "Volkswagen"),
        ("volkswagen", "Volkswagen"),
        ("Mercedes", "Mercedes-Benz"),
        ("mercedes-benz", "Mercedes-Benz"),
    ],
)
def test_make_aliases_collapse_to_one_canonical_value(raw: str, expected: str) -> None:
    assert normalization.normalize_make(raw) == expected


def test_unknown_make_is_cleaned_up_rather_than_guessed() -> None:
    assert normalization.normalize_make("  koenigsegg ") == "Koenigsegg"
    assert normalization.normalize_make(None) == "Unknown"


@pytest.mark.parametrize(
    ("make", "raw", "expected"),
    [
        ("BMW", "3 Serie", "3 Serie"),
        ("BMW", "3-serie", "3 Serie"),
        ("BMW", "3 Series", "3 Serie"),
        # Engine variants are frequently written as if they were the model.
        ("BMW", "330e", "3 Serie"),
        ("Mercedes-Benz", "C-Class", "C-Klasse"),
        ("Mercedes-Benz", "C Klasse", "C-Klasse"),
        ("Tesla", "model 3", "Model 3"),
    ],
)
def test_model_aliases_collapse_to_one_canonical_value(make: str, raw: str, expected: str) -> None:
    assert normalization.normalize_model(make, raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Automaat", Transmission.AUTOMATIC),
        ("automatic", Transmission.AUTOMATIC),
        ("AUTO", Transmission.AUTOMATIC),
        ("DSG", Transmission.AUTOMATIC),
        ("Handgeschakeld", Transmission.MANUAL),
        ("manual", Transmission.MANUAL),
        ("", Transmission.UNKNOWN),
        ("teleportatie", Transmission.UNKNOWN),
    ],
)
def test_transmission_normalization(raw: str, expected: Transmission) -> None:
    assert normalization.normalize_transmission(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Plug-in hybride", FuelType.PLUGIN_HYBRID),
        ("plugin hybrid", FuelType.PLUGIN_HYBRID),
        ("PHEV", FuelType.PLUGIN_HYBRID),
        ("Hybride", FuelType.HYBRID),
        ("Benzine", FuelType.PETROL),
        ("Elektrisch", FuelType.ELECTRIC),
        ("Diesel", FuelType.DIESEL),
    ],
)
def test_fuel_normalization_separates_hybrid_from_plugin_hybrid(
    raw: str, expected: FuelType
) -> None:
    assert normalization.normalize_fuel_type(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Touring", BodyType.STATIONWAGON),
        ("Avant", BodyType.STATIONWAGON),
        ("Estate", BodyType.STATIONWAGON),
        ("Variant", BodyType.STATIONWAGON),
        # The Dutch spelling, and exactly what RDW publishes.
        ("Stationwagen", BodyType.STATIONWAGON),
        ("stationwagon", BodyType.STATIONWAGON),
        ("Sedan", BodyType.SEDAN),
        ("Limousine", BodyType.SEDAN),
        ("Hatchback", BodyType.HATCHBACK),
    ],
)
def test_body_type_normalization(raw: str, expected: BodyType) -> None:
    assert normalization.normalize_body_type(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("quattro", Drivetrain.AWD),
        ("xDrive", Drivetrain.AWD),
        ("4MATIC", Drivetrain.AWD),
        ("Dual Motor", Drivetrain.AWD),
        ("Achterwielaandrijving", Drivetrain.RWD),
        ("Voorwielaandrijving", Drivetrain.FWD),
    ],
)
def test_drivetrain_normalization(raw: str, expected: Drivetrain) -> None:
    assert normalization.normalize_drivetrain(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("M Sport", "M Sport"),
        ("m-sport", "M Sport"),
        ("M Sportpakket", "M Sport"),
        ("AMG Line", "AMG Line"),
        ("s line", "S line"),
        ("R-Line", "R-Line"),
    ],
)
def test_trim_normalization(raw: str, expected: str) -> None:
    assert normalization.normalize_trim(raw) == expected


def test_appearance_package_is_not_turned_into_a_performance_model() -> None:
    # "330e M Sport" must never normalize into anything resembling an M3.
    assert normalization.normalize_trim("M Sport") == "M Sport"
    assert normalization.normalize_model("BMW", "M3") == "M3"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("K-123-AB", "K123AB"),
        ("k123ab", "K123AB"),
        (" KL 12 AB ", "KL12AB"),
        (None, None),
        ("---", None),
    ],
)
def test_license_plate_normalization(raw: str | None, expected: str | None) -> None:
    assert normalization.normalize_license_plate(raw) == expected


# --- Finding a trim inside a longer description ------------------------------
#
# Dealer listings name the package in the title rather than in a field of its
# own, so it has to be recognised within the text.


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1.5 eTSI Life Business AUTOMAAT", "Life"),
        ("1.0 eTSI 110pk DSG Life", "Life"),
        ("2.0 TSI GTI", "GTI"),
        ("1.5 eTSI R-Line Business 150 pk", "R-Line"),
        ("Variant 1.5 eTSI Style", "Style"),
        ("1.4 eHybrid GTE", "GTE"),
        ("330e M Sport", "M Sport"),
    ],
)
def test_a_trim_is_found_inside_a_longer_description(text: str, expected: str) -> None:
    assert normalization.find_trim(text) == expected


def test_a_longer_package_name_wins_over_the_word_it_contains() -> None:
    """ "Business Edition" must not be read as "Business"."""
    assert normalization.find_trim("2.0 TDI Business Edition") == "Business Edition"


def test_the_leftmost_package_wins() -> None:
    """A title names the trim before it lists the equipment."""
    assert normalization.find_trim("1.5 eTSI Style met Business pakket") == "Style"


@pytest.mark.parametrize("text", ["2.9 TFSI RS 5 quattro", "1.0 TSI 110 pk", "", None])
def test_unknown_wording_yields_no_trim(text: str | None) -> None:
    """An unrecognised package lowers confidence rather than being invented."""
    assert normalization.find_trim(text) is None
