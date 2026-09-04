"""Plate enrichment tests.

Nothing here touches the network. The register is reached through one function,
`httpx.get`, which is replaced with a stub; the fixtures below are trimmed
copies of real responses, kept as data so the mapping is tested against the
shape the register actually publishes.

The behaviour these lock down is mostly what enrichment must *not* do: invent
mileage, invent a trim, overwrite what a user typed, or let a failed lookup take
the rest of the application with it.
"""

from __future__ import annotations

from datetime import date

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from echte_auto_waarde.data_sources.base import RawVehicle, VehicleSourceUnavailable
from echte_auto_waarde.data_sources.factory import get_vehicle_source
from echte_auto_waarde.data_sources.rdw import (
    DATASET_BODY,
    DATASET_FUEL,
    DATASET_VEHICLES,
    RdwVehicleSource,
    map_to_raw_vehicle,
)
from echte_auto_waarde.data_sources.synthetic import SyntheticDataSource
from echte_auto_waarde.db.session import get_session
from echte_auto_waarde.domain import normalization
from echte_auto_waarde.main import app
from echte_auto_waarde.models.enums import BodyType, FuelType, Transmission
from echte_auto_waarde.models.vehicle import Vehicle
from echte_auto_waarde.services import plate_lookup as plate_lookup_service
from echte_auto_waarde.services.ingestion import ingest
from echte_auto_waarde.services.plate_lookup import (
    PlateLookupStatus,
    apply_enrichment,
    lookup_plate,
)
from echte_auto_waarde.services.vehicles import create_manual_vehicle

# A real registration record, trimmed to the fields we map.
REGISTRATION = {
    "kenteken": "XF100F",
    "voertuigsoort": "Personenauto",
    "merk": "VOLKSWAGEN",
    "handelsbenaming": "GOLF",
    "inrichting": "stationwagen",
    "aantal_zitplaatsen": "5",
    "aantal_deuren": "5",
    "eerste_kleur": "GRIJS",
    "cilinderinhoud": "1197",
    "catalogusprijs": "29318",
    "datum_eerste_toelating": "20140602",
    "datum_eerste_toelating_dt": "2014-06-02T00:00:00.000",
    "europese_voertuigcategorie": "M1",
}

FUEL = [{"brandstof_omschrijving": "Benzine", "nettomaximumvermogen": "77.00"}]
BODY = [{"type_carrosserie_europese_omschrijving": "Stationwagen"}]

# A concrete mixer. Real plate, real record, and not a car.
TRUCK = {
    "kenteken": "BB100B",
    "voertuigsoort": "Bedrijfsauto",
    "merk": "VOLVO",
    "handelsbenaming": "FM",
    "inrichting": "betonmixer",
}


class FakeResponse:
    def __init__(self, payload, status_code: int = 200, text: str | None = None) -> None:
        self._payload = payload
        self.status_code = status_code
        self._text = text

    def json(self):
        if self._text is not None:
            raise ValueError("not json")
        return self._payload


def stub_register(monkeypatch, responses: dict[str, object], record_calls: list | None = None):
    """Answer register requests from a dict keyed by dataset id."""

    def fake_get(url, params=None, headers=None, timeout=None):
        if record_calls is not None:
            record_calls.append((url, params, headers, timeout))
        for dataset, response in responses.items():
            if dataset in url:
                if isinstance(response, Exception):
                    raise response
                return response if isinstance(response, FakeResponse) else FakeResponse(response)
        return FakeResponse([])

    monkeypatch.setattr(httpx, "get", fake_get)


@pytest.fixture
def source() -> RdwVehicleSource:
    return RdwVehicleSource(base_url="https://example.invalid/resource", timeout_seconds=1.0)


class StubSource:
    """A specification source with no HTTP underneath."""

    key = "rdw"
    name = "Kentekenregister (open data)"

    def __init__(self, vehicle: RawVehicle | None = None, error: Exception | None = None) -> None:
        self._vehicle = vehicle
        self._error = error
        self.calls: list[str] = []

    def fetch_vehicle(self, plate: str) -> RawVehicle | None:
        self.calls.append(plate)
        if self._error is not None:
            raise self._error
        return self._vehicle


