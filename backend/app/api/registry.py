from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.config import Settings, get_settings
from app.registry import RegistryError, add_assignment, reassign_readings
from app.storage.models import Branch, Fridge, Logger, LoggerAssignment
from app.storage.session import get_db

router = APIRouter(prefix="/api", tags=["registry"])


class AssignmentOut(BaseModel):
    id: int
    branch: str
    fridge: str
    fridge_id: int
    unit: str
    assigned_from: date
    assigned_to: date | None


class LoggerOut(BaseModel):
    logger_code: str
    current: AssignmentOut | None
    assignments: list[AssignmentOut]


class AssignmentIn(BaseModel):
    branch: str = Field(min_length=1, max_length=100)
    fridge: str = Field(min_length=1, max_length=100)
    unit: str = Field(pattern="^[CFcf]$")
    assigned_from: date
    assigned_to: date | None = None


class BranchOut(BaseModel):
    id: int
    name: str
    fridge_count: int


class FridgeOut(BaseModel):
    id: int
    name: str
    branch: str
    current_logger: str | None


def _assignment_out(a: LoggerAssignment) -> AssignmentOut:
    return AssignmentOut(
        id=a.id,
        branch=a.fridge.branch.name,
        fridge=a.fridge.name,
        fridge_id=a.fridge_id,
        unit=a.unit,
        assigned_from=a.assigned_from,
        assigned_to=a.assigned_to,
    )


def _logger_out(lg: Logger) -> LoggerOut:
    items = [_assignment_out(a) for a in lg.assignments]
    current = next((x for x in reversed(items) if x.assigned_to is None), None)
    return LoggerOut(logger_code=lg.logger_code, current=current, assignments=items)


def _load_loggers(db: Session) -> list[Logger]:
    return list(
        db.scalars(
            select(Logger)
            .options(
                selectinload(Logger.assignments)
                .selectinload(LoggerAssignment.fridge)
                .selectinload(Fridge.branch)
            )
            .order_by(Logger.logger_code)
        )
    )


@router.get("/loggers", response_model=list[LoggerOut])
def list_loggers(db: Session = Depends(get_db)) -> list[LoggerOut]:
    return [_logger_out(lg) for lg in _load_loggers(db)]


@router.post("/loggers/{code}/assignments", response_model=LoggerOut, status_code=201)
def create_assignment(
    code: str,
    body: AssignmentIn,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> LoggerOut:
    """Record that a logger now sits in a fridge (creating the logger, branch or fridge if
    new). A current assignment that started earlier is closed the day before."""
    try:
        add_assignment(
            db, code, body.branch, body.fridge, body.unit, body.assigned_from, body.assigned_to
        )
        lg = db.scalar(select(Logger).where(Logger.logger_code == code.strip().upper()))
        assert lg is not None
        reassign_readings(db, settings, lg)
        db.commit()
    except RegistryError as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from exc
    lg = next(x for x in _load_loggers(db) if x.logger_code == code.strip().upper())
    return _logger_out(lg)


@router.get("/branches", response_model=list[BranchOut])
def list_branches(db: Session = Depends(get_db)) -> list[BranchOut]:
    rows = db.execute(
        select(Branch.id, Branch.name, func.count(Fridge.id))
        .outerjoin(Fridge, Fridge.branch_id == Branch.id)
        .group_by(Branch.id, Branch.name)
        .order_by(Branch.name)
    ).all()
    return [BranchOut(id=r[0], name=r[1], fridge_count=r[2]) for r in rows]


@router.get("/fridges", response_model=list[FridgeOut])
def list_fridges(
    branch: str | None = Query(None), db: Session = Depends(get_db)
) -> list[FridgeOut]:
    q = select(Fridge).join(Branch).options(selectinload(Fridge.branch))
    if branch:
        q = q.where(Branch.name == branch)
    fridges = list(db.scalars(q.order_by(Branch.name, Fridge.name)))
    current = {
        a.fridge_id: a.logger.logger_code
        for a in db.scalars(
            select(LoggerAssignment)
            .where(LoggerAssignment.assigned_to.is_(None))
            .options(selectinload(LoggerAssignment.logger))
        )
    }
    return [
        FridgeOut(id=f.id, name=f.name, branch=f.branch.name, current_logger=current.get(f.id))
        for f in fridges
    ]
