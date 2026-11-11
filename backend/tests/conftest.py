"""Test fixtures.

Database: inside Compose (`docker compose run --rm api pytest`) ``TEST_DATABASE_URL`` points
at the already-healthy ``mysql`` service as root, and the tests create a disposable schema
``squanchy_kitchens_test``, migrate it with Alembic, and drop it at the end. The demo
database is never touched. Without ``TEST_DATABASE_URL`` (host-side runs) the same tests
use a throwaway SQLite file, so `pytest` also works with just Python installed.
"""

from __future__ import annotations

import os
import warnings
from collections.abc import Iterator
from pathlib import Path

os.environ.setdefault("BCRYPT_ROUNDS", "4")  # fast hashing in tests only (prod: 12)

import pytest  # noqa: E402
from alembic.config import Config
from sqlalchemy import Engine, create_engine, delete, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SAWarning
from sqlalchemy.orm import Session, sessionmaker

from alembic import command
from app.config import Settings
from app.registry import seed_registry
from app.storage.models import Base

warnings.filterwarnings("ignore", category=SAWarning)  # SQLite + DECIMAL

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent


def _data_dir() -> Path:
    for candidate in (Path("/data/seed"), REPO / "data"):
        if (candidate / "loggers.csv").exists():
            return candidate
    raise RuntimeError("Cannot find data/loggers.csv (mount ./data at /data/seed)")


DATA = _data_dir()
MOCK = DATA / "mock-logger-files"
TEST_SCHEMA = "squanchy_kitchens_test"


@pytest.fixture(scope="session")
def engine(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Engine]:
    url = os.environ.get("TEST_DATABASE_URL")
    if url:
        # Connect to the always-present system schema to create/drop the test schema.
        # (URL.set(database=None) does not clear the name in SQLAlchemy 2.1.)
        server = make_url(url).set(database="mysql")
        admin = create_engine(server)
        with admin.begin() as c:
            c.execute(text(f"DROP DATABASE IF EXISTS {TEST_SCHEMA}"))
            c.execute(
                text(
                    f"CREATE DATABASE {TEST_SCHEMA} "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
            )
        test_url = make_url(url).set(database=TEST_SCHEMA)
    else:
        admin = None
        test_url = make_url(f"sqlite:///{tmp_path_factory.mktemp('db') / 'test.db'}")

    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    cfg.set_main_option(
        "sqlalchemy.url", test_url.render_as_string(hide_password=False).replace("%", "%%")
    )
    command.upgrade(cfg, "head")

    eng = create_engine(test_url, future=True)
    yield eng
    eng.dispose()
    if admin is not None:
        with admin.begin() as c:
            c.execute(text(f"DROP DATABASE IF EXISTS {TEST_SCHEMA}"))
        admin.dispose()


def wipe(engine: Engine) -> None:
    with engine.begin() as c:
        for table in reversed(Base.metadata.sorted_tables):
            c.execute(delete(table))


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        database_url="unused",
        upload_dir=str(tmp_path / "uploads"),
        seed_registry_file=str(DATA / "loggers.csv"),
        seed_demo_dir=str(MOCK),
        seed_demo_data=False,
    )


def seed_users(session: Session) -> None:
    """The admin (admin / admin2026#) and the 12 demo branch managers (manager2026#)."""
    from app.bootstrap import seed_admin, seed_demo_managers

    s = Settings(database_url="unused")
    seed_admin(session, s)
    seed_demo_managers(session, s)


@pytest.fixture
def db(engine: Engine) -> Iterator[Session]:
    """A fresh database with the registry, the admin and the demo managers seeded."""
    wipe(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    seed_registry(session, (DATA / "loggers.csv").read_text(encoding="utf-8"))
    seed_users(session)
    try:
        yield session
    finally:
        session.close()


def import_mock(db: Session, settings: Settings, name: str):  # noqa: ANN201
    from app.ingest import import_file, logger_code_from_filename

    path = MOCK / name
    code = logger_code_from_filename(name)
    assert code
    return import_file(db, settings, name, path.read_bytes(), code)


@pytest.fixture(scope="module")
def week_db(engine: Engine, tmp_path_factory: pytest.TempPathFactory) -> Iterator[Session]:
    """The whole mock week imported once (read-only tests share it)."""
    from app.bootstrap import seed_demo_files

    wipe(engine)
    s = Settings(
        database_url="unused",
        upload_dir=str(tmp_path_factory.mktemp("uploads")),
        seed_demo_dir=str(MOCK),
    )
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    seed_registry(session, (DATA / "loggers.csv").read_text(encoding="utf-8"))
    seed_users(session)
    from app.storage.models import User

    admin = session.scalar(select(User).where(User.username == "admin"))
    results = seed_demo_files(session, s, admin)
    session.week_results = results  # type: ignore[attr-defined]
    try:
        yield session
    finally:
        session.close()