GOLF_DRAFT = RawVehicle(
    make="VOLKSWAGEN",
    model="GOLF",
    year=2014,
    body_type="stationwagen",
    fuel_type="Benzine",
    power_kw=77,
    power_hp=105,
    engine_displacement_cc=1197,
    doors=5,
    seats=5,
    color="Grijs",
    catalog_price_cents=2_931_800,
    license_plate="XF100F",
)


@pytest.fixture
def client(session: Session):
    app.dependency_overrides[get_session] = lambda: session
    # No test may reach the network: the source is always supplied explicitly.
    app.dependency_overrides[get_vehicle_source] = lambda: None
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# --- 1. A valid plate maps onto a vehicle ------------------------------------


def test_valid_plate_maps_to_a_vehicle(source: RdwVehicleSource, monkeypatch) -> None:
    stub_register(
        monkeypatch,
        {DATASET_VEHICLES: [REGISTRATION], DATASET_FUEL: FUEL, DATASET_BODY: BODY},
    )

    raw = source.fetch_vehicle("XF100F")

    assert raw is not None
    assert (raw.make, raw.model, raw.year) == ("VOLKSWAGEN", "GOLF", 2014)
    assert raw.power_kw == 77
    # 77 kW in metric horsepower, rounded.
    assert raw.power_hp == 105
    assert raw.engine_displacement_cc == 1197
    assert raw.catalog_price_cents == 2_931_800
    assert raw.color == "Grijs"
    assert (raw.doors, raw.seats) == (5, 5)


def test_no_app_token_is_sent_unless_configured(source: RdwVehicleSource, monkeypatch) -> None:
    calls: list = []
    stub_register(monkeypatch, {DATASET_VEHICLES: [REGISTRATION]}, record_calls=calls)

    source.fetch_vehicle("XF100F")

    _, params, headers, timeout = calls[0]
    assert headers == {}
    assert params == {"kenteken": "XF100F"}
    assert timeout == 1.0


# --- 2. Plate normalization --------------------------------------------------


@pytest.mark.parametrize("written", ["XF-100-F", "xf100f", " XF 100 F ", "xf-100-f"])
def test_plate_normalization_reaches_the_register_in_register_form(
    written: str, source: RdwVehicleSource, monkeypatch
) -> None:
    """The register keys on a plate without separators."""
    calls: list = []
    stub_register(monkeypatch, {DATASET_VEHICLES: [REGISTRATION]}, record_calls=calls)

    source.fetch_vehicle(normalization.normalize_license_plate(written))

    assert calls[0][1] == {"kenteken": "XF100F"}


# --- 3. Not found ------------------------------------------------------------


def test_unknown_plate_returns_nothing(source: RdwVehicleSource, monkeypatch) -> None:
    stub_register(monkeypatch, {DATASET_VEHICLES: []})

    assert source.fetch_vehicle("ZZ999Z") is None


def test_a_lorry_is_not_a_vehicle_this_product_values(
    source: RdwVehicleSource, monkeypatch
) -> None:
    """BB-100-B is a real plate and a concrete mixer."""
    stub_register(monkeypatch, {DATASET_VEHICLES: [TRUCK]})

    assert source.fetch_vehicle("BB100B") is None


# --- 4-6. Unavailable, timeout, malformed ------------------------------------


def test_network_failure_is_reported_as_unavailable(source: RdwVehicleSource, monkeypatch) -> None:
    stub_register(monkeypatch, {DATASET_VEHICLES: httpx.ConnectError("no route")})

    with pytest.raises(VehicleSourceUnavailable):
        source.fetch_vehicle("XF100F")


def test_timeout_is_reported_as_unavailable(source: RdwVehicleSource, monkeypatch) -> None:
    stub_register(monkeypatch, {DATASET_VEHICLES: httpx.ReadTimeout("too slow")})

    with pytest.raises(VehicleSourceUnavailable) as error:
        source.fetch_vehicle("XF100F")
    assert "timed out" in str(error.value)


def test_http_error_status_is_reported_as_unavailable(
    source: RdwVehicleSource, monkeypatch
) -> None:
    stub_register(monkeypatch, {DATASET_VEHICLES: FakeResponse([], status_code=503)})

    with pytest.raises(VehicleSourceUnavailable):
        source.fetch_vehicle("XF100F")


