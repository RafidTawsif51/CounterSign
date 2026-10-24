import asyncio
import threading
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlmodel import Session, SQLModel, func, select

from app import events as ev_mod
from app.main import app
from app.models import (
    Attack,
    AuditLog,
    CallOutcome,
    Decision,
    Event,
    InjectionFinding,
    Invoice,
    Message,
    Payment,
    PaymentRun,
    PaymentStatus,
    RiskAssessment,
    VendorBankAccount,
    VerificationCall,
)
from app.services import extract, payments, risk, run, verify
from seed import seed as seedmod
from tests.helpers import use_engine

pytestmark = pytest.mark.slow  # every test here runs the whole payment run

BANK, POISON, CEO = (f"pay_{k}" for k in ("atk_bank_change", "atk_poisoned_pdf", "atk_ceo_pressure"))


@pytest.fixture()
def env(tmp_path, monkeypatch, seed_template):
    """A private copy of the seeded database that the app, the run and the services all use."""
    from tests.conftest import copy_seeded

    eng = create_engine(f"sqlite:///{copy_seeded(seed_template, tmp_path, 'run.sqlite')}", connect_args={"check_same_thread": False})

    @event.listens_for(eng, "connect")
    def _wal(conn, _):
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=10000")

    use_engine(monkeypatch, eng)
    monkeypatch.setattr(verify, "MOCK_STEP_DELAY", 0)
    verify.MOCK_OUTCOMES.clear()
    run._active.clear()
    with TestClient(app) as client:
        yield client, eng
    verify.MOCK_OUTCOMES.clear()


def go(client, timeout=30):
    t = time.perf_counter()
    r = client.post("/api/payment-runs")
    assert r.status_code == 202, r.text
    body = r.json()
    while time.perf_counter() - t < timeout:
        g = client.get(f"/api/payment-runs/{body['run_id']}").json()
        if g["status"] != "running":
            return body, g
        time.sleep(0.02)
    raise AssertionError("run did not finish")


def pay_status(eng, pid):
    with Session(eng) as s:
        p = s.get(Payment, pid)
        return p.status if p else None


# ---------------------------------------------------------------- the run end to end


def test_run_returns_at_once_and_finishes_fast(env):
    client, eng = env
    t = time.perf_counter()
    r = client.post("/api/payment-runs")
    assert time.perf_counter() - t < 1 and r.status_code == 202
    body = r.json()
    assert body["invoice_count"] == 40 and body["run_id"].startswith("run_")
    while client.get(f"/api/payment-runs/{body['run_id']}").json()["status"] == "running":
        time.sleep(0.02)
    g = client.get(f"/api/payment-runs/{body['run_id']}").json()
    assert g["status"] == "completed" and g["wall_seconds"] < 20
    assert g["totals"]["paid"] == 37 and g["totals"]["held"] == 1 and g["totals"]["blocked"] == 2 and g["totals"]["pending"] == 0
    assert g["invoice_count"] == 40 and set(g["timings_ms"]) >= {"extract", "scan", "risk", "commit", "transfer", "verify", "total"}
    with Session(eng) as s:
        paid = s.exec(select(func.sum(Payment.amount_usd)).where(Payment.run_id == body["run_id"], Payment.status == PaymentStatus.paid)).one()
        assert g["totals"]["total_usd"] == round(paid, 2)
        assert s.exec(select(func.count()).select_from(Payment).where(Payment.run_id == body["run_id"])).one() == 40


