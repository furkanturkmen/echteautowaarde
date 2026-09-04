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


def test_health_reports_the_optional_components_without_using_them() -> None:
    """Enrichment state is reported from configuration, never by calling out.

    Health is polled; the register is the only outbound call this application
    can make, and a status endpoint is no reason to make it.
    """
    payload = client.get("/health").json()
    components = {component["name"]: component for component in payload["components"]}

    assert components["plate_enrichment"]["available"] is False
    assert components["plate_enrichment"]["detail"] == "disabled by configuration"
    # Neither optional component may drag the application's status down.
    assert payload["status"] == "ok"
