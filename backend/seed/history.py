"""Seed history extras: real email threads and past decisions.

Both use their own random generators (seed + 11, seed + 13) and never touch the main stream, so this
week's 40 open invoices are identical with or without this module.

* Threads: every historical invoice email gets replies from Maria (AP) and sometimes the vendor:
  paid confirmations, acknowledgements, late-payment questions, corrected invoices, and the phone
  confirmation of the four legitimate bank changes. Threads have 2 to 4 messages.
* Past decisions: every historical payment has a risk assessment and audit rows. Five vendors were
  onboarded inside the window, so their first payment was held for the controller (hard rule: first
  payment) and approved. The four bank changes show hold, call, confirmation and payment.
"""

import random
import statistics
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

from app.models import AuditActor, AuditLog, Decision, Message, RiskAssessment, Signal

UTC = timezone.utc
MARIA = "maria@ridgelinebuilders.com"
SIGNATURE = "Maria\nAccounts Payable, Ridgeline Builders"
# Vendors onboarded inside the 12-month window: their first payment is a controller hold.
HOLD_VENDORS = ("greenfield", "clearline", "brightcoat", "evergreen", "ironwood")
PRE_WINDOW_NOTE = "Vendors onboarded before the window have earlier payments that are not part of the seed."


@dataclass
class H:
    """One historical invoice with everything tied to it."""

    n: int
    key: str
    vendor: str
    d: Any  # Draft
    inv: Any
    pay: Any
    msg: Message
    due: date
    run_date: date
    acct: Any  # Acct paid


def _at(d: date, hour: int, minute: int = 0, second: int = 0) -> datetime:
    return datetime(d.year, d.month, d.day, tzinfo=UTC) + timedelta(hours=hour, minutes=minute, seconds=second)


def onboard_late_vendors(first_day: dict, vrow: dict, contact1: dict, accts: dict) -> None:
    """Move the creation date of the hold vendors to just before their first invoice."""
    for key in HOLD_VENDORS:
        created = _at(first_day[key] - timedelta(days=9), 15)
        vrow[key].created_at = created
        contact1[key].first_seen = created
        accts[key][0].row.valid_from = created


