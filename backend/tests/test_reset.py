"""POST /api/demo/reset: rebuild the seeded state in under 5 seconds, stop whatever is running, optionally keep the leaderboard."""

import base64
import time
from pathlib import Path

import pytest
from sqlmodel import Session, func, select

from app.config import get_settings
from app.models import Attack, Event, Invoice, Message, Payment, PaymentRun, VerificationCall
from app.services import attacks, reset, run, verify
from seed import seed as seedmod
from tests.test_attacks import CLASSIC, ceo, evs, wait  # noqa: F401
from tests.test_run import env, go  # noqa: F401

pytestmark = pytest.mark.slow


def count(eng, model, *where):
    with Session(eng) as s:
        return s.exec(select(func.count()).select_from(model).where(*where)).one()


def open_invoices(eng):
    with Session(eng) as s:
        return s.exec(select(func.count()).select_from(Invoice).where(~Invoice.id.in_(select(Payment.invoice_id)))).one()


@pytest.fixture(autouse=True)
def clean_state():
    for s in (run._active, run._mini, run._claimed):
        s.clear()
    reset._busy = False
    yield
    for s in (run._active, run._mini, run._claimed):
        s.clear()
    reset._busy = False


def test_reset_restores_the_seeded_state_in_under_5_seconds(env):
    client, eng = env
    go(client)  # the full run pays 37, holds 1, blocks 2
    for a in [client.post("/api/attacks", json=ceo(f"P{i}")).json() for i in range(3)]:
        wait(client, a["run_id"])
    assert count(eng, Payment) > 1159 and count(eng, Attack) == 6 and open_invoices(eng) == 0  # 3 attacks + the 3 planted ones the full run logged

    t = time.perf_counter()
    r = client.post("/api/demo/reset")
    elapsed = time.perf_counter() - t
    assert r.status_code == 200 and elapsed < 5 and r.json()["seconds"] < 5
    body = r.json()
    assert body["status"] == "ok" and body["kept_leaderboard"] is False and body["kept_attacks"] == 0
    assert count(eng, Payment) == 1159 and open_invoices(eng) == 40 and count(eng, Attack) == 0 and count(eng, VerificationCall) == 4
    assert body["counts"]["invoices"] == 1199 and body["counts"]["payments"] == 1159
    assert client.get("/api/attacks/leaderboard").json()["attempts"] == []
    # and the run works again, with the same result
    _, g = go(client)
    assert (g["totals"]["paid"], g["totals"]["held"], g["totals"]["blocked"]) == (37, 1, 2)


def test_reset_can_be_repeated_and_stays_fast(env):
    client, eng = env
    times = []
    for _ in range(3):
        go(client)
        t = time.perf_counter()
        assert client.post("/api/demo/reset").status_code == 200
        times.append(time.perf_counter() - t)
    assert max(times) < 5
    assert open_invoices(eng) == 40 and count(eng, Payment) == 1159


@pytest.mark.parametrize("how", ["query", "body"])
def test_keep_leaderboard_keeps_the_attacks_and_wipes_the_rest(env, how):
    client, eng = env
    a1 = client.post("/api/attacks", json=CLASSIC).json()
    a2 = client.post("/api/attacks", json=ceo("Judge Lee")).json()
    for a in (a1, a2):
        wait(client, a["run_id"])
    before = client.get("/api/attacks/leaderboard").json()
    r = client.post("/api/demo/reset?keep_leaderboard=true") if how == "query" else client.post("/api/demo/reset", json={"keep_leaderboard": True})
    assert r.status_code == 200 and r.json()["kept_leaderboard"] is True and r.json()["kept_attacks"] == 2 and r.json()["seconds"] < 5
    assert count(eng, Attack) == 2 and count(eng, Payment) == 1159 and open_invoices(eng) == 40
    assert count(eng, Message, Message.id.in_([a1["message_id"], a2["message_id"]])) == 0  # the underlying records are gone
    after = client.get("/api/attacks/leaderboard").json()
    assert after == before  # but the leaderboard reads the same: handle, result, reasons and text live on the attack row
    assert after["attempts"][0]["text"]["body"].startswith("Maria") and after["totals"]["attempts"] == 2
    # the default reset clears them
    assert client.post("/api/demo/reset").status_code == 200 and count(eng, Attack) == 0


