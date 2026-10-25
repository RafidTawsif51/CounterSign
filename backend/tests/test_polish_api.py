"""Small read-only additions the finished UI relies on: the latest-run lookup and the provenance fields on a payment."""

import pytest
from sqlmodel import Session, select

from app.models import Payment, PaymentRun, PaymentStatus
from tests.test_run import BANK, CEO, env, go  # noqa: F401  (env is a fixture: a private seeded database + client)

pytestmark = pytest.mark.slow


def test_latest_run_is_404_before_any_run_then_the_newest_full_run(env):
    client, eng = env
    assert client.get("/api/payment-runs/latest").status_code == 404  # the seed's 50 historical runs do not count
    body, _ = go(client)
    got = client.get("/api/payment-runs/latest")
    assert got.status_code == 200 and got.json()["run_id"] == body["run_id"] and got.json()["status"] == "completed" and got.json()["invoice_count"] == 40


def test_an_attack_run_and_a_red_team_batch_are_never_the_latest_run(env):
    client, eng = env
    body, _ = go(client)
    with Session(eng) as s:
        for i, kind in enumerate(("attack", "redteam")):
            s.add(PaymentRun(id=f"run_{kind}_x", totals_json={"invoice_count": 1, "kind": kind}))
        s.commit()
    assert client.get("/api/payment-runs/latest").json()["run_id"] == body["run_id"]


def test_the_run_route_still_serves_a_real_run_id(env):
    client, _ = env
    body, _ = go(client)
    assert client.get(f"/api/payment-runs/{body['run_id']}").json()["id"] == body["run_id"]


def test_payment_detail_says_which_services_were_simulated(env):
    client, eng = env
    body, _ = go(client)
    d = client.get(f"/api/payments/{BANK}").json()
    assert d["calls"] and all(c["simulated"] is True for c in d["calls"])  # MOCK_TWILIO: no phone was involved
    assert d["independent_contact"]["simulated"] is True  # MOCK_APIFY: "Mock lookup"
    assert d["identity"]["source"] == "crs-sandbox-mock"
    assert d["invoice"]["extraction_source"] == "mock"
    with Session(eng) as s:
        paid_id = s.exec(select(Payment.id).where(Payment.run_id == body["run_id"], Payment.status == PaymentStatus.paid)).first()
    assert client.get(f"/api/payments/{paid_id}").json()["payment"]["transfer_mode"] == "mock"  # MOCK_NESSIE: no transfer left this machine
