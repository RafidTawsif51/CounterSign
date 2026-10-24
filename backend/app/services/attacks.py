# Owner: Backend lead
# Prize track: Hyphenate (the judge is the attacker), Armadin (the bounty), Atlassian
# Contract:
#   POST /api/attacks                    launch an attack card: {attacker_name, source, card, payload} -> 201 {attack_id, message_id, run_id, ...}
#                                        cards: classic_bank_change, poisoned_invoice, ceo_pressure, freestyle. A PDF (a seed file name or
#                                        pdf_base64) is accepted on poisoned_invoice and freestyle.
#   POST /api/bounty/inbound             inbound-email webhook for the Rob Countersign bounty (secret, rate limit, moderation)
#   GET  /api/attacks/leaderboard        newest first: handle, source, attack type, result, top reasons, and totals (attempts, unique
#                                        attackers, sandbox dollars moved). The attack text (subject, sender, body) is included ONLY when
#                                        moderation_status is approved; hidden rows are left out unless include_hidden. Bounty handles and
#                                        sender addresses are masked on the screen. Only console, judge and bounty_email attacks count:
#                                        the planted attacks of the seed (source "seeded") are never listed or totalled.
#   POST /api/attacks/{id}/moderation    approve or hide a row on the leaderboard screen
#
# An attack or a bounty email NEVER fails because a payment run is active. Each one gets a mini-run: its own run_id
# that processes only that attack's invoice, through the same pipeline as a full run.
#   * Nothing running: the mini-run starts at once.
#   * A full run (or an earlier attack) is running: the attack is queued and processed right after, in arrival order.
#     The response says queued: true; attack.queued and attack.logged are emitted straight away.
#   * The attack's invoice is claimed, so a full run started in the meantime leaves it alone, and a mini-run never blocks
#     POST /api/payment-runs.
#   If the server stops with attacks still queued, their invoices stay open and the next full run picks them up.
#
# What an attack creates: a message in the thread (the vendor comes from the thread, never from the sender), an invoice for
# it, an attack row, and a mini-run. The invoice is synthetic when the attack is an email: the amount is the first dollar
# figure in the body (else the vendor's average paid invoice), the bank details are the labeled Bank / Routing number /
# Account number lines if present (else the vendor's current account, i.e. no change). A pdf (a file name from
# backend/seed/invoices) or a bounty PDF attachment is saved under a generated name and extracted by the run.

import asyncio
import base64
import binascii
import hmac
import logging
import re
import shutil
import statistics
from datetime import timedelta
from pathlib import Path
from typing import Any, Literal, NamedTuple, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlmodel import Session, select

from app import events as ev
from app.audit import write_audit
from app.config import get_settings
from app.db import engine, get_session
from app.models import (
    Attack,
    AttackResult,
    AttackSource,
    AuditActor,
    Invoice,
    Message,
    ModerationStatus,
    Payment,
    PaymentRun,
    PaymentStatus,
    RunStatus,
    Vendor,
    VendorBankAccount,
    new_id,
    utcnow,
)
from app.services import run
from app.services.extract import hash_routing
from app.services.ingest import MAX_BODY_CHARS, MAX_PDF_BYTES, _EMAIL_RE, vendor_for_thread

log = logging.getLogger("countersign.attacks")
router = APIRouter()

BACKEND = Path(__file__).resolve().parents[2]
SEED_INVOICES = BACKEND / "seed" / "invoices"
POLL_SECONDS = 0.05
BOUNTY_LIMIT = 5  # submissions per sender per hour
BOUNTY_WINDOW = timedelta(hours=1)


class Job(NamedTuple):
    attack_id: str
    run_id: str
    invoice_id: str


_queue: Optional[asyncio.Queue] = None
_worker: Optional[asyncio.Task] = None
_current: Optional[Job] = None
_lock: Optional[asyncio.Lock] = None  # launches are handled one at a time, in arrival order


# ---------------------------------------------------------------- the queue


async def _loop(q: asyncio.Queue) -> None:
    global _current
    while True:
        job = await q.get()
        _current = job
        try:
            while run.full_run_active():  # a full run is on: wait for it, then go
                await asyncio.sleep(POLL_SECONDS)
            await run.start_mini_run(job.run_id, job.invoice_id)
        except asyncio.CancelledError:
            run._claimed.discard(job.invoice_id)
            raise
        except Exception:
            log.exception("attack run %s failed", job.run_id)
            run._claimed.discard(job.invoice_id)
            run._mini.discard(job.run_id)
            _mark_failed(job.run_id)
        finally:
            _current = None
            q.task_done()


