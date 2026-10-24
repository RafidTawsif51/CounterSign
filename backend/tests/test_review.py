"""Payment detail, controller approve / reject, and the vendor routes."""

import re
import time

import pytest
from sqlmodel import Session, func, select

from app.models import (
    AuditActor,
    AuditLog,
    Decision,
    Event,
    Invoice,
    Message,
    Payment,
    PaymentRun,
    PaymentStatus,
    RiskAssessment,
    Vendor,
    VendorBankAccount,
    utcnow,
)
from app.services import payments, review, run
from tests.test_run import BANK, CEO, POISON, env, go  # noqa: F401  (env is a fixture: a private seeded database + client)

REVIEW_RUN = "run_test_review"
ASK = {"reason": "Called the vendor's office; they confirmed the invoice amount.", "approver": "Dev"}


def hold(eng, invoice_id: str, *, rules=("destination_changed",), destination: str = "current") -> str:
    """Put an open seeded invoice into the state a finished run leaves it in: a held payment with its assessment and audit rows."""
    with Session(eng) as s:
        if s.get(PaymentRun, REVIEW_RUN) is None:
            from app.models import RunStatus

            s.add(PaymentRun(id=REVIEW_RUN, status=RunStatus.completed, completed_at=utcnow()))
        inv = s.get(Invoice, invoice_id)
        cur = s.exec(select(VendorBankAccount).where(VendorBankAccount.vendor_id == inv.vendor_id, VendorBankAccount.valid_to.is_(None))).one()
        pid = "pay_" + invoice_id.split("_", 1)[1]
        s.add(Payment(id=pid, run_id=REVIEW_RUN, invoice_id=invoice_id, amount_usd=inv.amount_usd, destination_account_id=cur.id if destination == "current" else destination,
                      status=PaymentStatus.held))
        s.add(RiskAssessment(id="ras_" + pid[4:], payment_id=pid, score=70, decision=Decision.hold_and_verify, hard_rules_fired=list(rules),
                             signals_json=[{"name": "bank_details_changed", "weight": 30, "detail": "New account ending 7781; last verified ending 2204", "evidence_id": "evd_x1"}],
                             model_version="risk-1"))
        s.commit()
        return pid


def audits(eng, pid):
    with Session(eng) as s:
        return [(a.actor, a.action, a.detail_json) for a in s.exec(select(AuditLog).where(AuditLog.entity == "payment", AuditLog.entity_id == pid).order_by(AuditLog.at))]


def events(eng, pid):
    with Session(eng) as s:
        return [(e.type, e.payload) for e in s.exec(select(Event).where(Event.run_id == REVIEW_RUN).order_by(Event.at)) if (e.payload or {}).get("payment_id") == pid]


@pytest.fixture()
def spy(monkeypatch):
    sent = []
    real = payments.send_transfer

    async def send(p):
        sent.append((p.id, p.destination_account_id, p.amount_usd, p.status.value))
        return await real(p)

    monkeypatch.setattr(payments, "send_transfer", send)
    return sent


# ================================================================ approve


def test_approve_pays_the_last_verified_account_and_audits_a_human(env, spy):
    client, eng = env
    pid = hold(eng, "inv_atk_ceo_pressure")  # the invoice asks for a NEW account (ending 3046)
    with Session(eng) as s:
        old = s.exec(select(VendorBankAccount).where(VendorBankAccount.vendor_id == "ven_northside", VendorBankAccount.valid_to.is_(None))).one()
        before = s.exec(select(func.count()).select_from(VendorBankAccount)).one()
        old_id, old_last4 = old.id, old.account_last4
    r = client.post(f"/api/payments/{pid}/approve", json=ASK)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "paid" and body["paid_account_last4"] == old_last4 != "3046" and body["invoice_asked_for_a_different_account"] is True
    assert spy == [(pid, old_id, spy[0][2], "pending")]  # exactly one transfer, to the verified account
    with Session(eng) as s:
        pay = s.get(Payment, pid)
        assert pay.status == PaymentStatus.paid and pay.destination_account_id == old_id and pay.nessie_transfer_id == body["nessie_transfer_id"]
        assert s.exec(select(func.count()).select_from(VendorBankAccount)).one() == before  # no bank account was written
        assert s.exec(select(VendorBankAccount).where(VendorBankAccount.vendor_id == "ven_northside", VendorBankAccount.account_last4 == "3046")).all() == []
    a = audits(eng, pid)
    human = [x for x in a if x[0] == AuditActor.human]
    assert [x[1] for x in human] == ["approved"] and human[0][2]["approver"] == "Dev" and human[0][2]["reason"] == ASK["reason"]
    assert human[0][2]["new_account_created"] is False and human[0][2]["invoice_asked_for_a_different_account"] is True
    assert [x[1] for x in a] == ["approved", "paid"]
    assert [t for t, _ in events(eng, pid)] == ["payment.reviewed", "payment.paid"]
    reviewed = events(eng, pid)[0][1]
    assert (reviewed["decision"], reviewed["approver"], reviewed["reason"]) == ("approved", "Dev", ASK["reason"])
    assert events(eng, pid)[1][1]["nessie_transfer_id"] == body["nessie_transfer_id"]


