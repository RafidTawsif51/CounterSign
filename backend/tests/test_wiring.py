"""Teammate B's integrations wired into the run: requested accounts are unverified candidates, auto-pay goes through
payments.pay_payment, and two independent money checks stand between a payment and the transfer."""

import pytest
from sqlmodel import Session, func, select

from app.models import (
    AuditLog,
    CallOutcome,
    Decision,
    Event,
    Invoice,
    Message,
    Payment,
    PaymentRun,
    PaymentStatus,
    RiskAssessment,
    RunStatus,
    Vendor,
    VendorBankAccount,
    utcnow,
)
from app.services import payments, risk, run, verify
from tests.test_review import ASK, REVIEW_RUN
from tests.test_run import BANK, CEO, env, go  # noqa: F401  (env is a fixture: a private seeded database + client)

pytestmark = pytest.mark.slow


def accounts(eng, vendor_id):
    with Session(eng) as s:
        return list(s.exec(select(VendorBankAccount).where(VendorBankAccount.vendor_id == vendor_id).order_by(VendorBankAccount.valid_from)))


def trusted(eng, vendor_id):
    with Session(eng) as s:
        a = verify.current_verified_account(s, vendor_id)
        return a.id if a else None


def audit_actions(eng, entity, entity_id):
    with Session(eng) as s:
        return [a.action for a in s.exec(select(AuditLog).where(AuditLog.entity == entity, AuditLog.entity_id == entity_id).order_by(AuditLog.at))]


def payment(eng, pid):
    with Session(eng) as s:
        p = s.get(Payment, pid)
        s.expunge(p)
        return p


# ================================================================ requested accounts are unverified candidates


def test_the_seeded_run_is_still_37_paid_1_held_2_blocked(env):
    client, _ = env
    _, g = go(client)
    assert (g["totals"]["paid"], g["totals"]["held"], g["totals"]["blocked"]) == (37, 1, 2) and g["totals"]["total_usd"] == 445491.88


def test_a_requested_account_is_stored_unverified_and_the_payment_points_at_it(env):
    client, eng = env
    go(client)
    summit = accounts(eng, "ven_summit")
    assert len(summit) == 2  # the onboarding account, plus the one the invoice asked for
    onboarding, candidate = summit
    assert onboarding.account_last4 == "2204" and candidate.account_last4 == "7781"
    assert candidate.verified_by_call_id is None  # nobody verified it
    assert verify.REQUESTED_ACTION in audit_actions(eng, "vendor_bank_account", candidate.id)
    assert payment(eng, BANK).destination_account_id == candidate.id  # the payment points at the REQUESTED account ...
    assert trusted(eng, "ven_summit") == onboarding.id != candidate.id  # ... which is not the trusted one
    # the vendor denied the change on the call, so the candidate was closed and can never be paid
    assert candidate.valid_to is not None and "requested_destination_rejected" in audit_actions(eng, "vendor_bank_account", candidate.id)
    assert payment(eng, BANK).status == PaymentStatus.blocked

    north = accounts(eng, "ven_northside")
    assert len(north) == 2 and north[1].account_last4 == "3046" and north[1].verified_by_call_id is None
    assert payment(eng, CEO).destination_account_id == north[1].id and trusted(eng, "ven_northside") == north[0].id
    assert north[1].valid_to is None and payment(eng, CEO).status == PaymentStatus.held  # the call was unclear: still a candidate, still unpaid


def test_clean_invoices_create_no_candidates_and_are_paid_to_the_trusted_account(env):
    client, eng = env
    body, _ = go(client)
    with Session(eng) as s:
        assert s.exec(select(func.count()).select_from(VendorBankAccount)).one() == 34 + 2  # only the two requested accounts were added
        paid = s.exec(select(Payment).where(Payment.run_id == body["run_id"], Payment.status == PaymentStatus.paid)).all()
        assert len(paid) == 37
        for p in paid:
            vid = s.get(Invoice, p.invoice_id).vendor_id
            assert p.destination_account_id == verify.current_verified_account(s, vid).id  # Teammate B's definition of trusted
            assert run.check_destination(p.id)[0] is True  # and the run's own backstop agrees


def test_a_confirmed_call_promotes_the_candidate_instead_of_adding_a_second_row(env):
    client, eng = env
    verify.MOCK_OUTCOMES[BANK] = CallOutcome.confirmed
    try:
        go(client)
    finally:
        verify.MOCK_OUTCOMES.clear()
    summit = accounts(eng, "ven_summit")
    assert len(summit) == 2  # promoted in place: no duplicate row
    onboarding, promoted = summit
    pay = payment(eng, BANK)
    assert pay.status == PaymentStatus.paid and pay.destination_account_id == promoted.id and promoted.account_last4 == "7781"
    assert promoted.verified_by_call_id and promoted.valid_to is None and onboarding.valid_to is not None
    assert trusted(eng, "ven_summit") == promoted.id and run.check_destination(BANK)[0] is True


# ================================================================ auto-pay goes through pay_payment

