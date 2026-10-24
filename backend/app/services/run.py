# Owner: Backend lead
# Prize track: Hyphenate (the autonomous payment run), Microsoft, Atlassian (least privilege, hard backstop)
# Contract: POST /api/payment-runs starts a run over every open invoice (an invoice with no payment row)
#   and returns run_id at once; the work runs in a background task, 5 invoices at a time.
#   GET /api/payment-runs/{id} returns status, totals and per-step timings.
#
# Per invoice: extract -> scan -> build payment -> identity (CRS) -> risk -> decide -> verify or pay.
#   * risk_assessments, injection_findings, attack results and audit rows are written by THIS module,
#     in the same transaction as the payment status change (risk and injection never touch the database).
#   * Hard rules beat the assessor: the decision is re-derived from the score and the fired rules, and
#     a changed destination always means a verification call.
#   * Backstop: right before send_transfer the destination is re-read from the database. If it is not
#     the vendor's current verified account, the transfer is refused and logged, whatever risk said.
#   * An error on one invoice never lets it pay: it is held with the error recorded.
# Flags: none of its own; each service it calls picks its mock or real adapter.

import asyncio
import logging
import re
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, update
from sqlmodel import Session, select

from app import events as ev
from app.audit import write_audit
from app.db import engine, get_session
from app.models import (
    Attack,
    AttackSource,
    CallOutcome,
    Decision,
    Invoice,
    Message,
    ModerationStatus,
    AttackResult,
    Payment,
    PaymentRun,
    PaymentStatus,
    RunStatus,
    Vendor,
    VendorBankAccount,
    VendorContact,
    utcnow,
)
from app.services import extract, identity, injection, layout, payments, risk, verify
from app.services.injection import Finding, ScanItem
from app.services.risk import Assessment, Destination, RiskContext

log = logging.getLogger("countersign.run")
router = APIRouter()

CONCURRENCY = 5
BACKEND = Path(__file__).resolve().parents[2]
_ORDER = [Decision.auto_pay, Decision.controller_review, Decision.hold, Decision.hold_and_verify]
# A phone number has a leading + or the usual separators. A bare run of digits is more likely a routing or account number.
_PHONE_RE = re.compile(r"\+\d[\d\s().-]{8,}\d|(?<!\d)\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}(?!\d)")

_active: set[str] = set()  # full runs being processed in this process (a second full run gets a 409)
_mini: set[str] = set()  # one-invoice attack runs being processed (see services/attacks.py); they never block a full run
_claimed: set[str] = set()  # invoices owned by a queued or running attack run; a full run leaves them alone
_tasks: set[asyncio.Task] = set()


# ---------------------------------------------------------------- small helpers


def effective_decision(a: Assessment, destination_changed: bool) -> Decision:
    """Spec thresholds applied again here, so a weak assessor cannot lower a hold."""
    d = a.decision
    if a.score >= 60:
        d = max(d, Decision.hold, key=_ORDER.index)
    elif a.score >= 30:
        d = max(d, Decision.controller_review, key=_ORDER.index)
    if a.hard_rules_fired:
        d = max(d, Decision.controller_review, key=_ORDER.index)
    if destination_changed or "destination_changed" in a.hard_rules_fired:
        d = Decision.hold_and_verify
    return d


def _resolve(path: str) -> Path:
    p = Path(path)
    if p.is_absolute() or p.exists():
        return p
    return BACKEND / p


@lru_cache(maxsize=512)
def _features(path: str, mtime: float) -> Optional[tuple]:
    try:
        return tuple(sorted(layout.features(_resolve(path).read_bytes()).items()))  # tuple: hashable for the cache
    except Exception:
        return None


def _digits(s: str) -> str:
    return re.sub(r"\D", "", s)


def contacts_differ(body: str, known_phones: list[str]) -> bool:
    """True if the request carries a phone number that is not one we already hold for this vendor."""
    known = {_digits(p)[-10:] for p in known_phones}
    return any(_digits(m)[-10:] not in known for m in _PHONE_RE.findall(body or ""))


