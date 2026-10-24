# Owner: Teammate B
# Prize track: Capital One (Best Use of Nessie)
# Contract: async send_transfer(payment: Payment) -> str   (the nessie_transfer_id)
#   Also: setup_sandbox, create_transfer, pay_payment (money-layer backstop, see below).
#   Moves sandbox money for one payment. Refuses (TransferRefused) unless the payment is pending and
#   has a destination account. It does not change the payment row; the caller stores the returned id
#   and sets status to paid. Idempotent: a payment that already has an id returns it without a new
#   transfer. This module has no function that edits bank accounts or contacts.
# Flag: MOCK_NESSIE. All money is sandbox money.

import asyncio
import logging
from typing import Optional, Protocol

import httpx
from sqlmodel import Session, select

from app.audit import write_audit
from app.config import get_settings
from app import db
from app.models import Invoice, Payment, PaymentStatus, Vendor, VendorBankAccount, new_id, utcnow

log = logging.getLogger("countersign.payments")

# Nessie sandbox. The key goes in the query string; it is never logged.
NESSIE_URL = "https://api.nessieisreal.com"  # plain http (port 80) is refused
OPERATING_NICKNAME = "ridgeline-operating"
OPERATING_BALANCE = 100_000_000
_account_cache: dict[str, str] = {}  # nickname -> Nessie account id


class TransferRefused(Exception):
    pass


class TransferSender(Protocol):
    async def send_transfer(self, payment: Payment) -> str: ...


def _guard(payment: Payment, session: Optional[Session] = None) -> None:
    """Money-layer backstop for every path that moves money (send_transfer and pay_payment)."""
    from app.services import verify  # local import: verify imports a lot of the app

    if payment.status != PaymentStatus.pending:
        raise TransferRefused(f"payment is {payment.status.value}, only pending payments can be sent")
    if not payment.destination_account_id:
        raise TransferRefused("payment has no destination account")
    if payment.amount_usd <= 0:
        raise TransferRefused("amount must be positive")

    def check(s: Session) -> None:
        invoice = s.get(Invoice, payment.invoice_id) if payment.invoice_id else None
        if invoice is None or not invoice.vendor_id:
            raise TransferRefused("payment has no invoice or vendor")
        verified = verify.current_verified_account(s, invoice.vendor_id)
        if verified is None:
            raise TransferRefused("vendor has no verified bank account")
        if payment.destination_account_id != verified.id:
            raise TransferRefused("destination is not the vendor's current verified account")

    session = session or Session.object_session(payment)  # engine is looked up at call time, never bound at import
    if session is not None:
        check(session)
    else:
        with Session(db.engine) as own:
            check(own)


# ---------------------------------------------------------------- Nessie REST


def _nessie(method: str, path: str, **kwargs) -> dict | list:
    """One Nessie call with a timeout and one retry."""
    key = get_settings().nessie_api_key
    last: Exception | None = None
    for _ in range(2):
        try:
            r = httpx.request(method, NESSIE_URL + path, params={"key": key}, timeout=10, **kwargs)
            r.raise_for_status()
            return r.json()
        except Exception as exc:  # noqa: BLE001
            last = exc
    detail = ""
    if isinstance(last, httpx.HTTPStatusError):  # status and body only; the URL carries the key
        detail = f" ({last.response.status_code}: {last.response.text[:200]})"
    raise RuntimeError(f"Nessie {method} {path} failed: {type(last).__name__}{detail}")


def _created(resp) -> dict:
    # POST responses look like {"code": 201, "message": "...", "objectCreated": {...}}
    return resp.get("objectCreated", resp) if isinstance(resp, dict) else {}


def _load_accounts() -> None:
    for acct in _nessie("GET", "/accounts"):
        if acct.get("nickname") and acct.get("_id"):
            _account_cache[acct["nickname"]] = acct["_id"]


def _ensure_account(nickname: str, owner_name: str, balance: int) -> bool:
    """Create a customer + checking account for this nickname unless one exists. True if created."""
    if nickname in _account_cache:
        return False
    first, _, last = owner_name.partition(" ")
    customer = _created(_nessie("POST", "/customers", json={
        "first_name": first or owner_name, "last_name": last or "Inc",
        "address": {"street_number": "1", "street_name": "Sandbox St", "city": "San Francisco", "state": "CA", "zip": "94123"},
    }))
    account = _created(_nessie("POST", f"/customers/{customer['_id']}/accounts", json={
        "type": "Checking", "nickname": nickname, "rewards": 0, "balance": balance,
    }))
    _account_cache[nickname] = account["_id"]
    return True


