"""Health endpoint.

Reports whether the core dependencies are reachable. The API is considered
healthy even when the local AI is down, because valuation never depends on it.
"""

from __future__ import annotations

from typing import Literal

import httpx
from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text

from echte_auto_waarde.config import get_settings
from echte_auto_waarde.db.session import engine

router = APIRouter(tags=["system"])


class ComponentStatus(BaseModel):
    name: str
    available: bool
    detail: str | None = None


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    components: list[ComponentStatus]


def _check_database() -> ComponentStatus:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return ComponentStatus(name="database", available=True)
    except Exception as exc:  # pragma: no cover - defensive
        return ComponentStatus(name="database", available=False, detail=str(exc))


def _check_ai() -> ComponentStatus:
    settings = get_settings()
    if not settings.ai_enabled:
        return ComponentStatus(name="ai", available=False, detail="disabled by configuration")
    try:
        response = httpx.get(f"{settings.ollama_base_url}/api/tags", timeout=2.0)
        response.raise_for_status()
        return ComponentStatus(name="ai", available=True, detail=settings.ollama_model)
    except Exception:
        return ComponentStatus(name="ai", available=False, detail="Ollama not reachable")


def _check_enrichment() -> ComponentStatus:
    """Report the plate-enrichment switch, without using it.

    Deliberately no request: this is the only outbound call the application can
    make, and a health check is not a reason to reach the network — least of all
    on an endpoint something might poll.
    """
    settings = get_settings()
    if not settings.rdw_enabled:
        return ComponentStatus(
            name="plate_enrichment", available=False, detail="disabled by configuration"
        )
    return ComponentStatus(
        name="plate_enrichment", available=True, detail=f"enabled ({settings.rdw_base_url})"
    )


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    components = [_check_database(), _check_ai(), _check_enrichment()]
    database_ok = components[0].available
    return HealthResponse(
        status="ok" if database_ok else "degraded",
        version="0.1.0",
        components=components,
    )