@dataclass
class Stats:
    steps: dict[str, list[float]] = field(default_factory=dict)
    notes: dict[str, str] = field(default_factory=dict)  # payment id -> latest one-line explanation

    def add(self, step: str, ms: float) -> None:
        self.steps.setdefault(step, []).append(ms)

    def summary(self) -> dict:
        return {k: {"count": len(v), "total": round(sum(v), 1), "avg": round(sum(v) / len(v), 1), "max": round(max(v), 1)} for k, v in self.steps.items()}


@contextmanager
def timer(stats: Stats, step: str, marks: dict):
    t = time.perf_counter()
    try:
        yield
    finally:
        ms = (time.perf_counter() - t) * 1000
        stats.add(step, ms)
        marks[step] = round(ms, 1)


# ---------------------------------------------------------------- loading (read only, no session across awaits)


@dataclass
class Loaded:
    invoice: Invoice
    vendor: Optional[Vendor]
    message: Optional[Message]
    pdf: Optional[bytes]
    current: Optional[VendorBankAccount]
    contact_phones: list[str]
    history_amounts: list[float]
    known_senders: set[str]
    usual_hours: set[int]
    prior_paid: int
    past_layouts: list[dict]  # layout features of the vendor's past invoices (distinct)


def _load(invoice_id: str, run_id: str) -> Loaded:
    with Session(engine) as s:
        inv = s.get(Invoice, invoice_id)
        vendor = s.get(Vendor, inv.vendor_id) if inv.vendor_id else None
        msg = s.get(Message, inv.message_id) if inv.message_id else None
        pdf = _resolve(inv.pdf_path).read_bytes() if inv.pdf_path and _resolve(inv.pdf_path).exists() else None
        current = phones = None
        hist, senders, hours, past, prior = [], set(), set(), [], 0
        if vendor:
            current = s.exec(select(VendorBankAccount).where(VendorBankAccount.vendor_id == vendor.id, VendorBankAccount.valid_to.is_(None))).first()
            phones = [c.phone for c in s.exec(select(VendorContact).where(VendorContact.vendor_id == vendor.id))]
            # History comes from earlier runs only, so the result does not depend on processing order.
            rows = s.exec(
                select(Invoice.amount_usd, Message.from_addr, Message.received_at, Invoice.pdf_path)
                .join(Payment, Payment.invoice_id == Invoice.id)
                .outerjoin(Message, Message.id == Invoice.message_id)
                .where(Invoice.vendor_id == vendor.id, Payment.status == PaymentStatus.paid, Payment.run_id != run_id)
            ).all()
            prior = len(rows)
            for amount, frm, at, path in rows:
                hist.append(amount)
                if frm:
                    senders.add(frm)
                if at:
                    hours.add(at.hour)
                if path:
                    pp = _resolve(path)
                    if pp.exists():
                        feats = _features(path, pp.stat().st_mtime)
                        if feats and dict(feats) not in past:
                            past.append(dict(feats))
        s.expunge_all()
        return Loaded(inv, vendor, msg, pdf, current, phones or [], hist, senders, hours, prior, past)


# ---------------------------------------------------------------- writes (one transaction per decision)


def _attack_for(s: Session, msg: Optional[Message], fired: bool, a: Optional[Assessment], status: PaymentStatus) -> Optional[Attack]:
    """Create or update the leaderboard row for an attack. Held and blocked count as caught."""
    if msg is None or not (msg.is_attack or fired):
        return None
    result = AttackResult.missed if status == PaymentStatus.paid else AttackResult.caught
    atk = s.exec(select(Attack).where(Attack.payload_ref == msg.id)).first()
    if atk is None:
        names = {x.name for x in a.signals} if a else set()
        card = "poisoned_invoice" if fired else "classic_bank_change" if "lookalike_domain" in names else "ceo_pressure" if "urgency_language" in names else "freestyle"
        atk = Attack(attacker_name="Seeded attack", source=AttackSource.console, card=card, payload_ref=msg.id, moderation_status=ModerationStatus.approved)
    atk.result = result
    s.add(atk)
    return atk


