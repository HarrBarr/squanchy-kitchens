"""Authentication, roles and branch scoping (squanchy-kitchens-auth.md §9).

Users come from the seed: admin, and one branch manager per branch (manager.rishon,
manager.telaviv, manager.ashdod, ...), with the test-only passwords set in conftest.py.
"""

from __future__ import annotations

import os
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.config import Settings
from app.storage.models import AuditLog, Excursion, Reading, Upload, User
from tests.conftest import MOCK
from tests.test_api import card, make_client

ADMIN_PW = os.environ["ADMIN_PASSWORD"]
MANAGER_PW = os.environ["DEMO_MANAGER_PASSWORD"]


@pytest.fixture
def anon(db, settings) -> TestClient:
    return make_client(db, settings, as_user=None)


@pytest.fixture
def admin(db, settings) -> TestClient:
    return make_client(db, settings, "admin")


@pytest.fixture
def rishon(db, settings) -> TestClient:
    return make_client(db, settings, "manager.rishon")


@pytest.fixture
def telaviv(db, settings) -> TestClient:
    return make_client(db, settings, "manager.telaviv")


@pytest.fixture
def ashdod(db, settings) -> TestClient:
    return make_client(db, settings, "manager.ashdod")


def upload(client: TestClient, name: str, logger: str | None = None, data: bytes | None = None):
    return client.post(
        "/api/uploads",
        files={"file": (name, data or (MOCK / name).read_bytes(), "text/csv")},
        data={"logger_id": logger or name.split("_")[0]},
    )


def login(client: TestClient, username: str, password: str):
    return client.post("/api/auth/login", data={"username": username, "password": password})


def readings(db, **where) -> int:
    q = select(func.count(Reading.id)).where(Reading.is_voided.is_(False))
    return db.scalar(q) or 0


# ---------- sign-in ----------


