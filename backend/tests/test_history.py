"""Email threads and past decisions in the seed."""

import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlmodel import Session, SQLModel, func, select

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from seed import history  # noqa: E402
from seed import seed as seedmod  # noqa: E402

from app.models import (  # noqa: E402
    AuditActor,
    AuditLog,
    CallOutcome,
    Decision,
    Invoice,
    Message,
    Payment,
    PaymentStatus,
    RiskAssessment,
    Vendor,
    VendorBankAccount,
    VerificationCall,
)
from tests.helpers import BACKEND  # noqa: E402

# Digest of this week's 40 invoices, their messages and their PDFs, taken BEFORE threads and past decisions were added.
# If this changes, this week's demo data moved.
THIS_WEEK_DIGEST = "b8908959e26d425ca7db2e80c3225b146dbbb2b395d096a37aa8ee716d9f0fd8"


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    engine = create_engine(f"sqlite:///{tmp_path_factory.mktemp('hist')}/h.sqlite")
    SQLModel.metadata.create_all(engine)
    s = Session(engine)
    summary = seedmod.seed_database(s)
    yield s, summary
    s.close()


def threads(s):
    out = defaultdict(list)
    for m in s.exec(select(Message).order_by(Message.received_at, Message.id)).all():
        out[m.thread_id].append(m)
    return out


# ---------------------------------------------------------------- this week did not move


def test_this_week_is_byte_for_byte_unchanged(world):
    s, _ = world
    open_invs = s.exec(select(Invoice).where(~Invoice.id.in_(select(Payment.invoice_id))).order_by(Invoice.id)).all()
    h = hashlib.sha256()
    for i in open_invs:
        m = s.get(Message, i.message_id)
        h.update(json.dumps([i.id, i.vendor_id, i.message_id, i.number, i.amount_usd, str(i.due_date), i.remittance_json, i.pdf_path, m.id, m.thread_id,
                             m.from_addr, m.reply_to, m.subject, m.body, m.received_at.isoformat(), m.is_attack], sort_keys=True).encode())
        h.update((BACKEND / i.pdf_path).read_bytes())
    assert len(open_invs) == 40 and h.hexdigest() == THIS_WEEK_DIGEST


# ---------------------------------------------------------------- threads


def test_most_threads_have_two_to_four_messages(world):
    s, summary = world
    sizes = Counter(len(v) for v in threads(s).values())
    history_threads = sum(n for size, n in sizes.items() if size >= 2)
    assert history_threads >= 0.9 * 1159 and all(2 <= size <= 5 for size in sizes if size > 1)
    assert set(summary.history["threads"]) == {2, 3, 4} and all(summary.history["threads"].values())
    assert sizes[1] == 40 - 2  # this week's new invoices; the two attack replies joined existing threads


def test_replies_stay_in_their_thread_and_vendor_and_come_after_the_invoice(world):
    s, _ = world
    for tid, msgs in threads(s).items():
        assert len({m.vendor_id for m in msgs}) == 1, tid  # the vendor comes from the thread
        assert [m.received_at for m in msgs] == sorted(m.received_at for m in msgs)
        if len(msgs) > 1 and not any(m.is_attack for m in msgs):
            assert msgs[0].from_addr.endswith(("@" + s.get(Vendor, msgs[0].vendor_id).email_domain)), tid  # the vendor starts the thread
            assert all(m.received_at > msgs[0].received_at for m in msgs[1:])


def test_maria_confirms_payment(world):
    s, _ = world
    confirmed = [m for m in s.exec(select(Message).where(Message.from_addr == history.MARIA)).all() if "went out in Thursday's payment run" in m.body]
    assert len(confirmed) > 1000
    pay = s.get(Payment, "pay_0001")
    inv = s.get(Invoice, pay.invoice_id)
    mine = [m for m in confirmed if m.thread_id == s.get(Message, inv.message_id).thread_id]
    assert len(mine) == 1 and pay.nessie_transfer_id in mine[0].body and inv.number in mine[0].body


def test_late_payment_questions_and_corrected_invoices(world):
    s, summary = world
    ts = threads(s)
    late = [v for v in ts.values() if any("past due?" in m.subject for m in v)]
    corrected = [v for v in ts.values() if any(m.subject.startswith("Corrected invoice") for m in v)]
    assert len(late) == summary.history["late"] > 20 and len(corrected) == summary.history["corrected"] > 20
    for msgs in late[:25]:
        q, a = [m for m in msgs if "past due?" in m.subject]
        assert q.from_addr == msgs[0].from_addr and a.from_addr == history.MARIA and a.received_at > q.received_at
        paid = [m for m in msgs if "went out in Thursday's payment run" in m.body][0]
        assert paid.received_at > a.received_at
    for msgs in corrected[:25]:
        first, fix, ack, paid = msgs
        inv = s.exec(select(Invoice).where(Invoice.message_id == first.id)).one()
        assert f"${inv.amount_usd:,.2f}" not in first.body  # the first email had the wrong total
        assert f"correct total is ${inv.amount_usd:,.2f}" in fix.body and ack.from_addr == history.MARIA


