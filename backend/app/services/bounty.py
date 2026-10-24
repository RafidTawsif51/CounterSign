# Owner: Backend lead
# Prize track: Armadin (Best Security Hack: the public bounty), Hyphenate (real attacks from real people)
# Contract:
#   POST /api/bounty/inbound          Postmark inbound-email webhook for the Rob Countersign bounty
#   GET  /api/bounty/queue            the moderation queue (default: pending), oldest first, with the full attack text for the moderator
#   POST /api/bounty/{attack_id}/moderate   {action: approve | hide, moderator}
#
# Inbound rules:
#   * Authenticated with BOUNTY_WEBHOOK_SECRET. Postmark does not sign inbound mail, so the secret travels in the webhook URL
#     (https://anything:SECRET@host/api/bounty/inbound, sent as HTTP Basic auth); the header x-webhook-secret is accepted too.
#     Anything without the secret is rejected before the body is read; with no secret configured the inbox is closed (503).
#   * At most BOUNTY_GLOBAL_LIMIT_PER_HOUR (60) accepted submissions per hour across all senders, then 429.
#   * At most 5 accepted submissions per sender per hour (a +tag or Gmail dots do not make a new sender). Request at most 8 MB,
#     email text at most 50 KB, PDF attachments only, each at most 5 MB, at most 3 of them.
#   * Postmark retries a delivery, so a MessageID that was already accepted answers 200 with duplicate: true and creates nothing.
#   * The email becomes a message in a NEW thread (the sender never joins a vendor's thread) with an invoice, an attack row
#     (source bounty_email, moderation pending) and a mini-run: attacks._build and _launch, the same pipeline as every other invoice.
#     A vendor named in the email is only a hint, recorded as unverified; money can only ever go to the vendor's verified account,
#     a changed account triggers a call, and calls only go to numbers on ALLOWED_CALL_NUMBERS. Transfers are Nessie sandbox money.
#   * Until a moderator approves it, the leaderboard shows only the handle and the result (attacks.leaderboard_row).
#   The queue and moderation routes need BOUNTY_MODERATOR_TOKEN once the inbox is live (secret set): blank means 503, never open.
#   Email text, subjects and attachments are untrusted data: render them as text.

import base64
import binascii
import hmac
import re
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.audit import write_audit
from app.config import get_settings
from app.db import get_session
from app.models import Attack, AttackSource, AuditLog, ModerationStatus, Vendor, utcnow
from app.services import attacks
from app.services.attacks import BOUNTY_LIMIT, BOUNTY_WINDOW
from app.services.ingest import MAX_PDF_BYTES, _EMAIL_RE

router = APIRouter()

MAX_REQUEST_BYTES = 8 * 1024 * 1024  # 5 MB of PDF is about 6.7 MB as base64, plus the text and headers
MAX_TEXT_BYTES = 50 * 1024
MAX_ATTACHMENTS = 3


# ---------------------------------------------------------------- authentication


def _secret_ok(request: Request, secret: str) -> bool:
    """The secret as the Basic-auth password (Postmark) or the x-webhook-secret header. Compared in constant time."""
    given = request.headers.get("x-webhook-secret", "")
    auth = request.headers.get("authorization", "")
    if auth[:6].lower() == "basic ":
        try:
            given = given or base64.b64decode(auth[6:], validate=True).decode().partition(":")[2]
        except (binascii.Error, ValueError):
            given = given
    return bool(given) and hmac.compare_digest(given.encode(), secret.encode())


def require_secret(request: Request) -> None:
    secret = get_settings().bounty_webhook_secret
    if not secret:
        raise HTTPException(503, "the bounty inbox is not configured (BOUNTY_WEBHOOK_SECRET)")
    if not _secret_ok(request, secret):
        raise HTTPException(401, "unsigned or wrong secret", headers={"WWW-Authenticate": "Basic"})


def require_moderator(request: Request) -> None:
    """The queue and moderation need BOUNTY_MODERATOR_TOKEN (header x-moderator-token). Once the inbox is live (BOUNTY_WEBHOOK_SECRET set)
    a blank token closes these routes with a 503 instead of leaving them open. With no inbox configured (local dev) they stay open."""
    s = get_settings()
    if s.bounty_webhook_secret and not s.bounty_moderator_token:
        raise HTTPException(503, "moderation is not configured (BOUNTY_MODERATOR_TOKEN); the bounty inbox is live, so it stays closed")
    if s.bounty_moderator_token and not hmac.compare_digest(request.headers.get("x-moderator-token", "").encode(), s.bounty_moderator_token.encode()):
        raise HTTPException(401, "moderator token required")