def test_malformed_body_is_reported_as_unavailable(source: RdwVehicleSource, monkeypatch) -> None:
    stub_register(monkeypatch, {DATASET_VEHICLES: FakeResponse(None, text="<html>oops</html>")})

    with pytest.raises(VehicleSourceUnavailable):
        source.fetch_vehicle("XF100F")


def test_unexpected_json_shape_is_reported_as_unavailable(
    source: RdwVehicleSource, monkeypatch
) -> None:
    stub_register(monkeypatch, {DATASET_VEHICLES: FakeResponse({"error": "nope"})})

    with pytest.raises(VehicleSourceUnavailable):
        source.fetch_vehicle("XF100F")


def test_a_failing_detail_dataset_still_yields_the_registration(
    source: RdwVehicleSource, monkeypatch
) -> None:
    """Less data beats no data: the main record alone is already useful."""
    stub_register(
        monkeypatch,
        {
            DATASET_VEHICLES: [REGISTRATION],
            DATASET_FUEL: httpx.ConnectError("no route"),
            DATASET_BODY: httpx.ConnectError("no route"),
        },
    )

    raw = source.fetch_vehicle("XF100F")

    assert raw is not None
    assert raw.make == "VOLKSWAGEN"
    assert raw.power_hp is None
    assert raw.fuel_type == ""


# --- 7. Missing optional fields ----------------------------------------------


def test_missing_optional_fields_stay_missing() -> None:
    raw = map_to_raw_vehicle({"kenteken": "AA11BB", "merk": "SEAT"}, [], [])

    assert raw.make == "SEAT"
    assert raw.model == ""
    for absent in (
        raw.year,
        raw.power_hp,
        raw.doors,
        raw.seats,
        raw.color,
        raw.catalog_price_cents,
        raw.engine_displacement_cc,
    ):
        assert absent is None


def test_unregistered_colour_is_not_a_colour() -> None:
    raw = map_to_raw_vehicle({"eerste_kleur": "Niet geregistreerd"}, [], [])

    assert raw.color is None


def test_the_register_never_supplies_what_it_does_not_publish() -> None:
    """Mileage, trim, transmission, drivetrain and options are not in it."""
    raw = map_to_raw_vehicle(REGISTRATION, FUEL, BODY)

    assert raw.mileage_km is None
    assert raw.trim is None
    assert raw.transmission is None
    assert raw.drivetrain is None
    assert raw.option_texts == ()
    assert raw.engine_description is None


# --- 8-10. Enrichment of a stored vehicle ------------------------------------


@pytest.fixture
def manual_golf(session: Session) -> Vehicle:
    """A vehicle a user entered by hand, with gaps enrichment could fill."""
    vehicle = create_manual_vehicle(
        session,
        RawVehicle(
            make="Volkswagen",
            model="Golf",
            trim="Highline",
            mileage_km=136_269,
            transmission="Automaat",
            license_plate="XF-100-F",
            option_texts=("panoramadak",),
        ),
    )
    session.commit()
    return vehicle


def test_enrichment_fills_gaps_on_a_stored_vehicle(session: Session, manual_golf: Vehicle) -> None:
    filled = apply_enrichment(manual_golf, GOLF_DRAFT)

    assert manual_golf.year == 2014
    assert manual_golf.body_type is BodyType.STATIONWAGON
    assert manual_golf.fuel_type is FuelType.PETROL
    assert manual_golf.power_hp == 105
    assert set(filled) >= {"year", "body_type", "fuel_type", "power_hp"}


def test_absent_register_values_never_erase_stored_values(
    session: Session, manual_golf: Vehicle
) -> None:
    manual_golf.year = 2015
    manual_golf.color = "Blauw"

    apply_enrichment(manual_golf, RawVehicle(make="", model="", year=None, color=None))

    assert manual_golf.year == 2015
    assert manual_golf.color == "Blauw"


def test_manual_values_survive_enrichment(session: Session, manual_golf: Vehicle) -> None:
    """What the user typed wins, including where the register disagrees."""
    before_options = {option.definition.key for option in manual_golf.options}

    apply_enrichment(
        manual_golf,
        RawVehicle(
            make="SKODA",  # a different make; the stored one must survive
            model="OCTAVIA",
            trim="Style",
            mileage_km=10,
            year=2014,
        ),
    )

    assert manual_golf.make == "Volkswagen"
    assert manual_golf.model == "Golf"
    assert manual_golf.trim == "Highline"
    assert manual_golf.mileage_km == 136_269
    assert manual_golf.transmission is Transmission.AUTOMATIC
    assert {option.definition.key for option in manual_golf.options} == before_options