def _payment_id(invoice_id: str) -> str:
    return "pay_" + invoice_id.split("_", 1)[-1]  # deterministic: inv_1160 -> pay_1160, inv_atk_x -> pay_atk_x


def _commit_decision(
    run_id: str, ld: Loaded, ex: Optional[extract.Extraction], status: PaymentStatus, amount: float, destination_id: Optional[str],
    a: Optional[Assessment], findings: list[Finding], fired: bool, ident: Optional[identity.IdentityResult], reason: str,
    transfer_id: Optional[str] = None, extraction_failure: Optional[str] = None,
) -> tuple[str, Optional[Attack]]:
    """Payment row + risk assessment + injection findings + invoice update + audit, all or nothing."""
    with Session(engine) as s:
        inv = s.get(Invoice, ld.invoice.id)
        msg = s.get(Message, inv.message_id) if inv.message_id else None
        if ex:
            inv.number, inv.amount_usd, inv.due_date = ex.invoice_number, ex.amount_usd, ex.due_date
            inv.remittance_json = ex.remittance.model_dump() if ex.remittance else None
            inv.extracted_json = {"status": "ok", **ex.model_dump(mode="json")}
        elif extraction_failure:
            inv.extracted_json = {"status": "extraction_failed", "reason": extraction_failure}
        if fired:
            inv.extracted_json = {**(inv.extracted_json or {}), "quarantined": True, "finding_ids": [f.evidence_id for f in findings]}
            if msg:
                msg.is_attack = True
                s.add(msg)
        s.add(inv)
        pay = Payment(id=_payment_id(inv.id), run_id=run_id, invoice_id=inv.id, amount_usd=amount, destination_account_id=destination_id,
                      status=status, nessie_transfer_id=transfer_id)
        s.add(pay)
        if findings:
            injection.save_findings(s, findings)
            write_audit("invoice", inv.id, "agent", "quarantined" if fired else "injection_findings",
                        {"findings": [{"id": f.evidence_id, "technique": f.technique, "confidence": f.confidence} for f in findings]}, session=s)
        if ident:
            write_audit("vendor", ld.vendor.id, "agent", "identity_check", ident.model_dump(mode="json"), session=s)
        if a:
            row = a.to_row()
            row.id = "ras_" + pay.id.split("_", 1)[-1]
            s.add(row)
            write_audit("payment", pay.id, "agent", "risk_assessed",
                        {"assessment_id": row.id, "score": a.score, "decision": a.decision.value, "hard_rules_fired": a.hard_rules_fired}, session=s)
        write_audit("payment", pay.id, "agent", status.value, {"reason": reason, "transfer_id": transfer_id}, session=s)
        atk = _attack_for(s, msg, fired, a, status)
        if atk:
            write_audit("attack", atk.id, "agent", f"attack_{atk.result.value}", {"payment_id": pay.id, "card": atk.card}, session=s)
        s.commit()
        if atk:
            s.refresh(atk)
            s.expunge(atk)
        return pay.id, atk


def _release(payment_id: str, run_id: str, transfer_id: Optional[str], status: PaymentStatus, reason: str, audit_action: str) -> Optional[Attack]:
    """Second transaction for a payment that waited on a call: pay it, or record why it stays held."""
    with Session(engine) as s:
        pay = s.get(Payment, payment_id)
        pay.status, pay.nessie_transfer_id = status, transfer_id
        s.add(pay)
        write_audit("payment", pay.id, "agent", audit_action, {"reason": reason, "transfer_id": transfer_id}, session=s)
        inv = s.get(Invoice, pay.invoice_id)
        msg = s.get(Message, inv.message_id) if inv.message_id else None
        atk = _attack_for(s, msg, False, None, status) if (msg and msg.is_attack) else None
        s.commit()
        if atk:
            s.refresh(atk)
            s.expunge(atk)
        return atk


