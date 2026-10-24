"""Test helper: build a RiskContext for an invoice from database rows, the way the payment run will."""

from pathlib import Path

from sqlmodel import Session, select

from app.models import Invoice, Message, Payment, PaymentStatus, Vendor, VendorBankAccount
from app.services import injection
from app.services.injection import ScanItem
from app.services.risk import Destination, RiskContext

BACKEND = Path(__file__).resolve().parent.parent


def build_context(session: Session, invoice: Invoice) -> tuple[Payment, RiskContext]:
    vendor = session.get(Vendor, invoice.vendor_id)
    msg = session.get(Message, invoice.message_id) if invoice.message_id else None
    rem = invoice.remittance_json
    requested = Destination(rem["routing_hash"], rem["account_last4"]) if rem else None
    current = session.exec(
        select(VendorBankAccount).where(VendorBankAccount.vendor_id == vendor.id, VendorBankAccount.valid_to.is_(None))
    ).first()
    last = Destination(current.routing_hash, current.account_last4) if current else None

    paid = session.exec(
        select(Invoice.amount_usd, Message.from_addr, Message.received_at)
        .join(Payment, Payment.invoice_id == Invoice.id)
        .join(Message, Message.id == Invoice.message_id)
        .where(Invoice.vendor_id == vendor.id, Payment.status == PaymentStatus.paid)
    ).all()

    findings = []
    if invoice.pdf_path:
        findings += injection.scan(ScanItem(kind="pdf", pdf_bytes=(BACKEND / invoice.pdf_path).read_bytes(), invoice_id=invoice.id))
    if msg:
        findings += injection.scan(ScanItem(kind="email", text=msg.body, message_id=msg.id))

    ctx = RiskContext(
        vendor=vendor,
        requested_destination=requested,
        last_verified_destination=last,
        message=msg,
        history_amounts=[p[0] for p in paid],
        prior_payment_count=len(paid),
        known_sender_addresses={p[1] for p in paid},
        usual_send_hours={p[2].hour for p in paid},
        injection_findings=findings,
        now=msg.received_at if msg else None or vendor.created_at,
    )
    payment = Payment(run_id="run_test", invoice_id=invoice.id, amount_usd=invoice.amount_usd)
    return payment, ctx
