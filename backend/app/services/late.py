# Owner: Backend lead
# Prize track: Hyphenate (the call is the moment), Microsoft (the record always matches reality)
# Contract: after_outcome(payment_id) runs after a verification call's final outcome has been applied outside a payment run (a
#   Twilio webhook in real mode, or a manual call). verify.handle_outcome has already updated the payment, written the audit rows
#   and emitted call.outcome plus payment.blocked / payment.paid. This module finishes the picture:
#     * the linked attack row (leaderboard) follows the payment: blocked or held is caught, paid is missed; attack.logged is re-sent;
#     * the cached /ask answers for the payment are dropped, and re-warmed for a seeded attack;
#     * if the payment belongs to a run that already finished, the run's saved totals are recomputed, an audit row is written and
#       run.updated carries the new totals (run channel and global channel).
#   It never moves money and never writes a bank account or a contact.

import asyncio
import logging

from sqlmodel import Session

from app import db, events as ev
from app.audit import write_audit
from app.models import Invoice, Message, Payment, PaymentRun, RunStatus
from app.services import ask, report, run

log = logging.getLogger("countersign.late")


async def after_outcome(payment_id: str) -> None:
    try:
        await _apply(payment_id)
    except Exception:  # noqa: BLE001  (the outcome is already saved; this is bookkeeping)
        log.exception("could not finish the late-outcome bookkeeping for %s", payment_id)


async def _apply(payment_id: str) -> None:
    atk = updated = None
    with Session(db.engine) as s:
        pay = s.get(Payment, payment_id)
        if pay is None:
            return
        run_id, status, amount = pay.run_id, pay.status, pay.amount_usd
        inv = s.get(Invoice, pay.invoice_id)
        msg = s.get(Message, inv.message_id) if inv and inv.message_id else None
        atk = run._attack_for(s, msg, False, None, status, amount) if (msg and msg.is_attack) else None  # keeps the existing reasons
        pr = s.get(PaymentRun, run_id)
        if pr is not None and pr.status != RunStatus.running and not run.is_active(run_id):  # the run is over: its totals move
            totals = run._totals(s, run_id)
            before = pr.totals_json or {}
            if any(before.get(k) != totals[k] for k in ("paid", "held", "blocked", "total_usd")):  # only when this outcome changed something
                pr.totals_json = {**before, **totals}
                s.add(pr)
                write_audit("run", run_id, "system", "totals_updated", {"payment_id": payment_id, "payment_status": status.value, **totals}, session=s)
                updated = (run_id, status.value, totals)
        s.commit()
        if atk is not None:
            s.refresh(atk)
            s.expunge(atk)
    if atk is not None:
        await run._emit_attack(run_id, atk)
    if updated:
        _, st, t = updated
        await ev.emit(ev.RunUpdated(run_id=run_id, payment_id=payment_id, status=st, paid=t["paid"], held=t["held"], blocked=t["blocked"],
                                    total_usd=t["total_usd"], blocked_usd=t["blocked_usd"]))
        # The run's report is out of date now. Rewrite it in the background so the webhook that brought the outcome is not kept waiting.
        rtask = asyncio.create_task(report.finish(run_id, late=True))
        run._tasks.add(rtask)
        rtask.add_done_callback(run._tasks.discard)
    ask.invalidate(payment_id)
    if payment_id in ask.SEEDED_PAYMENTS:
        task = asyncio.create_task(ask.warm((payment_id,)))
        run._tasks.add(task)
        task.add_done_callback(run._tasks.discard)
