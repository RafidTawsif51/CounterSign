# Owner: Backend lead
# Prize track: Hyphenate (the controller's view), CRS (the identity result sits on the vendor), Microsoft
# Contract:
#   GET /api/vendors                 vendors with a risk summary and the latest CRS result on file
#   GET /api/vendors/{id}/history    invoices, bank history, contacts and calls (with transcripts) for one vendor
#   Read only, except that the history call runs the CRS check once for a vendor that has none on file and
#   records it in the audit log (actor system, action identity_check), so the vendor card always has a result.
#   Phone numbers are masked to the last four digits. Message and call text is untrusted: render it as text.

from collections import defaultdict
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlmodel import Session, select

from app.audit import write_audit
from app.db import get_session
from app.models import (
    AuditLog,
    Invoice,
    Message,
    Payment,
    PaymentRun,
    PaymentStatus,
    RiskAssessment,
    Vendor,
    VendorBankAccount,
    VendorContact,
    VerificationCall,
)
from app.services import identity, verify

router = APIRouter()


def mask_phone(phone: str) -> str:
    return f"{phone[:2]}***{phone[-4:]}" if len(phone) > 6 else "***"


def latest_identity_map(session: Session, vendor_ids: Optional[list[str]] = None) -> dict[str, dict]:
    """The newest identity_check audit row per vendor, as the stored CRS result."""
    q = select(AuditLog).where(AuditLog.entity == "vendor", AuditLog.action == "identity_check").order_by(AuditLog.at)
    out: dict[str, dict] = {}
    for row in session.exec(q):
        if vendor_ids is None or row.entity_id in vendor_ids:
            out[row.entity_id] = {**(row.detail_json or {}), "checked_at": (row.detail_json or {}).get("checked_at") or row.at.isoformat()}
    return out


async def identity_for(session: Session, vendor: Vendor) -> dict:
    """The stored CRS result, or run the check once and keep it."""
    stored = latest_identity_map(session, [vendor.id]).get(vendor.id)
    if stored:
        return stored
    result = await identity.check(vendor)
    detail = result.model_dump(mode="json")
    write_audit("vendor", vendor.id, "system", "identity_check", detail, session=session)
    session.commit()
    return detail


def bank_view(a: VendorBankAccount, calls: dict[str, VerificationCall], trusted_id: Optional[str] = None, requested_ids: frozenset = frozenset()) -> dict:
    call = calls.get(a.verified_by_call_id) if a.verified_by_call_id else None
    requested = a.id in requested_ids and not a.verified_by_call_id
    verified_by = ("phone call: " + call.outcome.value) if call and call.outcome else ("requested, not verified" if requested else "onboarding" if a.verified_by_call_id is None else "unknown")
    return {
        "id": a.id, "bank_name": a.bank_name, "account_last4": a.account_last4, "valid_from": a.valid_from, "valid_to": a.valid_to,
        "current": a.id == trusted_id, "trusted": a.id == trusted_id, "verified_by_call_id": a.verified_by_call_id, "verified_by": verified_by,
    }


def call_view(c: VerificationCall, contact: Optional[VendorContact]) -> dict:
    return {
        "id": c.id, "payment_id": c.payment_id, "started_at": c.started_at, "outcome": c.outcome.value if c.outcome else None,
        "transcript": c.transcript or [], "recording_url": c.recording_url,
        "contact": {"id": contact.id, "source": contact.source.value, "source_url": contact.source_url, "phone": mask_phone(contact.phone)} if contact else None,
    }


@router.get("/vendors")
def list_vendors(session: Session = Depends(get_session)) -> list[dict]:
    vendors = session.exec(select(Vendor).order_by(Vendor.name)).all()
    current = {v.id: verify.open_verified_account(session, v.id) for v in vendors}  # the trusted account, never a requested candidate
    accounts_n = dict(session.exec(select(VendorBankAccount.vendor_id, func.count()).group_by(VendorBankAccount.vendor_id)).all())
    by_status: dict[str, dict[str, int]] = defaultdict(lambda: {"paid": 0, "held": 0, "blocked": 0, "pending": 0})
    for vid, st, n in session.exec(select(Invoice.vendor_id, Payment.status, func.count()).join(Invoice, Invoice.id == Payment.invoice_id).group_by(Invoice.vendor_id, Payment.status)):
        by_status[vid][st.value] = n
    open_n = dict(session.exec(select(Invoice.vendor_id, func.count()).where(~Invoice.id.in_(select(Payment.invoice_id))).group_by(Invoice.vendor_id)).all())
    attacks = dict(session.exec(select(Message.vendor_id, func.count()).where(Message.is_attack.is_(True)).group_by(Message.vendor_id)).all())
    flagged: dict[str, int] = defaultdict(int)  # payments where a hard rule fired
    for vid, rules in session.exec(select(Invoice.vendor_id, RiskAssessment.hard_rules_fired).join(Payment, Payment.invoice_id == Invoice.id)
                                   .join(RiskAssessment, RiskAssessment.payment_id == Payment.id)):
        if rules:
            flagged[vid] += 1
    latest: dict[str, tuple] = {}
    for vid, pid, score, dec in session.exec(select(Invoice.vendor_id, Payment.id, RiskAssessment.score, RiskAssessment.decision)
                                             .join(Invoice, Invoice.id == Payment.invoice_id).join(PaymentRun, PaymentRun.id == Payment.run_id)
                                             .join(RiskAssessment, RiskAssessment.payment_id == Payment.id).order_by(PaymentRun.started_at, Payment.id)):
        latest[vid] = (pid, score, dec)
    ident = latest_identity_map(session)
    requested_n: dict[str, int] = defaultdict(int)  # accounts that came from a payment request and no call has verified
    cand_ids = set(session.exec(select(AuditLog.entity_id).where(AuditLog.entity == "vendor_bank_account", AuditLog.action == verify.REQUESTED_ACTION)).all())
    for vid, aid, vcall, closed in session.exec(select(VendorBankAccount.vendor_id, VendorBankAccount.id, VendorBankAccount.verified_by_call_id, VendorBankAccount.valid_to)):
        if aid in cand_ids and not vcall and closed is None:
            requested_n[vid] += 1
    out = []
    for v in vendors:
        st = by_status[v.id]
        lp = latest.get(v.id)
        acct = current.get(v.id)
        out.append({
            "id": v.id, "name": v.name, "trade": v.trade, "email_domain": v.email_domain, "website_url": v.website_url, "status": v.status.value, "created_at": v.created_at,
            "current_account": {"bank_name": acct.bank_name, "account_last4": acct.account_last4, "since": acct.valid_from} if acct else None,
            "unverified_requested_accounts": requested_n.get(v.id, 0),
            "identity": ident.get(v.id),  # the CRS result, or null if no check has run yet (the history call runs one)
            "risk_summary": {
                "payments": st, "open_invoices": open_n.get(v.id, 0), "attack_messages": attacks.get(v.id, 0), "flagged_payments": flagged.get(v.id, 0),
                "bank_changes": max(0, accounts_n.get(v.id, 1) - 1),
                "latest_payment_id": lp[0] if lp else None, "latest_score": lp[1] if lp else None, "latest_decision": lp[2].value if lp else None,
                "attention": "blocked" if st["blocked"] else "held" if st["held"] else "clear",
            },
        })
    return out