def test_bank_change_threads_show_the_phone_confirmation(world):
    s, _ = world
    for key in seedmod.BANK_CHANGES:
        call = s.get(VerificationCall, f"cal_{key}_change")
        acct = s.get(VendorBankAccount, f"bac_{key}_2")
        thread = s.get(Message, s.get(Invoice, s.get(Payment, call.payment_id).invoice_id).message_id).thread_id
        msgs = threads(s)[thread]
        assert len(msgs) == 4 and msgs[0].subject == "Updated remittance details"
        assert "confirm it by phone" in msgs[1].body and "Confirmed by phone" in msgs[2].body
        assert acct.account_last4 in msgs[2].body and msgs[2].received_at > call.started_at


# ---------------------------------------------------------------- past decisions


def test_every_past_payment_has_an_assessment_and_audit_trail(world):
    s, summary = world
    pays = s.exec(select(Payment)).all()
    assert len(pays) == 1159 and summary.history["assessments"] == 1159
    assessed = {a.payment_id: a for a in s.exec(select(RiskAssessment)).all()}
    assert set(assessed) == {p.id for p in pays}
    actions = defaultdict(list)
    for a in s.exec(select(AuditLog).where(AuditLog.entity == "payment")).all():
        actions[a.entity_id].append(a.action)
    for p in pays:
        assert "risk_assessed" in actions[p.id] and "paid" in actions[p.id], p.id
        assert all(x["evidence_id"].startswith("evd_h") for x in assessed[p.id].signals_json)
    assert s.exec(select(func.count()).select_from(AuditLog)).one() > 2300


def test_five_holds_were_cleared_by_the_controller(world):
    s, summary = world
    approvals = s.exec(select(AuditLog).where(AuditLog.action == "approved")).all()
    assert len(approvals) == 5 == summary.history["holds_cleared"] and all(a.actor == AuditActor.human for a in approvals)
    assert {s.get(Invoice, s.get(Payment, a.entity_id).invoice_id).vendor_id for a in approvals} == {f"ven_{k}" for k in history.HOLD_VENDORS}
    for a in approvals:
        ras = s.exec(select(RiskAssessment).where(RiskAssessment.payment_id == a.entity_id)).one()
        assert ras.decision == Decision.controller_review and ras.hard_rules_fired == ["new_vendor"]
        chain = [x.action for x in sorted(s.exec(select(AuditLog).where(AuditLog.entity_id == a.entity_id)).all(), key=lambda r: r.at)]
        assert chain == ["risk_assessed", "held", "approved", "paid"]
        assert s.get(Payment, a.entity_id).status == PaymentStatus.paid
        v = s.get(Vendor, s.get(Invoice, s.get(Payment, a.entity_id).invoice_id).vendor_id)
        first = s.exec(select(func.min(Invoice.id)).where(Invoice.vendor_id == v.id, Invoice.id.in_(select(Payment.invoice_id)))).one()
        assert s.get(Payment, a.entity_id).invoice_id == first  # it really was the vendor's first payment
        assert (s.get(Message, s.get(Invoice, first).message_id).received_at - v.created_at).days < 30


def test_four_bank_changes_can_be_explained_from_the_records(world):
    """What /ask needs: 'this vendor changed banks before and confirmed it by phone'."""
    s, summary = world
    assert summary.history["bank_changes"] == 4
    for key in seedmod.BANK_CHANGES:
        acct = s.get(VendorBankAccount, f"bac_{key}_2")
        call = s.get(VerificationCall, acct.verified_by_call_id)
        assert call.outcome == CallOutcome.confirmed and call.transcript and "Yes" in call.transcript[1]["text"]
        ras = s.exec(select(RiskAssessment).where(RiskAssessment.payment_id == call.payment_id)).one()
        assert ras.decision == Decision.hold_and_verify and ras.hard_rules_fired == ["destination_changed"]
        sig = ras.signals_json[0]
        assert sig["name"] == "bank_details_changed" and f"ending {acct.account_last4}" in sig["detail"]
        chain = [x.action for x in sorted(s.exec(select(AuditLog).where(AuditLog.entity_id == call.payment_id)).all(), key=lambda r: r.at)]
        assert chain == ["risk_assessed", "held", "verification_call", "paid"]
        vendor_log = [x.action for x in s.exec(select(AuditLog).where(AuditLog.entity_id == f"ven_{key}"))]
        assert "bank_account_verified" in vendor_log and "identity_check" in vendor_log


def test_ordinary_payments_are_clean_and_outliers_are_honest(world):
    s, _ = world
    rows = s.exec(select(RiskAssessment)).all()
    plain = [r for r in rows if not r.hard_rules_fired]
    assert len(plain) >= 1150 and all(r.decision == Decision.auto_pay and r.score < 30 for r in plain)
    outliers = [r for r in plain if r.signals_json]
    assert all(r.signals_json[0]["name"] == "amount_outlier" and r.score == 15 for r in outliers)
