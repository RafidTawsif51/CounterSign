# Owner: Teammate B
# Prize track: Cartesia (voice of the call; Twilio carries it)
# Contract: async start_verification(payment_id: str, session: Optional[Session] = None) -> VerificationResult
#   Calls the vendor at an independently found number, records a verification_calls row, emits
#   call.started / call.transcript / call.outcome, and applies the outcome:
#     denied     -> payment blocked, request marked as fraud, attack scored as caught
#     confirmed  -> new bank account written with verified_by_call_id, payment released to pending
#     no_answer  -> hold stays; after 2 tries needs_controller is true
#     unclear    -> hold stays, goes to the controller with the transcript
#   THIS IS THE ONLY MODULE ALLOWED TO WRITE vendor_bank_accounts AND vendor_contacts. A test fails
#   if any other file under app/ constructs those rows.
#   Calls only go to numbers in ALLOWED_CALL_NUMBERS (assert_callable), in mock and real mode alike.
#   Call script rules for the real caller: say it is automated and recorded, read only the last 4
#   digits of an account, accept no new contact details, never confirm on the vendor's behalf, hang
#   up after CALL_TIMEOUT_SECONDS.
# Flags: MOCK_TWILIO and MOCK_CARTESIA. The mock caller is used if either is true.

import asyncio
import re
from datetime import datetime
from typing import Optional, Protocol

from pydantic import BaseModel
from sqlmodel import Session, select

from app import events as ev
from app.audit import write_audit
from app.config import get_settings
from app.db import engine
from app.models import (
    Attack,
    AttackResult,
    CallOutcome,
    ContactSource,
    Invoice,
    Message,
    Payment,
    PaymentStatus,
    Vendor,
    VendorBankAccount,
    VendorContact,
    VerificationCall,
    utcnow,
)
from app.services import contacts

CALL_TIMEOUT_SECONDS = 60
MAX_TRIES = 2
MOCK_NUMBER = "+14155550100"  # simulated, never dialed
MOCK_STEP_DELAY = 0.3  # seconds between transcript lines in mock mode


class CallNotAllowed(Exception):
    pass


class VerificationResult(BaseModel):
    payment_id: str
    call_id: str
    outcome: CallOutcome
    payment_status: PaymentStatus
    attempts: int
    needs_controller: bool
    contact_source: ContactSource
    number_flagged: bool  # on-file and independent numbers disagreed
    transcript: list[dict]


# ---------------------------------------------------------------- allow list


# 555-0100 to 555-0199 is the block reserved for fiction: these numbers cannot ring anyone.
_FICTION_RE = re.compile(r"^\+1\d{3}5550[1]\d{2}$")


def allowed_numbers() -> set[str]:
    s = get_settings()
    nums = set(s.allowed_call_numbers_list)
    if s.mock_twilio or s.mock_cartesia:
        nums.add(MOCK_NUMBER)  # simulated calls only
    return nums


def assert_callable(phone: str) -> None:
    """Calls go only to ALLOWED_CALL_NUMBERS. In mock mode (nothing is dialed) the fictional 555-01xx block is accepted too."""
    s = get_settings()
    if phone in s.allowed_call_numbers_list:
        return
    if (s.mock_twilio or s.mock_cartesia) and (phone == MOCK_NUMBER or _FICTION_RE.match(phone)):
        return
    raise CallNotAllowed("number is not in ALLOWED_CALL_NUMBERS")


# ---------------------------------------------------------------- number selection


def _digits(p: str) -> str:
    return "".join(c for c in p if c.isdigit())


def _when(dt: Optional[datetime], fallback: datetime) -> datetime:
    return dt or fallback


def select_number(
    on_file: list[VendorContact], independent: Optional[contacts.IndependentContact]
) -> tuple[str, ContactSource, bool, Optional[VendorContact]]:
    """Returns (phone, source, flagged, existing_contact_row_or_None).

    Take the most recently verified on-file contact, cross-check it with the independent lookup. If
    they disagree, prefer the one verified longest ago and flag it. Numbers from the request are
    never an input here.
    """
    best = max(on_file, key=lambda c: _when(c.last_verified, c.first_seen), default=None)
    if best is None and independent is None:
        raise ValueError("no independent phone number available")
    if best is None:
        return independent.phone, ContactSource(independent.source), False, None  # type: ignore[union-attr]
    if independent is None or _digits(best.phone) == _digits(independent.phone):
        return best.phone, ContactSource.on_file, False, best
    # Disagreement: the older verification wins. A just-found independent number is newer by definition.
    if _when(best.last_verified, best.first_seen) <= independent.found_at:
        return best.phone, ContactSource.on_file, True, best
    return independent.phone, ContactSource(independent.source), True, None


