"""HTTP API tests (FastAPI TestClient) against the test database."""

from __future__ import annotations

import csv
import io
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.main import create_app
from app.storage.models import Reading
from app.storage.session import get_db
from tests.conftest import MOCK


def make_client(session: Session, settings: Settings) -> TestClient:
    app = create_app()

    def _db() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app)


@pytest.fixture(scope="module")
def week_client(week_db, tmp_path_factory) -> TestClient:
    s = Settings(database_url="unused", upload_dir=str(tmp_path_factory.mktemp("up")))
    return make_client(week_db, s)


@pytest.fixture
def client(db, settings) -> TestClient:
    return make_client(db, settings)


def card(dash: dict, branch: str, fridge: str) -> dict:
    return next(c for c in dash["fridges"] if c["branch"] == branch and c["fridge"] == fridge)


# ---- read-only, whole week -------------------------------------------------------------


def test_health(week_client):
    r = week_client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["database"] == "ok"


def test_dashboard_defaults_to_latest_week_and_colours(week_client):
    d = week_client.get("/api/dashboard").json()
    assert (d["period_from"], d["period_to"], d["period_label"]) == (
        "2026-09-14",
        "2026-09-20",
        "2026-W38",
    )
    assert len({c["branch"] for c in d["fridges"]}) == 12
    assert d["counts"]["red"] == 3

    rishon = card(d, "Rishon LeZion", "Cream cakes")
    assert (rishon["colour"], rishon["ongoing"]) == ("red", True)
    assert rishon["reason"].startswith("Ongoing")
    ashdod = card(d, "Ashdod", "Dairy")
    assert (ashdod["colour"], ashdod["ongoing"]) == ("red", False)
    assert "for 1 h on Wed 16 Sep 03:00" in ashdod["reason"]
    beit = card(d, "Beit Shemesh", "Dairy")
    assert beit["colour"] == "amber" and beit["reason"].startswith("Gap 10 h")
    assert card(d, "Haifa", "Dairy")["colour"] == "amber"  # 4 ERR, no excursion
    assert card(d, "Jerusalem", "Dairy")["colour"] == "amber"  # 2 h 15 min gap
    healthy = card(d, "Netanya", "Dairy")
    assert (healthy["colour"], healthy["reason"]) == ("green", "OK")
    # Door-opening spikes stay green, with a footnote count.
    ta1 = card(d, "Tel Aviv", "Display 1")
    assert (ta1["colour"], ta1["spike_count"]) == ("green", 1)
    walk_in = card(d, "Tel Aviv", "Walk-in")
    assert walk_in["loggers"] == ["TL-0417", "TL-0420"]
    assert walk_in["colour"] == "green" and walk_in["spike_count"] == 2
    assert card(d, "Tel Aviv", "Display 2")["spike_count"] == 2
    assert card(d, "Haifa", "Dairy")["last_temp_c"] < 5


def test_dashboard_branch_filter(week_client):
    d = week_client.get("/api/dashboard", params={"branch": "Ashdod"}).json()
    assert {c["fridge"] for c in d["fridges"]} == {"Dairy", "Walk-in"}


def test_dashboard_empty_period_is_grey(week_client):
    d = week_client.get("/api/dashboard", params={"from": "2026-08-03", "to": "2026-08-09"}).json()
    assert d["counts"]["grey"] == len(d["fridges"])


def test_series_has_gap_and_no_fake_points(week_client):
    fridges = week_client.get("/api/fridges", params={"branch": "Jerusalem"}).json()
    dairy = next(f for f in fridges if f["name"] == "Dairy")
    s = week_client.get(f"/api/fridges/{dairy['id']}/series").json()
    assert s["threshold_c"] == 5.0
    assert [(g["start_local"], g["end_local"]) for g in s["gaps"]] == [
        ("2026-09-14T06:15:00", "2026-09-14T08:30:00")
    ]
    ts = [p["ts_local"] for p in s["readings"]]
    assert "2026-09-14T07:00:00" not in ts  # nothing interpolated
    assert len(ts) == 672 - 8  # 8 missing slots, duplicate collapsed


def test_series_spikes_for_tel_aviv_walk_in(week_client):
    fridges = week_client.get("/api/fridges", params={"branch": "Tel Aviv"}).json()
    walk_in = next(f for f in fridges if f["name"] == "Walk-in")
    s = week_client.get(f"/api/fridges/{walk_in['id']}/series").json()
    assert [(x["ts_local"], x["temp_c"]) for x in s["spikes"]] == [
        ("2026-09-14T06:15:00", 9.4),
        ("2026-09-15T14:30:00", 8.7),
    ]
    assert s["excursions"] == []
    assert {p["logger"] for p in s["readings"]} == {"TL-0417", "TL-0420"}


def test_series_unknown_fridge_404(week_client):
    assert week_client.get("/api/fridges/999999/series").status_code == 404