def test_the_three_attacks_and_why(env):
    client, eng = env
    body, g = go(client)
    with Session(eng) as s:
        for pid in (BANK, POISON, CEO):
            assert s.get(Payment, pid).nessie_transfer_id is None  # none of the three moved money
        assert [s.get(Payment, pid).status for pid in (BANK, POISON, CEO)] == [PaymentStatus.blocked, PaymentStatus.blocked, PaymentStatus.held]
        bank = s.exec(select(RiskAssessment).where(RiskAssessment.payment_id == BANK)).one()
        assert bank.decision == Decision.hold_and_verify and bank.hard_rules_fired == ["destination_changed"]
        assert {x["name"] for x in bank.signals_json} >= {"bank_details_changed", "lookalike_domain", "vendor_identity_check"}
        assert all(x["evidence_id"].startswith("evd_") for x in bank.signals_json)
        poison = s.exec(select(RiskAssessment).where(RiskAssessment.payment_id == POISON)).one()
        assert poison.hard_rules_fired == ["hidden_instructions"]
        calls = s.exec(select(VerificationCall).where(VerificationCall.payment_id.in_([BANK, CEO, POISON]))).all()
        assert {c.payment_id: c.outcome for c in calls} == {BANK: CallOutcome.denied, CEO: CallOutcome.unclear}  # no call for the quarantined one
        findings = s.exec(select(InjectionFinding)).all()
        assert [f.technique for f in findings] == ["white_text"] and findings[0].invoice_id == "inv_atk_poisoned_pdf"
        inv = s.get(Invoice, "inv_atk_poisoned_pdf")
        assert inv.extracted_json["quarantined"] is True and inv.extracted_json["finding_ids"] == [findings[0].id]
        atks = s.exec(select(Attack)).all()
        assert len(atks) == 3 and all(a.result.value == "caught" for a in atks)
        assert {a.card for a in atks} == {"classic_bank_change", "poisoned_invoice", "ceo_pressure"}
        assert {a.source.value for a in atks} == {"seeded"}  # stored for the record, but never on the leaderboard
        assert s.get(Message, "msg_atk_poisoned_pdf").is_attack


def test_every_decision_is_assessed_and_audited(env):
    client, eng = env
    body, g = go(client)
    with Session(eng) as s:
        mine = select(Payment.id).where(Payment.run_id == body["run_id"])
        started = s.get(PaymentRun, body["run_id"]).started_at
        assert s.exec(select(func.count()).select_from(RiskAssessment).where(RiskAssessment.payment_id.in_(mine))).one() == 40
        for p in s.exec(select(Payment).where(Payment.run_id == body["run_id"])).all():
            actions = [a.action for a in s.exec(select(AuditLog).where(AuditLog.entity == "payment", AuditLog.entity_id == p.id))]
            assert "risk_assessed" in actions and {p.status.value, "blocked_by_verification"} & set(actions), p.id
        runs = [a.action for a in s.exec(select(AuditLog).where(AuditLog.entity == "run", AuditLog.entity_id == body["run_id"]))]
        assert runs == ["started", "completed"] or set(runs) == {"started", "completed"}
        # CRS only for a changed destination or a first payment: here Summit's and Northside's forged requests
        ident = {a.entity_id for a in s.exec(select(AuditLog).where(AuditLog.action == "identity_check", AuditLog.at >= started))}
        assert ident == {"ven_summit", "ven_northside"}
        assert s.exec(select(func.count()).select_from(AuditLog).where(AuditLog.action == "paid", AuditLog.entity_id.in_(mine))).one() == 37


def test_event_stream_order_for_the_bank_change(env):
    client, eng = env
    body, g = go(client)
    with Session(eng) as s:
        evs = s.exec(select(Event).where(Event.run_id == body["run_id"]).order_by(Event.at)).all()
    types = [e.type for e in evs]
    assert types[0] == "run.started" and types[-2:] == ["run.completed", "run.report"]
    assert types.count("invoice.parsed") == 40 and types.count("risk.scored") == 40 and types.count("payment.paid") == 37
    assert types.count("payment.blocked") == 2 and types.count("payment.held") == 2  # bank change held then blocked; CEO held
    mine = [e.type for e in evs if (e.payload or {}).get("payment_id") == BANK]
    assert mine == ["risk.scored", "payment.held", "call.started", "call.transcript", "call.transcript", "call.transcript", "call.outcome", "payment.blocked"]
    poisoned = [e.type for e in evs if (e.payload or {}).get("payment_id") == POISON or (e.payload or {}).get("invoice_id") == "inv_atk_poisoned_pdf"]
    assert poisoned == ["invoice.parsed", "injection.detected", "risk.scored", "payment.blocked"]
    report = next(e for e in evs if e.type == "run.report").payload
    assert report["paid"] == 37 and report["held"] == 1 and report["blocked"] == 2 and report["blocked_usd"] > 0 and len(report["findings"]) == 3
    assert any("waiting for the controller" in f for f in report["findings"])
    assert [e for e in evs if e.type == "run.completed"][0].payload["total_usd"] == g["totals"]["total_usd"]


def test_second_run_with_nothing_open(env):
    client, _ = env
    go(client)
    body, g = go(client)
    assert body["invoice_count"] == 0 and g["status"] == "completed" and g["totals"]["paid"] == 0


