import hashlib
import json
import re
import statistics
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import pytest
from rapidfuzz.distance import Levenshtein
from sqlalchemy import create_engine, func
from sqlmodel import Session, SQLModel, select

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from seed import seed as seedmod  # noqa: E402

from app.config import Settings  # noqa: E402
from app.models import (  # noqa: E402
    Attack,
    AttackSource,
    AuditLog,
    CallOutcome,
    ContactSource,
    Decision,
    Invoice,
    Message,
    Payment,
    PaymentStatus,
    Vendor,
    VendorBankAccount,
    VendorContact,
    VerificationCall,
)
from app.services import extract, risk  # noqa: E402
from app.services.injection import ScanItem  # noqa: E402
from tests.helpers import BACKEND, build_context  # noqa: E402


def fresh_session(tmp_path, name="db"):
    engine = create_engine(f"sqlite:///{tmp_path}/{name}.sqlite")
    SQLModel.metadata.create_all(engine)
    return Session(engine)


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    s = fresh_session(tmp_path_factory.mktemp("seed"))
    started = time.perf_counter()
    summary = seedmod.seed_database(s)
    elapsed = time.perf_counter() - started
    yield s, summary, elapsed
    s.close()


def open_invoices(s):
    return s.exec(select(Invoice).where(~Invoice.id.in_(select(Payment.invoice_id)))).all()


# ---------------------------------------------------------------- shape


def test_seed_is_fast(world):
    assert world[2] < 10


def test_vendors(world):
    s, *_ = world
    vendors = s.exec(select(Vendor)).all()
    assert len(vendors) == 30
    assert len({v.email_domain for v in vendors}) == 30
    assert {"concrete", "steel", "electrical", "plumbing", "lumber", "equipment rental"} <= {v.trade for v in vendors}


def test_history_volume_and_billing_patterns(world):
    s, *_ = world
    paid = s.exec(select(Invoice).where(Invoice.id.in_(select(Payment.invoice_id)))).all()
    assert 1100 <= len(paid) <= 1300
    per_vendor = Counter(i.vendor_id for i in paid)
    for v in seedmod.VENDORS:
        n = per_vendor[f"ven_{v.key}"]
        assert n >= 8, v.key  # every vendor has enough history for the risk engine
        if v.kind == "monthly":
            assert 10 <= n <= 11, v.key
        if v.kind == "progress":
            assert n >= 40, v.key
        if v.kind == "rental":
            assert n < 40, v.key
    assert all(p.status == PaymentStatus.paid and p.nessie_transfer_id for p in s.exec(select(Payment)).all())


def test_seasonality_busier_in_spring_summer(world):
    s, *_ = world
    month_n, month_amt = Counter(), defaultdict(list)
    for inv_date, amt in s.exec(select(Message.received_at, Invoice.amount_usd).join(Invoice, Invoice.message_id == Message.id)
                                .where(Invoice.vendor_id.in_([f"ven_{v.key}" for v in seedmod.VENDORS if v.kind == "progress"]))):
        month_n[inv_date.month] += 1
        month_amt[inv_date.month].append(amt)
    busy = sum(month_n[m] for m in (4, 5, 6, 7)) / 4
    slow = sum(month_n[m] for m in (12, 1, 2)) / 3
    assert busy > 1.5 * slow
    assert statistics.mean(sum((month_amt[m] for m in (5, 6)), [])) > 1.5 * statistics.mean(sum((month_amt[m] for m in (12, 1)), []))


# ---------------------------------------------------------------- bank and contacts


def test_every_vendor_has_exactly_one_current_verified_account(world):
    s, *_ = world
    for v in s.exec(select(Vendor)).all():
        current = s.exec(select(VendorBankAccount).where(VendorBankAccount.vendor_id == v.id, VendorBankAccount.valid_to.is_(None))).all()
        assert len(current) == 1, v.id
        assert len(current[0].account_last4) == 4 and re.fullmatch(r"[0-9a-f]{64}", current[0].routing_hash)


def test_four_legitimate_bank_changes_each_with_a_confirmed_call(world):
    s, *_ = world
    changed = s.exec(select(VendorBankAccount).where(VendorBankAccount.verified_by_call_id.is_not(None))).all()
    assert len(changed) == 4
    for acct in changed:
        call = s.get(VerificationCall, acct.verified_by_call_id)
        assert call.outcome == CallOutcome.confirmed and call.transcript and call.contact_id
        pay = s.get(Payment, call.payment_id)
        assert pay.destination_account_id == acct.id and pay.status == PaymentStatus.paid
        old = s.exec(select(VendorBankAccount).where(VendorBankAccount.vendor_id == acct.vendor_id, VendorBankAccount.valid_to.is_not(None))).one()
        assert old.valid_to == acct.valid_from and old.account_last4 != acct.account_last4
    assert len(s.exec(select(VerificationCall)).all()) == 4