def test_auto_pay_uses_payments_pay_payment_after_the_assessment_is_saved(env, monkeypatch):
    client, eng = env
    calls = []
    real = payments.pay_payment

    async def spy(session, payment_id):
        with Session(eng) as check:  # at the moment of paying, the payment is pending and its assessment already exists
            p = check.get(Payment, payment_id)
            calls.append((payment_id, p.status, check.exec(select(func.count()).select_from(RiskAssessment).where(RiskAssessment.payment_id == payment_id)).one()))
        return await real(session, payment_id)

    monkeypatch.setattr(payments, "pay_payment", spy)
    body, g = go(client)
    assert len(calls) == 37 and all(st == PaymentStatus.pending and n == 1 for _, st, n in calls)
    pid = calls[0][0]
    a = audit_actions(eng, "payment", pid)
    assert a.index("risk_assessed") < a.index("cleared_for_payment") < a.index("paid") and a.count("paid") == 1
    with Session(eng) as s:
        types = [e.type for e in s.exec(select(Event).where(Event.run_id == body["run_id"]).order_by(Event.at)) if (e.payload or {}).get("payment_id") == pid]
    assert types == ["risk.scored", "payment.paid"]  # pay_payment emitted payment.paid exactly once


# ================================================================ two independent money checks

class Liar(risk.RealRiskAssessor):
    def assess(self, payment, ctx):
        a = super().assess(payment, ctx)
        return a.model_copy(update={"score": 0, "decision": Decision.auto_pay, "hard_rules_fired": [], "reasons": []})


def blind_risk(monkeypatch):
    """Risk and the decision rules both say 'pay everything'."""
    monkeypatch.setattr(risk, "get_assessor", lambda: Liar())
    monkeypatch.setattr(run, "effective_decision", lambda a, changed: Decision.auto_pay)


def spy_transfers(monkeypatch):
    sent = []
    real = payments.create_transfer

    async def spy(dest, amount, description):
        sent.append(description.rsplit(" ", 1)[-1])
        return await real(dest, amount, description)

    monkeypatch.setattr(payments, "create_transfer", spy)
    return sent


def test_the_runs_backstop_alone_stops_a_requested_account(env, monkeypatch):
    """Teammate B's guard is switched off; the run's own check still refuses."""
    client, eng = env
    blind_risk(monkeypatch)
    monkeypatch.setattr(payments, "_guard", lambda *a, **k: None)
    sent = spy_transfers(monkeypatch)
    _, g = go(client)
    assert BANK not in sent and CEO not in sent and len(sent) == 37
    for pid in (BANK, CEO):
        assert payment(eng, pid).status == PaymentStatus.held and payment(eng, pid).nessie_transfer_id is None
    reason = [a for a in _held_reasons(eng, BANK)][0]
    assert reason.startswith("backstop_refused") and "only requested" in reason


def test_payments_guard_alone_stops_a_requested_account(env, monkeypatch):
    """The run's backstop is switched off; Teammate B's guard inside pay_payment still refuses."""
    client, eng = env
    blind_risk(monkeypatch)
    monkeypatch.setattr(run, "check_destination", lambda payment_id: (True, "ok"))
    sent = spy_transfers(monkeypatch)
    go(client)
    assert BANK not in sent and CEO not in sent and len(sent) == 37
    for pid in (BANK, CEO):
        assert payment(eng, pid).status == PaymentStatus.held and payment(eng, pid).nessie_transfer_id is None
    assert _held_reasons(eng, BANK)[0].startswith("payment_guard_refused") and "current verified account" in _held_reasons(eng, BANK)[0]


def _held_reasons(eng, pid):
    with Session(eng) as s:
        return [a.detail_json["reason"] for a in s.exec(select(AuditLog).where(AuditLog.entity == "payment", AuditLog.entity_id == pid, AuditLog.action == "held").order_by(AuditLog.at))]


def test_the_backstop_refuses_every_kind_of_untrusted_destination(env):
    client, eng = env
    body, _ = go(client)
    with Session(eng) as s:
        p = s.exec(select(Payment).where(Payment.status == PaymentStatus.paid, Payment.run_id == body["run_id"])).first()  # one paid by this run
        pid, vid = p.id, s.get(Invoice, p.invoice_id).vendor_id
        good = p.destination_account_id
        other = s.exec(select(VendorBankAccount).where(VendorBankAccount.vendor_id != vid, VendorBankAccount.valid_to.is_(None))).first().id
        s.add(VendorBankAccount(id="bac_cand", vendor_id=vid, routing_hash="a" * 64, account_last4="1111", bank_name="B", valid_from=utcnow()))
        s.add(AuditLog(id="aud_req", entity="vendor_bank_account", entity_id="bac_cand", actor="agent", action=verify.REQUESTED_ACTION))
        s.add(VendorBankAccount(id="bac_plain", vendor_id=vid, routing_hash="b" * 64, account_last4="2222", bank_name="B", valid_from=utcnow()))
        s.commit()

    def with_dest(dest):
        with Session(eng) as s:
            q = s.get(Payment, pid)
            q.destination_account_id = dest
            s.add(q)
            s.commit()
        return run.check_destination(pid)

    assert with_dest(good)[0] is True
    assert "only requested" in with_dest("bac_cand")[1]  # created from a payment request
    assert "only requested" in with_dest("bac_plain")[1]  # not the onboarding account and not verified by a call
    assert "different vendor" in with_dest(other)[1]
    assert "no destination" in with_dest(None)[1] and "no destination" in with_dest("bac_missing")[1]
    with Session(eng) as s:
        inv = s.get(Invoice, s.get(Payment, pid).invoice_id)
        inv.remittance_json = {"routing_hash": "z" * 64, "account_last4": "9999", "bank_name": "B"}  # the invoice asks for something else
        s.add(inv)
        s.commit()
    assert "different account" in with_dest(good)[1]


