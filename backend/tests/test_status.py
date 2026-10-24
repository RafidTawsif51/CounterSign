"""GET /api/system/status feeds the status panel: every component reports real, simulated or mock."""

from fastapi.testclient import TestClient

from app.config import get_settings
from app.services import liveness

from app.main import app

MODES = {"real", "sandboxed", "simulated", "mock", "degraded"}


def test_status_lists_every_component_with_a_mode():
    with TestClient(app) as client:
        r = client.get("/api/system/status")
    assert r.status_code == 200
    rows = {row["name"]: row for row in r.json()}
    assert all(row["mode"] in MODES and row["detail"] for row in rows.values())
    for name in ("Claude extraction", "Risk engine", "Injection defense", "Verification call (Twilio)", "Call voice (Cartesia)",
                 "Vendor phone lookup (Apify)", "Vendor identity (CRS)", "Bank payments (Nessie)", "Company and vendor history"):
        assert name in rows


def test_status_follows_the_mock_flags():
    with TestClient(app) as client:
        rows = {row["name"]: row for row in client.get("/api/system/status").json()}
    # conftest pins every sponsor mock on and the local risk and injection engines off
    assert rows["Verification call (Twilio)"]["mode"] == "mock"
    assert rows["Bank payments (Nessie)"]["mode"] == "mock"
    assert rows["Risk engine"]["mode"] == "real"
    assert rows["Injection defense"]["mode"] == "real"
    assert rows["Company and vendor history"]["mode"] == "simulated"


def test_seeded_demo_calls_are_shown_as_simulated():
    with TestClient(app) as client:
        rows = {row["name"]: row for row in client.get("/api/system/status").json()}
    assert rows["Seeded demo calls"]["mode"] == "simulated"


def test_live_components_show_their_last_success_and_nessie_is_sandboxed(monkeypatch, tmp_path):
    monkeypatch.setattr(liveness, "PATH", tmp_path / "last_success.json")
    s = get_settings()
    for flag in ("mock_claude", "mock_risk", "mock_injection", "mock_twilio", "mock_cartesia", "mock_crs", "mock_nessie", "mock_apify"):
        monkeypatch.setattr(s, flag, False)
    from app.services import payments  # other tests leave Nessie failures in the shared database; this test is about the live row

    monkeypatch.setattr(payments, "nessie_health", lambda session=None: {"state": "ok", "last_success_at": None})
    keys = ("claude", "risk", "injection", "twilio", "cartesia", "crs", "nessie", "apify")
    for k in keys:
        liveness.mark(k)
    with TestClient(app) as client:
        rows = {row["name"]: row for row in client.get("/api/system/status").json()}
    names = ("Claude extraction", "Risk engine", "Injection defense", "Verification call (Twilio)", "Call voice (Cartesia)",
             "Vendor identity (CRS)", "Bank payments (Nessie)", "Vendor phone lookup (Apify)", "Database")
    assert all(rows[n]["last_success_at"] for n in names), {n: rows[n].get("last_success_at") for n in names}
    assert rows["Bank payments (Nessie)"]["mode"] == "sandboxed"
    assert rows["Bank payments (Nessie)"]["detail"] == "Real Capital One Nessie API, sandbox money"
    assert rows["Vendor identity (CRS)"]["mode"] == "sandboxed"


def test_a_mocked_component_never_shows_a_last_success(monkeypatch, tmp_path):
    monkeypatch.setattr(liveness, "PATH", tmp_path / "last_success.json")
    liveness.mark("twilio")
    with TestClient(app) as client:
        rows = {row["name"]: row for row in client.get("/api/system/status").json()}
    assert rows["Verification call (Twilio)"]["mode"] == "mock" and rows["Verification call (Twilio)"]["last_success_at"] is None