def test_reset_stops_a_run_in_progress(env, monkeypatch):
    client, eng = env
    monkeypatch.setattr(verify, "MOCK_STEP_DELAY", 0.4)
    run_id = client.post("/api/payment-runs").json()["run_id"]
    time.sleep(0.5)  # in the middle of the run
    assert run.full_run_active()
    t = time.perf_counter()
    r = client.post("/api/demo/reset")
    assert r.status_code == 200 and time.perf_counter() - t < 5
    assert not run.full_run_active() and not run._claimed and not run._mini
    time.sleep(1.5)  # nothing may write into the fresh database afterwards
    assert count(eng, Payment) == 1159 and open_invoices(eng) == 40 and count(eng, PaymentRun, PaymentRun.id == run_id) == 0
    monkeypatch.setattr(verify, "MOCK_STEP_DELAY", 0)
    _, g = go(client)
    assert (g["totals"]["paid"], g["totals"]["held"], g["totals"]["blocked"]) == (37, 1, 2)


def test_reset_empties_the_attack_queue(env, monkeypatch):
    client, eng = env
    monkeypatch.setattr(verify, "MOCK_STEP_DELAY", 0.4)
    posted = [client.post("/api/attacks", json=ceo(f"Q{i}")).json() for i in range(4)]
    assert posted[1]["queued"] and posted[3]["queued"]
    assert client.post("/api/demo/reset").status_code == 200
    assert not run._claimed and not run._mini and attacks._queue.qsize() == 0
    time.sleep(1.5)
    assert count(eng, Payment) == 1159 and count(eng, Attack) == 0  # none of the queued attacks ran afterwards
    monkeypatch.setattr(verify, "MOCK_STEP_DELAY", 0)
    a = client.post("/api/attacks", json=CLASSIC).json()  # and the queue accepts new attacks
    assert a["queued"] is False and wait(client, a["run_id"])["status"] == "completed"


def test_a_second_reset_at_the_same_time_gets_409(env):
    client, _ = env
    reset._busy = True
    r = client.post("/api/demo/reset")
    assert r.status_code == 409
    reset._busy = False
    assert client.post("/api/demo/reset").status_code == 200


def test_uploaded_attack_pdfs_are_removed_but_the_seed_pdfs_stay(env):
    client, eng = env
    pdf = (seedmod.PDF_DIR / "poisoned_white_text.pdf").read_bytes()
    a = client.post("/api/attacks", json={"attacker_name": "x", "card": "poisoned_invoice", "payload": {
        **CLASSIC["payload"], "pdf_base64": base64.b64encode(pdf).decode()}}).json()
    wait(client, a["run_id"])
    uploads = Path(get_settings().upload_dir)
    assert list(uploads.glob("*.pdf"))
    r = client.post("/api/demo/reset")
    assert r.json()["uploads_removed"] >= 1 and not list(uploads.glob("*.pdf"))
    assert len(list(seedmod.PDF_DIR.glob("*.pdf"))) == 134


def test_reset_tells_the_screens(env, monkeypatch):
    client, eng = env
    sent = []
    real = reset.ev.emit

    async def spy(event):
        sent.append(event)
        return await real(event)

    monkeypatch.setattr(reset.ev, "emit", spy)
    client.post("/api/demo/reset?keep_leaderboard=true")
    assert [(e.type, e.kept_leaderboard) for e in sent] == [("demo.reset", True)]
    with Session(eng) as s:
        assert s.exec(select(Event.type)).all() == ["demo.reset"]  # the only event after the wipe


def test_reset_is_deterministic(env):
    client, eng = env
    def snapshot():
        with Session(eng) as s:
            return (sorted(s.exec(select(Invoice.id)).all()), sorted(s.exec(select(Payment.id)).all()), sorted(s.exec(select(Message.id)).all()))
    first = (client.post("/api/demo/reset"), snapshot())[1]
    go(client)
    client.post("/api/demo/reset")
    assert snapshot() == first