def test_a_complete_local_vehicle_costs_no_request(session: Session, manual_golf: Vehicle) -> None:
    """Specifications already stored are not fetched again."""
    from dataclasses import replace as replace_fields

    apply_enrichment(
        manual_golf, replace_fields(GOLF_DRAFT, first_registration_date=date(2014, 6, 2))
    )
    session.commit()
    stub = StubSource(GOLF_DRAFT)

    result = lookup_plate(session, "XF-100-F", stub)

    assert result.status is PlateLookupStatus.LOCAL
    assert stub.calls == []


def test_a_stored_vehicle_with_gaps_is_enriched_in_place(
    session: Session, manual_golf: Vehicle
) -> None:
    stub = StubSource(GOLF_DRAFT)

    result = lookup_plate(session, "XF-100-F", stub)

    assert result.status is PlateLookupStatus.LOCAL
    assert result.vehicle is manual_golf
    assert "year" in result.enriched_fields
    assert stub.calls == ["XF100F"]


def test_enrichment_failure_leaves_a_stored_vehicle_usable(
    session: Session, manual_golf: Vehicle
) -> None:
    stub = StubSource(error=VehicleSourceUnavailable("register down"))

    result = lookup_plate(session, "XF-100-F", stub)

    assert result.status is PlateLookupStatus.LOCAL
    assert result.vehicle is manual_golf
    assert result.enriched_fields == []


# --- 11-13. Normalization of register wording --------------------------------


def test_stationwagen_normalizes_to_the_estate_body_type() -> None:
    """The register spells it without the o, and this once mapped to UNKNOWN."""
    assert normalization.normalize_body_type("stationwagen") is BodyType.STATIONWAGON
    assert normalization.normalize_body_type("Stationwagen") is BodyType.STATIONWAGON


@pytest.mark.parametrize(
    ("wording", "expected"),
    [
        ("Benzine", FuelType.PETROL),
        ("Diesel", FuelType.DIESEL),
        ("Elektriciteit", FuelType.ELECTRIC),
        ("Waterstof", FuelType.ELECTRIC),
        ("LPG", FuelType.LPG),
        ("CNG", FuelType.LPG),
    ],
)
def test_register_fuel_wording_normalizes(wording: str, expected: FuelType) -> None:
    assert normalization.normalize_fuel_type(wording) is expected


def test_two_fuels_without_external_charging_is_a_hybrid() -> None:
    raw = map_to_raw_vehicle(
        REGISTRATION,
        [
            {"brandstof_omschrijving": "Benzine", "nettomaximumvermogen": "72.00"},
            {"brandstof_omschrijving": "Elektriciteit", "nettomaximumvermogen": "20.00"},
        ],
        [],
    )

    assert normalization.normalize_fuel_type(raw.fuel_type) is FuelType.HYBRID
    # The combustion figure describes the car, not the electric motor alone.
    assert raw.power_kw == 72


def test_external_charging_makes_it_a_plug_in_hybrid() -> None:
    raw = map_to_raw_vehicle(
        REGISTRATION,
        [
            {"brandstof_omschrijving": "Benzine", "nettomaximumvermogen": "135.00"},
            {
                "brandstof_omschrijving": "Elektriciteit",
                "nettomaximumvermogen": "80.00",
                "actie_radius_extern_opladen_wltp": "58",
            },
        ],
        [],
    )

    assert normalization.normalize_fuel_type(raw.fuel_type) is FuelType.PLUGIN_HYBRID


def test_registration_dates_map_to_a_date_and_a_year() -> None:
    from_iso = map_to_raw_vehicle(REGISTRATION, [], [])
    assert from_iso.first_registration_date is not None
    assert (from_iso.first_registration_date.isoformat(), from_iso.year) == ("2014-06-02", 2014)

    # The register also publishes the compact form; both must agree.
    compact_only = map_to_raw_vehicle({"datum_eerste_toelating": "20140602"}, [], [])
    assert compact_only.first_registration_date == from_iso.first_registration_date

    assert map_to_raw_vehicle({"datum_eerste_toelating": "niet bekend"}, [], []).year is None