def add_history_extras(rows: list, hist: list[H], *, seed: int, windows: dict, accts: dict) -> dict:
    tr = random.Random(seed + 11)
    counter = {"msg": 0, "aud": 0}

    def reply(base: Message, frm: str, subject: str, body: str, when: datetime) -> Message:
        counter["msg"] += 1
        return Message(id=f"msg_r{counter['msg']:05d}", thread_id=base.thread_id, vendor_id=base.vendor_id, from_addr=frm,
                       subject=subject, body=body, received_at=when)

    def audit(entity: str, entity_id: str, actor: AuditActor, action: str, when: datetime, detail: dict) -> None:
        counter["aud"] += 1
        rows.append(AuditLog(id=f"aud_h{counter['aud']:06d}", at=when, entity=entity, entity_id=entity_id, actor=actor, action=action, detail_json=detail))

    stats = {"threads": {2: 0, 3: 0, 4: 0}, "late": 0, "corrected": 0, "holds_cleared": 0, "bank_changes": 0, "assessments": 0}

    # ---------------------------------------------------------------- threads
    for h in hist:
        num, amt, due = h.d.number, h.d.amount, h.due
        subject = "Re: " + h.msg.subject
        run_dt = _at(h.run_date, 17)
        paid_at = run_dt + timedelta(minutes=tr.randint(25, 170))
        w0, w1 = windows[h.key]
        paid_body = (f"Hi,\n\nInvoice {num} for ${amt:,.2f} went out in Thursday's payment run ({h.pay.nessie_transfer_id}). "
                     f"You should see it in a day or two.\n\nThanks,\n{SIGNATURE}")
        out: list[Message] = []
        if h.d.trigger:
            new = accts[h.key][1].row
            call_at = new.valid_from
            out.append(reply(h.msg, MARIA, subject, "Thanks for letting us know. Before we pay a new account we confirm it by phone, on the number we already "
                             f"have on file. I will call you before Thursday's run.\n\n{SIGNATURE}", h.msg.received_at + timedelta(hours=tr.randint(3, 20))))
            out.append(reply(h.msg, MARIA, subject, f"Confirmed by phone. The account ending {new.account_last4} is now on file and invoice {num} is in Thursday's run.\n\n{SIGNATURE}",
                             call_at + timedelta(minutes=12)))
            out.append(reply(h.msg, MARIA, subject, paid_body, paid_at))
        elif (h.run_date - due).days >= 2 and tr.random() < 0.4:
            asked = _at(due + timedelta(days=1), tr.randint(w0, w1 - 1), tr.randint(0, 59))
            out.append(reply(h.msg, h.msg.from_addr, f"Invoice {num} past due?",
                             f"Hi Maria,\n\nOur records show invoice {num} (${amt:,.2f}, due {due:%b %d}) is still unpaid. Could you confirm when we can expect payment?\n\n"
                             f"Thanks,\n{h.vendor}", asked))
            out.append(reply(h.msg, MARIA, f"Re: Invoice {num} past due?",
                             f"Sorry for the delay. Invoice {num} is queued for this Thursday's run and you will get a confirmation when it is paid.\n\n{SIGNATURE}",
                             asked + timedelta(hours=tr.randint(2, 5))))
            out.append(reply(h.msg, MARIA, subject, paid_body, paid_at))
            stats["late"] += 1
        else:
            r = tr.random()
            if r < 0.07:  # the vendor sent a wrong total, then a corrected invoice
                wrong = round(amt + tr.choice([-1, 1]) * tr.randint(50, 900), 2)
                h.msg.body = f"Hi Maria,\n\nAttached is invoice {num} for ${wrong:,.2f}, due {due:%b %d}.\n\nThanks,\n{h.vendor}"
                fixed = _at(h.msg.received_at.date() + timedelta(days=1), tr.randint(w0, w1 - 1), tr.randint(0, 59))
                out.append(reply(h.msg, h.msg.from_addr, f"Corrected invoice {num}",
                                 f"Hi Maria,\n\nSorry, invoice {num} listed ${wrong:,.2f} by mistake. The correct total is ${amt:,.2f}. Corrected copy attached, "
                                 f"please disregard the earlier one.\n\nThanks,\n{h.vendor}", fixed))
                out.append(reply(h.msg, MARIA, f"Re: Corrected invoice {num}", f"No problem, I have updated it to ${amt:,.2f}.\n\n{SIGNATURE}",
                                 fixed + timedelta(hours=tr.randint(2, 4))))
                out.append(reply(h.msg, MARIA, subject, paid_body, paid_at))
                stats["corrected"] += 1
            elif r < 0.27:  # acknowledgement, then the paid confirmation
                out.append(reply(h.msg, MARIA, subject, f"Got invoice {num}, thank you. It will go out in the next Thursday run.\n\n{SIGNATURE}",
                                 h.msg.received_at + timedelta(hours=tr.randint(3, 20))))
                out.append(reply(h.msg, MARIA, subject, paid_body, paid_at))
            else:
                out.append(reply(h.msg, MARIA, subject, paid_body, paid_at))
        stats["threads"][1 + len(out)] += 1
        rows.extend(out)

    # ---------------------------------------------------------------- past decisions
    seen: dict[str, int] = {}
    amounts: dict[str, list[float]] = {}
    for h in hist:
        key, n, amt = h.key, h.n, h.d.amount
        prior, earlier = seen.get(key, 0), amounts.get(key, [])
        run_dt = _at(h.run_date, 17)
        t0 = run_dt + timedelta(seconds=n % 50 + 1)
        if h.d.trigger:  # the bank change was assessed and held before the call that ran ahead of the payment
            t0 = accts[key][1].row.valid_from - timedelta(minutes=10)
        signals: list[Signal] = []
        rules: list[str] = []
        decision = Decision.auto_pay

        def sig(name: str, weight: int, detail: str) -> None:
            signals.append(Signal(name=name, weight=weight, detail=detail, evidence_id=f"evd_h{n:04d}{len(signals)}"))

        if h.d.trigger:
            old, new = accts[key][0].row, accts[key][1].row
            sig("bank_details_changed", 30, f"New account ending {new.account_last4}; last verified ending {old.account_last4}")
            rules.append("destination_changed")
            decision = Decision.hold_and_verify
        first_hold = key in HOLD_VENDORS and prior == 0
        if first_hold:
            rules.append("new_vendor")
            decision = Decision.controller_review
        if len(earlier) >= 3:
            mean = statistics.fmean(earlier)
            z = (amt - mean) / max(statistics.pstdev(earlier), 0.05 * mean)
            if z > 2:
                sig("amount_outlier", 15, f"${amt:,.2f} is {z:.1f} standard deviations above the ${mean:,.2f} average")
        score = min(100, sum(s.weight for s in signals))
        rows.append(RiskAssessment(
            id=f"ras_{n:04d}", payment_id=h.pay.id, score=score, decision=decision, hard_rules_fired=rules,
            signals_json=[s.model_dump() for s in signals], model_version="seed-history-1"))
        stats["assessments"] += 1
        audit("payment", h.pay.id, AuditActor.agent, "risk_assessed", t0,
              {"assessment_id": f"ras_{n:04d}", "score": score, "decision": decision.value, "hard_rules_fired": rules})

        if h.d.trigger:
            call = accts[key][1].row
            audit("payment", h.pay.id, AuditActor.agent, "held", call.valid_from - timedelta(minutes=9), {"reason": "destination_changed: verification call required"})
            audit("vendor", f"ven_{key}", AuditActor.agent, "identity_check", call.valid_from - timedelta(minutes=8),
                  {"status": "verified", "summary": "CRS identity check: verified", "source": "crs-sandbox-mock"})
            audit("payment", h.pay.id, AuditActor.agent, "verification_call", call.valid_from + timedelta(minutes=2),
                  {"call_id": call.verified_by_call_id, "outcome": "confirmed", "contact_source": "on_file"})
            audit("vendor", f"ven_{key}", AuditActor.agent, "bank_account_verified", call.valid_from + timedelta(minutes=3),
                  {"call_id": call.verified_by_call_id, "account_last4": call.account_last4})
            audit("payment", h.pay.id, AuditActor.agent, "paid", run_dt + timedelta(minutes=5 + n % 10), {"reason": "paid to the verified account", "transfer_id": h.pay.nessie_transfer_id})
            stats["bank_changes"] += 1
        elif first_hold:
            audit("payment", h.pay.id, AuditActor.agent, "held", t0 + timedelta(seconds=1), {"reason": "new_vendor: first payment to this vendor"})
            audit("vendor", f"ven_{key}", AuditActor.agent, "identity_check", t0 + timedelta(seconds=2),
                  {"status": "verified", "summary": "CRS identity check: verified", "source": "crs-sandbox-mock"})
            approved = run_dt + timedelta(minutes=12 + n % 7)
            audit("payment", h.pay.id, AuditActor.human, "approved", approved,
                  {"approver": "Dev (controller)", "reason": "Onboarding documents checked and W-9 on file. First payment approved."})
            audit("payment", h.pay.id, AuditActor.agent, "paid", approved + timedelta(minutes=1), {"reason": "approved by the controller", "transfer_id": h.pay.nessie_transfer_id})
            stats["holds_cleared"] += 1
        else:
            audit("payment", h.pay.id, AuditActor.agent, "paid", t0 + timedelta(seconds=2), {"reason": "paid to the last verified account", "transfer_id": h.pay.nessie_transfer_id})
        seen[key] = prior + 1
        amounts.setdefault(key, []).append(amt)
    return stats