# ================================================================ the controller route stays safe


def test_approve_pays_the_verified_account_never_the_requested_one(env, monkeypatch):
    client, eng = env
    go(client)  # the CEO payment is held; its destination is the UNVERIFIED account ending 3046
    north = accounts(eng, "ven_northside")
    candidate, verified = north[1], north[0]
    assert payment(eng, CEO).destination_account_id == candidate.id
    before = len(accounts(eng, "ven_northside"))
    detail = client.get(f"/api/payments/{CEO}").json()
    assert detail["actions"]["can_approve"] is True and detail["payment"]["destination"]["trusted"] is False
    assert detail["payment"]["approve_pays"]["account_last4"] == verified.account_last4 != "3046"

    sent = []
    real = payments.create_transfer

    async def spy(dest, amount, description):
        sent.append(dest)
        return await real(dest, amount, description)

    monkeypatch.setattr(payments, "create_transfer", spy)
    r = client.post(f"/api/payments/{CEO}/approve", json=ASK)
    assert r.status_code == 200 and r.json()["paid_account_last4"] == verified.account_last4 and r.json()["invoice_asked_for_a_different_account"] is True
    pay = payment(eng, CEO)
    assert pay.status == PaymentStatus.paid and pay.destination_account_id == verified.id  # repointed to the verified account
    assert len(accounts(eng, "ven_northside")) == before  # no account was written
    now = accounts(eng, "ven_northside")[1]
    assert now.id == candidate.id and now.verified_by_call_id is None and now.valid_to is None  # the candidate is still unverified, still unpaid
    assert trusted(eng, "ven_northside") == verified.id
    with Session(eng) as s:
        approved = s.exec(select(AuditLog).where(AuditLog.entity == "payment", AuditLog.entity_id == CEO, AuditLog.action == "approved")).one()
        assert approved.detail_json["unverified_requested_account_id"] == candidate.id and approved.detail_json["requested_account_trusted"] is False
        assert approved.detail_json["paid_account_id"] == verified.id and approved.detail_json["new_account_created"] is False


def test_a_new_vendors_first_requested_account_is_never_trusted(env):
    client, eng = env
    with Session(eng) as s:  # a vendor with no onboarding account at all: its only account is the one an invoice asked for
        s.add(Vendor(id="ven_fresh", name="Fresh Vendor", trade="x", email_domain="fresh.example", created_at=utcnow()))
        s.commit()
        cand = verify.record_requested_destination(s, "ven_fresh", "c" * 64, "4321", "Some Bank")
        s.add(PaymentRun(id=REVIEW_RUN, status=RunStatus.completed, completed_at=utcnow()))
        s.add(Message(id="msg_fresh", thread_id="thr_fresh", vendor_id="ven_fresh", from_addr="a@fresh.example", subject="s", body="b"))
        s.add(Invoice(id="inv_fresh", vendor_id="ven_fresh", message_id="msg_fresh", number="F-1", amount_usd=100.0, due_date=utcnow().date(),
                      remittance_json={"routing_hash": "c" * 64, "account_last4": "4321", "bank_name": "Some Bank"}))
        s.add(Payment(id="pay_fresh", run_id=REVIEW_RUN, invoice_id="inv_fresh", amount_usd=100.0, destination_account_id=cand, status=PaymentStatus.held))
        s.commit()
    assert trusted(eng, "ven_fresh") is None  # not trusted by default
    r = client.post("/api/payments/pay_fresh/approve", json=ASK)
    assert r.status_code == 409 and "no verified bank account" in str(r.json()["detail"])
    assert payment(eng, "pay_fresh").status == PaymentStatus.held
    assert client.get("/api/payments/pay_fresh").json()["actions"]["can_approve"] is False


# ================================================================ vendor views


def test_vendor_views_show_requested_accounts_as_not_trusted(env):
    client, eng = env
    go(client)
    vs = {v["id"]: v for v in client.get("/api/vendors").json()}
    assert vs["ven_northside"]["unverified_requested_accounts"] == 1 and vs["ven_summit"]["unverified_requested_accounts"] == 0  # Summit's was denied and closed
    assert vs["ven_northside"]["current_account"]["account_last4"] != "3046" and vs["ven_summit"]["current_account"]["account_last4"] == "2204"
    h = client.get("/api/vendors/ven_northside/history").json()["bank_accounts"]
    assert [a["verified_by"] for a in h] == ["onboarding", "requested, not verified"] and [a["trusted"] for a in h] == [True, False]