def check_destination(payment_id: str) -> tuple[bool, str]:
    """The hard backstop. Reads the database fresh: the payment must go to the vendor's CURRENT verified
    account, and the invoice must not be asking for any other account."""
    with Session(engine) as s:
        pay = s.get(Payment, payment_id)
        inv = s.get(Invoice, pay.invoice_id)
        if not inv.vendor_id:
            return False, "invoice has no vendor"
        current = s.exec(select(VendorBankAccount).where(VendorBankAccount.vendor_id == inv.vendor_id, VendorBankAccount.valid_to.is_(None))).first()
        if current is None:
            return False, "vendor has no verified bank account"
        if pay.destination_account_id != current.id:
            return False, "payment destination is not the last verified account"
        rem = inv.remittance_json
        if rem and (rem.get("routing_hash"), rem.get("account_last4")) != (current.routing_hash, current.account_last4):
            return False, "invoice asks for an account that is not the last verified one"
        return True, "ok"


# ---------------------------------------------------------------- the pipeline for one invoice


async def _pay(run_id: str, payment_id: str, stats: Stats, marks: dict, prelim: Optional[tuple] = None) -> PaymentStatus:
    """Backstop, then send_transfer. Returns the final status. `prelim` is (ld, ex, amount, dest, a, findings, ident) for the
    auto-pay path, where the payment row does not exist yet and is written together with the assessment."""
    ok, why = check_destination_for(payment_id, prelim)
    if not ok:
        log.warning("backstop refused %s: %s", payment_id, why)
        return await _finish(run_id, payment_id, stats, marks, prelim, PaymentStatus.held, f"backstop_refused: {why}", None)
    try:
        with timer(stats, "transfer", marks):
            pay = Payment(id=payment_id, run_id=run_id, invoice_id=prelim[0].invoice.id if prelim else "", amount_usd=prelim[2] if prelim else 0,
                          destination_account_id=prelim[3] if prelim else None, status=PaymentStatus.pending)
            if not prelim:
                with Session(engine) as s:
                    pay = s.get(Payment, payment_id)
                    s.expunge(pay)
            transfer_id = await payments.send_transfer(pay)
    except Exception as exc:
        log.exception("transfer failed for %s", payment_id)
        return await _finish(run_id, payment_id, stats, marks, prelim, PaymentStatus.held, f"transfer_failed: {type(exc).__name__}", None)
    return await _finish(run_id, payment_id, stats, marks, prelim, PaymentStatus.paid, "paid to the last verified account", transfer_id)


def check_destination_for(payment_id: str, prelim: Optional[tuple]) -> tuple[bool, str]:
    if prelim is None:
        return check_destination(payment_id)
    # Payment not written yet: apply the same checks to the values we are about to pay.
    ld, ex, amount, dest, a, findings, ident = prelim
    with Session(engine) as s:
        current = s.exec(select(VendorBankAccount).where(VendorBankAccount.vendor_id == ld.invoice.vendor_id, VendorBankAccount.valid_to.is_(None))).first()
    if current is None:
        return False, "vendor has no verified bank account"
    if dest != current.id:
        return False, "payment destination is not the last verified account"
    rem = ex.remittance if ex else None
    req = (rem.routing_hash, rem.account_last4) if rem else ((ld.invoice.remittance_json or {}).get("routing_hash"), (ld.invoice.remittance_json or {}).get("account_last4")) if ld.invoice.remittance_json else None
    if req and req != (current.routing_hash, current.account_last4):
        return False, "invoice asks for an account that is not the last verified one"
    return True, "ok"


