"""The standalone user-seeding script (python -m app.seed_users)."""

from __future__ import annotations

import io

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

import app.seed_users as seed_users
import app.storage.session as session_mod
from app.auth import verify_password
from app.config import Settings
from app.registry import seed_registry
from app.storage.models import AuditLog, User
from tests.conftest import DATA, wipe


@pytest.fixture
def bare(engine, monkeypatch, capsys):
    """Registry seeded, no users; the script talks to the test database."""
    wipe(engine)
    maker = sessionmaker(bind=engine, expire_on_commit=False)
    with maker() as s:
        seed_registry(s, (DATA / "loggers.csv").read_text(encoding="utf-8"))
    monkeypatch.setattr(session_mod, "get_sessionmaker", lambda: maker)
    monkeypatch.setattr(seed_users, "get_settings", lambda: Settings(database_url="unused"))
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    monkeypatch.delenv("DEMO_MANAGER_PASSWORD", raising=False)
    monkeypatch.setattr("sys.stdin", io.StringIO(""))  # not a terminal: never prompt
    capsys.readouterr()
    with maker() as s:
        yield s


def fresh(db: Session) -> Session:
    """End the test session's transaction so it sees the script's commits (MySQL's
    REPEATABLE READ would otherwise keep the snapshot from the first read)."""
    db.rollback()
    return db


def count_users(db: Session) -> int:
    return fresh(db).scalar(select(func.count(User.id))) or 0


def user(db: Session, username: str) -> User:
    fresh(db)
    u = db.scalar(select(User).where(User.username == username))
    assert u is not None
    return u


def test_creates_admin_and_one_manager_per_branch(bare, monkeypatch, capsys):
    monkeypatch.setenv("ADMIN_PASSWORD", "summer-pass-1")
    monkeypatch.setenv("DEMO_MANAGER_PASSWORD", "branch-pass-1")
    assert seed_users.main([]) == 0
    out = capsys.readouterr().out
    assert count_users(bare) == 13
    admin = user(bare, "admin")
    assert (admin.role, admin.branch_id, admin.full_name) == ("admin", None, "Summer Smith")
    assert verify_password("summer-pass-1", admin.password_hash)
    rishon = user(bare, "manager.rishon")
    assert rishon.branch.name == "Rishon LeZion" and rishon.role == "branch_manager"
    assert verify_password("branch-pass-1", rishon.password_hash)
    assert "manager.rehovot" in out and "13 account(s) set" in out
    assert out.count("branch-pass-1") == 12


def test_idempotent_and_never_overwrites_without_reset(bare, monkeypatch, capsys):
    monkeypatch.setenv("ADMIN_PASSWORD", "summer-pass-1")
    monkeypatch.setenv("DEMO_MANAGER_PASSWORD", "branch-pass-1")
    seed_users.main([])
    monkeypatch.setenv("ADMIN_PASSWORD", "different-2")
    capsys.readouterr()
    seed_users.main([])
    out = capsys.readouterr().out
    assert "Nothing changed" in out and "different-2" not in out
    assert verify_password("summer-pass-1", user(bare, "admin").password_hash)
    assert count_users(bare) == 13


def test_reset_passwords(bare, monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "summer-pass-1")
    monkeypatch.setenv("DEMO_MANAGER_PASSWORD", "branch-pass-1")
    seed_users.main([])
    monkeypatch.setenv("ADMIN_PASSWORD", "summer-pass-2")
    monkeypatch.setenv("DEMO_MANAGER_PASSWORD", "branch-pass-2")
    seed_users.main(["--reset-passwords"])
    assert verify_password("summer-pass-2", user(bare, "admin").password_hash)
    assert verify_password("branch-pass-2", user(bare, "manager.haifa").password_hash)
    resets = fresh(bare).scalar(
        select(func.count(AuditLog.id)).where(AuditLog.action == "user.password_reset")
    )
    assert resets == 13


def test_generate_per_manager_gives_distinct_random_passwords(bare, capsys):
    seed_users.main(["--generate", "--per-manager"])
    out = capsys.readouterr().out
    lines = [ln.split() for ln in out.splitlines() if ln.startswith("manager.")]
    passwords = {parts[-1] for parts in lines}
    assert len(lines) == 12 and len(passwords) == 12
    for parts in lines:
        assert verify_password(parts[-1], user(bare, parts[0]).password_hash)


def test_env_format_for_a_dotenv_file(bare, capsys):
    seed_users.main(["--generate", "--format", "env"])
    out = capsys.readouterr().out.strip().splitlines()
    assert [ln.split("=")[0] for ln in out] == ["ADMIN_PASSWORD", "DEMO_MANAGER_PASSWORD"]
    admin_pw = out[0].split("=", 1)[1]
    assert len(admin_pw) >= 12 and verify_password(admin_pw, user(bare, "admin").password_hash)


def test_must_change_and_admin_only_managers_only(bare, monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "summer-pass-1")
    seed_users.main(["--admin-only"])
    assert count_users(bare) == 1
    monkeypatch.setenv("DEMO_MANAGER_PASSWORD", "branch-pass-1")
    seed_users.main(["--managers-only", "--must-change"])
    assert count_users(bare) == 13
    assert user(bare, "manager.telaviv").must_change_password is True
    assert user(bare, "admin").must_change_password is False


def test_refuses_without_a_password_source(bare):
    with pytest.raises(SystemExit, match="ADMIN_PASSWORD is not set"):
        seed_users.main([])
    assert count_users(bare) == 0


def test_refuses_short_passwords(bare, monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "short")
    with pytest.raises(SystemExit, match="at least 8"):
        seed_users.main(["--admin-only"])


def test_branch_missing_from_registry_is_skipped(bare, monkeypatch, capsys):
    seed_users.BRANCH_MANAGERS["Nowhere"] = "manager.nowhere"
    try:
        seed_users.main(["--generate", "--managers-only"])
    finally:
        del seed_users.BRANCH_MANAGERS["Nowhere"]
    out = capsys.readouterr().out
    assert "manager.nowhere" in out and "skipped: branch not in the registry yet" in out
    assert fresh(bare).scalar(select(User).where(User.username == "manager.nowhere")) is None


def test_startup_seeding_uses_the_same_functions(bare):
    from app.bootstrap import seed_admin, seed_demo_managers

    s = Settings(database_url="unused")
    seed_admin(bare, s)
    assert seed_demo_managers(bare, s) == 12
    assert seed_demo_managers(bare, s) == 0  # idempotent
    assert verify_password(s.demo_manager_password, user(bare, "manager.ashdod").password_hash)
