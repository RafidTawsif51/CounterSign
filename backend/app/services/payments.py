# Owner: Teammate B
# Prize track: Capital One (Best Use of Nessie)
# Contract: async send_transfer(payment: Payment) -> str   (the nessie_transfer_id)
#   Moves sandbox money for one payment. Refuses (TransferRefused) unless the payment is pending and
#   has a destination account. It does not change the payment row; the caller stores the returned id
#   and sets status to paid. Idempotent: a payment that already has an id returns it without a new
#   transfer. This module has no function that edits bank accounts or contacts.
# Flag: MOCK_NESSIE. All money is sandbox money.

from typing import Protocol

from app.config import get_settings
from app.models import Payment, PaymentStatus, new_id


class TransferRefused(Exception):
    pass


class TransferSender(Protocol):
    async def send_transfer(self, payment: Payment) -> str: ...


def _guard(payment: Payment) -> None:
    if payment.status != PaymentStatus.pending:
        raise TransferRefused(f"payment is {payment.status.value}, only pending payments can be sent")
    if not payment.destination_account_id:
        raise TransferRefused("payment has no destination account")
    if payment.amount_usd <= 0:
        raise TransferRefused("amount must be positive")


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
        raise NotImplementedError("Real Nessie transfer is not built yet; set MOCK_NESSIE=true")


def get_sender() -> TransferSender:
    return MockTransferSender() if get_settings().mock_nessie else RealTransferSender()


async def send_transfer(payment: Payment) -> str:
    return await get_sender().send_transfer(payment)