# --- 14-16. The endpoint and the rest of the application ---------------------


def test_lookup_reports_what_the_user_still_has_to_supply(client: TestClient) -> None:
    app.dependency_overrides[get_vehicle_source] = lambda: StubSource(GOLF_DRAFT)

    body = client.get("/vehicles/plate/XF-100-F/lookup").json()

    assert body["status"] == "ENRICHED"
    assert body["draft"]["make"] == "VOLKSWAGEN"
    assert body["draft"]["year"] == 2014
    # The register has none of these, so the interface must ask for them.
    assert set(body["missingFields"]) == {"mileage_km", "transmission", "trim"}
    assert "handmatig" not in body["message"]


def test_lookup_of_an_unknown_plate_points_at_the_manual_route(client: TestClient) -> None:
    app.dependency_overrides[get_vehicle_source] = lambda: StubSource(None)

    response = client.get("/vehicles/plate/ZZ-999-Z/lookup")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "NOT_FOUND"
    assert body["draft"] is None
    assert "handmatig" in body["message"]


def test_lookup_degrades_when_the_register_is_unreachable(client: TestClient) -> None:
    app.dependency_overrides[get_vehicle_source] = lambda: StubSource(
        error=VehicleSourceUnavailable("down")
    )

    response = client.get("/vehicles/plate/XF-100-F/lookup")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "UNAVAILABLE"
    assert "handmatig" in body["message"]


def test_lookup_with_enrichment_switched_off_makes_no_call(client: TestClient) -> None:
    response = client.get("/vehicles/plate/XF-100-F/lookup")

    assert response.status_code == 200
    assert response.json()["status"] == "UNAVAILABLE"


def test_lookup_never_returns_market_data(client: TestClient) -> None:
    """The register publishes no prices, and none may appear in the response.

    Catalogue price is a registration fact from when the car was new, not a
    market value, and it is the only price the register knows.
    """
    app.dependency_overrides[get_vehicle_source] = lambda: StubSource(GOLF_DRAFT)

    body = client.get("/vehicles/plate/XF-100-F/lookup").json()

    for forbidden in ("askingPrice", "estimatedMarketValue", "marketValue", "comparables"):
        assert forbidden not in str(body)
    assert body["draft"]["catalogPriceCents"] == 2_931_800


def test_the_manual_route_still_works_after_a_failed_lookup(client: TestClient) -> None:
    app.dependency_overrides[get_vehicle_source] = lambda: StubSource(
        error=VehicleSourceUnavailable("down")
    )
    assert client.get("/vehicles/plate/XF-100-F/lookup").json()["status"] == "UNAVAILABLE"

    created = client.post(
        "/vehicles/manual",
        json={
            "make": "Volkswagen",
            "model": "Golf",
            "year": 2014,
            "mileageKm": 136269,
            "transmission": "Automaat",
            "trim": "Highline",
        },
    )

    assert created.status_code == 201
    assert created.json()["make"] == "Volkswagen"


def test_valuation_and_comparables_work_without_any_enrichment(
    client: TestClient, session: Session
) -> None:
    """Nothing in the valuation path depends on the register."""
    ingest(session, SyntheticDataSource())
    session.commit()
    vehicle = session.scalars(select(Vehicle)).first()

    response = client.post("/valuations", json={"vehicleId": vehicle.id})

    assert response.status_code == 200
    body = response.json()
    assert body["sufficientData"] is True
    assert body["comparableCount"] > 0


def test_the_register_source_is_not_a_listing_source() -> None:
    """It is deliberately not a `DataSourceAdapter`: it has no listings."""
    assert not hasattr(RdwVehicleSource, "fetch_listings")


def test_the_provenance_row_is_created_once(session: Session, manual_golf: Vehicle) -> None:
    first = plate_lookup_service.ensure_register_data_source(session)
    second = plate_lookup_service.ensure_register_data_source(session)

    assert first.id == second.id
    assert "RDW" not in first.name


# --- Demo data must never answer for a real plate ----------------------------
#
# BB-100-B is a real plate on a lorry, and the synthetic market happens to have
# invented the same plate for a fictional BMW. A consumer typing it must never
# be handed the fiction.

