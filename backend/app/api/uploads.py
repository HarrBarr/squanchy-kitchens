"""Uploads: import a raw logger file, history, and the flag -> review -> void lifecycle.

* Anyone signed in may upload, but a branch manager only files whose every reading belongs
  to their branch on that date (checked in ``app.ingest``; otherwise 403, nothing imported).
* The owner (or an admin) can flag an upload as "uploaded by mistake". It stays visible.
* Only an admin can dismiss a flag or void an upload. A void is a soft delete: the row, the
  readings and the original file stay; excursions are recomputed without it.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.auth import (
    BranchScope,
    active_user,
    admin_user,
    audit,
    branch_scope,
    forbidden,
    utcnow,
)
from app.config import Settings, get_settings
from app.ingest import ImportForbidden, ImportRejected, import_file, void_upload
from app.storage.models import (
    ROLE_ADMIN,
    UPLOAD_ACTIVE,
    UPLOAD_FLAGGED,
    UPLOAD_VOIDED,
    Logger,
    Upload,
    User,
)
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
    branch: str | None
    original_filename: str
    sha256: str
    row_count: int
    error_count: int
    status: str  # active | flagged_mistake | voided
    started_at: datetime
    finished_at: datetime | None
    note: str | None
    uploaded_by_id: int | None
    uploaded_by: str | None
    flag_reason: str | None
    flagged_by: str | None
    flagged_at: datetime | None
    void_reason: str | None
    voided_by: str | None
    voided_at: datetime | None


class ReasonIn(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)


class PendingCount(BaseModel):
    count: int


def _out(u: Upload) -> UploadOut:
    return UploadOut(
        id=u.id,
        logger=u.logger.logger_code,
        branch=u.branch.name if u.branch else None,
        original_filename=u.original_filename,
        sha256=u.sha256,
        row_count=u.row_count,
        error_count=u.error_count,
        status=u.status,
        started_at=u.started_at,
        finished_at=u.finished_at,
        note=u.note,
        uploaded_by_id=u.uploaded_by,
        uploaded_by=u.uploader.full_name if u.uploader else None,
        flag_reason=u.flag_reason,
        flagged_by=u.flagger.full_name if u.flagger else None,
        flagged_at=u.flagged_at,
        void_reason=u.void_reason,
        voided_by=u.voider.full_name if u.voider else None,
        voided_at=u.voided_at,
    )


def _query():  # noqa: ANN202
    return select(Upload).options(
        selectinload(Upload.logger),
        selectinload(Upload.branch),
        selectinload(Upload.uploader),
        selectinload(Upload.flagger),
        selectinload(Upload.voider),
    )


def _get_upload(db: Session, upload_id: int, user: User) -> Upload:
    u = db.scalar(_query().where(Upload.id == upload_id))
    if u is None:
        raise HTTPException(404, "Upload not found.")
    if user.role != ROLE_ADMIN and u.branch_id != user.branch_id:
        raise forbidden("This upload belongs to another branch.")
    return u


@router.post("/uploads", response_model=ImportSummaryOut)
def upload(
    file: UploadFile = File(...),
    logger_id: str = Form(..., description="Logger code, e.g. TL-0231"),
    user: User = Depends(active_user),
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
        summary = import_file(
            db, settings, file.filename or "upload.csv", data, logger_id, user=user
        )
    except ImportForbidden as exc:
        db.rollback()
        raise forbidden(str(exc)) from exc
    except ImportRejected as exc:
        db.rollback()
        raise HTTPException(422, str(exc)) from exc
    if not summary.already_imported:
        audit(
            db,
            user,
            "upload.created",
            "upload",
            summary.upload_id,
            logger=summary.logger,
            filename=summary.filename,
            rows=summary.rows_in_file,
            excursions=summary.excursions,
        )
        db.commit()
    return ImportSummaryOut(**summary.__dict__)


@router.get("/uploads", response_model=list[UploadOut])
def list_uploads(
    status: str | None = Query(None, description="active | flagged_mistake | voided"),
    logger: str | None = Query(None, description="Logger code"),
    scope: BranchScope = Depends(branch_scope),
    db: Session = Depends(get_db),
) -> list[UploadOut]:
    """Upload history, newest first. Branch managers see their branch only."""
    q = _query().order_by(Upload.id.desc()).limit(500)
    if scope.branch_id is not None:
        q = q.where(Upload.branch_id == scope.branch_id)
    if status:
        q = q.where(Upload.status == status)
    if logger:
        q = q.join(Logger, Logger.id == Upload.logger_id).where(
            Logger.logger_code == logger.strip().upper()
        )
    return [_out(u) for u in db.scalars(q)]


@router.get("/uploads/pending-review", response_model=list[UploadOut])
def pending_review(_: User = Depends(admin_user), db: Session = Depends(get_db)) -> list[UploadOut]:
    """Uploads flagged as 'uploaded by mistake', oldest flag first. Admin only."""
    q = _query().where(Upload.status == UPLOAD_FLAGGED).order_by(Upload.flagged_at)
    return [_out(u) for u in db.scalars(q)]


@router.get("/uploads/pending-review/count", response_model=PendingCount)
def pending_review_count(
    _: User = Depends(admin_user), db: Session = Depends(get_db)
) -> PendingCount:
    """For the badge in Summer's toolbar."""
    n = db.scalar(select(func.count(Upload.id)).where(Upload.status == UPLOAD_FLAGGED))
    return PendingCount(count=n or 0)