# ---------------------------------------------------------------- parsing


def sender_key(addr: str) -> str:
    """The identity the rate limit counts: lower case, no +tag, no dots in a Gmail local part."""
    local, _, domain = addr.lower().partition("@")
    local = local.split("+", 1)[0]
    if domain in ("gmail.com", "googlemail.com"):
        local, domain = local.replace(".", ""), "gmail.com"
    return f"{local}@{domain}"


def _sender(data: dict) -> str:
    from email.utils import parseaddr

    full = data.get("FromFull")
    raw = full.get("Email") if isinstance(full, dict) else None
    addr = parseaddr(str(raw or data.get("From") or ""))[1].lower()
    if not _EMAIL_RE.match(addr):
        raise HTTPException(422, "the From address is not valid")
    return addr


def _vendor_hint(s: Session, text: str) -> Optional[str]:
    """A new bounty thread has no vendor. If the email names one (or its domain), keep it as an UNVERIFIED hint. The sender is never used."""
    low = text.lower()
    best = None
    for v in s.exec(select(Vendor)):
        if v.name.lower() in low or v.email_domain.lower() in low:
            if best is None or len(v.name) > len(best.name):
                best = v
    return best.id if best else None


def _pdfs(data: dict) -> list[bytes]:
    """The PDF attachments. Anything that is not a PDF, is too large, or is not valid base64 rejects the whole email."""
    atts = data.get("Attachments") or []
    if not isinstance(atts, list):
        raise HTTPException(422, "Attachments must be a list")
    if len(atts) > MAX_ATTACHMENTS:
        raise HTTPException(413, f"at most {MAX_ATTACHMENTS} attachments")
    out = []
    for att in atts:
        if not isinstance(att, dict):
            raise HTTPException(422, "bad attachment")
        try:
            raw = base64.b64decode(str(att.get("Content") or ""), validate=False)
        except (binascii.Error, ValueError):
            raise HTTPException(422, "attachment is not valid base64")
        if len(raw) > MAX_PDF_BYTES:
            raise HTTPException(413, "attachments must be at most 5 MB")
        if not raw.startswith(b"%PDF-") or "pdf" not in str(att.get("ContentType") or "").lower():
            raise HTTPException(415, "only PDF attachments are accepted")
        out.append(raw)
    return out


# ---------------------------------------------------------------- POST /api/bounty/inbound


