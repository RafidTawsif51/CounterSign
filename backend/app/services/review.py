# Owner: Backend lead
# Prize track: Hyphenate (humans approve the exceptions), Microsoft (responsible design), Atlassian (least privilege)
# Contract:
#   GET  /api/payments/{id}          everything a controller needs to decide: payment, invoice, vendor, risk with
#                                    signals, injection findings, CRS result, calls with transcripts, the audit trail
#   POST /api/payments/{id}/approve  {reason, approver}. Held payments only. Pays the vendor's LAST VERIFIED account,
#                                    never the account an invoice or email asks for, and never writes a bank account.
#                                    The transfer goes through the same destination check as the run's backstop.
#   POST /api/payments/{id}/reject   {reason, approver}. Held payments only. Sets the payment to blocked.
#   Both decisions are audited as actor human (approver and reason in the detail) and emit payment.reviewed, then
#   payment.paid or payment.blocked. A payment cannot be decided while its payment run is still processing it, and an
#   approval claims the payment with one conditional update first, so two clicks cannot send two transfers.
#   Message, call and finding text is untrusted: render it as text.

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import update
from sqlmodel import Session, select

from app import events as ev
from app.audit import write_audit
from app.db import engine, get_session
from app.models import (
    AuditActor,
    AuditLog,
    InjectionFinding,
    Invoice,
    Message,
    Payment,
    PaymentStatus,
    RiskAssessment,
    Vendor,
    VendorBankAccount,
    VendorContact,
    VerificationCall,
)
from app.services import payments, risk, run, verify
from app.services.vendors import call_view, identity_for

router = APIRouter()


class ReviewIn(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)
    approver: str = Field(min_length=1, max_length=100)

    @field_validator("reason", "approver")
    @classmethod
    def _clean(cls, v: str) -> str:
        v = v.strip()
        if not v or any(ord(c) < 32 and c not in "\n\t" for c in v):
            raise ValueError("must be plain text")
        return v


def _conflict(error: str, **extra) -> HTTPException:
    return HTTPException(409, detail={"error": error, **extra})


def _current_account(s: Session, vendor_id: Optional[str]) -> Optional[VendorBankAccount]:
    """The vendor's trusted account (verify.current_verified_account): never an account that only came from a payment request."""
    return verify.open_verified_account(s, vendor_id) if vendor_id else None


def _is_unverified_request(s: Session, acct: Optional[VendorBankAccount], vendor_id: Optional[str]) -> bool:
    """True for a candidate account that a payment request created (verify.record_requested_destination) and no call has verified."""
    if acct is None or acct.vendor_id != vendor_id or acct.verified_by_call_id:
        return False
    return s.exec(select(AuditLog.id).where(AuditLog.entity == "vendor_bank_account", AuditLog.entity_id == acct.id, AuditLog.action == verify.REQUESTED_ACTION)).first() is not None


def _account_view(a: Optional[VendorBankAccount], trusted_id: Optional[str] = None) -> Optional[dict]:
    return None if a is None else {"id": a.id, "bank_name": a.bank_name, "account_last4": a.account_last4, "valid_from": a.valid_from,
                                   "valid_to": a.valid_to, "verified_by_call_id": a.verified_by_call_id,
                                   "trusted": a.id == trusted_id}  # false for an account that only came from a payment request


def _latest_assessment(s: Session, payment_id: str) -> Optional[RiskAssessment]:
    return s.exec(select(RiskAssessment).where(RiskAssessment.payment_id == payment_id).order_by(RiskAssessment.id.desc())).first()


def _guard_decidable(pay: Payment, verb: str) -> None:
    if run.is_active(pay.run_id):
        raise _conflict("the payment run is still processing this payment", run_id=pay.run_id)
    if pay.status != PaymentStatus.held:
        raise _conflict(f"only held payments can be {verb}", status=pay.status.value)


def _released_to_held(payment_id: str) -> None:
    with Session(engine) as s:
        s.execute(update(Payment).where(Payment.id == payment_id, Payment.status == PaymentStatus.pending).values(status=PaymentStatus.held))
        s.commit()


# ---------------------------------------------------------------- GET