# ---------------------------------------------------------------- callers


class Caller(Protocol):
    async def call(self, phone: str, question_last4: str, vendor_name: str, is_attack: bool, payment_id: str) -> tuple[CallOutcome, list[dict]]: ...


# Demo and test hook: force an outcome for a payment id.
MOCK_OUTCOMES: dict[str, CallOutcome] = {}

# Scripted outcomes for the SEEDED planted attacks only, matched by their fixed payment ids. This makes the
# seeded demo run end 37 paid, 1 held, 2 blocked: the CEO-pressure vendor cannot be reached clearly. A judge's
# attack gets a new payment id, so it is never matched here and still gets a denied call.
SEEDED_OUTCOMES: dict[str, CallOutcome] = {"pay_atk_ceo_pressure": CallOutcome.unclear}


class MockCaller:
    """Simulated call. By default a vendor denies a request that came from an attack message and
    confirms one that did not, so legitimate bank changes pass."""

    async def call(self, phone, question_last4, vendor_name, is_attack, payment_id):
        outcome = MOCK_OUTCOMES.get(payment_id) or SEEDED_OUTCOMES.get(payment_id) or (CallOutcome.denied if is_attack else CallOutcome.confirmed)
        agent_q = (
            f"Hello, this is an automated assistant calling for Ridgeline Builders accounts payable. "
            f"This call is recorded. We received a request to change where we send {vendor_name}'s payments, "
            f"to an account ending {question_last4}. Did your company make this change?"
        )
        script = {
            CallOutcome.confirmed: [("vendor", "Yes, that change is correct."), ("agent", "Thank you. I will note that you confirmed it. Goodbye.")],
            CallOutcome.denied: [("vendor", "No. We never changed banks."), ("agent", "Thank you. I will not process that change and I am alerting the controller. Goodbye.")],
            CallOutcome.unclear: [("vendor", "Sorry, who is this? I am not sure what you are asking."), ("agent", "Thank you. I will pass this to a person. Goodbye.")],
            CallOutcome.no_answer: [],
        }[outcome]
        transcript = [{"speaker": "agent", "text": agent_q}] if outcome != CallOutcome.no_answer else []
        transcript += [{"speaker": s, "text": t} for s, t in script]
        return outcome, transcript


class RealCaller:
    """Twilio outbound call + media stream + Cartesia speech + STT classification. Teammate B builds this."""

    async def call(self, phone, question_last4, vendor_name, is_attack, payment_id):
        raise NotImplementedError("Real verification call is not built yet; set MOCK_TWILIO=true or MOCK_CARTESIA=true")


def get_caller() -> Caller:
    s = get_settings()
    return MockCaller() if (s.mock_twilio or s.mock_cartesia) else RealCaller()


# ---------------------------------------------------------------- the only writers of bank/contact rows


def _write_verified_account(session: Session, vendor_id: str, rem: dict, call_id: str) -> VendorBankAccount:
    now = utcnow()
    for old in session.exec(
        select(VendorBankAccount).where(VendorBankAccount.vendor_id == vendor_id, VendorBankAccount.valid_to.is_(None))
    ):
        old.valid_to = now
        session.add(old)
    acct = VendorBankAccount(
        vendor_id=vendor_id,
        routing_hash=rem["routing_hash"],
        account_last4=rem["account_last4"],
        bank_name=rem["bank_name"],
        valid_from=now,
        verified_by_call_id=call_id,
    )
    session.add(acct)
    return acct


def _store_contact(session: Session, vendor_id: str, c: contacts.IndependentContact) -> VendorContact:
    row = VendorContact(
        vendor_id=vendor_id,
        phone=c.phone,
        source=ContactSource(c.source),
        source_url=c.source_url,
        first_seen=c.found_at,
    )
    session.add(row)
    return row


# ---------------------------------------------------------------- orchestration