def _mark_failed(run_id: str) -> None:
    try:
        with Session(engine) as s:
            r = s.get(PaymentRun, run_id)
            if r and r.status == RunStatus.running:
                r.status, r.completed_at = RunStatus.failed, utcnow()
                s.add(r)
                s.commit()
    except Exception:
        log.exception("could not mark %s failed", run_id)


async def start() -> None:
    """Start the worker on the running event loop (called from the app's lifespan)."""
    global _queue, _worker, _current, _lock
    _queue, _current, _lock = asyncio.Queue(), None, asyncio.Lock()
    _worker = asyncio.create_task(_loop(_queue))


async def stop() -> None:
    global _worker, _queue
    if _worker:
        _worker.cancel()
        try:
            await _worker
        except (asyncio.CancelledError, Exception):
            pass
    _worker, _queue = None, None


def _plan() -> tuple[bool, int, Optional[str]]:
    """Would a new attack have to wait? (queued, position, waiting_for). Position 0 means it starts right away."""
    if _queue is None:
        raise HTTPException(503, "the attack queue is not running")
    waiting_for = next(iter(run._active), None) or (_current.run_id if _current else None)
    ahead = _queue.qsize() + (1 if _current else 0)
    queued = bool(run.full_run_active() or ahead)
    return queued, (_queue.qsize() + 1 if queued else 0), waiting_for if queued else None  # position 1 = next to run


# ---------------------------------------------------------------- building the attack


_ROUTING_RE = re.compile(r"routing(?:\s*(?:number|no\.?|#))?\s*[:\-]?\s*(\d{9})", re.I)
_ACCOUNT_RE = re.compile(r"account(?:\s*(?:number|no\.?|#))?\s*[:\-]?\s*([\d\*xX \-]{4,})", re.I)
_BANK_RE = re.compile(r"^\s*bank(?:\s+name)?\s*[:\-]\s*(.+)$", re.I | re.M)
_MONEY_RE = re.compile(r"\$\s?([\d]{1,3}(?:,\d{3})+(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)")


def parse_bank_details(body: str) -> Optional[dict]:
    """Labeled bank lines in an email -> a remittance dict (hash and last 4 only). None if it does not carry both numbers."""
    routing, account = _ROUTING_RE.search(body), _ACCOUNT_RE.search(body)
    digits = re.sub(r"\D", "", account.group(1)) if account else ""
    if not routing or len(digits) < 4:
        return None
    bank = _BANK_RE.search(body)
    return {"bank_name": (bank.group(1).strip()[:80] if bank else "Unknown bank"), "routing_hash": hash_routing(routing.group(1)), "account_last4": digits[-4:]}


def parse_amount(body: str) -> Optional[float]:
    for m in _MONEY_RE.finditer(body):
        try:
            v = float(m.group(1).replace(",", ""))
        except ValueError:
            continue
        if 0 < v < 10_000_000:
            return round(v, 2)
    return None


def _typical_amount(s: Session, vendor_id: Optional[str]) -> float:
    if not vendor_id:
        return 1000.0
    amounts = s.exec(select(Invoice.amount_usd).join(Payment, Payment.invoice_id == Invoice.id).where(Invoice.vendor_id == vendor_id, Payment.status == PaymentStatus.paid)).all()
    amounts = [a for a in amounts if a]
    return round(statistics.fmean(amounts), 2) if amounts else 1000.0


def _save_pdf(invoice_id: str, data: bytes) -> str:
    folder = Path(get_settings().upload_dir)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{invoice_id}.pdf"
    path.write_bytes(data)
    return path.as_posix()


def _decode_pdf(data: str) -> bytes:
    try:
        raw = base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(422, "pdf_base64 is not valid base64")
    if not raw.startswith(b"%PDF-") or len(raw) > MAX_PDF_BYTES:
        raise HTTPException(422, "pdf_base64 must be a PDF of at most 5 MB")
    return raw


def _read_seed_pdf(name: str) -> bytes:
    path = (SEED_INVOICES / name).resolve()
    if path.parent != SEED_INVOICES.resolve() or not path.is_file():
        raise HTTPException(422, f"pdf must be the name of a file in backend/seed/invoices: {name!r}")
    return path.read_bytes()