@router.post("/bounty/inbound")
async def bounty_inbound(request: Request, session: Session = Depends(get_session)) -> dict:
    require_secret(request)  # before anything is read
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_REQUEST_BYTES:
        raise HTTPException(413, "request too large")
    raw = await request.body()
    if len(raw) > MAX_REQUEST_BYTES:
        raise HTTPException(413, "request too large")
    try:
        import json

        data = json.loads(raw)
        assert isinstance(data, dict)
    except Exception:
        raise HTTPException(422, "expected a JSON object")

    sender = _sender(data)
    key = sender_key(sender)
    now = utcnow()
    in_window = session.exec(select(Attack).where(Attack.source == AttackSource.bounty_email, Attack.created_at >= now - BOUNTY_WINDOW)).all()
    cap = get_settings().bounty_global_limit_per_hour
    if len(in_window) >= cap:  # across all senders
        oldest_any = min((a.created_at for a in in_window), default=now)
        retry = max(1, int((oldest_any + BOUNTY_WINDOW - now).total_seconds()))
        raise HTTPException(429, detail={"error": f"the bounty inbox accepts at most {cap} submissions per hour in total", "retry_after_seconds": retry},
                            headers={"Retry-After": str(retry)})
    recent = [a for a in in_window if sender_key(a.attacker_name) == key]
    if len(recent) >= BOUNTY_LIMIT:
        oldest = min(a.created_at for a in recent)
        retry = max(1, int((oldest + BOUNTY_WINDOW - now).total_seconds()))
        raise HTTPException(429, detail={"error": f"at most {BOUNTY_LIMIT} submissions per sender per hour", "retry_after_seconds": retry},
                            headers={"Retry-After": str(retry)})

    text = data.get("TextBody") or data.get("HtmlBody") or ""
    if not isinstance(text, str):
        raise HTTPException(422, "the body must be text")
    if len(text.encode()) > MAX_TEXT_BYTES:
        raise HTTPException(413, "the email text is limited to 50 KB")
    pdfs = _pdfs(data)

    mid = re.sub(r"[^\w.@-]", "", str(data.get("MessageID") or ""))[:100]
    if mid:  # Postmark delivers again after a failure: the same MessageID is not a second attack
        seen = session.exec(select(AuditLog).where(AuditLog.entity == "bounty_message", AuditLog.entity_id == mid)).first()
        if seen is not None:
            return {"duplicate": True, "attack_id": (seen.detail_json or {}).get("attack_id")}

    subject = re.sub(r"[\x00-\x1f\x7f]+", " ", str(data.get("Subject") or "(no subject)"))[:300].strip() or "(no subject)"
    hint = _vendor_hint(session, f"{subject}\n{text}")
    attack, msg, inv, run_id = attacks._build(session, attacker_name=sender, source=AttackSource.bounty_email, card="bounty", thread_id=None, from_addr=sender,
                                              reply_to=None, subject=subject, body=text, pdf=pdfs[0] if pdfs else None, vendor_id=hint)
    attack.detail_json = {**(attack.detail_json or {}), "vendor_claim": {"vendor_id": hint, "verified": False}}
    write_audit("attack", attack.id, "system", "bounty_received",
                {"claimed_vendor_id": hint, "vendor_claim": "unverified", "attachments": len(pdfs), "text_bytes": len(text.encode())}, session=session)
    if mid:
        write_audit("bounty_message", mid, "system", "received", {"attack_id": attack.id}, session=session)
    session.commit()
    session.refresh(attack), session.refresh(msg), session.refresh(inv)
    return await attacks._launch(attack, msg, inv, run_id)


# ---------------------------------------------------------------- moderation


@router.get("/bounty/queue", dependencies=[Depends(require_moderator)])
def queue(status: Literal["pending", "approved", "hidden", "all"] = "pending", limit: int = Query(50, ge=1, le=200),
          session: Session = Depends(get_session)) -> dict:
    """Bounty submissions for a moderator, oldest first. Includes the attack text (untrusted: render as text); the sender is masked."""
    q = select(Attack).where(Attack.source == AttackSource.bounty_email).order_by(Attack.created_at, Attack.id)
    if status != "all":
        q = q.where(Attack.moderation_status == ModerationStatus(status))
    rows = []
    for a in session.exec(q.limit(limit)):
        d = a.detail_json or {}
        rows.append({
            "id": a.id, "handle": attacks.mask_handle(a.attacker_name), "sender": attacks._mask_addr(a.attacker_name), "created_at": a.created_at,
            "moderation_status": a.moderation_status.value, "result": a.result.value if a.result else None, "outcome": d.get("outcome", "processing"),
            "reasons": d.get("reasons", []), "amount_usd": d.get("amount_usd"), "paid_usd": d.get("paid_usd", 0.0),
            "claimed_vendor": d.get("vendor_claim") or {"vendor_id": None, "verified": False},
            "subject": d.get("subject"), "body": (d.get("body") or "")[:4000], "has_pdf": d.get("has_pdf", False),
        })
    pending = session.exec(select(Attack).where(Attack.source == AttackSource.bounty_email, Attack.moderation_status == ModerationStatus.pending)).all()
    return {"status": status, "pending_count": len(pending), "items": rows}


class ModerateIn(BaseModel):
    action: Literal["approve", "hide"]
    moderator: str = Field(min_length=1, max_length=100)


@router.post("/bounty/{attack_id}/moderate", dependencies=[Depends(require_moderator)])
async def moderate(attack_id: str, body: ModerateIn, session: Session = Depends(get_session)) -> dict:
    a = session.get(Attack, attack_id)
    if a is None or a.source != AttackSource.bounty_email:
        raise HTTPException(404, "bounty submission not found")
    return await attacks.moderate(attack_id, attacks.ModerationIn(status="approved" if body.action == "approve" else "hidden", moderator=body.moderator), session)