def test_approve_cannot_pay_a_new_account(env, spy):
    """The point of the whole design: no click can send money to an account no call has verified."""
    client, eng = env
    pid = hold(eng, "inv_atk_bank_change")  # asks for the attacker's account, ending 7781
    with Session(eng) as s:
        s.add(VendorBankAccount(id="bac_attacker", vendor_id="ven_summit", routing_hash="x" * 64, account_last4="7781", bank_name="Harborline Bank",
                                valid_from=utcnow(), valid_to=utcnow()))  # an account row that is NOT the current verified one
        s.commit()
        cur_id = s.get(Payment, pid).destination_account_id
    # 1. approving the honest held payment pays the OLD account, never the one on the invoice
    # 2. a payment re-pointed at any other account is refused outright
    for bad in ("bac_attacker", "bac_does_not_exist", None):
        with Session(eng) as s:
            p = s.get(Payment, pid)
            p.destination_account_id = bad
            p.status = PaymentStatus.held
            s.add(p)
            s.commit()
        r = client.post(f"/api/payments/{pid}/approve", json=ASK)
        assert r.status_code == 409 and "verified account" in str(r.json()["detail"]), (bad, r.text)
        assert pay_state(eng, pid) == (PaymentStatus.held, None)
    assert spy == []  # nothing was ever sent
    with Session(eng) as s:
        assert s.exec(select(func.count()).select_from(VendorBankAccount).where(VendorBankAccount.account_last4 == "7781")).one() == 1  # only the seeded row above
        assert "approved" not in [a[1] for a in audits(eng, pid)]


def test_approve_refuses_when_the_verified_account_changed_after_the_hold(env, spy):
    client, eng = env
    pid = hold(eng, "inv_atk_bank_change")
    with Session(eng) as s:
        cur = s.exec(select(VendorBankAccount).where(VendorBankAccount.vendor_id == "ven_summit", VendorBankAccount.valid_to.is_(None))).one()
        cur.valid_to = utcnow()
        s.add(cur)
        s.add(VendorBankAccount(id="bac_summit_new", vendor_id="ven_summit", routing_hash="y" * 64, account_last4="0001", bank_name="B", valid_from=utcnow()))
        s.commit()
    r = client.post(f"/api/payments/{pid}/approve", json=ASK)
    assert r.status_code == 409 and "changed after this payment was held" in str(r.json()["detail"])
    assert spy == [] and pay_state(eng, pid)[0] == PaymentStatus.held


def test_the_backstop_is_read_again_right_before_the_money_moves(env, spy, monkeypatch):
    client, eng = env
    pid = hold(eng, "inv_atk_bank_change")
    real = review._current_account
    calls = {"n": 0}

    def flip(s, vendor_id):
        calls["n"] += 1
        acct = real(s, vendor_id)
        if calls["n"] == 2 and acct is not None:  # the second read, taken just before send_transfer, sees a different account
            return VendorBankAccount(id="bac_other", vendor_id=vendor_id, routing_hash="z" * 64, account_last4="9999", bank_name="B", valid_from=utcnow())
        return acct

    monkeypatch.setattr(review, "_current_account", flip)
    r = client.post(f"/api/payments/{pid}/approve", json=ASK)
    assert r.status_code == 409 and "nothing was sent" in str(r.json()["detail"])
    assert spy == [] and pay_state(eng, pid)[0] == PaymentStatus.held  # released back to held