def _setup_sandbox_sync(rows: list[tuple[str, str]]) -> dict:
    _load_accounts()
    created = 0
    created += _ensure_account(OPERATING_NICKNAME, "Ridgeline Builders", OPERATING_BALANCE)
    for account_id, vendor_name in rows:
        created += _ensure_account(account_id, vendor_name, 0)
    return {"created": created, "known": len(_account_cache)}


def setup_sandbox(session: Session) -> dict:
    """Idempotently create the company account and one Nessie customer + account per
    vendor_bank_accounts row. Each Nessie account's nickname is the vendor_bank_accounts.id. Reads
    our database only. Needs MOCK_NESSIE=false and a key."""
    if get_settings().mock_nessie:
        return {"created": 0, "known": 0, "mock": True}
    rows = [
        (a.id, v.name)
        for a, v in session.exec(select(VendorBankAccount, Vendor).where(VendorBankAccount.vendor_id == Vendor.id))
    ]
    return _setup_sandbox_sync(rows)


def _real_transfer(destination_account_id: str, amount_usd: float, description: str) -> str:
    """Record a transfer in the Nessie sandbox and return its id.

    This Nessie version's TransferCreate takes only transaction_date, status, amount and
    description (medium, payee_id and any payer or payee field are rejected as extra), so a transfer
    cannot name a second account. We create it under the vendor's account, the payee, and name the
    paying account in the description.
    """
    if destination_account_id not in _account_cache:
        _load_accounts()
    payee = _account_cache.get(destination_account_id)
    if not payee:
        raise RuntimeError("Nessie account not set up; run setup-nessie")
    resp = _nessie("POST", f"/accounts/{payee}/transfers", json={
        "transaction_date": utcnow().date().isoformat(), "status": "pending", "amount": round(amount_usd, 2),
        "description": f"From {OPERATING_NICKNAME}: {description}"[:200],
    })
    return str(_created(resp)["_id"])


def fetch_transfer(destination_account_id: str, transfer_id: str) -> Optional[dict]:
    """Read a transfer back from the vendor's Nessie account (there is no get-by-id route)."""
    payee = _account_cache.get(destination_account_id)
    if not payee:
        return None
    rows = _nessie("GET", f"/accounts/{payee}/transfers")
    return next((r for r in rows if r.get("id") == transfer_id or r.get("_id") == transfer_id), None)


async def create_transfer(destination_account_id: str, amount_usd: float, description: str) -> str:
    """Move sandbox money and return the transfer id. Falls back to mock_tr_<id> if MOCK_NESSIE is
    on or Nessie fails after the retry, so the demo never breaks."""
    if not get_settings().mock_nessie:
        try:
            return await asyncio.to_thread(_real_transfer, destination_account_id, amount_usd, description)
        except Exception as exc:  # noqa: BLE001
            log.warning("Nessie transfer failed (%s); using a mock transfer id", type(exc).__name__)
    return new_id("mock_tr")


async def pay_payment(session: Session, payment_id: str) -> str:
    """Pay one pending payment to the vendor's current verified account. Raises TransferRefused otherwise."""
    from app import events as ev

    payment = session.get(Payment, payment_id)
    if payment is None:
        raise TransferRefused("payment not found")
    if payment.nessie_transfer_id and payment.status == PaymentStatus.paid:
        return payment.nessie_transfer_id
    _guard(payment, session)
    transfer_id = await create_transfer(payment.destination_account_id, payment.amount_usd, f"Countersign payment {payment.id}")
    payment.status, payment.nessie_transfer_id = PaymentStatus.paid, transfer_id
    session.add(payment)
    write_audit("payment", payment.id, "agent", "paid", {"transfer_id": transfer_id, "to_last_verified_account": True}, session=session)
    session.commit()
    await ev.emit(ev.PaymentPaid(run_id=payment.run_id, payment_id=payment.id, nessie_transfer_id=transfer_id))
    return transfer_id


class MockTransferSender:
    async def send_transfer(self, payment: Payment) -> str:
        if payment.nessie_transfer_id:
            return payment.nessie_transfer_id
        _guard(payment)
        return new_id("nes_mock")


class RealTransferSender:
    async def send_transfer(self, payment: Payment) -> str:
        if payment.nessie_transfer_id:
            return payment.nessie_transfer_id
        _guard(payment)
        return await create_transfer(payment.destination_account_id, payment.amount_usd, f"Countersign payment {payment.id}")  # type: ignore[arg-type]


def get_sender() -> TransferSender:
    return MockTransferSender() if get_settings().mock_nessie else RealTransferSender()


async def send_transfer(payment: Payment) -> str:
    return await get_sender().send_transfer(payment)