async def _finish(run_id, payment_id, stats, marks, prelim, status: PaymentStatus, reason: str, transfer_id: Optional[str]) -> PaymentStatus:
    with timer(stats, "commit", marks):
        if prelim:
            ld, ex, amount, dest, a, findings, ident = prelim
            _, atk = _commit_decision(run_id, ld, ex, status, amount, dest, a, findings, False, ident, reason, transfer_id)
            vendor_name = ld.vendor.name
        else:
            audit_action = status.value if status != PaymentStatus.held else "held_after_verification"
            atk = _release(payment_id, run_id, transfer_id, status, reason, audit_action)
            vendor_name = ""
    stats.notes[payment_id] = reason
    if prelim:
        await ev.emit(ev.RiskScored(run_id=run_id, payment_id=payment_id, score=prelim[4].score, decision=prelim[4].decision, top_signals=prelim[4].signals[:4]))
    if status == PaymentStatus.paid:
        await ev.emit(ev.PaymentPaid(run_id=run_id, payment_id=payment_id, nessie_transfer_id=transfer_id))
    else:
        await ev.emit(ev.PaymentHeld(run_id=run_id, payment_id=payment_id, reasons=[reason] + (prelim[4].reasons if prelim else [])))
    if atk:
        await _emit_attack(run_id, atk)
    return status


async def _emit_attack(run_id: str, atk: Attack) -> None:
    await ev.emit(ev.AttackLogged(run_id=run_id, attack_id=atk.id, attacker_name=atk.attacker_name, source=atk.source, card=atk.card,
                                  result=atk.result, moderation_status=atk.moderation_status))


async def process_invoice(run_id: str, invoice_id: str, stats: Stats) -> None:
    marks: dict[str, float] = {}
    t0 = time.perf_counter()
    try:
        await _process(run_id, invoice_id, stats, marks)
    except Exception as exc:  # never let an error pay: hold it with the error recorded
        log.exception("invoice %s failed", invoice_id)
        try:
            await _hold_on_error(run_id, invoice_id, f"processing_error: {type(exc).__name__}", stats)
        except Exception:
            log.exception("could not record failure for %s", invoice_id)
    marks["total"] = round((time.perf_counter() - t0) * 1000, 1)
    stats.add("total", marks["total"])
    log.info("timing %s %s", invoice_id, " ".join(f"{k}={v}ms" for k, v in marks.items()))


async def _hold_on_error(run_id: str, invoice_id: str, reason: str, stats: Stats) -> None:
    pid = _payment_id(invoice_id)
    atk = None
    with Session(engine) as s:
        inv = s.get(Invoice, invoice_id)
        if s.get(Payment, pid) is None:
            s.add(Payment(id=pid, run_id=run_id, invoice_id=invoice_id, amount_usd=inv.amount_usd or 0.0, status=PaymentStatus.held))
            write_audit("payment", pid, "agent", "held", {"reason": reason}, session=s)
            msg = s.get(Message, inv.message_id) if inv.message_id else None
            atk = _attack_for(s, msg, False, None, PaymentStatus.held)  # held counts as caught: an attack that could not move money
            s.commit()
            if atk:
                s.refresh(atk)
                s.expunge(atk)
    stats.notes[pid] = reason
    await ev.emit(ev.PaymentHeld(run_id=run_id, payment_id=pid, reasons=[reason]))
    if atk:
        await _emit_attack(run_id, atk)