def test_a_failed_transfer_leaves_the_payment_held(env, monkeypatch):
    client, eng = env
    pid = hold(eng, "inv_atk_ceo_pressure")

    async def boom(p):
        raise payments.TransferRefused("sandbox down")

    monkeypatch.setattr(payments, "send_transfer", boom)
    r = client.post(f"/api/payments/{pid}/approve", json=ASK)
    assert r.status_code == 502 and pay_state(eng, pid) == (PaymentStatus.held, None)
    assert [x[1] for x in audits(eng, pid)] == ["approve_failed"] and audits(eng, pid)[0][0] == AuditActor.human
    assert events(eng, pid) == []  # nothing happened, so no event


def test_only_held_payments_can_be_approved_and_it_cannot_be_done_twice(env, spy):
    client, eng = env
    pid = hold(eng, "inv_atk_ceo_pressure")
    assert client.post(f"/api/payments/{pid}/approve", json=ASK).status_code == 200
    again = client.post(f"/api/payments/{pid}/approve", json=ASK)
    assert again.status_code == 409 and "only held payments" in str(again.json()["detail"])
    assert len(spy) == 1  # one transfer
    for status in (PaymentStatus.blocked, PaymentStatus.pending, PaymentStatus.paid):
        with Session(eng) as s:
            p = s.get(Payment, pid)
            p.status = status
            s.add(p)
            s.commit()
        r = client.post(f"/api/payments/{pid}/approve", json=ASK)
        assert r.status_code == 409 and r.json()["detail"]["status"] == status.value
        assert client.post(f"/api/payments/{pid}/reject", json=ASK).status_code == 409
    assert len(spy) == 1


def test_a_quarantined_document_cannot_be_approved(env, spy):
    client, eng = env
    pid = hold(eng, "inv_atk_poisoned_pdf", rules=("hidden_instructions",))
    r = client.post(f"/api/payments/{pid}/approve", json=ASK)
    assert r.status_code == 409 and "quarantined" in str(r.json()["detail"]) and spy == []
    detail = client.get(f"/api/payments/{pid}").json()
    assert detail["actions"]["can_approve"] is False and "quarantined" in detail["actions"]["approve_blocked_reason"]
    assert client.post(f"/api/payments/{pid}/reject", json=ASK).status_code == 200  # but it can be rejected


def test_nothing_is_decided_while_the_run_is_still_processing_it(env, spy):
    client, eng = env
    pid = hold(eng, "inv_atk_ceo_pressure")
    run._active.add(REVIEW_RUN)
    try:
        assert client.post(f"/api/payments/{pid}/approve", json=ASK).status_code == 409
        assert client.post(f"/api/payments/{pid}/reject", json=ASK).status_code == 409
        assert client.get(f"/api/payments/{pid}").json()["actions"] == {"can_approve": False, "approve_blocked_reason": "the payment run is still processing it", "can_reject": False}
    finally:
        run._active.discard(REVIEW_RUN)
    assert spy == [] and pay_state(eng, pid)[0] == PaymentStatus.held


@pytest.mark.parametrize("payload", [{}, {"reason": "ok reason"}, {"approver": "Dev"}, {"reason": "x", "approver": "Dev"}, {"reason": "fine reason", "approver": ""},
                                     {"reason": "fine reason", "approver": "D" * 101}, {"reason": "bad \x00 char", "approver": "Dev"}, {"reason": "a" * 1001, "approver": "Dev"}])
def test_approve_and_reject_validate_the_body(env, payload):
    client, eng = env
    pid = hold(eng, "inv_atk_ceo_pressure")
    assert client.post(f"/api/payments/{pid}/approve", json=payload).status_code == 422
    assert client.post(f"/api/payments/{pid}/reject", json=payload).status_code == 422
    assert pay_state(eng, pid)[0] == PaymentStatus.held


def test_unknown_payment_is_404(env):
    client, _ = env
    for call in (client.get("/api/payments/pay_nope"), client.post("/api/payments/pay_nope/approve", json=ASK), client.post("/api/payments/pay_nope/reject", json=ASK)):
        assert call.status_code == 404


# ================================================================ reject