def test_report_lists_the_three_excursions(week_client):
    r = week_client.get("/api/report").json()
    rows = [(x["logger"], x["start_local"], x["duration_minutes"], x["peak_c"]) for x in r["rows"]]
    assert rows == [
        ("TL-0388", "2026-09-14T06:15:00", 9690, 11.5),
        ("TL-0901", "2026-09-16T03:00:00", 60, 7.4),
        ("TL-0601", "2026-09-16T13:45:00", 6360, 9.4),
    ]
    assert r["timezone"] == "Asia/Jerusalem"


def test_report_filters(week_client):
    r = week_client.get("/api/report", params={"branch": "Ashdod"}).json()
    assert [x["logger"] for x in r["rows"]] == ["TL-0901"]
    r = week_client.get("/api/report", params={"from": "2026-09-17", "to": "2026-09-20"}).json()
    assert {x["logger"] for x in r["rows"]} == {"TL-0388", "TL-0601"}  # still ongoing


def test_report_csv(week_client):
    r = week_client.get("/api/report.csv")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    rows = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))
    assert rows[0][0] == "Branch" and len(rows) == 4
    beer = next(x for x in rows if x[2] == "TL-0601")
    assert beer[:2] == ["Be'er Sheva", "Dairy"]
    assert beer[3:6] == ["2026-09-16 13:45", "2026-09-20 23:45", "6360"]
    assert beer[7] == "9.4"


def test_loggers_and_branches(week_client):
    loggers = {lg["logger_code"]: lg for lg in week_client.get("/api/loggers").json()}
    assert loggers["TL-0231"]["current"]["unit"] == "F"
    assert loggers["TL-0417"]["current"]["fridge"] == "Display 2"
    assert len(loggers["TL-0417"]["assignments"]) == 2
    branches = week_client.get("/api/branches").json()
    assert len(branches) == 12


# ---- mutating, fresh database ----------------------------------------------------------


def _post(client, name: str, logger: str | None = None):
    data = (MOCK / name).read_bytes()
    return client.post(
        "/api/uploads",
        files={"file": (name, data, "text/csv")},
        data={"logger_id": logger or name.split("_")[0]},
    )


def test_upload_happy_path(client):
    r = _post(client, "TL-0901_2026-W38.csv")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["already_imported"] is False
    assert (body["inserted"], body["excursions"], body["gaps"]) == (672, 1, 0)
    hist = client.get("/api/uploads").json()
    assert hist[0]["original_filename"] == "TL-0901_2026-W38.csv"


def test_upload_twice_is_idempotent(client, db):
    _post(client, "TL-0512_2026-W38.csv")
    n = db.scalar(select(func.count(Reading.id)))
    r = _post(client, "TL-0512_2026-W38.csv")
    assert r.status_code == 200 and r.json()["already_imported"] is True
    assert db.scalar(select(func.count(Reading.id))) == n
    assert len(client.get("/api/uploads").json()) == 1


def test_upload_unknown_logger_422(client, db):
    r = _post(client, "TL-9999_2026-W38.csv")
    assert r.status_code == 422
    assert "TL-9999 is not in the registry" in r.json()["detail"]
    assert db.scalar(select(func.count(Reading.id))) == 0


def test_upload_requires_logger(client):
    r = client.post("/api/uploads", files={"file": ("x.csv", b"a,b\n", "text/csv")})
    assert r.status_code == 422


def test_registry_move_reassigns_existing_readings(client):
    _post(client, "TL-0419_2026-W38.csv")  # Tel Aviv / Display 1 all week
    r = client.post(
        "/api/loggers/TL-0419/assignments",
        json={
            "branch": "Tel Aviv",
            "fridge": "Display 3",
            "unit": "C",
            "assigned_from": "2026-09-16",
        },
    )
    assert r.status_code == 201, r.text
    lg = r.json()
    assert lg["current"]["fridge"] == "Display 3"
    assert lg["assignments"][0]["assigned_to"] == "2026-09-15"
    d = client.get("/api/dashboard", params={"branch": "Tel Aviv"}).json()
    assert card(d, "Tel Aviv", "Display 3")["spike_count"] == 1  # 16 Sep 11:00 moved over
    assert card(d, "Tel Aviv", "Display 1")["spike_count"] == 0


def test_registry_add_new_logger_then_upload(client):
    r = client.post(
        "/api/loggers/TL-9999/assignments",
        json={"branch": "Eilat", "fridge": "Dairy", "unit": "C", "assigned_from": "2026-09-01"},
    )
    assert r.status_code == 201
    up = _post(client, "TL-9999_2026-W38.csv")
    assert up.status_code == 200
    body = up.json()
    assert body["inserted"] == 8 and body["sensor_errors"] == 5 and body["rejected_lines"] >= 4


def test_registry_overlap_is_409(client):
    r = client.post(
        "/api/loggers/TL-0420/assignments",
        json={
            "branch": "Tel Aviv",
            "fridge": "Walk-in",
            "unit": "C",
            "assigned_from": "2026-09-10",
            "assigned_to": "2026-09-20",
        },
    )
    assert r.status_code == 409
