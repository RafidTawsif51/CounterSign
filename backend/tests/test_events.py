import asyncio

import pytest
from pydantic import ValidationError
from sqlmodel import Session, select

from app import events as ev
from app.db import create_all, engine
from app.models import Decision, Event, Signal


def test_emit_persists_and_scopes_by_run():
    create_all()

    async def go():
        b = ev.Broadcaster()
        q_a, q_b = b.subscribe("run_a"), b.subscribe("run_b")
        q_board = b.subscribe(ev.LEADERBOARD)
        await b.emit(ev.RunStarted(run_id="run_a", invoice_count=3))
        await b.emit(ev.AttackLogged(attack_id="atk_1", attacker_name="x", source="judge", card="c"))
        assert q_a.qsize() == 1 and q_b.qsize() == 0 and q_board.qsize() == 1
        assert q_a.get_nowait()["type"] == "run.started"
        b.unsubscribe("run_a", q_a)
        assert "run_a" not in b.subscriber_count()

    asyncio.run(go())
    with Session(engine) as s:
        types = {e.type for e in s.exec(select(Event)).all()}
    assert {"run.started", "attack.logged"} <= types


def test_slow_subscriber_drops_oldest(monkeypatch):
    monkeypatch.setattr(ev, "QUEUE_MAX", 2)

    async def go():
        b = ev.Broadcaster()
        q = b.subscribe("run_s")
        for n in (1, 2, 3):
            await b.emit(ev.RunStarted(run_id="run_s", invoice_count=n))
        assert [q.get_nowait()["invoice_count"] for _ in range(2)] == [2, 3]

    asyncio.run(go())


def test_replay_returns_stored_events_in_order():
    async def go():
        b = ev.Broadcaster()
        await b.emit(ev.RunStarted(run_id="run_r", invoice_count=1))
        await b.emit(ev.RunCompleted(run_id="run_r", paid=1, held=0, blocked=0, total_usd=5))

    asyncio.run(go())
    assert [m["type"] for m in ev.stored_messages("run_r")] == ["run.started", "run.completed"]


def test_injection_needs_a_source():
    with pytest.raises(ValidationError):
        ev.InjectionDetected(run_id="r", technique="white_text", snippet="x")


def test_signal_carries_evidence_id():
    e = ev.RiskScored(
        run_id="r", payment_id="p", score=85, decision=Decision.hold_and_verify,
        top_signals=[Signal(name="n", weight=30, detail="d")],
    )
    assert e.payload()["top_signals"][0]["evidence_id"].startswith("evd_")


def test_a_controller_decision_reaches_the_global_channel_with_its_payment_event():
    """A board that only watches the global channel must see an approve or reject, even for a payment that never had a call."""
    create_all()

    async def go():
        b = ev.Broadcaster()
        board = b.subscribe(ev.LEADERBOARD)
        await b.emit(ev.PaymentHeld(run_id="run_a", payment_id="pay_nocall", reasons=["x"]))
        assert board.qsize() == 0  # a held payment with no call stays off the channel
        await b.emit(ev.PaymentReviewed(run_id="run_a", payment_id="pay_nocall", decision="rejected", approver="Dev", reason="no"))
        await b.emit(ev.PaymentBlocked(run_id="run_a", payment_id="pay_nocall", reason="Rejected by Dev: no"))
        assert [board.get_nowait()["type"] for _ in range(board.qsize())] == ["payment.reviewed", "payment.blocked"]

    asyncio.run(go())