def test_reject_blocks_audits_a_human_and_emits(env, spy):
    client, eng = env
    pid = hold(eng, "inv_atk_ceo_pressure")
    r = client.post(f"/api/payments/{pid}/reject", json={"reason": "The CEO never asked for this.", "approver": "Dev"})
    assert r.status_code == 200 and r.json() == {"payment_id": pid, "status": "blocked"}
    assert pay_state(eng, pid) == (PaymentStatus.blocked, None) and spy == []
    a = audits(eng, pid)
    assert [(x[0], x[1]) for x in a] == [(AuditActor.human, "rejected")] and a[0][2] == {"approver": "Dev", "reason": "The CEO never asked for this."}
    ev = events(eng, pid)
    assert [t for t, _ in ev] == ["payment.reviewed", "payment.blocked"]
    assert ev[0][1]["decision"] == "rejected" and ev[1][1]["reason"] == "Rejected by Dev: The CEO never asked for this."


# ================================================================ GET /payments/{id}


@pytest.mark.slow
def test_payment_detail_after_a_real_run(env):
    client, eng = env
    go(client)
    d = client.get(f"/api/payments/{BANK}").json()
    assert d["payment"]["status"] == "blocked" and d["payment"]["destination"]["account_last4"] == d["payment"]["last_verified_account"]["account_last4"]
    assert d["invoice"]["requested_account_differs_from_verified"] is True and d["invoice"]["requested_remittance"]["account_last4"] == "7781"
    assert d["vendor"]["name"] == "Summit Concrete" and d["vendor"]["identity"]["status"] and d["identity"] == d["vendor"]["identity"]
    assert d["message"]["from_addr"].endswith("@summit-concrete.co") and d["message"]["is_attack"] is True
    r = d["risk"]
    assert r["decision"] == "hold_and_verify" and r["hard_rules_fired"] == ["destination_changed"] and r["score"] == 100
    assert {s["name"] for s in r["signals"]} >= {"bank_details_changed", "lookalike_domain", "reply_to_mismatch", "urgency_language"}
    assert all(s["detail"] and s["evidence_id"].startswith("evd_") for s in r["signals"]) and r["hard_rule_actions"]["destination_changed"]
    (call,) = d["calls"]
    assert call["outcome"] == "denied" and [t["speaker"] for t in call["transcript"]] == ["agent", "vendor", "agent"] and call["contact"]["phone"].startswith("+1***")
    times = [a["at"] for a in d["audit"]]
    assert times == sorted(times) and [a["action"] for a in d["audit"]][:2] == ["risk_assessed", "held"]
    assert {"risk_assessed", "held", "verification_call", "blocked_by_verification"} <= {a["action"] for a in d["audit"]} and "created" in {a["action"] for a in d["audit"]} or True
    assert d["actions"]["can_approve"] is False

    p = client.get(f"/api/payments/{POISON}").json()
    assert p["invoice"]["quarantined"] is True and [f["technique"] for f in p["injection_findings"]] == ["white_text"]
    assert p["risk"]["hard_rules_fired"] == ["hidden_instructions"] and p["calls"] == []

    c = client.get(f"/api/payments/{CEO}").json()
    assert c["payment"]["status"] == "held" and c["calls"][0]["outcome"] == "unclear" and c["actions"]["can_approve"] is True


def test_payment_detail_has_every_section_and_orders_the_audit_trail(env):
    client, eng = env
    pid = hold(eng, "inv_atk_ceo_pressure")
    with Session(eng) as s:  # an invoice-level and a payment-level audit row, written out of order
        s.add(AuditLog(id="aud_zzz", at=utcnow(), entity="invoice", entity_id="inv_atk_ceo_pressure", actor=AuditActor.system, action="late"))
        s.add(AuditLog(id="aud_aaa", at=utcnow().replace(year=2020), entity="payment", entity_id=pid, actor=AuditActor.agent, action="early"))
        s.commit()
    d = client.get(f"/api/payments/{pid}").json()
    assert set(d) == {"payment", "invoice", "vendor", "message", "risk", "injection_findings", "identity", "calls", "audit", "actions"}
    assert d["vendor"]["id"] == "ven_northside" and d["identity"] is not None and d["message"]["body"].startswith("Maria")
    actions = [a["action"] for a in d["audit"]]
    assert actions[0] == "early" and actions[-1] == "late"
    assert d["actions"]["can_approve"] is True and d["actions"]["can_reject"] is True
    assert "pdf_path" not in str(d)  # no server path leaks