async def _process(run_id: str, invoice_id: str, stats: Stats, marks: dict) -> None:
    ld = await asyncio.to_thread(_load, invoice_id, run_id)
    inv, vendor, msg = ld.invoice, ld.vendor, ld.message
    pid = _payment_id(invoice_id)
    if vendor is None:
        return await _hold_on_error(run_id, invoice_id, "extraction_failed: invoice is not linked to a vendor", stats)

    # 1. extract (cached by content hash)
    ex: Optional[extract.Extraction] = None
    failure: Optional[str] = None
    with timer(stats, "extract", marks):
        if ld.pdf is not None:
            try:
                ex = await asyncio.to_thread(extract.extract_pdf, ld.pdf)
            except extract.ExtractionFailed as exc:
                failure = exc.reason
        elif inv.amount_usd and inv.number:
            pass  # no PDF: trust the row an earlier step filled
        else:
            failure = "no_pdf_and_no_fields"
    amount = ex.amount_usd if ex else (inv.amount_usd or 0.0)
    if ex or not failure:  # an invoice with no PDF (an emailed request) is "parsed" from its row
        await ev.emit(ev.InvoiceParsed(run_id=run_id, invoice_id=inv.id, vendor=vendor.name, amount_usd=amount))
    if failure:
        reason = f"extraction_failed: {failure}"
        _commit_decision(run_id, ld, None, PaymentStatus.held, amount, ld.current.id if ld.current else None, None, [], False, None, reason,
                         extraction_failure=failure)
        stats.notes[pid] = reason
        await ev.emit(ev.PaymentHeld(run_id=run_id, payment_id=pid, reasons=[reason]))
        return

    # 2. scan the invoice and the message
    findings: list[Finding] = []
    with timer(stats, "scan", marks):
        if ld.pdf is not None:
            findings += await asyncio.to_thread(injection.scan, ScanItem(kind="pdf", pdf_bytes=ld.pdf, invoice_id=inv.id))
        if msg is not None:
            findings += await asyncio.to_thread(injection.scan, ScanItem(kind="email", text=msg.body, message_id=msg.id))
    fired = any(f.confidence >= risk.HIDDEN_RULE_MIN_CONFIDENCE for f in findings)

    # 3. build the payment: where it would go, where the invoice asks it to go
    rem = ex.remittance if ex else None
    if rem:
        requested = Destination(rem.routing_hash, rem.account_last4)
    elif inv.remittance_json:
        requested = Destination(inv.remittance_json["routing_hash"], inv.remittance_json["account_last4"])
    else:
        requested = None
    last = Destination(ld.current.routing_hash, ld.current.account_last4) if ld.current else None
    destination_changed = requested is not None and requested != last
    dest_id = ld.current.id if ld.current else None

    # 4. CRS identity check: changed destination or first payment (skipped when the document is already quarantined)
    ident = None
    if not fired and (destination_changed or ld.prior_paid == 0):
        with timer(stats, "identity", marks):
            ident = await identity.check(vendor)

    # 5. risk
    with timer(stats, "risk", marks):
        features = await asyncio.to_thread(layout.features, ld.pdf) if (ld.pdf is not None and ld.past_layouts) else None
        ctx = RiskContext(
            vendor=vendor, requested_destination=requested, last_verified_destination=last, message=msg, history_amounts=ld.history_amounts,
            prior_payment_count=ld.prior_paid, known_sender_addresses=ld.known_senders, usual_send_hours=ld.usual_hours or None,
            layout_features=features, past_layout_features=ld.past_layouts, requested_contacts_differ=contacts_differ(msg.body if msg else "", ld.contact_phones),
            injection_findings=findings, identity=ident,
        )
        payment = Payment(id=pid, run_id=run_id, invoice_id=inv.id, amount_usd=amount, destination_account_id=dest_id, status=PaymentStatus.pending)
        a = await asyncio.to_thread(risk.assess, payment, ctx)  # may call Claude: keep it off the event loop
    decision = effective_decision(a, destination_changed)

    # 6a. quarantined: block
    if fired:
        reason = "Hidden instructions detected in the document; quarantined"
        with timer(stats, "commit", marks):
            _, atk = _commit_decision(run_id, ld, ex, PaymentStatus.blocked, amount, dest_id, a, findings, True, ident, reason)
        stats.notes[pid] = reason
        for f in findings:
            await ev.emit(ev.InjectionDetected(run_id=run_id, invoice_id=f.invoice_id, message_id=None if f.invoice_id else f.message_id,
                                               technique=f.technique, snippet=f.snippet))
        await ev.emit(ev.RiskScored(run_id=run_id, payment_id=pid, score=a.score, decision=a.decision, top_signals=a.signals[:4]))
        await ev.emit(ev.PaymentBlocked(run_id=run_id, payment_id=pid, reason=reason))
        if atk:
            await _emit_attack(run_id, atk)
        return

    prelim = (ld, ex, amount, dest_id, a, findings, ident)

    # 6b. clean: auto-pay through the backstop
    if decision == Decision.auto_pay:
        await _pay(run_id, pid, stats, marks, prelim)
        return

    # 6c. hold; a changed destination also gets a verification call
    reasons = a.reasons or ["held for review"]
    with timer(stats, "commit", marks):
        _, atk = _commit_decision(run_id, ld, ex, PaymentStatus.held, amount, dest_id, a, findings, False, ident, "; ".join(reasons[:2]))
    stats.notes[pid] = reasons[0]
    for f in findings:  # low-confidence findings are still recorded and shown
        await ev.emit(ev.InjectionDetected(run_id=run_id, invoice_id=f.invoice_id, message_id=None if f.invoice_id else f.message_id,
                                           technique=f.technique, snippet=f.snippet))
    await ev.emit(ev.RiskScored(run_id=run_id, payment_id=pid, score=a.score, decision=a.decision, top_signals=a.signals[:4]))
    await ev.emit(ev.PaymentHeld(run_id=run_id, payment_id=pid, reasons=reasons))
    if atk:
        await _emit_attack(run_id, atk)
    if decision != Decision.hold_and_verify:
        return

    with timer(stats, "verify", marks):
        try:
            result = await verify.start_verification(pid)
        except Exception as exc:
            log.warning("verification unavailable for %s: %s", pid, type(exc).__name__)
            note = f"verification_unavailable: {type(exc).__name__}"
            _release(pid, run_id, None, PaymentStatus.held, note, "verification_unavailable")
            stats.notes[pid] = note
            await ev.emit(ev.PaymentHeld(run_id=run_id, payment_id=pid, reasons=[note] + reasons))
            return

    if result.outcome == CallOutcome.denied:
        stats.notes[pid] = "Vendor denied the bank change on the verification call"
        return  # verify blocked it and emitted payment.blocked
    if result.outcome != CallOutcome.confirmed:
        stats.notes[pid] = f"verification {result.outcome.value}; waiting for the controller"
        return
    # Confirmed. Release only if the destination was the only reason for the hold.
    others = [r for r in a.hard_rules_fired if r != "destination_changed"]
    if others:
        stats.notes[pid] = f"call confirmed the account, but {', '.join(others)} still needs the controller"
        _release(pid, run_id, None, PaymentStatus.held, stats.notes[pid], "held_after_verification")
        await ev.emit(ev.PaymentHeld(run_id=run_id, payment_id=pid, reasons=[stats.notes[pid]]))
        return
    await _pay(run_id, pid, stats, marks, None)