@router.post("/uploads/{upload_id}/flag", response_model=UploadOut)
def flag_upload(
    upload_id: int,
    body: ReasonIn,
    user: User = Depends(active_user),
    db: Session = Depends(get_db),
) -> UploadOut:
    """Flag an upload as 'uploaded by mistake' for Summer to review. A branch manager may
    flag only their own uploads. The data stays on the dashboard until it is voided."""
    u = _get_upload(db, upload_id, user)
    if user.role != ROLE_ADMIN and u.uploaded_by != user.id:
        raise forbidden("You can only flag files you uploaded yourself.")
    if u.status == UPLOAD_VOIDED:
        raise HTTPException(409, "This upload was already voided.")
    u.status = UPLOAD_FLAGGED
    u.flagged_by = user.id
    u.flag_reason = body.reason.strip()
    u.flagged_at = utcnow()
    audit(
        db,
        user,
        "upload.flagged",
        "upload",
        u.id,
        filename=u.original_filename,
        logger=u.logger.logger_code,
        branch=u.branch.name if u.branch else None,
        reason=u.flag_reason,
    )
    db.commit()
    db.refresh(u)
    return _out(u)


@router.post("/uploads/{upload_id}/dismiss-flag", response_model=UploadOut)
def dismiss_flag(
    upload_id: int, user: User = Depends(admin_user), db: Session = Depends(get_db)
) -> UploadOut:
    """The file was fine after all: back to active. Admin only."""
    u = _get_upload(db, upload_id, user)
    if u.status != UPLOAD_FLAGGED:
        raise HTTPException(409, "This upload is not flagged.")
    u.status = UPLOAD_ACTIVE
    audit(
        db,
        user,
        "upload.flag_dismissed",
        "upload",
        u.id,
        filename=u.original_filename,
        reason=u.flag_reason,
    )
    db.commit()
    db.refresh(u)
    return _out(u)


@router.post("/uploads/{upload_id}/void", response_model=UploadOut)
def void(
    upload_id: int,
    body: ReasonIn,
    user: User = Depends(admin_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> UploadOut:
    """Soft-delete an upload (admin only). Hidden from dashboards, charts and reports; the
    row, readings and original file are kept; excursions and gaps are recomputed."""
    u = _get_upload(db, upload_id, user)
    if u.status == UPLOAD_VOIDED:
        raise HTTPException(409, "This upload was already voided.")
    result = void_upload(db, settings, u, user, body.reason.strip())
    audit(
        db,
        user,
        "upload.voided",
        "upload",
        u.id,
        filename=u.original_filename,
        logger=u.logger.logger_code,
        branch=u.branch.name if u.branch else None,
        reason=u.void_reason,
        readings_hidden=result.hidden,
        readings_restored=result.restored,
    )
    db.commit()
    db.refresh(u)
    return _out(u)