@router.get("/payments/{payment_id}")
async def get_payment(payment_id: str, session: Session = Depends(get_session)) -> dict:
    pay = session.get(Payment, payment_id)
    if pay is None:
        raise HTTPException(404, "payment not found")
    inv = session.get(Invoice, pay.invoice_id)
    vendor = session.get(Vendor, inv.vendor_id) if inv and inv.vendor_id else None
    msg = session.get(Message, inv.message_id) if inv and inv.message_id else None
    ras = _latest_assessment(session, pay.id)
    current = _current_account(session, vendor.id if vendor else None)
    destination = session.get(VendorBankAccount, pay.destination_account_id) if pay.destination_account_id else None
    dest_is_request = _is_unverified_request(session, destination, vendor.id if vendor else None)
    requested = inv.remittance_json if inv else None
    requested_differs = bool(requested and current and (requested.get("routing_hash"), requested.get("account_last4")) != (current.routing_hash, current.account_last4))

    findings = session.exec(select(InjectionFinding).where((InjectionFinding.invoice_id == inv.id) | (InjectionFinding.message_id == (msg.id if msg else None)))).all() if inv else []
    calls = session.exec(select(VerificationCall).where(VerificationCall.payment_id == pay.id).order_by(VerificationCall.started_at)).all()
    contacts = {c.id: c for c in session.exec(select(VendorContact).where(VendorContact.vendor_id == (vendor.id if vendor else "")))}
    entities = [("payment", pay.id)] + ([("invoice", inv.id)] if inv else []) + ([("message", msg.id)] if msg else [])
    audit: list[AuditLog] = []
    for ent, eid in entities:
        audit += session.exec(select(AuditLog).where(AuditLog.entity == ent, AuditLog.entity_id == eid)).all()
    audit.sort(key=lambda a: (a.at, a.id))

    reasons = []
    if ras:
        reasons = [f"{r}: {risk.HARD_RULE_ACTIONS[r]}" for r in ras.hard_rules_fired if r in risk.HARD_RULE_ACTIONS]
        reasons += [f"{s['name']}: {s['detail']}" for s in ras.signals_json if s.get("weight", 0) > 0 and s["name"] != "vendor_identity_check"][:4]
    ident = await identity_for(session, vendor) if vendor else None

    can_approve, approve_blocked = True, None
    if pay.status != PaymentStatus.held:
        can_approve, approve_blocked = False, f"payment is {pay.status.value}"
    elif run.is_active(pay.run_id):
        can_approve, approve_blocked = False, "the payment run is still processing it"
    elif ras and "hidden_instructions" in ras.hard_rules_fired:
        can_approve, approve_blocked = False, "quarantined document: reject it"
    elif current is None:
        can_approve, approve_blocked = False, "the vendor has no verified bank account to pay"
    elif pay.destination_account_id != current.id and not dest_is_request:
        can_approve, approve_blocked = False, "no current verified account matches this payment"

    return {
        "payment": {"id": pay.id, "run_id": pay.run_id, "status": pay.status.value, "amount_usd": pay.amount_usd, "nessie_transfer_id": pay.nessie_transfer_id,
                    "transfer_mode": pay.transfer_mode,
                    "destination": _account_view(destination, current.id if current else None), "last_verified_account": _account_view(current, current.id if current else None),
                    "approve_pays": _account_view(current, current.id if current else None)},  # approving always pays this account
        "invoice": None if inv is None else {
            "id": inv.id, "number": inv.number, "amount_usd": inv.amount_usd, "due_date": inv.due_date, "has_pdf": bool(inv.pdf_path),
            "requested_remittance": requested, "requested_account_differs_from_verified": requested_differs,
            "quarantined": bool((inv.extracted_json or {}).get("quarantined")), "extraction_status": (inv.extracted_json or {}).get("status")},
        "vendor": None if vendor is None else {"id": vendor.id, "name": vendor.name, "trade": vendor.trade, "email_domain": vendor.email_domain,
                                               "status": vendor.status.value, "created_at": vendor.created_at, "identity": ident},
        "message": None if msg is None else {"id": msg.id, "thread_id": msg.thread_id, "from_addr": msg.from_addr, "reply_to": msg.reply_to,
                                             "subject": msg.subject, "body": msg.body, "received_at": msg.received_at, "is_attack": msg.is_attack},
        "risk": None if ras is None else {
            "id": ras.id, "score": ras.score, "decision": ras.decision.value, "hard_rules_fired": ras.hard_rules_fired,
            "hard_rule_actions": {r: risk.HARD_RULE_ACTIONS.get(r) for r in ras.hard_rules_fired}, "signals": ras.signals_json,
            "model_version": ras.model_version, "reasons": reasons},
        "injection_findings": [{"id": f.id, "technique": f.technique, "snippet": f.snippet, "confidence": f.confidence,
                                "invoice_id": f.invoice_id, "message_id": f.message_id} for f in findings],
        "identity": ident,
        "calls": [call_view(c, contacts.get(c.contact_id) if c.contact_id else None) for c in calls],
        "audit": [{"id": a.id, "at": a.at, "entity": a.entity, "entity_id": a.entity_id, "actor": a.actor.value, "action": a.action, "detail": a.detail_json} for a in audit],
        "actions": {"can_approve": can_approve, "approve_blocked_reason": approve_blocked, "can_reject": pay.status == PaymentStatus.held and not run.is_active(pay.run_id)},
    }


# ---------------------------------------------------------------- approve


