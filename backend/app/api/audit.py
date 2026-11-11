"""Audit log (admin only): who uploaded, flagged, voided, exported, managed users."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.auth import admin_user
from app.storage.models import AuditLog, User
from app.storage.session import get_db

router = APIRouter(prefix="/api", tags=["audit"])


class AuditOut(BaseModel):
    id: int
    created_at: datetime  # UTC
    user: str | None
    username: str | None
    action: str
    entity_type: str
    entity_id: int | None
    details: dict[str, Any] | None


@router.get("/audit-log", response_model=list[AuditOut])
def audit_log(
    action: str | None = Query(None, description="Exact action, or a prefix like 'upload.'"),
    user: str | None = Query(None, description="Username"),
    from_: date | None = Query(None, alias="from"),
    to: date | None = Query(None),
    limit: int = Query(200, ge=1, le=1000),
    _: User = Depends(admin_user),
    db: Session = Depends(get_db),
) -> list[AuditOut]:
    q = select(AuditLog).options(selectinload(AuditLog.user)).order_by(AuditLog.id.desc())
    if action:
        q = q.where(
            AuditLog.action.startswith(action)
            if action.endswith(".")
            else AuditLog.action == action
        )
    if user:
        q = q.join(User, User.id == AuditLog.user_id).where(User.username == user.strip().lower())
    if from_:
        q = q.where(AuditLog.created_at >= datetime.combine(from_, time.min))
    if to:
        q = q.where(AuditLog.created_at < datetime.combine(to + timedelta(days=1), time.min))
    return [
        AuditOut(
            id=a.id,
            created_at=a.created_at,
            user=a.user.full_name if a.user else None,
            username=a.user.username if a.user else None,
            action=a.action,
            entity_type=a.entity_type,
            entity_id=a.entity_id,
            details=a.details,
        )
        for a in db.scalars(q.limit(limit))
    ]
