"""Hard-rule edge cases for tests and the red team. NOT part of this week's run.

    from seed import edge_cases
    cases = edge_cases.add_edge_cases(session)   # after seed_database(session)

`seed_database` never calls this, so the seeded run stays 37 paid, 1 held, 2 blocked. Each case is one
open invoice built to fire exactly one hard rule and nothing else:

| case                   | hard rule fired   | how |
|------------------------|-------------------|-----|
| new_vendor_first_payment | new_vendor      | vendor created 12 days ago, first payment |
| amount_over_max        | amount_over_max   | 1.6x the vendor's 12-month maximum |
| contacts_differ        | contacts_differ   | the email gives a phone number we do not hold |
| one_off_rental         | new_vendor        | an old vendor with exactly one invoice, never paid before |

Invoices for the two new vendors get PDFs (their bank numbers are generated here). The two cases on
existing vendors have no PDF: the seed does not keep full account numbers, only hashes and last 4.
Everything is fictional and deterministic.
"""

import random
import sys
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlmodel import Session, select  # noqa: E402

try:  # imported as part of the seed package (tests)
    from seed import seed as S
except ImportError:  # run next to seed.py
    import seed as S  # type: ignore[no-redef]

from app.models import (  # noqa: E402
    ContactSource,
    Invoice,
    Message,
    Payment,
    PaymentStatus,
    Vendor,
    VendorBankAccount,
    VendorContact,
)
from app.services.extract import hash_routing  # noqa: E402
from invoice_pdf import layout_for, render_invoice  # noqa: E402


@dataclass(frozen=True)
class EdgeCase:
    name: str
    rule: str  # the one hard rule this case must fire
    vendor_id: str
    invoice_id: str
    message_id: str
    note: str


EXPECTED_RULES = {
    "new_vendor_first_payment": "new_vendor",
    "amount_over_max": "amount_over_max",
    "contacts_differ": "contacts_differ",
    "one_off_rental": "new_vendor",
}


def _new_vendor(session: Session, rng: random.Random, vid: str, name: str, trade: str, domain: str, age_days: int, phone: str):
    created = S.ANCHOR - timedelta(days=age_days)
    session.add(Vendor(id=vid, name=name, trade=trade, email_domain=domain, created_at=created))
    routing = "99" + "".join(str(rng.randint(0, 9)) for _ in range(7))
    number = "".join(str(rng.randint(0, 9)) for _ in range(10))
    acct = VendorBankAccount(id=f"bac_{vid[4:]}_1", vendor_id=vid, routing_hash=hash_routing(routing), account_last4=number[-4:],
                             bank_name="Cascadia Savings", valid_from=created)
    session.add(acct)
    session.add(VendorContact(id=f"con_{vid[4:]}_1", vendor_id=vid, phone=phone, source=ContactSource.on_file, first_seen=created, last_verified=created))
    session.add(VendorContact(id=f"con_{vid[4:]}_2", vendor_id=vid, phone=phone, source=ContactSource.website, source_url=f"https://www.{domain}/contact",
                              first_seen=created, last_verified=created))
    return acct, routing, number


