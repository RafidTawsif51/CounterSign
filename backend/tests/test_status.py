"""GET /api/system/status feeds the status panel: every component reports real, simulated or mock."""

from fastapi.testclient import TestClient

from app.main import app

MODES = {"real", "simulated", "mock", "down"}


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