@router.get("/vendors/{vendor_id}/history")
async def vendor_history(vendor_id: str, limit: int = Query(300, ge=1, le=2000), session: Session = Depends(get_session)) -> dict:
    vendor = session.get(Vendor, vendor_id)
    if vendor is None:
        raise HTTPException(404, "vendor not found")
    ident = await identity_for(session, vendor)

    invoices = session.exec(select(Invoice).where(Invoice.vendor_id == vendor_id).order_by(Invoice.id.desc()).limit(limit)).all()
    pays = {p.invoice_id: p for p in session.exec(select(Payment).where(Payment.invoice_id.in_([i.id for i in invoices])))} if invoices else {}
    ras = {r.payment_id: r for r in session.exec(select(RiskAssessment).where(RiskAssessment.payment_id.in_([p.id for p in pays.values()])))} if pays else {}
    all_pay_ids = list(session.exec(select(Payment.id).join(Invoice, Invoice.id == Payment.invoice_id).where(Invoice.vendor_id == vendor_id)).all())
    calls = session.exec(select(VerificationCall).where(VerificationCall.payment_id.in_(all_pay_ids)).order_by(VerificationCall.started_at)).all() if all_pay_ids else []
    contacts = session.exec(select(VendorContact).where(VendorContact.vendor_id == vendor_id).order_by(VendorContact.first_seen)).all()
    by_contact = {c.id: c for c in contacts}
    accounts = session.exec(select(VendorBankAccount).where(VendorBankAccount.vendor_id == vendor_id).order_by(VendorBankAccount.valid_from)).all()
    trusted = verify.open_verified_account(session, vendor_id)
    requested_ids = frozenset(session.exec(select(AuditLog.entity_id).where(AuditLog.entity == "vendor_bank_account", AuditLog.action == verify.REQUESTED_ACTION)).all())
    call_by_id = {c.id: c for c in calls}

    rows = []
    for i in invoices:
        p, r = pays.get(i.id), (ras.get(pays[i.id].id) if i.id in pays else None)
        rows.append({
            "id": i.id, "number": i.number, "amount_usd": i.amount_usd, "due_date": i.due_date, "has_pdf": bool(i.pdf_path),
            "remittance": i.remittance_json, "payment_id": p.id if p else None, "status": p.status.value if p else "open",
            "score": r.score if r else None, "decision": r.decision.value if r else None, "hard_rules_fired": r.hard_rules_fired if r else [],
        })
    paid_amounts = [i["amount_usd"] for i in rows if i["status"] == "paid" and i["amount_usd"]]
    return {
        "vendor": {"id": vendor.id, "name": vendor.name, "trade": vendor.trade, "email_domain": vendor.email_domain, "website_url": vendor.website_url, "status": vendor.status.value, "created_at": vendor.created_at},
        "identity": ident,
        "summary": {"invoices": len(rows), "paid": len(paid_amounts), "average_paid_usd": round(sum(paid_amounts) / len(paid_amounts), 2) if paid_amounts else None,
                    "max_paid_usd": max(paid_amounts) if paid_amounts else None},
        "invoices": rows,
        "bank_accounts": [bank_view(a, call_by_id, trusted.id if trusted else None, requested_ids) for a in accounts],
        "contacts": [{"id": c.id, "source": c.source.value, "source_url": c.source_url, "phone": mask_phone(c.phone), "first_seen": c.first_seen,
                      "last_verified": c.last_verified} for c in contacts],
        "calls": [call_view(c, by_contact.get(c.contact_id) if c.contact_id else None) for c in calls],
    }
