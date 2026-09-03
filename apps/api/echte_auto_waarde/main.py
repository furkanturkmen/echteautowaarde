"""FastAPI application factory for the Echte Auto Waarde API."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from echte_auto_waarde.api.routes import health
from echte_auto_waarde.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description=(
            "Local, zero-cost automotive market comparison and valuation API. "
            "All MVP market data is synthetic and unsuitable for real purchase decisions."
        ),
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    return app


app = create_app()
