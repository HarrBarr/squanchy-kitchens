"""SQLAlchemy models. Datetimes are stored naive: *_utc columns hold UTC, *_local hold
Asia/Jerusalem wall-clock time (what the file said, and what the inspector reads)."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Branch(Base):
    __tablename__ = "branches"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    fridges: Mapped[list["Fridge"]] = relationship(back_populates="branch")


class Fridge(Base):
    __tablename__ = "fridges"
    __table_args__ = (UniqueConstraint("branch_id", "name", name="uq_fridge_branch_name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"))
    name: Mapped[str] = mapped_column(String(100))
    branch: Mapped[Branch] = relationship(back_populates="fridges")


class Logger(Base):
    __tablename__ = "loggers"
    id: Mapped[int] = mapped_column(primary_key=True)
    logger_code: Mapped[str] = mapped_column(String(32), unique=True)
    assignments: Mapped[list["LoggerAssignment"]] = relationship(
        back_populates="logger", order_by="LoggerAssignment.assigned_from"
    )


class LoggerAssignment(Base):
    """Where a logger sits, from when, in which unit. assigned_to is inclusive of that local
    day; NULL means the assignment is current."""

    __tablename__ = "logger_assignments"
    __table_args__ = (Index("ix_assign_logger_from", "logger_id", "assigned_from"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    logger_id: Mapped[int] = mapped_column(ForeignKey("loggers.id"))
    fridge_id: Mapped[int] = mapped_column(ForeignKey("fridges.id"))
    unit: Mapped[str] = mapped_column(String(1))  # "C" | "F"
    assigned_from: Mapped[date] = mapped_column(Date)
    assigned_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    logger: Mapped[Logger] = relationship(back_populates="assignments")
    fridge: Mapped[Fridge] = relationship()


ROLE_ADMIN = "admin"
ROLE_MANAGER = "branch_manager"

UPLOAD_ACTIVE = "active"
UPLOAD_FLAGGED = "flagged_mistake"
UPLOAD_VOIDED = "voided"


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(128))
    role: Mapped[str] = mapped_column(String(20))  # "admin" | "branch_manager"
    branch_id: Mapped[int | None] = mapped_column(ForeignKey("branches.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    branch: Mapped[Branch | None] = relationship()

    @property
    def is_admin(self) -> bool:
        return self.role == ROLE_ADMIN


class Upload(Base):
    __tablename__ = "uploads"
    __table_args__ = (Index("ix_uploads_status", "status"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    logger_id: Mapped[int] = mapped_column(ForeignKey("loggers.id"))
    # Branch the file's readings belong to (the assignment at its timestamps).
    branch_id: Mapped[int | None] = mapped_column(ForeignKey("branches.id"), nullable=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    # Equal to sha256 while the upload is not voided, NULL once voided. Unique, so the
    # same bytes cannot be imported twice, yet a voided file can be uploaded again
    # (MySQL allows many NULLs in a unique index; it has no partial indexes).
    active_sha256: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    stored_path: Mapped[str] = mapped_column(String(512))
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    # Review lifecycle: active | flagged_mistake | voided (never physically deleted).
    status: Mapped[str] = mapped_column(String(20), default=UPLOAD_ACTIVE)
    started_at: Mapped[datetime] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    note: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    flagged_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    flag_reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    flagged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    voided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    void_reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    logger: Mapped[Logger] = relationship()
    branch: Mapped[Branch | None] = relationship()
    uploader: Mapped[User | None] = relationship(foreign_keys=[uploaded_by])
    flagger: Mapped[User | None] = relationship(foreign_keys=[flagged_by])
    voider: Mapped[User | None] = relationship(foreign_keys=[voided_by])


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_audit_created", "created_at"),
        Index("ix_audit_user_created", "user_id", "created_at"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(64))
    entity_type: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    user: Mapped[User | None] = relationship()


class Reading(Base):
    __tablename__ = "readings"
    __table_args__ = (
        UniqueConstraint("logger_id", "ts_utc", name="uq_reading_logger_ts"),
        Index("ix_readings_fridge_ts", "fridge_id", "ts_utc"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    upload_id: Mapped[int] = mapped_column(ForeignKey("uploads.id"))
    logger_id: Mapped[int] = mapped_column(ForeignKey("loggers.id"))
    fridge_id: Mapped[int] = mapped_column(ForeignKey("fridges.id"))
    ts_local: Mapped[datetime] = mapped_column(DateTime)
    ts_utc: Mapped[datetime] = mapped_column(DateTime)
    raw_value: Mapped[str] = mapped_column(String(64))
    temp_c: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    status: Mapped[str] = mapped_column(String(8))  # "ok" | "err"
    # True when the upload that wrote this reading was voided and no earlier upload covers
    # the timestamp. Hidden from every view and from excursion/gap recompute; never deleted.
    is_voided: Mapped[bool] = mapped_column(Boolean, default=False)


class Excursion(Base):
    __tablename__ = "excursions"
    __table_args__ = (Index("ix_excursions_fridge_start", "fridge_id", "start_utc"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    fridge_id: Mapped[int] = mapped_column(ForeignKey("fridges.id"))
    logger_id: Mapped[int] = mapped_column(ForeignKey("loggers.id"))
    start_utc: Mapped[datetime] = mapped_column(DateTime)
    end_utc: Mapped[datetime] = mapped_column(DateTime)
    start_local: Mapped[datetime] = mapped_column(DateTime)
    end_local: Mapped[datetime] = mapped_column(DateTime)
    duration_minutes: Mapped[int] = mapped_column(Integer)
    peak_c: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    n_readings: Mapped[int] = mapped_column(Integer)
    is_open: Mapped[bool] = mapped_column(Boolean, default=False)
    fridge: Mapped[Fridge] = relationship()
    logger: Mapped[Logger] = relationship()


class Gap(Base):
    __tablename__ = "gaps"
    __table_args__ = (Index("ix_gaps_fridge_start", "fridge_id", "start_utc"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    fridge_id: Mapped[int] = mapped_column(ForeignKey("fridges.id"))
    logger_id: Mapped[int] = mapped_column(ForeignKey("loggers.id"))
    start_utc: Mapped[datetime] = mapped_column(DateTime)
    end_utc: Mapped[datetime] = mapped_column(DateTime)
    start_local: Mapped[datetime] = mapped_column(DateTime)
    end_local: Mapped[datetime] = mapped_column(DateTime)
    duration_minutes: Mapped[int] = mapped_column(Integer)
