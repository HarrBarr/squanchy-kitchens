"""SQLAlchemy models. Datetimes are stored naive: *_utc columns hold UTC, *_local hold
Asia/Jerusalem wall-clock time (what the file said, and what the inspector reads)."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
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


class Upload(Base):
    __tablename__ = "uploads"
    id: Mapped[int] = mapped_column(primary_key=True)
    logger_id: Mapped[int] = mapped_column(ForeignKey("loggers.id"))
    original_filename: Mapped[str] = mapped_column(String(255))
    sha256: Mapped[str] = mapped_column(String(64), unique=True)
    stored_path: Mapped[str] = mapped_column(String(512))
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20))
    started_at: Mapped[datetime] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    note: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    logger: Mapped[Logger] = relationship()


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
