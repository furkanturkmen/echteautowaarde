from dataclasses import replace

from echte_auto_waarde.domain.fingerprint import VehicleFingerprint
from echte_auto_waarde.domain.similarity import (
    DEFAULT_WEIGHTS,
    SimilarityWeights,
    score_similarity,
    unstated_factors,
)
from echte_auto_waarde.models.enums import BodyType, Drivetrain, FuelType, Transmission

TARGET = VehicleFingerprint(
    make="BMW",
    model="3 Serie",
    generation="G20",
    body_type=BodyType.SEDAN,
    fuel_type=FuelType.PLUGIN_HYBRID,
    transmission=Transmission.AUTOMATIC,
    drivetrain=Drivetrain.RWD,
    engine_description="330e",
    power_hp=292,
    year=2021,
    mileage_km=82_000,
    trim="M Sport",
    option_keys=frozenset({"panoramic_roof", "adaptive_cruise_control"}),
)


def _codes(entries: list[dict]) -> set[str]:
    return {entry["code"] for entry in entries}


def test_weights_sum_to_one() -> None:
    assert round(DEFAULT_WEIGHTS.total(), 6) == 1.0


def test_identical_vehicles_score_one() -> None:
    assert score_similarity(TARGET, TARGET).score == 1.0


def test_score_stays_within_bounds() -> None:
    very_different = VehicleFingerprint(
        make="BMW",
        model="3 Serie",
        generation="E90",
        body_type=BodyType.STATIONWAGON,
        fuel_type=FuelType.DIESEL,
        transmission=Transmission.MANUAL,
        drivetrain=Drivetrain.AWD,
        engine_description="320d",
        power_hp=163,
        year=2009,
        mileage_km=310_000,
        trim="Executive",
    )
    score = score_similarity(TARGET, very_different).score
    assert 0.0 <= score <= 1.0


def test_same_car_with_more_mileage_scores_lower_but_stays_comparable() -> None:
    higher_mileage = replace(TARGET, mileage_km=TARGET.mileage_km + 30_000)
    result = score_similarity(TARGET, higher_mileage)

    assert 0.8 < result.score < 1.0
    assert "MILEAGE_DIFFERENCE" in _codes(result.differences)
    difference = next(
        entry for entry in result.differences if entry["code"] == "MILEAGE_DIFFERENCE"
    )
    assert difference["delta"] == 30_000


def test_different_powertrain_costs_more_than_a_year_of_age() -> None:
    one_year_older = replace(TARGET, year=2020)
    diesel = replace(TARGET, fuel_type=FuelType.DIESEL, engine_description="320d")

    assert score_similarity(TARGET, diesel).score < score_similarity(TARGET, one_year_older).score


def test_related_powertrains_score_between_identical_and_unrelated() -> None:
    hybrid = replace(TARGET, fuel_type=FuelType.HYBRID)
    diesel = replace(TARGET, fuel_type=FuelType.DIESEL)

    identical = score_similarity(TARGET, TARGET).score
    related = score_similarity(TARGET, hybrid).score
    unrelated = score_similarity(TARGET, diesel).score

    assert unrelated < related < identical


def test_reasons_describe_what_matches() -> None:
    result = score_similarity(TARGET, replace(TARGET, mileage_km=90_000))
    codes = _codes(result.reasons)

    assert {
        "SAME_GENERATION",
        "SAME_BODY_TYPE",
        "SAME_POWERTRAIN",
        "SAME_ENGINE",
        "SAME_TRANSMISSION",
        "SAME_TRIM",
        "SAME_YEAR",
    } <= codes


def test_differences_describe_what_does_not_match() -> None:
    other = replace(
        TARGET,
        year=2019,
        trim="Business Edition",
        transmission=Transmission.MANUAL,
        option_keys=frozenset({"panoramic_roof", "tow_bar"}),
    )
    result = score_similarity(TARGET, other)
    codes = _codes(result.differences)

    assert {
        "YEAR_DIFFERENCE",
        "DIFFERENT_TRIM",
        "DIFFERENT_TRANSMISSION",
        "EXTRA_OPTION",
        "MISSING_OPTION",
    } <= codes

    extra = next(entry for entry in result.differences if entry["code"] == "EXTRA_OPTION")
    assert extra["value"] == "tow_bar"
    missing = next(entry for entry in result.differences if entry["code"] == "MISSING_OPTION")
    assert missing["value"] == "adaptive_cruise_control"


def test_a_characteristic_neither_car_states_takes_no_part_in_the_score() -> None:
    """It cannot tell the two apart, so it is left out rather than half-scored."""
    unknown_generation = replace(TARGET, generation=None)
    result = score_similarity(TARGET, unknown_generation)

    assert "generation" not in result.components
    assert "generation" in result.unevaluated
    assert "SAME_GENERATION" not in _codes(result.reasons)
    assert "DIFFERENT_GENERATION" not in _codes(result.differences)


