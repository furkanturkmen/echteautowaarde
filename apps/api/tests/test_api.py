"""API tests.

Each test runs against a freshly seeded in-memory synthetic market, so the API
is exercised end to end (normalization, comparables, valuation, confidence)
without touching the developer's database or the network.
"""

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from echte_auto_waarde.data_sources.synthetic import SyntheticDataSource
from echte_auto_waarde.db.session import get_session
from echte_auto_waarde.main import app
from echte_auto_waarde.models.listing import Listing
from echte_auto_waarde.models.vehicle import Vehicle
from echte_auto_waarde.services.ingestion import ingest


@pytest.fixture
def client(session: Session) -> Generator[TestClient, None, None]:
    ingest(session, SyntheticDataSource())
    session.commit()

    app.dependency_overrides[get_session] = lambda: session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _bmw_330e(session: Session) -> Vehicle:
    return session.scalars(
        select(Vehicle).where(
            Vehicle.engine_description == "330e",
            Vehicle.trim == "M Sport",
        )
    ).first()


def test_health_stays_ok_without_local_ai(client: TestClient) -> None:
    payload = client.get("/health").json()
    components = {component["name"]: component for component in payload["components"]}

    # AI is optional by design: its absence must never degrade the API.
    assert payload["status"] == "ok"
    assert components["database"]["available"] is True


def test_get_vehicle_returns_normalized_data(client: TestClient, session: Session) -> None:
    vehicle = _bmw_330e(session)
    payload = client.get(f"/vehicles/{vehicle.id}").json()

    assert payload["make"] == "BMW"
    assert payload["model"] == "3 Serie"
    assert payload["fuelType"] == "PLUGIN_HYBRID"
    assert payload["options"]


def test_unknown_vehicle_returns_404(client: TestClient) -> None:
    assert client.get("/vehicles/999999").status_code == 404


def test_lookup_by_license_plate(client: TestClient, session: Session) -> None:
    vehicle = _bmw_330e(session)
    # Plates are normalized, so separators and case must not matter.
    plate = vehicle.license_plate
    formatted = f"{plate[:2]}-{plate[2:5]}-{plate[5:]}".lower()

    payload = client.get(f"/vehicles/plate/{formatted}").json()
    assert payload["id"] == vehicle.id


def test_unknown_plate_tells_the_user_what_to_do(client: TestClient) -> None:
    response = client.get("/vehicles/plate/ZZ-999-Z")

    assert response.status_code == 404
    assert "manually" in response.json()["detail"]