BB_PLATE = "BB-100-B"


@pytest.fixture
def synthetic_collision(session: Session) -> Vehicle:
    """A demo vehicle occupying a plate a real vehicle also uses."""
    ingest(session, SyntheticDataSource())
    demo = session.scalars(select(Vehicle).where(Vehicle.license_plate.is_not(None))).first()
    demo.license_plate = normalization.normalize_license_plate(BB_PLATE)
    session.commit()
    return demo


def test_a_collision_does_not_stop_the_register_from_being_asked(
    session: Session, synthetic_collision: Vehicle
) -> None:
    """1. Typed real plate + demo collision + enrichment on."""
    stub = StubSource(GOLF_DRAFT)

    result = lookup_plate(session, BB_PLATE, stub)

    assert result.status is PlateLookupStatus.ENRICHED
    assert result.vehicle is None
    assert result.draft is GOLF_DRAFT
    assert stub.calls == ["BB100B"]


def test_a_collision_without_enrichment_is_not_presented_as_the_real_car(
    session: Session, synthetic_collision: Vehicle
) -> None:
    """2. Same collision, enrichment off: say we could not look it up."""
    result = lookup_plate(session, BB_PLATE, None)

    assert result.status is PlateLookupStatus.UNAVAILABLE
    assert result.vehicle is None
    assert result.draft is None


def test_a_collision_the_register_does_not_know_is_not_found(
    session: Session, synthetic_collision: Vehicle
) -> None:
    """6. A lorry's plate returns nothing, never the fictional BMW."""
    stub = StubSource(None)  # the register has no passenger car for this plate

    result = lookup_plate(session, BB_PLATE, stub)

    assert result.status is PlateLookupStatus.NOT_FOUND
    assert result.vehicle is None
    assert result.draft is None


def test_a_valuation_cannot_be_requested_for_a_demo_plate(
    client: TestClient, synthetic_collision: Vehicle
) -> None:
    """6. The same rule on the path the homepage actually uses."""
    response = client.post("/valuations", json={"licensePlate": BB_PLATE})

    assert response.status_code == 404
    assert "manually" in response.json()["detail"]


def test_the_demo_flow_still_works_by_id(client: TestClient, synthetic_collision: Vehicle) -> None:
    """3. Examples are offered by id, and that route is untouched."""
    examples = client.get("/market/examples?limit=3").json()
    assert examples

    chosen = examples[0]
    valuation = client.post("/valuations", json={"vehicleId": chosen["vehicleId"]})

    assert valuation.status_code == 200
    assert valuation.json()["sufficientData"] is True
    assert client.get(f"/vehicles/{chosen['vehicleId']}").status_code == 200


def test_a_manually_stored_vehicle_keeps_local_first_behaviour(
    session: Session, manual_golf: Vehicle
) -> None:
    """4. A vehicle someone entered is real, and still enriched in place."""
    stub = StubSource(GOLF_DRAFT)

    result = lookup_plate(session, "XF-100-F", stub)

    assert result.status is PlateLookupStatus.LOCAL
    assert result.vehicle is manual_golf
    assert "year" in result.enriched_fields


def test_manual_values_survive_gap_filling_through_the_service(
    session: Session, manual_golf: Vehicle
) -> None:
    """5. XF-100-F: the register fills gaps and touches nothing else."""
    lookup_plate(session, "XF-100-F", StubSource(GOLF_DRAFT))

    # What the user typed.
    assert manual_golf.mileage_km == 136_269
    assert manual_golf.trim == "Highline"
    assert manual_golf.transmission is Transmission.AUTOMATIC
    # What the register added.
    assert manual_golf.year == 2014
    assert manual_golf.power_hp == 105
    assert manual_golf.catalog_price_cents == 2_931_800


def test_a_vehicle_without_listings_is_not_demo_data(
    session: Session, manual_golf: Vehicle
) -> None:
    """Provenance, not the absence of data, decides what counts as demo."""
    from echte_auto_waarde.services.vehicles import is_demo_vehicle

    assert is_demo_vehicle(manual_golf) is False


def test_enrichment_is_off_unless_it_is_switched_on() -> None:
    """The only outbound call the application can make is opt-in."""
    from echte_auto_waarde.config import Settings

    assert Settings().rdw_enabled is False