def test_no_full_account_or_routing_numbers_in_database(world):
    s, *_ = world
    blob = json.dumps([a.model_dump(mode="json") for a in s.exec(select(VendorBankAccount)).all()]
                      + [i.remittance_json for i in s.exec(select(Invoice)).all()])
    assert not re.search(r"\b99\d{7}\b", blob) and not re.search(r"\b\d{9,}\b", blob)


def test_contacts_on_file_plus_independent_source(world):
    s, *_ = world
    for v in s.exec(select(Vendor)).all():
        cs = s.exec(select(VendorContact).where(VendorContact.vendor_id == v.id)).all()
        assert {c.source for c in cs} >= {ContactSource.on_file}
        indep = [c for c in cs if c.source != ContactSource.on_file]
        assert len(indep) == 1 and indep[0].source_url.startswith("https://")
    for c in s.exec(select(VendorContact)).all():
        assert re.fullmatch(r"\+1415555\d{4}", c.phone), c.phone  # obviously fake 555 numbers (demo phone unset in tests)


def test_demo_phone_is_used_for_summit_when_configured(tmp_path, monkeypatch):
    monkeypatch.setattr(seedmod, "get_settings", lambda: Settings(demo_vendor_phone="+14155550142"))
    s = fresh_session(tmp_path)
    seedmod.seed_database(s, write_pdfs=False)
    phones = {c.phone for c in s.exec(select(VendorContact).where(VendorContact.vendor_id == "ven_summit"))}
    assert phones == {"+14155550142"}


# ---------------------------------------------------------------- messages and send times


def test_send_times_are_consistent_per_vendor(world):
    s, *_ = world
    hours = defaultdict(set)
    for vid, ts in s.exec(select(Message.vendor_id, Message.received_at).where(Message.is_attack.is_(False))):
        hours[vid].add(ts.hour)
    for vid, hs in hours.items():
        assert max(hs) - min(hs) <= 6, vid  # one daily window per vendor
    # different vendors work different windows
    assert len({tuple(sorted(h)) for h in hours.values()}) > 3


# ---------------------------------------------------------------- this week


def test_this_week_is_40_open_invoices_37_clean_3_attacks(world):
    s, summary, _ = world
    opened = open_invoices(s)
    assert len(opened) == 40 and len(summary.clean_invoice_ids) == 37
    attacks = s.exec(select(Message).where(Message.is_attack.is_(True))).all()
    assert {m.id for m in attacks} == {p["message"] for p in seedmod.PLANTED.values()}
    assert {i.id for i in opened} - set(summary.clean_invoice_ids) == {p["invoice"] for p in seedmod.PLANTED.values()}
    assert all((seedmod.PDF_DIR / f"{i.id}.pdf").exists() for i in opened)
    assert s.exec(select(func.count()).select_from(Attack)).one() == 0


def test_clean_invoices_match_a_verified_account_and_score_clean(world):
    s, summary, _ = world
    for inv_id in summary.clean_invoice_ids:
        inv = s.get(Invoice, inv_id)
        cur = s.exec(select(VendorBankAccount).where(VendorBankAccount.vendor_id == inv.vendor_id, VendorBankAccount.valid_to.is_(None))).one()
        assert (inv.remittance_json["routing_hash"], inv.remittance_json["account_last4"]) == (cur.routing_hash, cur.account_last4)
        payment, ctx = build_context(s, inv)
        a = risk.assess(payment, ctx)
        assert a.hard_rules_fired == [] and a.decision == Decision.auto_pay and a.score == 0, (inv_id, a.reasons)


def test_bank_change_attack(world):
    s, *_ = world
    inv = s.get(Invoice, seedmod.PLANTED["bank_change"]["invoice"])
    msg = s.get(Message, inv.message_id)
    assert msg.thread_id == "thr_summit_0919" and msg.from_addr.endswith("@summit-concrete.co")
    real = s.exec(select(Message).where(Message.thread_id == "thr_summit_0919", Message.is_attack.is_(False))).all()
    assert real and all(m.from_addr.endswith("@summitconcrete.com") for m in real)  # a real earlier thread
    payment, ctx = build_context(s, inv)
    a = risk.assess(payment, ctx)
    names = {x.name for x in a.signals}
    assert a.decision == Decision.hold_and_verify and "destination_changed" in a.hard_rules_fired
    assert {"bank_details_changed", "lookalike_domain", "reply_to_mismatch", "urgency_language"} <= names
    assert [x.detail for x in a.signals if x.name == "bank_details_changed"] == ["New account ending 7781; last verified ending 2204"]