def test_an_unstated_characteristic_no_longer_caps_an_otherwise_perfect_match() -> None:
    """The compression this replaced: dealer listings state no generation,
    power or drivetrain, which held two identical cars well below a full match.
    """
    sparse = replace(TARGET, generation=None, power_hp=None, drivetrain=Drivetrain.UNKNOWN)

    assert score_similarity(sparse, sparse).score == 1.0


def test_the_remaining_weights_carry_the_score() -> None:
    """A mismatch weighs more once the unknown factors leave the average."""
    with_generation = replace(TARGET, trim="Executive")
    without_generation = replace(TARGET, trim="Executive", generation=None)

    full = score_similarity(TARGET, with_generation).score
    partial = score_similarity(replace(TARGET, generation=None), without_generation).score

    assert partial < full


def test_a_nearly_empty_description_cannot_score_a_full_match() -> None:
    """Renormalising must not reward having almost nothing to compare."""
    bare = VehicleFingerprint(make="BMW", model="3 Serie", year=2021, mileage_km=82_000)

    result = score_similarity(bare, bare)

    assert result.score < 1.0
    # Only year and mileage are known, so the floor, not the known weight, divides.
    assert round(result.score, 4) == round((0.12 + 0.14) / 0.5, 4)


def test_the_same_engine_written_two_ways_still_matches() -> None:
    """Dealers title one engine differently; the designation is what matters."""
    golf = VehicleFingerprint(
        make="Volkswagen", model="Golf", engine_description="1.0 eTSI 110pk DSG Life"
    )
    same_engine = replace(golf, engine_description="Variant 1.0 eTSI Life Business")
    other_engine = replace(golf, engine_description="1.5 eTSI R-Line Business 150 PK")

    assert score_similarity(golf, same_engine).components["engine"] == 1.0
    assert score_similarity(golf, other_engine).components["engine"] == 0.0
    assert "SAME_ENGINE" in _codes(score_similarity(golf, same_engine).reasons)


def test_engines_without_a_designation_are_still_compared_whole() -> None:
    """ "330e" and "45 TFSI quattro" name no displacement and family."""
    assert (
        score_similarity(TARGET, replace(TARGET, engine_description="320i")).components["engine"]
        == 0.0
    )
    assert score_similarity(TARGET, TARGET).components["engine"] == 1.0


def test_two_cars_that_both_list_no_options_are_not_a_match_on_equipment() -> None:
    """A source that publishes no options looks exactly like a car with none."""
    no_options = replace(TARGET, option_keys=frozenset())

    result = score_similarity(no_options, no_options)

    assert "options" not in result.components
    assert "options" in result.unevaluated


def test_important_options_weigh_more_than_trivial_ones() -> None:
    without_panoramic = replace(TARGET, option_keys=frozenset({"adaptive_cruise_control"}))
    without_parking_sensors = replace(
        TARGET,
        option_keys=frozenset({"panoramic_roof", "adaptive_cruise_control"}),
    )
    with_extra_trivial = replace(
        TARGET,
        option_keys=frozenset({"panoramic_roof", "adaptive_cruise_control", "parking_sensors"}),
    )

    missing_important = score_similarity(TARGET, without_panoramic).components["options"]
    extra_trivial = score_similarity(TARGET, with_extra_trivial).components["options"]
    exact = score_similarity(TARGET, without_parking_sensors).components["options"]

    assert missing_important < extra_trivial < exact == 1.0


def test_weights_are_configurable_per_search() -> None:
    higher_mileage = replace(TARGET, mileage_km=TARGET.mileage_km + 40_000)
    mileage_matters = SimilarityWeights(
        generation=0.05,
        body_type=0.05,
        fuel_type=0.10,
        engine=0.05,
        power=0.05,
        transmission=0.05,
        drivetrain=0.05,
        year=0.05,
        mileage=0.50,
        trim=0.03,
        options=0.02,
    )

    default_score = score_similarity(TARGET, higher_mileage).score
    weighted_score = score_similarity(TARGET, higher_mileage, mileage_matters).score

    assert weighted_score < default_score


def test_a_target_reports_what_it_does_not_state() -> None:
    """Heaviest first, so an interface can name the few that matter most."""
    assert unstated_factors(TARGET) == ()

    thin = VehicleFingerprint(make="BMW", model="3 Serie", year=2020, mileage_km=70_000)
    missing = unstated_factors(thin)

    assert "fuel_type" in missing and "engine" in missing
    assert "year" not in missing and "mileage" not in missing
    # Fuel carries the most weight of anything it leaves blank.
    assert missing[0] == "fuel_type"