def test_only_one_run_at_a_time(env, monkeypatch):
    client, _ = env
    monkeypatch.setattr(verify, "MOCK_STEP_DELAY", 0.3)
    first = client.post("/api/payment-runs").json()
    second = client.post("/api/payment-runs")
    assert second.status_code == 409 and second.json()["detail"]["run_id"] == first["run_id"]
    while client.get(f"/api/payment-runs/{first['run_id']}").json()["status"] == "running":
        time.sleep(0.05)
    assert client.post("/api/payment-runs").status_code == 202


def test_unknown_run_is_404(env):
    assert env[0].get("/api/payment-runs/run_nope").status_code == 404


def test_five_at_a_time(env, monkeypatch):
    client, _ = env
    real, state, lock = extract.extract_pdf, {"now": 0, "max": 0}, threading.Lock()

    def slow(data):
        with lock:
            state["now"] += 1
            state["max"] = max(state["max"], state["now"])
        time.sleep(0.05)
        try:
            return real(data)
        finally:
            with lock:
                state["now"] -= 1

    monkeypatch.setattr(extract, "extract_pdf", slow)
    go(client)
    assert state["max"] == run.CONCURRENCY == 5


# ---------------------------------------------------------------- safety


def test_verification_confirmed_releases_to_the_new_verified_account(env):
    client, eng = env
    verify.MOCK_OUTCOMES[BANK] = CallOutcome.confirmed
    body, g = go(client)
    assert g["totals"]["paid"] == 38 and g["totals"]["blocked"] == 1 and g["totals"]["held"] == 1
    with Session(eng) as s:
        p = s.get(Payment, BANK)
        acct = s.exec(select(VendorBankAccount).where(VendorBankAccount.vendor_id == "ven_summit", VendorBankAccount.valid_to.is_(None))).one()
        assert p.status == PaymentStatus.paid and p.nessie_transfer_id and p.destination_account_id == acct.id
        assert acct.verified_by_call_id and acct.account_last4 != "2204"
        assert s.exec(select(Attack).where(Attack.payload_ref == "msg_atk_bank_change")).one().result.value == "missed"  # the vendor said yes


def test_other_rules_keep_a_confirmed_payment_held(env, monkeypatch):
    client, eng = env
    verify.MOCK_OUTCOMES[BANK] = CallOutcome.confirmed
    real = risk.RealRiskAssessor.assess

    def with_extra_rule(self, payment, ctx):
        a = real(self, payment, ctx)
        if payment.id == BANK:
            a.hard_rules_fired = a.hard_rules_fired + ["amount_over_max"]
        return a

    monkeypatch.setattr(risk.RealRiskAssessor, "assess", with_extra_rule)
    go(client)
    assert pay_status(eng, BANK) == PaymentStatus.held  # the call settled the account, not the amount


@pytest.mark.parametrize("outcome", [CallOutcome.unclear, CallOutcome.no_answer])
def test_unresolved_calls_leave_the_payment_held(env, outcome):
    client, eng = env
    verify.MOCK_OUTCOMES[CEO] = outcome
    body, g = go(client)
    assert g["totals"]["held"] == 1 and pay_status(eng, CEO) == PaymentStatus.held


def test_a_number_not_on_the_allow_list_stays_held_and_is_logged(env, monkeypatch):
    client, eng = env
    with Session(eng) as s:
        from app.models import VendorContact

        for c in s.exec(select(VendorContact).where(VendorContact.vendor_id == "ven_northside")).all():
            c.phone = "+14085551234"
            s.add(c)
        s.commit()
    from app.services import contacts

    contacts.MOCK_OVERRIDES["ven_northside"] = "+14085551234"
    try:
        body, g = go(client)
    finally:
        contacts.MOCK_OVERRIDES.clear()
    assert pay_status(eng, CEO) == PaymentStatus.held and g["totals"]["held"] == 1
    with Session(eng) as s:
        assert s.exec(select(func.count()).select_from(AuditLog).where(AuditLog.action == "verification_unavailable")).one() == 1
        assert s.exec(select(VerificationCall).where(VerificationCall.payment_id == CEO)).all() == []


