from fastapi.testclient import TestClient

from echte_auto_waarde.main import app

client = TestClient(app)


def test_health_reports_database_available() -> None:
    response = client.get("/health")
    assert response.status_code == 200

    payload = response.json()
    assert payload["status"] == "ok"

    components = {component["name"]: component for component in payload["components"]}
    assert components["database"]["available"] is True
    # AI availability is environment dependent and must never affect health status.
    assert "ai" in components
