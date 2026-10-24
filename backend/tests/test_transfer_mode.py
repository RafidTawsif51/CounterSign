"""Nessie honesty: every payment records how its transfer was made, and a fallback to a mock id is never silent."""

import asyncio

import pytest
from sqlmodel import select

from app import events as ev
from app.config import Settings
from app.models import AuditLog, Payment
from app.services import payments
from tests.test_integrations import pending, session, world  # noqa: F401  (session is a fixture)


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def sent(monkeypatch):
    """Collect emitted events, start each test with clean Nessie health."""
    out = []

    async def fake_emit(event):
        out.append(event)

    monkeypatch.setattr(ev, "emit", fake_emit)
    monkeypatch.setattr(payments, "_health", {"last_failure": None, "last_failure_at": None, "last_success_at": None, "failures": 0})
    return out


def live(monkeypatch, real):
    monkeypatch.setattr(payments, "get_settings", lambda: Settings(mock_nessie=False, nessie_api_key="sekret"))
    monkeypatch.setattr(payments, "_real_transfer", real)


def audit(session, entity, entity_id, action):
    return session.exec(select(AuditLog).where(AuditLog.entity == entity, AuditLog.entity_id == entity_id, AuditLog.action == action)).all()


def test_a_real_sandbox_transfer_is_mode_nessie(session, sent, monkeypatch):
    live(monkeypatch, lambda *a: "nes_real_1")
    world(session)
    pending(session, "bac_t_1")
    tid = run(payments.pay_payment(session, "pay_t"))
    pay = session.get(Payment, "pay_t")
    assert tid == "nes_real_1" and pay.transfer_mode == "nessie"
    assert sent[-1].transfer_mode == "nessie" and sent[-1].nessie_transfer_id == "nes_real_1"
    assert not audit(session, "payment", "pay_t", "nessie_failed") and not audit(session, "integration", "nessie", "transfer_failed")
    assert payments.nessie_health(session)["state"] == "ok"


def test_a_failed_nessie_falls_back_and_says_so(session, sent, monkeypatch):
    def boom(*a):
        raise RuntimeError("Nessie POST /x failed: HTTPStatusError (500: boom) key=sekret")

    live(monkeypatch, boom)
    world(session)
    pending(session, "bac_t_1")
    tid = run(payments.pay_payment(session, "pay_t"))
    pay = session.get(Payment, "pay_t")
    assert tid.startswith("mock_tr_") and pay.status.value == "paid"
    assert pay.transfer_mode == "mock_fallback" and sent[-1].transfer_mode == "mock_fallback"
    (row,) = audit(session, "payment", "pay_t", "nessie_failed")
    assert "500" in row.detail_json["error"] and "sekret" not in row.detail_json["error"] and row.detail_json["transfer_id"] == tid
    assert audit(session, "integration", "nessie", "transfer_failed")
    assert audit(session, "payment", "pay_t", "paid")[0].detail_json["transfer_mode"] == "mock_fallback"


def test_nessie_is_degraded_after_a_fallback_until_a_transfer_succeeds(session, sent, monkeypatch):
    calls = {"fail": True}

    def flaky(*a):
        if calls["fail"]:
            raise RuntimeError("down")
        return "nes_real_2"

    live(monkeypatch, flaky)
    world(session)
    pending(session, "bac_t_1")
    assert payments.nessie_health(session)["state"] == "unknown"
    run(payments.pay_payment(session, "pay_t"))
    health = payments.nessie_health(session)
    assert health["state"] == "degraded" and "down" in health["last_failure"]
    # a fresh process still knows, from the audit log
    monkeypatch.setattr(payments, "_health", {"last_failure": None, "last_failure_at": None, "last_success_at": None, "failures": 0})
    assert payments.nessie_health(session)["state"] == "degraded"
    calls["fail"] = False
    assert run(payments.create_transfer("x", 1.0, "d")).mode == "nessie"
    assert payments.nessie_health(session)["state"] == "ok"


def test_mock_nessie_is_mode_mock_not_a_failure(session, sent, monkeypatch):
    monkeypatch.setattr(payments, "get_settings", lambda: Settings(mock_nessie=True))
    world(session)
    pending(session, "bac_t_1")
    run(payments.pay_payment(session, "pay_t"))
    assert session.get(Payment, "pay_t").transfer_mode == "mock" and sent[-1].transfer_mode == "mock"
    assert not audit(session, "integration", "nessie", "transfer_failed")
    assert payments.nessie_health(session)["state"] == "mock"

