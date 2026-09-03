from dataclasses import replace

from echte_auto_waarde.domain.comparables import (
    ComparableCandidate,
    ComparableCriteria,
    select_comparables,
)
from echte_auto_waarde.domain.fingerprint import VehicleFingerprint
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


def _candidate(index: int, fingerprint: VehicleFingerprint, price: int = 2_700_000):
    return ComparableCandidate(listing_id=index, fingerprint=fingerprint, asking_price_cents=price)


def _near_identical_group(size: int) -> list[ComparableCandidate]:
    return [
        _candidate(index, replace(TARGET, mileage_km=TARGET.mileage_km + index * 2_000))
        for index in range(size)
    ]


def test_strict_level_is_used_when_it_yields_enough_evidence() -> None:
    selection = select_comparables(TARGET, _near_identical_group(10))

    assert selection.widening_level == 0
    assert selection.count == 10


def test_search_widens_when_the_strict_level_is_too_thin() -> None:
    # Only diesel cars of the same generation exist: level 0 (same powertrain)
    # finds nothing, so the engine has to widen.
    candidates = [
        _candidate(
            index,
            replace(TARGET, fuel_type=FuelType.DIESEL, engine_description="320d", year=2020),
        )
        for index in range(10)
    ]

    selection = select_comparables(TARGET, candidates, ComparableCriteria(min_similarity=0.4))

    assert selection.widening_level == 2
    assert selection.count == 10
    # Widening must be visible in the result, never silent.
    assert "any generation" in selection.widening_description


def test_widening_stops_at_the_first_level_that_has_enough() -> None:
    strict = _near_identical_group(8)
    loose = [
        _candidate(100 + index, replace(TARGET, generation="F30", year=2018)) for index in range(10)
    ]

    selection = select_comparables(TARGET, strict + loose, ComparableCriteria(min_comparables=8))

    assert selection.widening_level == 0
    assert selection.count == 8


def test_candidates_below_the_similarity_threshold_are_rejected() -> None:
    weak = [
        _candidate(index, replace(TARGET, mileage_km=TARGET.mileage_km + 250_000))
        for index in range(5)
    ]

    selection = select_comparables(TARGET, weak, ComparableCriteria(min_similarity=0.99))

    assert selection.count == 0
    # An empty result still has to explain itself.
    assert selection.rejected_below_threshold == 5


def test_a_different_model_line_is_never_comparable() -> None:
    other_model = replace(TARGET, model="5 Serie")
    selection = select_comparables(TARGET, [_candidate(1, other_model)])

    assert selection.count == 0
    assert selection.rejected_by_requirements == 1
    # Every level was tried, so the broadest one is reported.
    assert selection.widening_level == 2


def test_results_are_ordered_by_similarity() -> None:
    candidates = [
        _candidate(1, replace(TARGET, mileage_km=140_000)),
        _candidate(2, replace(TARGET, mileage_km=84_000)),
        _candidate(3, replace(TARGET, mileage_km=110_000)),
    ]

    selection = select_comparables(TARGET, candidates, ComparableCriteria(min_comparables=3))
    scores = [item.score for item in selection.comparables]

    assert scores == sorted(scores, reverse=True)
    assert selection.comparables[0].candidate.listing_id == 2


def test_required_options_filter_out_cars_without_them() -> None:
    with_tow_bar = replace(TARGET, option_keys=TARGET.option_keys | {"tow_bar"})
    candidates = [_candidate(1, TARGET), _candidate(2, with_tow_bar)]

    selection = select_comparables(
        TARGET,
        candidates,
        ComparableCriteria(min_comparables=1, required_option_keys=frozenset({"tow_bar"})),
    )

    assert [item.candidate.listing_id for item in selection.comparables] == [2]


def test_transmission_can_be_required_to_match() -> None:
    manual = replace(TARGET, transmission=Transmission.MANUAL)
    candidates = [_candidate(1, manual), _candidate(2, TARGET)]

    selection = select_comparables(
        TARGET,
        candidates,
        ComparableCriteria(min_comparables=1, require_same_transmission=True),
    )

    assert [item.candidate.listing_id for item in selection.comparables] == [2]


def test_engine_can_be_required_to_match() -> None:
    other_engine = replace(TARGET, engine_description="320i", fuel_type=TARGET.fuel_type)
    candidates = [_candidate(1, other_engine), _candidate(2, TARGET)]

    selection = select_comparables(
        TARGET, candidates, ComparableCriteria(min_comparables=1, require_same_engine=True)
    )

    assert [item.candidate.listing_id for item in selection.comparables] == [2]


def test_result_size_is_capped() -> None:
    selection = select_comparables(
        TARGET, _near_identical_group(50), ComparableCriteria(max_comparables=12)
    )

    assert selection.count == 12


def test_empty_market_yields_an_empty_selection() -> None:
    selection = select_comparables(TARGET, [])

    assert selection.count == 0
    assert selection.candidates_considered == 0