def test_manual_vehicle_is_normalized_on_entry(client: TestClient) -> None:
    response = client.post(
        "/vehicles/manual",
        json={
            "make": "bmw",
            "model": "3-serie",
            "year": 2021,
            "mileageKm": 82_000,
            "trim": "m-sport",
            "generation": "G20",
            "bodyType": "Sedan",
            "fuelType": "Plug-in hybride",
            "transmission": "Automaat",
            "engineDescription": "330e",
            "optionTexts": ["panoramadak", "ACC"],
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["make"] == "BMW"
    assert payload["model"] == "3 Serie"
    assert payload["trim"] == "M Sport"
    assert {option["key"] for option in payload["options"]} == {
        "panoramic_roof",
        "adaptive_cruise_control",
    }


def test_manual_vehicle_rejects_invalid_input(client: TestClient) -> None:
    response = client.post("/vehicles/manual", json={"make": "", "model": "Golf"})
    assert response.status_code == 422


def test_comparable_search_returns_the_evidence(client: TestClient, session: Session) -> None:
    vehicle = _bmw_330e(session)
    payload = client.post("/comparables/search", json={"vehicleId": vehicle.id}).json()

    assert payload["comparableCount"] > 0
    assert payload["candidatesConsidered"] >= payload["comparableCount"]
    assert payload["wideningDescription"]

    first = payload["comparables"][0]
    assert 0.0 <= first["similarity"] <= 1.0
    assert first["vehicle"]["make"] == "BMW"
    assert first["reasons"]


def test_comparable_search_honours_required_options(client: TestClient, session: Session) -> None:
    vehicle = _bmw_330e(session)
    payload = client.post(
        "/comparables/search",
        json={
            "vehicleId": vehicle.id,
            "criteria": {"requiredOptionKeys": ["tow_bar"], "minSimilarity": 0.3},
        },
    ).json()

    for comparable in payload["comparables"]:
        assert "tow_bar" in {option["key"] for option in comparable["vehicle"]["options"]}


def test_valuation_returns_value_range_confidence_and_evidence(
    client: TestClient, session: Session
) -> None:
    vehicle = _bmw_330e(session)
    listing = session.scalars(select(Listing).where(Listing.vehicle_id == vehicle.id)).one()

    payload = client.post(
        "/valuations",
        json={"vehicleId": vehicle.id, "askingPriceCents": listing.asking_price_cents},
    ).json()

    assert payload["sufficientData"] is True
    assert payload["estimatedMarketValueCents"] > 0
    assert (
        payload["recommendedBuyPriceLowCents"]
        < payload["recommendedBuyPriceHighCents"]
        <= payload["estimatedMarketValueCents"]
    )
    assert payload["dealClassification"] in {
        "EXCELLENT_DEAL",
        "GOOD_DEAL",
        "FAIR_PRICE",
        "EXPENSIVE",
        "VERY_EXPENSIVE",
    }
    assert 0.0 <= payload["confidenceScore"] <= 1.0
    assert payload["confidenceFactors"]
    assert payload["comparables"]
    assert payload["marketStatistics"]["comparableCount"] == payload["comparableCount"]
    assert payload["algorithmVersion"] == "valuation-v0.1"
    # Synthetic data must never be presented as real market advice.
    assert "synthetische" in payload["dataDisclaimer"]


def test_valuation_without_asking_price_has_no_deal_classification(
    client: TestClient, session: Session
) -> None:
    vehicle = _bmw_330e(session)
    payload = client.post("/valuations", json={"vehicleId": vehicle.id}).json()

    assert payload["dealClassification"] is None
    assert payload["estimatedMarketValueCents"] > 0


def test_adjustments_explain_the_difference_from_the_market_basis(
    client: TestClient, session: Session
) -> None:
    vehicle = _bmw_330e(session)
    payload = client.post("/valuations", json={"vehicleId": vehicle.id}).json()

    total = sum(adjustment["amountCents"] for adjustment in payload["adjustments"])
    assert abs(payload["estimatedMarketValueCents"] - (payload["marketBasisCents"] + total)) < 100
    for adjustment in payload["adjustments"]:
        assert adjustment["reason"]


def test_a_vehicle_without_a_market_gets_no_fabricated_value(client: TestClient) -> None:
    payload = client.post(
        "/valuations",
        json={
            "manualVehicle": {
                "make": "Lancia",
                "model": "Delta",
                "year": 1992,
                "mileageKm": 120_000,
                "fuelType": "Benzine",
                "transmission": "Handgeschakeld",
            }
        },
    ).json()

    assert payload["sufficientData"] is False
    assert payload["estimatedMarketValueCents"] is None
    assert payload["insufficientDataReason"]


def test_a_stored_valuation_can_be_retrieved(client: TestClient, session: Session) -> None:
    vehicle = _bmw_330e(session)
    created = client.post(
        "/valuations", json={"vehicleId": vehicle.id, "askingPriceCents": 2_750_000}
    ).json()

    fetched = client.get(f"/valuations/{created['id']}").json()

    assert fetched["estimatedMarketValueCents"] == created["estimatedMarketValueCents"]
    assert fetched["confidenceScore"] == created["confidenceScore"]
    assert len(fetched["comparables"]) == len(created["comparables"])
    assert fetched["algorithmVersion"] == created["algorithmVersion"]


def test_valuation_requires_a_target(client: TestClient) -> None:
    response = client.post("/valuations", json={})
    assert response.status_code == 422


def test_listing_and_history_expose_observed_facts(client: TestClient, session: Session) -> None:
    listing = session.scalars(select(Listing)).first()

    detail = client.get(f"/listings/{listing.id}").json()
    assert detail["askingPriceCents"] == listing.asking_price_cents
    assert detail["dataSource"] == "synthetic"

    history = client.get(f"/listings/{listing.id}/history").json()
    assert history["snapshots"]
    assert history["daysListed"] >= 0
    # A price reduction shows up as a negative change, never as an inferred sale.
    assert history["priceChangeCents"] <= 0


def test_market_stats_describe_the_local_dataset(client: TestClient) -> None:
    payload = client.get("/market/stats").json()

    assert payload["listingCount"] == 100
    assert payload["makeCount"] == 5
    assert payload["medianPriceCents"] > 0
    assert payload["dataSources"] == ["synthetic"]
    assert payload["isSynthetic"] is True
