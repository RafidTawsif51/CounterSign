# Owner: Teammate B
# Prize track: Capital One (Best Use of Nessie)
# Contract: async send_transfer(payment: Payment) -> str   (the nessie_transfer_id)
#   Also: setup_sandbox, create_transfer, pay_payment (money-layer backstop, see below).
#   Moves sandbox money for one payment. Refuses (TransferRefused) unless the payment is pending and
#   has a destination account. It does not change the payment row; the caller stores the returned id
#   and sets status to paid. Idempotent: a payment that already has an id returns it without a new
#   transfer. This module has no function that edits bank accounts or contacts.
# Flag: MOCK_NESSIE. All money is sandbox money.
# Transfer honesty: every transfer id carries how it was made (transfer_mode):
#   "nessie"         a real transfer in the Nessie sandbox
#   "mock_fallback"  Nessie failed after its retry; the id is a mock_tr_ id so the demo goes on. The payment is still paid, but
#                    the failure is audited (payment "nessie_failed", integration "transfer_failed") and remembered for
#                    nessie_health(), which /api/system/status can show as degraded
#   "mock"           MOCK_NESSIE is on; nothing was sent anywhere

import asyncio
import logging
import time
from typing import Literal, Optional, Protocol

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


TransferMode = Literal["nessie", "mock_fallback", "mock"]
DEGRADED_FOR_SECONDS = 15 * 60  # Nessie shows as degraded this long after its last failure, unless a transfer succeeded since


class TransferId(str):
    """A transfer id (it IS the string) that also says how the transfer was made and why it fell back, if it did."""

    mode: TransferMode
    error: Optional[str]

    def __new__(cls, value: str, mode: TransferMode, error: Optional[str] = None) -> "TransferId":
        obj = super().__new__(cls, value)
        obj.mode, obj.error = mode, error
        return obj


def transfer_mode_of(transfer_id: str) -> TransferMode:
    """The mode of any transfer id, including plain strings from the mock sender or a test double."""
    mode = getattr(transfer_id, "mode", None)
    if mode:
        return mode
    return "mock" if str(transfer_id).startswith(("nes_mock", "mock_tr", "nes_seed")) else "nessie"


# What this process has seen of Nessie. Failures are also written to the audit log (entity "integration"), which survives a restart.
_health: dict = {"last_failure": None, "last_failure_at": None, "last_success_at": None, "failures": 0}


def _redact(text: str) -> str:
    key = get_settings().nessie_api_key
    text = text.replace(key, "***") if key else text
    return text[:300]


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


async def create_transfer(destination_account_id: str, amount_usd: float, description: str) -> TransferId:
    """Move sandbox money and return the transfer id (a TransferId: a string that knows its mode and error).
    Falls back to mock_tr_<id> if MOCK_NESSIE is on or Nessie fails after the retry, so the demo never breaks. A fallback is
    never silent: the id says mode "mock_fallback" with the reason, and the caller audits it."""
    if not get_settings().mock_nessie:
        try:
            real = await asyncio.to_thread(_real_transfer, destination_account_id, amount_usd, description)
            _health["last_success_at"] = time.time()
            return TransferId(real, "nessie")
        except Exception as exc:  # noqa: BLE001
            log.warning("Nessie transfer failed (%s); using a mock transfer id", type(exc).__name__)
            reason = _redact(f"{type(exc).__name__}: {exc}")
            _health.update(last_failure=reason, last_failure_at=time.time(), failures=_health["failures"] + 1)
            return TransferId(new_id("mock_tr"), "mock_fallback", reason)
    return TransferId(new_id("mock_tr"), "mock")


def record_transfer_mode(session: Session, payment: Payment, transfer_id: str) -> TransferMode:
    """Store the mode on the payment, and when Nessie failed write the two audit rows. The caller commits."""
    mode = transfer_mode_of(transfer_id)
    payment.transfer_mode = mode
    if mode == "mock_fallback":
        reason = getattr(transfer_id, "error", None) or "Nessie failed"
        detail = {"error": reason, "transfer_id": str(transfer_id), "fallback": "mock_tr id; the payment is paid but no Nessie transfer exists"}
        write_audit("payment", payment.id, "agent", "nessie_failed", detail, session=session)
        write_audit("integration", "nessie", "system", "transfer_failed", {**detail, "payment_id": payment.id}, session=session)
    return mode


def nessie_health(session: Optional[Session] = None) -> dict:
    """Nessie's state for the status panel: mock | ok | degraded | unknown. Degraded = a transfer fell back to a mock id within the
    last 15 minutes and no transfer has succeeded since. With a session the last failure is also read from the audit log,
    so a restart does not forget it."""
    from app.models import AuditLog

    if get_settings().mock_nessie:
        return {"state": "mock", "last_failure": None, "failures_seen": 0}
    failure, failed_at = _health["last_failure"], _health["last_failure_at"]
    if session is not None:
        row = session.exec(select(AuditLog).where(AuditLog.entity == "integration", AuditLog.entity_id == "nessie", AuditLog.action == "transfer_failed")
                           .order_by(AuditLog.at.desc())).first()
        if row is not None and (failed_at is None or row.at.timestamp() > failed_at):
            failure, failed_at = (row.detail_json or {}).get("error"), row.at.timestamp()
    succeeded_at = _health["last_success_at"]
    recent = failed_at is not None and time.time() - failed_at < DEGRADED_FOR_SECONDS
    degraded = recent and (succeeded_at is None or succeeded_at < failed_at)
    state = "degraded" if degraded else "ok" if succeeded_at else "unknown"
    return {"state": state, "last_failure": failure, "last_failure_at": failed_at, "last_success_at": succeeded_at, "failures_seen": _health["failures"]}


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
    payment.status, payment.nessie_transfer_id = PaymentStatus.paid, str(transfer_id)
    mode = record_transfer_mode(session, payment, transfer_id)
    session.add(payment)
    write_audit("payment", payment.id, "agent", "paid", {"transfer_id": str(transfer_id), "to_last_verified_account": True, "transfer_mode": mode}, session=session)
    session.commit()
    await ev.emit(ev.PaymentPaid(run_id=payment.run_id, payment_id=payment.id, nessie_transfer_id=str(transfer_id), transfer_mode=mode))
    return str(transfer_id)


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