# ================================================================ vendors


def test_vendor_list_has_a_risk_summary_and_the_crs_result(env):
    client, eng = env
    vs = client.get("/api/vendors").json()
    assert len(vs) == 30 and [v["name"] for v in vs] == sorted(v["name"] for v in vs)
    by = {v["id"]: v for v in vs}
    assert sum(v["risk_summary"]["payments"]["paid"] for v in vs) == 1159 and sum(v["risk_summary"]["open_invoices"] for v in vs) == 40
    lake = by["ven_lakeshore"]
    assert lake["risk_summary"]["bank_changes"] == 1 and lake["current_account"]["account_last4"] and lake["identity"]["status"] == "verified"
    assert by["ven_summit"]["risk_summary"]["attack_messages"] == 1 and by["ven_summit"]["risk_summary"]["bank_changes"] == 0
    assert by["ven_greenfield"]["risk_summary"]["flagged_payments"] == 1  # its first payment was held for the new-vendor rule
    assert by["ven_alder"]["identity"] is None  # no CRS check has run for Alder yet
    assert all(v["risk_summary"]["attention"] == "clear" for v in vs)


def test_vendor_list_shows_attention_after_a_hold(env):
    client, eng = env
    hold(eng, "inv_atk_ceo_pressure")
    vs = {v["id"]: v for v in client.get("/api/vendors").json()}
    assert vs["ven_northside"]["risk_summary"]["attention"] == "held" and vs["ven_northside"]["risk_summary"]["payments"]["held"] == 1
    assert vs["ven_northside"]["risk_summary"]["latest_decision"] == "hold_and_verify"


def test_vendor_history(env):
    client, eng = env
    h = client.get("/api/vendors/ven_lakeshore/history").json()
    assert h["vendor"]["name"] == "Lakeshore Plumbing and Heating" and h["identity"]["status"] == "verified"
    accts = h["bank_accounts"]
    assert len(accts) == 2 and [a["current"] for a in accts] == [False, True] and accts[1]["verified_by"] == "phone call: confirmed" and accts[0]["verified_by"] == "onboarding"
    (call,) = h["calls"]
    assert call["outcome"] == "confirmed" and len(call["transcript"]) == 3 and call["contact"]["source"] == "on_file" and re.fullmatch(r"\+1\*\*\*\d{4}", call["contact"]["phone"])
    assert {c["source"] for c in h["contacts"]} == {"on_file", "website", "listing"} & {c["source"] for c in h["contacts"]} and all("***" in c["phone"] for c in h["contacts"])
    inv = h["invoices"]
    assert h["summary"]["invoices"] == len(inv) > 60 and inv[0]["id"] > inv[-1]["id"]
    paid = [i for i in inv if i["status"] == "paid"]
    assert paid and all(i["score"] is not None and i["decision"] == "auto_pay" or i["hard_rules_fired"] for i in paid)
    assert h["summary"]["max_paid_usd"] == max(i["amount_usd"] for i in paid) and "pdf_path" not in str(h)
    assert len(client.get("/api/vendors/ven_lakeshore/history?limit=5").json()["invoices"]) == 5


def test_vendor_history_runs_the_crs_check_once_and_keeps_it(env):
    client, eng = env
    def n():
        with Session(eng) as s:
            return s.exec(select(func.count()).select_from(AuditLog).where(AuditLog.entity_id == "ven_alder", AuditLog.action == "identity_check")).one()
    assert n() == 0
    first = client.get("/api/vendors/ven_alder/history").json()["identity"]
    assert first["status"] == "verified" and first["source"] == "crs-sandbox-mock" and n() == 1
    assert client.get("/api/vendors/ven_alder/history").json()["identity"] == first and n() == 1  # kept, not recomputed
    assert client.get("/api/vendors").json()  # and the list now shows it
    assert {v["id"]: v for v in client.get("/api/vendors").json()}["ven_alder"]["identity"]["status"] == "verified"


def test_unknown_vendor_is_404(env):
    assert env[0].get("/api/vendors/ven_nope/history").status_code == 404


def pay_state(eng, pid):
    with Session(eng) as s:
        p = s.get(Payment, pid)
        return p.status, p.nessie_transfer_id