@router.post("/payments/{payment_id}/approve")
async def approve(payment_id: str, body: ReviewIn) -> dict:
    with Session(engine) as s:
        pay = s.get(Payment, payment_id)
        if pay is None:
            raise HTTPException(404, "payment not found")
        _guard_decidable(pay, "approved")
        inv = s.get(Invoice, pay.invoice_id)
        ras = _latest_assessment(s, pay.id)
        if ras and "hidden_instructions" in ras.hard_rules_fired:
            raise _conflict("this document was quarantined for hidden instructions; reject it instead of approving")
        current = _current_account(s, inv.vendor_id if inv else None)
        if current is None:
            raise _conflict("the vendor has no verified bank account to pay")
        # The payment points either at the verified account, or at the UNVERIFIED account the invoice asked for. In the second
        # case approving pays the verified account instead, never the requested one. Anything else (an account that was
        # trusted once, someone else's account, no account) is refused.
        repoint = False
        if pay.destination_account_id != current.id:
            if not _is_unverified_request(s, s.get(VendorBankAccount, pay.destination_account_id) if pay.destination_account_id else None, inv.vendor_id):
                raise _conflict("the vendor's verified account changed after this payment was held; it needs a fresh review", payment_destination=pay.destination_account_id,
                                verified_account=current.id)
            repoint = True
        unverified_id = pay.destination_account_id if repoint else None
        requested = inv.remittance_json or {}
        asks_other = bool(requested) and (requested.get("routing_hash"), requested.get("account_last4")) != (current.routing_hash, current.account_last4)
        run_id, amount, current_id, current_last4 = pay.run_id, pay.amount_usd, current.id, current.account_last4
        invoice_id = pay.invoice_id
        # Claim the payment: only one request can move it from held to pending.
        claimed = s.execute(update(Payment).where(Payment.id == payment_id, Payment.status == PaymentStatus.held).values(status=PaymentStatus.pending)).rowcount
        s.commit()
        if claimed != 1:
            raise _conflict("another request is already deciding this payment")

    # The backstop, read fresh right before the money moves: the destination must STILL be the current verified account.
    with Session(engine) as s:
        now_current = _current_account(s, s.get(Invoice, invoice_id).vendor_id)
    if now_current is None or now_current.id != current_id:
        _released_to_held(payment_id)
        raise _conflict("the vendor's verified account changed while approving; nothing was sent")

    transient = Payment(id=payment_id, run_id=run_id, invoice_id=invoice_id, amount_usd=amount, destination_account_id=current_id, status=PaymentStatus.pending)
    try:
        transfer_id = await payments.send_transfer(transient)
    except Exception as exc:
        _released_to_held(payment_id)
        with Session(engine) as s:
            write_audit("payment", payment_id, AuditActor.human, "approve_failed", {"approver": body.approver, "reason": body.reason, "error": type(exc).__name__}, session=s)
            s.commit()
        raise HTTPException(502, detail={"error": "the transfer failed; the payment is still held", "type": type(exc).__name__})

    with Session(engine) as s:
        pay = s.get(Payment, payment_id)
        pay.status, pay.nessie_transfer_id, pay.destination_account_id = PaymentStatus.paid, str(transfer_id), current_id
        mode = payments.record_transfer_mode(s, pay, transfer_id)  # stores the mode; audits a Nessie failure
        s.add(pay)
        write_audit("payment", payment_id, AuditActor.human, "approved",
                    {"approver": body.approver, "reason": body.reason, "paid_account_id": current_id, "paid_account_last4": current_last4,
                     "invoice_asked_for_a_different_account": asks_other, "new_account_created": False,
                     "unverified_requested_account_id": unverified_id, "requested_account_trusted": False}, session=s)
        write_audit("payment", payment_id, AuditActor.agent, "paid", {"reason": "approved by the controller", "transfer_id": transfer_id,
                                                                      "to_last_verified_account": True}, session=s)
        s.commit()
    await ev.emit(ev.PaymentReviewed(run_id=run_id, payment_id=payment_id, decision="approved", approver=body.approver, reason=body.reason))
    await ev.emit(ev.PaymentPaid(run_id=run_id, payment_id=payment_id, nessie_transfer_id=str(transfer_id), transfer_mode=mode))
    return {"payment_id": payment_id, "status": "paid", "nessie_transfer_id": str(transfer_id), "transfer_mode": mode, "paid_account_last4": current_last4,
            "invoice_asked_for_a_different_account": asks_other}


# ---------------------------------------------------------------- reject


@router.post("/payments/{payment_id}/reject")
async def reject(payment_id: str, body: ReviewIn) -> dict:
    with Session(engine) as s:
        pay = s.get(Payment, payment_id)
        if pay is None:
            raise HTTPException(404, "payment not found")
        _guard_decidable(pay, "rejected")
        run_id = pay.run_id
        changed = s.execute(update(Payment).where(Payment.id == payment_id, Payment.status == PaymentStatus.held).values(status=PaymentStatus.blocked)).rowcount
        if changed != 1:
            s.rollback()
            raise _conflict("another request is already deciding this payment")
        write_audit("payment", payment_id, AuditActor.human, "rejected", {"approver": body.approver, "reason": body.reason}, session=s)
        s.commit()
    reason = f"Rejected by {body.approver}: {body.reason}"
    await ev.emit(ev.PaymentReviewed(run_id=run_id, payment_id=payment_id, decision="rejected", approver=body.approver, reason=body.reason))
    await ev.emit(ev.PaymentBlocked(run_id=run_id, payment_id=payment_id, reason=reason))
    return {"payment_id": payment_id, "status": "blocked"}
