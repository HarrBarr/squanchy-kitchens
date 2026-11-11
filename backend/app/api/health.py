from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.storage.session import get_db

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
def health(db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> dict:
    try:
        db.execute(text("SELECT 1"))
        database = "ok"
    except Exception as exc:  # noqa: BLE001 - report, don't crash the probe
        database = f"down: {exc.__class__.__name__}"
    return {
        "status": "ok" if database == "ok" else "degraded",
        "database": database,
        "version": settings.app_version,
        "env": settings.app_env,
    }