def test_poisoned_pdf_attack(world):
    s, *_ = world
    inv = s.get(Invoice, seedmod.PLANTED["poisoned_pdf"]["invoice"])
    payment, ctx = build_context(s, inv)
    assert {f.technique for f in ctx.injection_findings} >= {"white_text"}
    a = risk.assess(payment, ctx)
    assert "hidden_instructions" in a.hard_rules_fired and a.decision != Decision.auto_pay
    assert "destination_changed" not in a.hard_rules_fired  # visible remittance is the real account; the hidden text asks for another
    assert "AI assistant" not in "".join(m.body for m in s.exec(select(Message).where(Message.id == inv.message_id)))  # email itself is clean


def test_ceo_pressure_attack(world):
    s, *_ = world
    inv = s.get(Invoice, seedmod.PLANTED["ceo_pressure"]["invoice"])
    msg = s.get(Message, inv.message_id)
    assert "CEO approved" in msg.body and "quiet" in msg.body and msg.thread_id == seedmod.PLANTED["ceo_pressure"]["thread"]
    payment, ctx = build_context(s, inv)
    a = risk.assess(payment, ctx)
    names = {x.name for x in a.signals}
    assert a.decision == Decision.hold_and_verify and {"urgency_language", "first_message_from_sender", "bank_details_changed", "outside_usual_hours"} <= names


def test_pdfs_extract_to_the_database_values(world, monkeypatch, tmp_path):
    s, *_ = world
    monkeypatch.setattr(extract, "get_settings", lambda: Settings(mock_claude=True, extract_cache_dir=str(tmp_path)))
    for inv in open_invoices(s):
        ex = extract.extract_pdf((BACKEND / inv.pdf_path).read_bytes())
        assert (ex.invoice_number, ex.amount_usd, ex.due_date) == (inv.number, inv.amount_usd, inv.due_date)
        assert ex.vendor_name == s.get(Vendor, inv.vendor_id).name
        assert ex.remittance.routing_hash == inv.remittance_json["routing_hash"]
        assert ex.remittance.account_last4 == inv.remittance_json["account_last4"]


# ---------------------------------------------------------------- lookalikes


def test_ten_lookalike_domains(world):
    _, summary, _ = world
    assert len(summary.lookalikes) == 10
    names = {v.key: v.domain for v in seedmod.VENDORS}
    for entry in summary.lookalikes:
        legit, fake = entry["legit"], entry["lookalike"]
        assert fake != legit and fake not in names.values()
        assert Levenshtein.distance(fake, legit) <= 2, entry
    assert (summary.lookalikes[0]["legit"], summary.lookalikes[0]["lookalike"]) == ("summitconcrete.com", "summit-concrete.co")


# ---------------------------------------------------------------- determinism and reset


def digest(s: Session) -> dict:
    out = {}
    for t in SQLModel.metadata.sorted_tables:
        rows = s.execute(t.select()).mappings().all()
        out[t.name] = (len(rows), hashlib.sha256(json.dumps(sorted(json.dumps(dict(r), default=str, sort_keys=True) for r in rows)).encode()).hexdigest())
    return out


def pdf_hashes():
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(seedmod.PDF_DIR.glob("*.pdf"))}


def test_two_runs_are_identical(tmp_path):
    a, b = fresh_session(tmp_path, "a"), fresh_session(tmp_path, "b")
    sa = seedmod.seed_database(a)
    pa = pdf_hashes()
    sb = seedmod.seed_database(b)
    pb = pdf_hashes()
    assert sa.counts == sb.counts
    assert digest(a) == digest(b)  # same rows, same ids, same values
    assert pa == pb and len(pa) == 77  # PDF bytes identical, so the extraction cache keeps hitting
    ids = lambda s, m: sorted(x for x in s.exec(select(m.id)))  # noqa: E731
    assert ids(a, Invoice) == ids(b, Invoice) and ids(a, Payment) == ids(b, Payment)


def test_reseed_over_existing_data_resets_it(tmp_path):
    s = fresh_session(tmp_path)
    seedmod.seed_database(s, write_pdfs=False)
    before = digest(s)
    s.add(Message(thread_id="thr_x", from_addr="a@b.com", subject="s", body="b"))
    s.add(Attack(attacker_name="x", source=AttackSource.judge, card="c"))
    s.add(AuditLog(entity="x", entity_id="y", actor="system", action="a"))
    s.commit()
    seedmod.seed_database(s, write_pdfs=False)
    assert digest(s) == before  # everything wiped, including attacks and append-only tables
    s.add(Attack(attacker_name="x", source=AttackSource.judge, card="c"))
    s.commit()
    seedmod.seed_database(s, keep_attacks=True, write_pdfs=False)
    assert s.exec(select(func.count()).select_from(Attack)).one() == 1
