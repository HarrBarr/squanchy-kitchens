import logging

from fastapi import FastAPI

from app.api import audit, auth, dashboard, fridges, health, registry, report, uploads, users
from app.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    app = FastAPI(
        title="Squanchy Kitchens API",
        version=settings.app_version,
        description=(
            "Fridge temperature-logger ingest for Squanchy Bakery: standardise raw exports, "
            "flag sensor errors, gaps and excursions above "
            f"{settings.alert_threshold_c}°C, and export the inspector report."
        ),
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )
    for r in (health, auth, users, registry, uploads, dashboard, fridges, report, audit):
        app.include_router(r.router)
    return app


app = create_app()