def _build(
    s: Session, *, attacker_name: str, source: AttackSource, card: str, thread_id: Optional[str], from_addr: str, reply_to: Optional[str],
    subject: str, body: str, pdf: Optional[bytes], vendor_id: Optional[str] = None,
) -> tuple[Attack, Message, Invoice, str]:
    thread_id = thread_id or new_id("thr")
    vendor_id = vendor_for_thread(s, thread_id) or vendor_id  # the thread decides; a hint only fills in for a brand-new thread
    msg = Message(thread_id=thread_id, vendor_id=vendor_id, from_addr=from_addr, reply_to=reply_to, subject=subject, body=body, is_attack=True)
    inv = Invoice(vendor_id=vendor_id, message_id=msg.id, number="ATK-" + msg.id.split("_", 1)[1][:8].upper(),
                  amount_usd=parse_amount(body) or _typical_amount(s, vendor_id), due_date=(utcnow() + timedelta(days=15)).date())
    remit = parse_bank_details(body)
    if pdf is not None:
        inv.pdf_path = _save_pdf(inv.id, pdf)  # the run extracts amount, number and bank details from it
    elif remit is None and vendor_id:
        cur = s.exec(select(VendorBankAccount).where(VendorBankAccount.vendor_id == vendor_id, VendorBankAccount.valid_to.is_(None))).first()
        remit = {"bank_name": cur.bank_name, "routing_hash": cur.routing_hash, "account_last4": cur.account_last4} if cur else None
    inv.remittance_json = remit if pdf is None else None
    attack = Attack(
        attacker_name=attacker_name, source=source, card=card, payload_ref=msg.id,
        moderation_status=ModerationStatus.pending if source == AttackSource.bounty_email else ModerationStatus.approved)
    attack.detail_json = {"subject": subject, "from_addr": from_addr, "body": body[:4000], "has_pdf": pdf is not None, "amount_usd": inv.amount_usd,
                          "outcome": "processing", "reasons": [], "paid_usd": 0.0}
    run_id = new_id("run")
    s.add_all([msg, inv, attack, PaymentRun(id=run_id, totals_json={"invoice_count": 1, "kind": "attack", "attack_id": attack.id})])
    actor = AuditActor.system if source == AttackSource.bounty_email else AuditActor.human
    write_audit("attack", attack.id, actor, "launched", {"card": card, "source": source.value, "attacker": attacker_name, "message_id": msg.id,
                                                         "invoice_id": inv.id, "run_id": run_id}, session=s)
    write_audit("message", msg.id, "system", "created", {"thread_id": thread_id, "vendor_id": vendor_id, "from_addr": from_addr, "is_attack": True,
                                                        "body_chars": len(body)}, session=s)
    write_audit("invoice", inv.id, "system", "created", {"message_id": msg.id, "synthetic": pdf is None, "amount_usd": inv.amount_usd}, session=s)
    return attack, msg, inv, run_id


async def _launch(attack: Attack, msg: Message, inv: Invoice, run_id: str) -> dict:
    run._claimed.add(inv.id)  # at once, with no await before it: a full run started now must leave this invoice alone
    if _lock is None or _queue is None:
        run._claimed.discard(inv.id)
        raise HTTPException(503, "the attack queue is not running")
    async with _lock:  # one launch at a time, first come first served
        queued, position, waiting_for = _plan()
        await ev.emit(ev.AttackLogged(run_id=run_id, attack_id=attack.id, attacker_name=run.public_handle(attack), source=attack.source, card=attack.card,
                                      result=None, moderation_status=attack.moderation_status))
        if queued:
            await ev.emit(ev.AttackQueued(run_id=run_id, attack_id=attack.id, position=position, waiting_for=waiting_for))
        _queue.put_nowait(Job(attack.id, run_id, inv.id))  # only now can the worker start it, so the events above come first
    return {"attack_id": attack.id, "message_id": msg.id, "invoice_id": inv.id, "run_id": run_id, "queued": queued, "position": position, "waiting_for": waiting_for}


# ---------------------------------------------------------------- POST /api/attacks


class AttackPayload(BaseModel):
    thread_id: Optional[str] = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,64}$")
    from_addr: str = Field(max_length=254)
    reply_to: Optional[str] = Field(default=None, max_length=254)
    subject: str = Field(default="(no subject)", min_length=1, max_length=300)
    body: str = Field(max_length=MAX_BODY_CHARS)
    pdf: Optional[str] = Field(default=None, pattern=r"^[A-Za-z0-9_.-]{1,100}\.pdf$")  # a file in backend/seed/invoices
    pdf_base64: Optional[str] = Field(default=None, max_length=7_500_000)  # or the PDF itself, up to 5 MB

    @field_validator("from_addr", "reply_to")
    @classmethod
    def _addr(cls, v: Optional[str]) -> Optional[str]:
        if v in (None, ""):
            return None
        if not _EMAIL_RE.match(v):
            raise ValueError("not a valid email address")
        return v

    @field_validator("from_addr")
    @classmethod
    def _from(cls, v: Optional[str]) -> str:
        if not v:
            raise ValueError("from_addr is required")
        return v

    @field_validator("subject")
    @classmethod
    def _subject(cls, v: str) -> str:
        if re.search(r"[\x00-\x1f\x7f]", v):
            raise ValueError("subject must be a single line")
        return v.strip()