# ---------------------------------------------------------------- the run


def _open_invoice_ids(s: Session) -> list[str]:
    return [i for i in s.exec(select(Invoice.id).where(~Invoice.id.in_(select(Payment.invoice_id))).order_by(Invoice.id)).all() if i not in _claimed]


def is_active(run_id: str) -> bool:
    """True while this process is still processing the run."""
    return run_id in _active or run_id in _mini


def full_run_active() -> bool:
    return bool(_active)


async def start_mini_run(run_id: str, invoice_id: str) -> None:
    """Process one invoice as its own run (an attack). The caller has already claimed the invoice."""
    _mini.add(run_id)
    try:
        await execute_run(run_id, [invoice_id], _mini)
    finally:
        _claimed.discard(invoice_id)


def mark_stale_runs() -> None:
    """A run left 'running' by a crashed process can never finish; mark it failed at startup."""
    with Session(engine) as s:
        s.execute(update(PaymentRun).where(PaymentRun.status == RunStatus.running).values(status=RunStatus.failed))
        s.commit()


def _totals(s: Session, run_id: str) -> dict:
    rows = s.exec(select(Payment.status, func.count(), func.coalesce(func.sum(Payment.amount_usd), 0.0)).where(Payment.run_id == run_id).group_by(Payment.status)).all()
    by = {st.value if hasattr(st, "value") else st: (n, usd) for st, n, usd in rows}
    g = lambda k: by.get(k, (0, 0.0))  # noqa: E731
    return {"paid": g("paid")[0], "held": g("held")[0], "blocked": g("blocked")[0], "pending": g("pending")[0],
            "total_usd": round(g("paid")[1], 2), "blocked_usd": round(g("blocked")[1], 2)}