def test_login_admin_and_manager(anon):
    r = login(anon, "admin", ADMIN_PW)
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer" and body["must_change_password"] is False
    me = anon.get("/api/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.json()["role"] == "admin" and me.json()["branch"] is None

    r = login(anon, "manager.rishon", MANAGER_PW)
    assert r.status_code == 200
    me = anon.get("/api/auth/me", headers={"Authorization": f"Bearer {r.json()['access_token']}"})
    assert (me.json()["role"], me.json()["branch"]) == ("branch_manager", "Rishon LeZion")


def test_login_fails_for_bad_password_unknown_user_and_deactivated(anon, admin, db):
    assert login(anon, "admin", "wrong").status_code == 401
    assert login(anon, "nobody", "whatever").status_code == 401
    uid = db.scalar(select(User.id).where(User.username == "manager.haifa"))
    assert admin.patch(f"/api/users/{uid}", json={"is_active": False}).status_code == 200
    r = login(anon, "manager.haifa", MANAGER_PW)
    assert r.status_code == 401 and r.json()["detail"] == "Wrong username or password."


def test_everything_but_health_and_login_needs_a_token(anon):
    assert anon.get("/api/health").status_code == 200
    for path in ("/api/dashboard", "/api/report", "/api/loggers", "/api/uploads", "/api/users"):
        assert anon.get(path).status_code == 401, path
    bad = anon.get("/api/dashboard", headers={"Authorization": "Bearer not-a-jwt"})
    assert bad.status_code == 401


def test_deactivated_user_is_refused_even_with_an_unexpired_token(db, settings, admin):
    manager = make_client(db, settings, "manager.rishon")
    assert manager.get("/api/dashboard").status_code == 200
    uid = db.scalar(select(User.id).where(User.username == "manager.rishon"))
    admin.patch(f"/api/users/{uid}", json={"is_active": False})
    assert manager.get("/api/dashboard").status_code == 401


def test_branch_comes_from_the_database_not_the_token(db, settings, admin):
    manager = make_client(db, settings, "manager.rishon")
    assert manager.get("/api/dashboard").json()["scope_branch"] == "Rishon LeZion"
    uid = db.scalar(select(User.id).where(User.username == "manager.rishon"))
    tel_aviv = next(b["id"] for b in admin.get("/api/branches").json() if b["name"] == "Tel Aviv")
    admin.patch(f"/api/users/{uid}", json={"branch_id": tel_aviv})
    # Same (old) token: the live branch wins.
    assert manager.get("/api/dashboard").json()["scope_branch"] == "Tel Aviv"


# ---------- branch scoping ----------


def test_manager_sees_only_their_branch(rishon, admin):
    upload(admin, "TL-0388_2026-W38.csv")
    upload(admin, "TL-0901_2026-W38.csv")
    d = rishon.get("/api/dashboard")
    assert d.status_code == 200
    assert {c["branch"] for c in d.json()["fridges"]} == {"Rishon LeZion"}
    assert [b["branch"] for b in d.json()["branches"]] == ["Rishon LeZion"]
    assert [b["name"] for b in rishon.get("/api/branches").json()] == ["Rishon LeZion"]
    assert {f["branch"] for f in rishon.get("/api/fridges").json()} == {"Rishon LeZion"}
    report = rishon.get("/api/report").json()
    assert {r["logger"] for r in report["rows"]} == {"TL-0388"}  # not Ashdod's TL-0901
    uploads = rishon.get("/api/uploads").json()
    assert {u["logger"] for u in uploads} == {"TL-0388"}
    loggers = rishon.get("/api/loggers").json()
    assert {lg["logger_code"] for lg in loggers} == {"TL-0388", "TL-0389", "TL-0390"}


def test_manager_asking_for_another_branch_gets_403_not_an_empty_list(rishon, admin):
    for path in ("/api/dashboard", "/api/report", "/api/report.csv", "/api/uploads"):
        r = rishon.get(path, params={"branch": "Ashdod"})
        assert r.status_code == 403, path
    upload(admin, "TL-0901_2026-W38.csv")
    ashdod_dairy = next(
        f["id"] for f in admin.get("/api/fridges", params={"branch": "Ashdod"}).json()
        if f["name"] == "Dairy"
    )  # fmt: skip
    assert rishon.get(f"/api/fridges/{ashdod_dairy}/series").status_code == 403
    assert rishon.get("/api/report", params={"fridge": ashdod_dairy}).status_code == 403


def test_admin_sees_all_branches_or_one(admin):
    upload(admin, "TL-0388_2026-W38.csv")
    all_ = admin.get("/api/dashboard").json()
    assert len({c["branch"] for c in all_["fridges"]}) == 12 and all_["scope_branch"] is None
    one = admin.get("/api/dashboard", params={"branch": "Ashdod"}).json()
    assert {c["branch"] for c in one["fridges"]} == {"Ashdod"}


# ---------- uploads ----------


def test_manager_cannot_upload_another_branchs_logger(telaviv, db):
    r = upload(telaviv, "TL-0388_2026-W38.csv")  # Rishon LeZion's logger
    assert r.status_code == 403
    assert "not assigned to your branch" in r.json()["detail"]
    assert readings(db) == 0 and db.scalar(select(func.count(Upload.id))) == 0


def test_manager_uploads_own_logger_and_exports_their_report(rishon, db):
    r = upload(rishon, "TL-0388_2026-W38.csv")
    assert r.status_code == 200 and r.json()["excursions"] == 1
    u = db.scalar(select(Upload))
    assert u.uploaded_by == db.scalar(select(User.id).where(User.username == "manager.rishon"))
    assert u.branch.name == "Rishon LeZion"
    csv = rishon.get("/api/report.csv")
    assert csv.status_code == 200 and "TL-0388" in csv.text
    exported = db.scalar(select(AuditLog).where(AuditLog.action == "report.exported"))
    assert exported is not None and exported.details["branch"] == "Rishon LeZion"


def test_manager_upload_spanning_another_branch_is_refused_whole(db, settings, admin):
    """TL-0417 moves inside Tel Aviv, so use a registry move to another branch: readings
    after 2026-09-17 belong to Ashdod. A Tel Aviv manager's file is then refused whole."""
    admin.post(
        "/api/loggers/TL-0419/assignments",
        json={
            "branch": "Ashdod",
            "fridge": "Display 9",
            "unit": "C",
            "assigned_from": "2026-09-17",
        },
    )
    telaviv = make_client(db, settings, "manager.telaviv")
    r = upload(telaviv, "TL-0419_2026-W38.csv")
    assert r.status_code == 403 and "Nothing was imported" in r.json()["detail"]
    assert readings(db) == 0


def test_unknown_logger_message_for_a_manager(rishon):
    r = upload(rishon, "TL-9999_2026-W38.csv")
    assert r.status_code == 422 and "Ask Summer" in r.json()["detail"]


# ---------- flag -> review -> void ----------


def test_flag_by_owner_shows_up_for_review(rishon, admin):
    uid = upload(rishon, "TL-0388_2026-W38.csv").json()["upload_id"]
    r = rishon.post(f"/api/uploads/{uid}/flag", json={"reason": "Wrong week, sorry"})
    assert r.status_code == 200 and r.json()["status"] == "flagged_mistake"
    assert admin.get("/api/uploads/pending-review/count").json() == {"count": 1}
    pending = admin.get("/api/uploads/pending-review").json()
    assert [(p["id"], p["flag_reason"]) for p in pending] == [(uid, "Wrong week, sorry")]
    # Flagging keeps the data on the dashboard.
    d = rishon.get("/api/dashboard").json()
    assert card(d, "Rishon LeZion", "Cream cakes")["colour"] == "red"
    # Admin dismisses: back to active.
    assert admin.post(f"/api/uploads/{uid}/dismiss-flag").json()["status"] == "active"
    assert admin.get("/api/uploads/pending-review/count").json() == {"count": 0}


def test_manager_cannot_flag_someone_elses_upload(db, settings, admin, rishon, telaviv):
    uid = upload(admin, "TL-0388_2026-W38.csv").json()["upload_id"]  # admin's upload
    r = rishon.post(f"/api/uploads/{uid}/flag", json={"reason": "not mine"})
    assert r.status_code == 403 and "uploaded yourself" in r.json()["detail"]
    r = telaviv.post(f"/api/uploads/{uid}/flag", json={"reason": "other branch"})
    assert r.status_code == 403


def test_only_admin_reviews_and_voids(rishon, admin):
    uid = upload(rishon, "TL-0388_2026-W38.csv").json()["upload_id"]
    rishon.post(f"/api/uploads/{uid}/flag", json={"reason": "mistake"})
    assert rishon.post(f"/api/uploads/{uid}/void", json={"reason": "x" * 5}).status_code == 403
    assert rishon.post(f"/api/uploads/{uid}/dismiss-flag").status_code == 403
    assert rishon.get("/api/uploads/pending-review").status_code == 403


def test_admin_void_hides_data_recomputes_and_keeps_everything(admin, db):
    uid = upload(admin, "TL-0901_2026-W38.csv").json()["upload_id"]
    assert card(admin.get("/api/dashboard").json(), "Ashdod", "Dairy")["colour"] == "red"
    n = db.scalar(select(func.count(Reading.id)))

    r = admin.post(f"/api/uploads/{uid}/void", json={"reason": "Wrong logger picked"})
    assert r.status_code == 200
    body = r.json()
    assert (body["status"], body["void_reason"], body["voided_by"]) == (
        "voided",
        "Wrong logger picked",
        "Summer Smith",
    )
    # Hidden everywhere, excursion recomputed away...
    assert db.scalar(select(func.count(Excursion.id))) == 0
    assert admin.get("/api/report").json()["rows"] == []
    assert card(admin.get("/api/dashboard").json(), "Ashdod", "Dairy")["colour"] == "grey"
    # ...but nothing physically deleted: rows, readings and the original file remain.
    u = db.get(Upload, uid)
    assert u is not None and db.scalar(select(func.count(Reading.id))) == n
    with open(u.stored_path, "rb") as fh:
        assert fh.read() == (MOCK / "TL-0901_2026-W38.csv").read_bytes()
    audit = admin.get("/api/audit-log", params={"action": "upload.voided"}).json()
    assert audit[0]["details"]["reason"] == "Wrong logger picked"


def test_after_void_the_same_file_can_be_uploaded_again(admin, db):
    uid = upload(admin, "TL-0901_2026-W38.csv").json()["upload_id"]
    admin.post(f"/api/uploads/{uid}/void", json={"reason": "test"})
    again = upload(admin, "TL-0901_2026-W38.csv").json()
    assert again["already_imported"] is False and again["updated"] == 672
    assert again["excursions"] == 1
    assert card(admin.get("/api/dashboard").json(), "Ashdod", "Dairy")["colour"] == "red"


def test_voiding_a_correction_restores_the_earlier_files_values(admin, db):
    upload(admin, "TL-0901_2026-W38.csv")
    text = (MOCK / "TL-0901_2026-W38.csv").read_text()
    fixed = text.replace("2026-09-16 03:15;6.8", "2026-09-16 03:15;4.0").encode()
    uid = upload(admin, "TL-0901_fix.csv", "TL-0901", fixed).json()["upload_id"]
    exc = db.scalar(select(Excursion))
    assert exc.n_readings == 3  # 03:30-04:00 after the "correction"

    r = admin.post(f"/api/uploads/{uid}/void", json={"reason": "the correction was wrong"})
    assert r.status_code == 200
    reading = db.scalar(
        select(Reading).where(Reading.raw_value == "6.8", Reading.is_voided.is_(False))
    )
    assert reading is not None and reading.temp_c == Decimal("6.80")
    exc = db.scalar(select(Excursion))
    assert (exc.n_readings, exc.duration_minutes) == (5, 60)  # the original excursion is back


# ---------- users, registry, audit ----------


def test_manager_cannot_manage_users_registry_or_read_audit(rishon):
    assert rishon.get("/api/users").status_code == 403
    r = rishon.post(
        "/api/users",
        json={"username": "x.y", "full_name": "X", "branch_id": 1, "password": "password1"},
    )
    assert r.status_code == 403
    assert rishon.get("/api/audit-log").status_code == 403
    r = rishon.post(
        "/api/loggers/TL-0388/assignments",
        json={"branch": "Rishon LeZion", "fridge": "Dairy", "unit": "C",
              "assigned_from": "2026-10-01"},
    )  # fmt: skip
    assert r.status_code == 403


def test_new_manager_must_change_password_before_using_the_app(admin, anon):
    haifa = next(b["id"] for b in admin.get("/api/branches").json() if b["name"] == "Haifa")
    r = admin.post(
        "/api/users",
        json={"username": "Dana.Levi", "full_name": "Dana Levi", "branch_id": haifa,
              "password": "first-pass-1"},
    )  # fmt: skip
    assert r.status_code == 201
    assert (r.json()["username"], r.json()["must_change_password"]) == ("dana.levi", True)

    tok = login(anon, "dana.levi", "first-pass-1").json()
    assert tok["must_change_password"] is True
    h = {"Authorization": f"Bearer {tok['access_token']}"}
    blocked = anon.get("/api/dashboard", headers=h)
    assert blocked.status_code == 403 and blocked.json()["detail"]["code"] == "must_change_password"
    assert anon.get("/api/auth/me", headers=h).status_code == 200  # still allowed

    r = anon.post(
        "/api/auth/change-password",
        headers=h,
        json={"current_password": "first-pass-1", "new_password": "my-own-pass-2"},
    )
    assert r.status_code == 200 and r.json()["must_change_password"] is False
    assert anon.get("/api/dashboard", headers=h).json()["scope_branch"] == "Haifa"


def test_admin_reset_password_returns_a_temporary_password_once(admin, anon, db):
    uid = db.scalar(select(User.id).where(User.username == "manager.rishon"))
    r = admin.post(f"/api/users/{uid}/reset-password")
    assert r.status_code == 200
    temp = r.json()["temporary_password"]
    assert login(anon, "manager.rishon", MANAGER_PW).status_code == 401
    assert login(anon, "manager.rishon", temp).json()["must_change_password"] is True
    entry = admin.get("/api/audit-log", params={"action": "user.password_reset"}).json()[0]
    assert temp not in str(entry)  # never logged


def test_change_password_needs_the_current_one(rishon):
    r = rishon.post(
        "/api/auth/change-password",
        json={"current_password": "nope", "new_password": "whatever-123"},
    )
    assert r.status_code == 400


def test_audit_log_records_who_did_what(admin, rishon):
    uid = upload(rishon, "TL-0388_2026-W38.csv").json()["upload_id"]
    rishon.post(f"/api/uploads/{uid}/flag", json={"reason": "duplicate"})
    rishon.get("/api/report.csv")
    log = admin.get("/api/audit-log").json()
    actions = [(e["action"], e["username"]) for e in log]
    assert ("upload.created", "manager.rishon") in actions
    assert ("upload.flagged", "manager.rishon") in actions
    assert ("report.exported", "manager.rishon") in actions
    only_uploads = admin.get("/api/audit-log", params={"action": "upload."}).json()
    assert {e["action"] for e in only_uploads} == {"upload.created", "upload.flagged"}


# ---------- dashboard: last upload and missing week ----------


def test_dashboard_shows_last_upload_and_marks_missing_branches(admin, rishon):
    upload(rishon, "TL-0388_2026-W38.csv")
    d = admin.get("/api/dashboard").json()
    by_branch = {b["branch"]: b for b in d["branches"]}
    rl = by_branch["Rishon LeZion"]
    assert rl["missing"] is False
    assert (rl["last_upload"]["filename"], rl["last_upload"]["uploaded_by"]) == (
        "TL-0388_2026-W38.csv",
        "Rishon LeZion manager",
    )
    assert by_branch["Ashdod"]["missing"] is True and by_branch["Ashdod"]["last_upload"] is None


def test_seed_admin_does_not_overwrite_a_changed_password(db, anon):
    from app.bootstrap import seed_admin

    admin = db.scalar(select(User).where(User.username == "admin"))
    from app.auth import hash_password

    admin.password_hash = hash_password("changed-by-summer")
    db.commit()
    seed_admin(db, Settings(database_url="unused"))  # e.g. a container restart
    assert login(anon, "admin", "changed-by-summer").status_code == 200
    assert login(anon, "admin", ADMIN_PW).status_code == 401


def test_backfill_gives_old_uploads_their_branch(admin, db):
    from app.bootstrap import backfill_upload_branches

    uid = upload(admin, "TL-0388_2026-W38.csv").json()["upload_id"]
    u = db.get(Upload, uid)
    u.branch_id = None  # as if imported before the column existed
    db.commit()
    assert backfill_upload_branches(db) == 1
    db.refresh(u)
    assert u.branch.name == "Rishon LeZion"


# ---------- no secrets in the repository ----------


def test_blank_compose_values_count_as_unset():
    s = Settings(
        database_url="unused", admin_password="", jwt_secret="  ", demo_manager_password=""
    )
    assert (s.admin_password, s.jwt_secret, s.demo_manager_password) == (None, None, None)


def test_first_start_without_passwords_generates_them(engine, capsys):
    from sqlalchemy.orm import sessionmaker

    from app.auth import verify_password
    from app.bootstrap import ensure_admin, missing_demo_managers, seed_demo_managers
    from app.registry import seed_registry
    from tests.conftest import DATA, wipe

    wipe(engine)
    db = sessionmaker(bind=engine, expire_on_commit=False)()
    seed_registry(db, (DATA / "loggers.csv").read_text(encoding="utf-8"))
    s = Settings(database_url="unused", admin_password="", demo_manager_password="")
    admin, pw = ensure_admin(db, s)
    assert pw and len(pw) >= 12 and verify_password(pw, admin.password_hash)
    assert ensure_admin(db, s)[1] is None  # exists now: nothing generated, nothing shown
    with pytest.raises(ValueError):
        seed_demo_managers(db, s)  # refuses to invent a password silently
    assert len(missing_demo_managers(db)) == 12
    db.close()


def test_jwt_secret_is_generated_once_per_install(tmp_path, monkeypatch):
    from app import auth

    auth._persisted_secret.cache_clear()
    s = Settings(database_url="unused", jwt_secret="", state_dir=str(tmp_path))
    k1 = auth._signing_key(s)
    secret_file = tmp_path / "jwt_secret"
    assert secret_file.exists() and len(secret_file.read_text()) >= 40
    assert oct(secret_file.stat().st_mode & 0o777) == "0o600"
    auth._persisted_secret.cache_clear()
    assert auth._signing_key(s) == k1  # same secret after a restart
    other = Settings(database_url="unused", jwt_secret="", state_dir=str(tmp_path / "other"))
    assert auth._signing_key(other) != k1  # another install, another secret
    auth._persisted_secret.cache_clear()