PDF_CARDS = ("poisoned_invoice", "freestyle")
LEADERBOARD_SOURCES = (AttackSource.console, AttackSource.judge, AttackSource.bounty_email)


class AttackIn(BaseModel):
    attacker_name: str = Field(min_length=1, max_length=80)
    card: Literal["classic_bank_change", "poisoned_invoice", "ceo_pressure", "freestyle"]
    source: Literal["console", "judge"] = "console"
    payload: AttackPayload

    @model_validator(mode="after")
    def _pdf_rules(self) -> "AttackIn":
        p = self.payload
        if (p.pdf or p.pdf_base64) and self.card not in PDF_CARDS:
            raise ValueError("only poisoned_invoice and freestyle attacks take a PDF")
        if p.pdf and p.pdf_base64:
            raise ValueError("send either pdf or pdf_base64, not both")
        return self


@router.post("/attacks", status_code=201)
async def launch_attack(body: AttackIn, session: Session = Depends(get_session)) -> dict:
    p = body.payload
    pdf = _read_seed_pdf(p.pdf) if p.pdf else _decode_pdf(p.pdf_base64) if p.pdf_base64 else None
    attack, msg, inv, run_id = _build(session, attacker_name=body.attacker_name.strip(), source=AttackSource(body.source), card=body.card, thread_id=p.thread_id,
                                      from_addr=p.from_addr, reply_to=p.reply_to, subject=p.subject, body=p.body, pdf=pdf)
    session.commit()
    session.refresh(attack), session.refresh(msg), session.refresh(inv)
    return await _launch(attack, msg, inv, run_id)


# ---------------------------------------------------------------- POST /api/bounty/inbound


def _first(d: dict, *names: str) -> Any:
    for n in names:
        if d.get(n) not in (None, ""):
            return d[n]
    return None


def _sender(raw: str) -> str:
    from email.utils import parseaddr

    addr = parseaddr(raw or "")[1].lower()
    if not _EMAIL_RE.match(addr):
        raise HTTPException(422, "the From address is not valid")
    return addr


def _vendor_hint(s: Session, text: str) -> Optional[str]:
    """A brand-new bounty thread has no vendor. If the email names one (or its domain), use it as a hint. The sender is never used."""
    low = text.lower()
    best = None
    for v in s.exec(select(Vendor)):
        if v.name.lower() in low or v.email_domain.lower() in low:
            if best is None or len(v.name) > len(best.name):
                best = v
    return best.id if best else None


@router.post("/bounty/inbound")
async def bounty_inbound(request: Request, session: Session = Depends(get_session)) -> dict:
    """Inbound-email webhook. Accepts a normalized body {from, subject, text, html, attachments:[{filename, content_type, content_base64}]}
    or Postmark's field names (From, Subject, TextBody, HtmlBody, Attachments:[{Name, ContentType, Content}])."""
    secret = get_settings().bounty_webhook_secret
    if not secret:
        raise HTTPException(503, "the bounty inbox is not configured (BOUNTY_WEBHOOK_SECRET)")
    if not hmac.compare_digest(request.headers.get("x-webhook-secret", ""), secret):
        raise HTTPException(401, "bad webhook secret")
    try:
        data = await request.json()
        assert isinstance(data, dict)
    except Exception:
        raise HTTPException(422, "expected a JSON object")

    sender = _sender(str(_first(data, "from", "From", "sender") or ""))
    now = utcnow()
    recent = session.exec(select(Attack).where(Attack.source == AttackSource.bounty_email, Attack.attacker_name == sender, Attack.created_at >= now - BOUNTY_WINDOW)).all()
    if len(recent) >= BOUNTY_LIMIT:
        oldest = min(a.created_at for a in recent)
        retry = max(1, int((oldest + BOUNTY_WINDOW - now).total_seconds()))
        raise HTTPException(429, detail={"error": f"at most {BOUNTY_LIMIT} submissions per sender per hour", "retry_after_seconds": retry}, headers={"Retry-After": str(retry)})

    subject = re.sub(r"[\x00-\x1f\x7f]+", " ", str(_first(data, "subject", "Subject") or "(no subject)"))[:300].strip() or "(no subject)"
    body = str(_first(data, "text", "TextBody", "html", "HtmlBody") or "")[:MAX_BODY_CHARS]
    pdf = None
    for att in _first(data, "attachments", "Attachments") or []:
        if not isinstance(att, dict):
            continue
        try:
            raw = base64.b64decode(str(_first(att, "content_base64", "Content") or ""), validate=False)
        except (binascii.Error, ValueError):
            continue
        if raw.startswith(b"%PDF-") and 0 < len(raw) <= MAX_PDF_BYTES:
            pdf = raw
            break
    hint = _vendor_hint(session, f"{subject}\n{body}")
    attack, msg, inv, run_id = _build(session, attacker_name=sender, source=AttackSource.bounty_email, card="bounty", thread_id=None, from_addr=sender, reply_to=None,
                                      subject=subject, body=body, pdf=pdf, vendor_id=hint)
    session.commit()
    session.refresh(attack), session.refresh(msg), session.refresh(inv)
    return await _launch(attack, msg, inv, run_id)