def test_backstop_refuses_a_destination_that_is_not_the_last_verified_account(env, monkeypatch):
    client, eng = env
    # A broken assessor AND a broken decision rule both say "pay". The backstop must still stop the money.
    class Liar(risk.RealRiskAssessor):
        def assess(self, payment, ctx):
            a = super().assess(payment, ctx)
            return a.model_copy(update={"score": 0, "decision": Decision.auto_pay, "hard_rules_fired": [], "reasons": []})

    monkeypatch.setattr(risk, "get_assessor", lambda: Liar())
    monkeypatch.setattr(run, "effective_decision", lambda a, changed: Decision.auto_pay)
    sent = []
    real = payments.create_transfer

    async def spy(dest, amount, description):
        sent.append(description.rsplit(" ", 1)[-1])  # "Countersign payment pay_xxx"
        return await real(dest, amount, description)

    monkeypatch.setattr(payments, "create_transfer", spy)
    body, g = go(client)
    assert BANK not in sent and CEO not in sent
    assert pay_status(eng, BANK) == pay_status(eng, CEO) == PaymentStatus.held
    assert g["totals"]["paid"] == 37 - 0 and len(sent) == 37
    with Session(eng) as s:
        refused = s.exec(select(AuditLog).where(AuditLog.entity_id == BANK, AuditLog.action == "held")).one()
        assert refused.detail_json["reason"].startswith("backstop_refused") and "only requested" in refused.detail_json["reason"]


def test_check_destination_reads_the_database_fresh(env):
    client, eng = env
    body, _ = go(client)
    with Session(eng) as s:
        p = s.exec(select(Payment).where(Payment.status == PaymentStatus.paid, Payment.run_id == body["run_id"])).first()
        pid, vendor_id = p.id, s.get(Invoice, p.invoice_id).vendor_id
        assert run.check_destination(pid)[0] is True
        # the vendor's verified account changes underneath the payment
        cur = s.exec(select(VendorBankAccount).where(VendorBankAccount.vendor_id == vendor_id, VendorBankAccount.valid_to.is_(None))).one()
        cur.valid_to = ev_mod.utcnow()
        s.add(cur)
        s.add(VendorBankAccount(id="bac_swapped", vendor_id=vendor_id, routing_hash="x" * 64, account_last4="0000", bank_name="B", valid_from=ev_mod.utcnow()))
        s.commit()
    ok, why = run.check_destination(pid)
    assert ok is False and "closed" in why


def test_a_failed_transaction_leaves_no_partial_records(env, monkeypatch):
    client, eng = env

    def boom(session, findings):
        session.add(InjectionFinding(id="inj_partial", invoice_id="inv_atk_poisoned_pdf", technique="t", snippet="s", confidence=1.0))
        raise RuntimeError("disk full")

    monkeypatch.setattr(run.injection, "save_findings", boom)
    body, g = go(client)
    with Session(eng) as s:
        p = s.get(Payment, POISON)
        assert p.status == PaymentStatus.held  # an error never pays
        assert s.exec(select(RiskAssessment).where(RiskAssessment.payment_id == POISON)).all() == []  # rolled back with it
        assert s.exec(select(func.count()).select_from(InjectionFinding)).one() == 0
        assert (s.get(Invoice, "inv_atk_poisoned_pdf").extracted_json or {}).get("quarantined") is None  # invoice update rolled back too
    assert g["status"] == "completed" and g["totals"]["paid"] == 37


def test_extraction_failure_holds_the_invoice(env, monkeypatch):
    client, eng = env
    real = extract.extract_pdf
    target = (seedmod.PDF_DIR / "inv_1160.pdf").read_bytes()

    def flaky(data):
        if data == target:
            raise extract.ExtractionFailed("invalid_output_after_retry")
        return real(data)

    monkeypatch.setattr(extract, "extract_pdf", flaky)
    body, g = go(client)
    with Session(eng) as s:
        inv = s.exec(select(Invoice).where(Invoice.extracted_json["status"].as_string() == "extraction_failed")).all()
        assert len(inv) == 1
        p = s.exec(select(Payment).where(Payment.invoice_id == inv[0].id)).one()
        assert p.status == PaymentStatus.held and s.exec(select(RiskAssessment).where(RiskAssessment.payment_id == p.id)).all() == []
    assert g["totals"]["paid"] == 36 and g["totals"]["held"] == 2


# ---------------------------------------------------------------- pure helpers