def add_edge_cases(session: Session, *, write_pdfs: bool = True) -> dict[str, EdgeCase]:
    rng = random.Random(S.SEED + 21)
    cases: dict[str, EdgeCase] = {}
    due = (S.ANCHOR + timedelta(days=15)).date()
    sent = (S.ANCHOR - timedelta(days=1)).replace(hour=16, minute=30)

    def remit(a: VendorBankAccount) -> dict:
        return {"bank_name": a.bank_name, "routing_hash": a.routing_hash, "account_last4": a.account_last4}

    def pdf(inv_id, vname, trade, key, number, amount, a_routing, a_number, terms):
        if not write_pdfs:
            return None
        S.PDF_DIR.mkdir(parents=True, exist_ok=True)
        items = [("Site services, week 41", round(amount * 0.7, 2)), ("Materials", round(amount - round(amount * 0.7, 2), 2))]
        data = render_invoice(layout_for(key, trade), vendor=vname, number=number, inv_date=sent.date(), due=sent.date() + timedelta(days=terms),
                              items=items, total=amount, bank="Cascadia Savings", routing=a_routing, account=a_number)
        (S.PDF_DIR / f"{inv_id}.pdf").write_bytes(data)
        return f"{S.PDF_REL}/{inv_id}.pdf"

    # 1. a vendor created 12 days ago, paid for the first time
    acct, routing, number = _new_vendor(session, rng, "ven_edge_newleaf", "Newleaf Site Services", "site services", "newleafsite.com", 12, "+14155550190")
    session.add(Message(id="msg_edge_newleaf", thread_id="thr_edge_newleaf", vendor_id="ven_edge_newleaf", from_addr="ar@newleafsite.com",
                        subject="Invoice NEW-1001", body="Hi Maria,\n\nFirst invoice NEW-1001 for $4,250.00 attached. Welcome aboard.\n\nThanks,\nNewleaf Site Services",
                        received_at=sent))
    path = pdf("inv_edge_newleaf", "Newleaf Site Services", "site services", "newleaf", "NEW-1001", 4250.00, routing, number, 15)
    session.add(Invoice(id="inv_edge_newleaf", vendor_id="ven_edge_newleaf", message_id="msg_edge_newleaf", number="NEW-1001", amount_usd=4250.00,
                        due_date=due, remittance_json=remit(acct), pdf_path=path))
    cases["new_vendor_first_payment"] = EdgeCase("new_vendor_first_payment", "new_vendor", "ven_edge_newleaf", "inv_edge_newleaf", "msg_edge_newleaf",
                                                 "Vendor created 12 days ago; no earlier payment.")

    # 2. a normal vendor, an invoice 1.6x its 12-month maximum
    vid = f"ven_{S.BY_KEY['alder'].key}"
    past = session.exec(select(Invoice.amount_usd).join(Payment, Payment.invoice_id == Invoice.id).where(Invoice.vendor_id == vid, Payment.status == PaymentStatus.paid)).all()
    cur = session.exec(select(VendorBankAccount).where(VendorBankAccount.vendor_id == vid, VendorBankAccount.valid_to.is_(None))).one()
    last = session.exec(select(Message).join(Invoice, Invoice.message_id == Message.id).where(Invoice.vendor_id == vid).order_by(Message.received_at.desc())).first()
    big = round(max(past) * 1.6, 2)
    session.add(Message(id="msg_edge_overmax", thread_id="thr_edge_overmax", vendor_id=vid, from_addr=last.from_addr, subject="Invoice ALD-8001",
                        body=f"Hi Maria,\n\nAttached is invoice ALD-8001 for ${big:,.2f}, including the extra delivery.\n\nThanks,\nAlder Lumber Co",
                        received_at=sent.replace(hour=last.received_at.hour, minute=15)))
    session.add(Invoice(id="inv_edge_overmax", vendor_id=vid, message_id="msg_edge_overmax", number="ALD-8001", amount_usd=big, due_date=due, remittance_json=remit(cur)))
    cases["amount_over_max"] = EdgeCase("amount_over_max", "amount_over_max", vid, "inv_edge_overmax", "msg_edge_overmax",
                                        f"${big:,.2f} is 1.6x the vendor's maximum of ${max(past):,.2f}.")

    # 3. a normal vendor, an email with a phone number we do not hold
    vid = f"ven_{S.BY_KEY['cascade'].key}"
    cur = session.exec(select(VendorBankAccount).where(VendorBankAccount.vendor_id == vid, VendorBankAccount.valid_to.is_(None))).one()
    last = session.exec(select(Message).join(Invoice, Invoice.message_id == Message.id).where(Invoice.vendor_id == vid).order_by(Message.received_at.desc())).first()
    typical = round(sum(session.exec(select(Invoice.amount_usd).where(Invoice.vendor_id == vid, Invoice.id.in_(select(Payment.invoice_id)))).all()) /
                    len(session.exec(select(Invoice.amount_usd).where(Invoice.vendor_id == vid, Invoice.id.in_(select(Payment.invoice_id)))).all()), 2)
    session.add(Message(id="msg_edge_contacts", thread_id="thr_edge_contacts", vendor_id=vid, from_addr=last.from_addr, subject="Invoice CAS-8001",
                        body=(f"Hi Maria,\n\nInvoice CAS-8001 for ${typical:,.2f} is attached. Our accounting line has changed, please call +1 415 555 0177 "
                              "if you have any questions.\n\nThanks,\nCascade Fasteners and Hardware"),
                        received_at=sent.replace(hour=last.received_at.hour, minute=20)))
    session.add(Invoice(id="inv_edge_contacts", vendor_id=vid, message_id="msg_edge_contacts", number="CAS-8001", amount_usd=typical, due_date=due, remittance_json=remit(cur)))
    cases["contacts_differ"] = EdgeCase("contacts_differ", "contacts_differ", vid, "inv_edge_contacts", "msg_edge_contacts",
                                        "The email carries +1 415 555 0177, which is not on file for this vendor.")

    # 4. a true one-off rental vendor: onboarded long ago, exactly one invoice, never paid
    acct, routing, number = _new_vendor(session, rng, "ven_edge_quickhaul", "Quickhaul One-Day Crane Hire", "crane rental", "quickhaulcrane.com", 300, "+14155550191")
    session.add(Message(id="msg_edge_oneoff", thread_id="thr_edge_oneoff", vendor_id="ven_edge_quickhaul", from_addr="billing@quickhaulcrane.com",
                        subject="Invoice QH-0001", body="Hi Maria,\n\nInvoice QH-0001 for the one-day crane hire on Oct 19 is attached: $3,900.00.\n\nThanks,\nQuickhaul",
                        received_at=sent))
    path = pdf("inv_edge_oneoff", "Quickhaul One-Day Crane Hire", "crane rental", "quickhaul", "QH-0001", 3900.00, routing, number, 7)
    session.add(Invoice(id="inv_edge_oneoff", vendor_id="ven_edge_quickhaul", message_id="msg_edge_oneoff", number="QH-0001", amount_usd=3900.00,
                        due_date=(S.ANCHOR + timedelta(days=7)).date(), remittance_json=remit(acct), pdf_path=path))
    cases["one_off_rental"] = EdgeCase("one_off_rental", "new_vendor", "ven_edge_quickhaul", "inv_edge_oneoff", "msg_edge_oneoff",
                                       "Vendor created 300 days ago; this is its only invoice and the first payment.")

    session.commit()
    return cases