# ---------------------------------------------------------------- leaderboard and moderation


mask_handle = run.mask_handle


def _mask_addr(addr: str) -> str:
    return mask_handle(addr) + ("@" + addr.split("@", 1)[1] if "@" in addr else "")


def leaderboard_row(a: Attack) -> dict:
    d = a.detail_json or {}
    bounty = a.source == AttackSource.bounty_email
    row = {
        "id": a.id, "handle": mask_handle(a.attacker_name) if bounty else a.attacker_name, "source": a.source.value, "card": a.card,
        "result": a.result.value if a.result else None, "outcome": d.get("outcome", "processing"), "top_reasons": d.get("reasons", [])[:3],
        "amount_usd": d.get("amount_usd"), "paid_usd": d.get("paid_usd", 0.0), "created_at": a.created_at, "moderation_status": a.moderation_status.value,
        "text": None,
    }
    if a.moderation_status == ModerationStatus.approved:  # the attack text is shown only once a person approved it
        row["text"] = {"subject": d.get("subject"), "from_addr": _mask_addr(d["from_addr"]) if bounty and d.get("from_addr") else d.get("from_addr"),
                       "body": (d.get("body") or "")[:2000], "has_pdf": d.get("has_pdf", False)}
    return row


@router.get("/attacks/leaderboard")
def leaderboard(limit: int = Query(100, ge=1, le=500), include_hidden: bool = False, session: Session = Depends(get_session)) -> dict:
    q = select(Attack).where(Attack.source.in_(LEADERBOARD_SOURCES)).order_by(Attack.created_at.desc(), Attack.id.desc())  # never the seeded ones
    if not include_hidden:
        q = q.where(Attack.moderation_status != ModerationStatus.hidden)
    attacks = session.exec(q.limit(limit)).all()
    rows = [leaderboard_row(a) for a in attacks]
    return {
        "attempts": rows,
        "totals": {
            "attempts": len(rows), "unique_attackers": len({a.attacker_name.lower() for a in attacks}),
            "sandbox_usd_moved": round(sum(r["paid_usd"] or 0.0 for r in rows if r["result"] == "missed"), 2),
            "caught": sum(r["result"] == "caught" for r in rows), "missed": sum(r["result"] == "missed" for r in rows),
            "pending_result": sum(r["result"] is None for r in rows),
            "by_card": {c: sum(r["card"] == c for r in rows) for c in sorted({r["card"] for r in rows})},
        },
    }


class ModerationIn(BaseModel):
    status: Literal["approved", "hidden"]
    moderator: str = Field(min_length=1, max_length=100)


@router.post("/attacks/{attack_id}/moderation")
async def moderate(attack_id: str, body: ModerationIn, session: Session = Depends(get_session)) -> dict:
    a = session.get(Attack, attack_id)
    if a is None:
        raise HTTPException(404, "attack not found")
    a.moderation_status = ModerationStatus(body.status)
    session.add(a)
    write_audit("attack", a.id, AuditActor.human, f"moderation_{body.status}", {"moderator": body.moderator}, session=session)
    session.commit()
    session.refresh(a)
    inv = session.exec(select(Invoice).where(Invoice.message_id == a.payload_ref)).first()
    pay = session.exec(select(Payment).where(Payment.invoice_id == inv.id)).first() if inv else None
    run_id = pay.run_id if pay else None
    await ev.emit(ev.AttackLogged(run_id=run_id, attack_id=a.id, attacker_name=run.public_handle(a), source=a.source, card=a.card, result=a.result,
                                  moderation_status=a.moderation_status))
    return {"id": a.id, "moderation_status": a.moderation_status.value}