def test_effective_decision_applies_the_spec_thresholds():
    def a(score, rules=(), decision=Decision.auto_pay):
        return risk.Assessment(payment_id="p", score=score, decision=decision, hard_rules_fired=list(rules), hard_rule_actions={}, signals=[],
                               reasons=[], model_version="t")

    assert run.effective_decision(a(0), False) == Decision.auto_pay
    assert run.effective_decision(a(29), False) == Decision.auto_pay
    assert run.effective_decision(a(30), False) == Decision.controller_review
    assert run.effective_decision(a(59), False) == Decision.controller_review
    assert run.effective_decision(a(60), False) == Decision.hold
    assert run.effective_decision(a(0, ["new_vendor"]), False) == Decision.controller_review  # any rule holds, even at score 0
    assert run.effective_decision(a(0), True) == Decision.hold_and_verify  # a changed destination always means a call
    assert run.effective_decision(a(0, ["destination_changed"]), False) == Decision.hold_and_verify


def test_contacts_differ():
    known = ["+14155550100"]
    assert run.contacts_differ("call me on +1 415 555 0177", known) is True
    assert run.contacts_differ("our line is (415) 555-0100", known) is False
    assert run.contacts_differ("no phone here", known) is False
    # bank numbers are not phone numbers
    assert run.contacts_differ("Bank: X\nRouting number: 996031174\nAccount number: 4410886213", known) is False
    assert run.contacts_differ("account 000123456789 routing 021000021", known) is False
    assert run.contacts_differ("call 415-555-0177 or 415.555.0177", known) is True
    assert run.contacts_differ("call +14155550100 or (415) 555-0100", known) is False


# ---------------------------------------------------------------- scripted vs live outcomes


def test_a_denied_override_still_blocks_the_seeded_ceo_attack(env):
    client, eng = env
    verify.MOCK_OUTCOMES[CEO] = CallOutcome.denied  # explicit overrides beat the scripted default
    body, g = go(client)
    assert g["totals"]["held"] == 0 and g["totals"]["blocked"] == 3 and pay_status(eng, CEO) == PaymentStatus.blocked


def test_a_judges_ceo_attack_still_gets_a_denied_call(env):
    """Same attack as the seeded CEO one, launched live: new ids, so the scripted 'unclear' does not apply."""
    client, eng = env
    go(client)  # the seeded run: CEO attack held
    with Session(eng) as s:
        seeded = s.get(Invoice, "inv_atk_ceo_pressure")
        thread = s.get(Message, seeded.message_id).thread_id
        s.add(Message(id="msg_judge_ceo", thread_id=thread, vendor_id="ven_northside", from_addr="dana.whitfield@ridgeline-builders.co",
                      subject="pay today", body="The CEO approved this, please pay today and keep it quiet.", received_at=ev_mod.utcnow(), is_attack=True))
        s.add(Invoice(id="inv_judge_ceo", vendor_id="ven_northside", message_id="msg_judge_ceo", number="NOR-JUDGE", amount_usd=2400.0,
                      due_date=seeded.due_date, remittance_json=seeded.remittance_json, pdf_path=seeded.pdf_path))
        s.commit()
    body, g = go(client)
    assert body["invoice_count"] == 1
    assert g["totals"]["blocked"] == 1 and g["totals"]["held"] == 0
    with Session(eng) as s:
        call = s.exec(select(VerificationCall).where(VerificationCall.payment_id == "pay_judge_ceo")).one()
        assert call.outcome == CallOutcome.denied and s.get(Payment, "pay_judge_ceo").status == PaymentStatus.blocked
        assert s.get(Payment, CEO).status == PaymentStatus.held  # the seeded one is untouched


def test_scripted_outcomes_apply_only_to_the_seeded_payment_id():
    assert set(verify.SEEDED_OUTCOMES) == {"pay_atk_ceo_pressure"}
    assert verify.SEEDED_OUTCOMES[CEO] == CallOutcome.unclear


def test_edge_cases_through_the_run_are_all_held(env):
    """The four hard-rule edge cases join the seeded week: none is paid, and the original 40 still end 37/1/2."""
    from seed import edge_cases

    client, eng = env
    with Session(eng) as s:
        cases = edge_cases.add_edge_cases(s)
    body, g = go(client)
    assert body["invoice_count"] == 44
    assert g["totals"]["paid"] == 37 and g["totals"]["blocked"] == 2 and g["totals"]["held"] == 5
    with Session(eng) as s:
        for c in cases.values():
            p = s.exec(select(Payment).where(Payment.invoice_id == c.invoice_id)).one()
            ras = s.exec(select(RiskAssessment).where(RiskAssessment.payment_id == p.id)).one()
            assert p.status == PaymentStatus.held and p.nessie_transfer_id is None, c.name
            assert ras.hard_rules_fired == [c.rule], c.name
