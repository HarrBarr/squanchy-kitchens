from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import Settings, get_settings
from app.ingest import ImportRejected, import_file
from app.storage.models import Upload
from app.storage.session import get_db

router = APIRouter(prefix="/api", tags=["uploads"])


class ImportSummaryOut(BaseModel):
    logger: str
    filename: str
    sha256: str
    already_imported: bool
    upload_id: int | None
    rows_in_file: int
    inserted: int
    updated: int
    unchanged: int
    duplicates: int
    sensor_errors: int
    rejected_lines: int
    unassigned_rows: int
    excursions: int
    spikes: int
    gaps: int
    first_reading_local: datetime | None
    last_reading_local: datetime | None
    warnings: list[str]


class UploadOut(BaseModel):
    id: int
    logger: str
    original_filename: str
    sha256: str
    row_count: int
    error_count: int
    status: str
    started_at: datetime
    finished_at: datetime | None
    note: str | None


@router.post("/uploads", response_model=ImportSummaryOut)
def upload(
    file: UploadFile = File(...),
    logger_id: str = Form(..., description="Logger code, e.g. TL-0231"),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ImportSummaryOut:
    limit = settings.max_upload_mb * 1024 * 1024
    data = file.file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(413, f"File is larger than {settings.max_upload_mb} MB.")
    if not data.strip():
        raise HTTPException(422, "The file is empty.")
    try:
        summary = import_file(db, settings, file.filename or "upload.csv", data, logger_id)
    except ImportRejected as exc:
        db.rollback()
        raise HTTPException(422, str(exc)) from exc
    return ImportSummaryOut(**summary.__dict__)


@router.get("/uploads", response_model=list[UploadOut])
def list_uploads(db: Session = Depends(get_db)) -> list[UploadOut]:
    rows = db.scalars(
        select(Upload).options(selectinload(Upload.logger)).order_by(Upload.id.desc()).limit(500)
    )
    return [
        UploadOut(
            id=u.id,
            logger=u.logger.logger_code,
            original_filename=u.original_filename,
            sha256=u.sha256,
            row_count=u.row_count,
            error_count=u.error_count,
            status=u.status,
            started_at=u.started_at,
            finished_at=u.finished_at,
            note=u.note,
        )
        for u in rows
    ]