async def start_verification(payment_id: str, session: Optional[Session] = None) -> VerificationResult:
    if session is None:
        with Session(engine) as own:
            return await start_verification(payment_id, own)

    payment = session.get(Payment, payment_id)
    if payment is None:
        raise ValueError("payment not found")
    invoice = session.get(Invoice, payment.invoice_id)
    vendor = session.get(Vendor, invoice.vendor_id) if invoice and invoice.vendor_id else None
    if invoice is None or vendor is None:
        raise ValueError("payment has no invoice or vendor")
    rem = invoice.remittance_json
    if not rem:
        raise ValueError("invoice has no remittance details to verify")
    message = session.get(Message, invoice.message_id) if invoice.message_id else None

    # 1. Pick the number. Never from the request.
    on_file = list(session.exec(select(VendorContact).where(VendorContact.vendor_id == vendor.id, VendorContact.source == ContactSource.on_file)))
    independent = await contacts.lookup_phone(vendor)
    phone, source, flagged, existing = select_number(on_file, independent)
    assert_callable(phone)  # raises before anything is stored or dialed
    if existing is None:
        existing = _store_contact(session, vendor.id, independent)  # type: ignore[arg-type]

    prior_no_answers = len(
        session.exec(select(VerificationCall).where(VerificationCall.payment_id == payment.id, VerificationCall.outcome == CallOutcome.no_answer)).all()
    )
    call = VerificationCall(payment_id=payment.id, contact_id=existing.id)
    session.add(call)
    session.commit()

    run_id = payment.run_id
    await ev.emit(ev.CallStarted(run_id=run_id, payment_id=payment.id, contact_source=source))

    # 2. Place the call (simulated in mock mode).
    outcome, transcript = await get_caller().call(
        phone, rem["account_last4"], vendor.name, bool(message and message.is_attack), payment.id
    )
    for line in transcript:
        await ev.emit(ev.CallTranscript(run_id=run_id, payment_id=payment.id, speaker=line["speaker"], text=line["text"]))
        if get_settings().mock_twilio or get_settings().mock_cartesia:
            await asyncio.sleep(MOCK_STEP_DELAY)
    call.outcome, call.transcript = outcome, transcript
    session.add(call)
    await ev.emit(ev.CallOutcomeEvent(run_id=run_id, payment_id=payment.id, outcome=outcome))

    # 3. Act on the outcome.
    attempts = prior_no_answers + 1
    needs_controller = outcome == CallOutcome.unclear or (outcome == CallOutcome.no_answer and attempts >= MAX_TRIES)
    if outcome == CallOutcome.denied:
        payment.status = PaymentStatus.blocked
        if message:
            message.is_attack = True
            session.add(message)
            for atk in session.exec(select(Attack).where(Attack.payload_ref == message.id)):
                atk.result = AttackResult.caught
                snap = dict(atk.detail_json or {})
                snap["outcome"] = "blocked"
                snap["reasons"] = ["The vendor denied the bank change on the verification call"] + [r for r in snap.get("reasons", [])][:2]
                atk.detail_json = snap
                session.add(atk)
        write_audit("payment", payment.id, "agent", "blocked_by_verification", {"call_id": call.id, "outcome": "denied"}, session=session)
    elif outcome == CallOutcome.confirmed:
        acct = _write_verified_account(session, vendor.id, rem, call.id)
        payment.destination_account_id = acct.id
        payment.status = PaymentStatus.pending  # released; the run pays it
        write_audit("vendor", vendor.id, "agent", "bank_account_verified", {"call_id": call.id, "account_last4": acct.account_last4}, session=session)
    else:
        write_audit("payment", payment.id, "agent", f"verification_{outcome.value}", {"call_id": call.id, "attempts": attempts}, session=session)
    session.add(payment)
    write_audit("payment", payment.id, "agent", "verification_call", {"call_id": call.id, "outcome": outcome.value, "contact_source": source.value, "number_flagged": flagged}, session=session)
    session.commit()

    if outcome == CallOutcome.denied:
        await ev.emit(ev.PaymentBlocked(run_id=run_id, payment_id=payment.id, reason="Vendor denied the bank change on the verification call"))

    return VerificationResult(
        payment_id=payment.id,
        call_id=call.id,
        outcome=outcome,
        payment_status=payment.status,
        attempts=attempts,
        needs_controller=needs_controller,
        contact_source=source,
        number_flagged=flagged,
        transcript=transcript,
    )