async def execute_run(run_id: str, invoice_ids: list[str], registry: Optional[set[str]] = None) -> None:
    registry = _active if registry is None else registry
    started = time.perf_counter()
    stats = Stats()
    try:
        await ev.emit(ev.RunStarted(run_id=run_id, invoice_count=len(invoice_ids)))
        sem = asyncio.Semaphore(CONCURRENCY)

        async def one(iid: str) -> None:
            async with sem:
                await process_invoice(run_id, iid, stats)

        await asyncio.gather(*(one(i) for i in invoice_ids))

        wall = round(time.perf_counter() - started, 2)
        with Session(engine) as s:
            totals = _totals(s, run_id)
            run = s.get(PaymentRun, run_id)
            run.status, run.completed_at = RunStatus.completed, utcnow()
            run.totals_json = {**(run.totals_json or {}), **totals, "wall_seconds": wall, "timings_ms": stats.summary()}
            s.add(run)
            write_audit("run", run_id, "system", "completed", {k: totals[k] for k in ("paid", "held", "blocked", "total_usd")}, session=s)
            s.commit()
            notes = []
            for pay, vname in s.exec(select(Payment, Vendor.name).join(Invoice, Invoice.id == Payment.invoice_id).join(Vendor, Vendor.id == Invoice.vendor_id)
                                     .where(Payment.run_id == run_id, Payment.status != PaymentStatus.paid).order_by(Payment.id)).all():
                notes.append(f"{vname}: {stats.notes.get(pay.id, pay.status.value)}")
        log.info("run %s done in %ss: %s", run_id, wall, totals)
        await ev.emit(ev.RunCompleted(run_id=run_id, paid=totals["paid"], held=totals["held"], blocked=totals["blocked"], total_usd=totals["total_usd"]))
        await ev.emit(ev.RunReport(
            run_id=run_id,
            summary=(f"{len(invoice_ids)} invoices processed: {totals['paid']} paid (${totals['total_usd']:,.2f}), {totals['held']} held for the controller, "
                     f"{totals['blocked']} blocked (${totals['blocked_usd']:,.2f} protected)."),
            paid=totals["paid"], held=totals["held"], blocked=totals["blocked"], paid_usd=totals["total_usd"], blocked_usd=totals["blocked_usd"], findings=notes))
    except Exception:
        log.exception("run %s failed", run_id)
        with Session(engine) as s:
            run = s.get(PaymentRun, run_id)
            run.status, run.completed_at = RunStatus.failed, utcnow()
            s.add(run)
            s.commit()
    finally:
        registry.discard(run_id)


# ---------------------------------------------------------------- routes


@router.post("/payment-runs", status_code=202)
async def start_run() -> dict:
    """Start a run over every open invoice. Returns at once; follow it on /payment-runs/{id}/events."""
    if _active:
        raise HTTPException(409, detail={"error": "a payment run is already in progress", "run_id": next(iter(_active))})
    with Session(engine) as s:
        ids = _open_invoice_ids(s)
        run = PaymentRun(totals_json={"invoice_count": len(ids)})
        s.add(run)
        write_audit("run", run.id, "system", "started", {"invoice_count": len(ids)}, session=s)
        s.commit()
        run_id = run.id
    _active.add(run_id)
    task = asyncio.create_task(execute_run(run_id, ids))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return {"run_id": run_id, "invoice_count": len(ids), "events_url": f"/api/payment-runs/{run_id}/events"}


@router.get("/payment-runs/{run_id}")
def get_run(run_id: str, session: Session = Depends(get_session)) -> dict:
    run = session.get(PaymentRun, run_id)
    if run is None:
        raise HTTPException(404, "run not found")
    saved = run.totals_json or {}
    totals = _totals(session, run_id)
    return {
        "id": run.id,
        "status": run.status.value,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
        "invoice_count": saved.get("invoice_count"),
        "totals": totals,
        "wall_seconds": saved.get("wall_seconds"),
        "timings_ms": saved.get("timings_ms"),
    }
