"""Teammate B's router: voice audio, the Twilio smoke TwiML, the verification call webhooks (TwiML, Gather, status) and
the manual call route, plus integration_status() for /api/system/status. Same pattern as dev.py."""

import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from pathlib import Path
from sqlmodel import Session, select

from app import db, events as ev
from app.config import get_settings
from app.models import AuditLog, CallOutcome, Invoice, Payment, PaymentStatus, Vendor, VerificationCall
from app.services import identity, payments, verify, voice

log = logging.getLogger("countersign.integrations")

voice_router = APIRouter(prefix="/voice")
webhook_router = APIRouter(prefix="/webhooks/twilio")
verification_router = APIRouter(prefix="/verifications")
router = APIRouter()  # main.py includes this one; it carries all three

STATIC_DIR = Path(__file__).resolve().parent / "static"
SMOKE_SENTENCE = "This is Countersign. Custom TwiML from our own server is working."
SMOKE_CLIP_TEXT = "This is a Countersign voice clip."


def integration_status() -> dict:
    """Per integration: whether it runs real or mocked, and whether its key is set (never the key)."""
    s = get_settings()
    flags = s.mock_flags
    keys = {
        "twilio": bool(s.twilio_account_sid and s.twilio_auth_token and s.twilio_from_number),
        "cartesia": bool(s.cartesia_api_key and s.cartesia_voice_id),
        "nessie": bool(s.nessie_api_key),
        "apify": bool(s.apify_token),
        "crs": bool(identity._env("CRS_USERNAME") and identity._env("CRS_PASSWORD")),  # CRS login lives in the environment, not config.py
        "claude": bool(s.anthropic_api_key),
    }
    return {name: {"mode": "mock" if flags[name] else "real", "key_set": keys[name]} for name in keys}


@voice_router.get("/audio/{name}")
def audio(name: str) -> FileResponse:
    path = voice.audio_path(name)
    if path is None:
        raise HTTPException(404, "no such clip")
    return FileResponse(path, media_type="audio/wav")


def _smoke_twiml() -> Response:
    """Say, then Play the clip if it was pre-generated. Never generates audio while Twilio waits."""
    parts = [f"<Say>{SMOKE_SENTENCE}</Say>"]
    if voice.audio_path(voice._clip_name(SMOKE_CLIP_TEXT)) is not None:
        parts.append(f"<Play>{voice.clip_url(SMOKE_CLIP_TEXT)}</Play>")
    return Response(f'<?xml version="1.0" encoding="UTF-8"?><Response>{"".join(parts)}</Response>', media_type="application/xml")


@voice_router.get("/smoke-twiml")
def smoke_twiml_get() -> Response:
    return _smoke_twiml()


@voice_router.post("/smoke-twiml")
def smoke_twiml_post() -> Response:
    return _smoke_twiml()


# ---------------------------------------------------------------- Twilio signature

NO_STORE = {"Cache-Control": "no-store"}


def call_token_required() -> bool:
    """TWILIO_REQUIRE_CALL_TOKEN (config.py); blank means on whenever Twilio is real."""
    return get_settings().call_token_required


def signature_validation_on() -> bool:
    """TWILIO_VALIDATE_SIGNATURES: strict mode, a valid X-Twilio-Signature is also required. Off by default, because trial
    accounts fetch TwiML without a signature. When a signature IS sent it is still checked and the result is logged."""
    return get_settings().twilio_validate_signatures


def _signature_ok(request: Request, form: dict) -> bool:
    from twilio.request_validator import RequestValidator

    s = get_settings()
    url = s.public_base_url.rstrip("/") + request.url.path + (f"?{request.url.query}" if request.url.query else "")
    signature = request.headers.get("X-Twilio-Signature", "")
    return bool(s.twilio_auth_token and signature and RequestValidator(s.twilio_auth_token).validate(url, form, signature))


async def twilio_form(request: Request) -> dict:
    """The form Twilio posted, after authenticating the request.

    1. The per-call secret (?t=, or the last path segment of the status callback) must match the one made when the call was
       placed, or 403. On by default in real mode.
    2. A Twilio signature is an extra check: required (403) only in strict mode, otherwise logged when present.
    """
    call_id = request.path_params.get("call_id") or request.query_params.get("call_id") or ""
    token = request.path_params.get("t") or request.query_params.get("t")
    if call_token_required() and not voice.check_call_token(call_id, token):
        log.warning("webhook rejected: missing or wrong call token (%s)", request.url.path)
        raise HTTPException(403, "bad call token")
    form = {k: v for k, v in (await request.form()).items() if isinstance(v, str)}
    if signature_validation_on():
        if not _signature_ok(request, form):
            raise HTTPException(403, "bad Twilio signature")
    elif request.headers.get("X-Twilio-Signature"):
        log.info("twilio signature on %s verified: %s", request.url.path, _signature_ok(request, form))
    return form


def _xml(body: str) -> Response:
    return Response(body, media_type="application/xml", headers=NO_STORE)


# ---------------------------------------------------------------- the verification call webhooks


def _context(session: Session, call_id: str):
    call = session.get(VerificationCall, call_id)
    if call is None:
        raise HTTPException(404, "no such call")
    payment = session.get(Payment, call.payment_id)
    invoice = session.get(Invoice, payment.invoice_id)
    vendor = session.get(Vendor, invoice.vendor_id)
    script = voice.call_script(vendor.name, (invoice.remittance_json or {})["account_last4"])
    return call, payment, script


def _url(path: str, request: Optional[Request] = None) -> str:
    """A public URL for Twilio to call back. Carries the incoming request's call token along, so the whole call stays authenticated."""
    url = voice.public_url(path)  # PUBLIC_BASE_URL over https, never the request's own URL
    token = request.query_params.get("t") if request is not None else None
    return voice.with_token(url, token) if token else url


async def _record_lines(session: Session, call: VerificationCall, payment: Payment, lines: list[dict]) -> list[dict]:
    """Append lines to the call's transcript and emit a call.transcript event for each."""
    call.transcript = [*(call.transcript or []), *lines]
    session.add(call)
    session.commit()
    for line in lines:
        await ev.emit(ev.CallTranscript(run_id=payment.run_id, payment_id=payment.id, speaker=line["speaker"], text=line["text"]))
    return call.transcript


@voice_router.post("/twiml/{call_id}")
async def call_twiml(call_id: str, request: Request, background: BackgroundTasks, retry: int = 0, end: int = 0, r: int = 0, _form: dict = Depends(twilio_form)) -> Response:
    """Served when the vendor picks up. Intro and question in a speech Gather; silence redirects once to a retry version,
    and silence again ends the call as unclear. Never generates audio: clips were made before dialing."""
    with Session(db.engine) as s:
        call, payment, script = _context(s, call_id)
        if call.outcome is not None:
            return _xml(voice.twiml_close(script.closing(call.outcome.value)))
        if end:
            transcript = await _record_lines(s, call, payment, ([] if r else [{"speaker": "agent", "text": script.question}]) + [
                {"speaker": "vendor", "text": "(no response)"}, {"speaker": "agent", "text": script.unclear}])
            background.add_task(verify.handle_outcome, call_id, CallOutcome.unclear, transcript, None, True,
                                {"classifier": "silence", "reason": "nothing was heard after two prompts"})
            return _xml(voice.twiml_close(script.unclear))
    verify.arm_answer_watchdog(call_id)  # the 60 s rule starts when the vendor picks up
    voice.log_state(call_id, "answered", channel="twilio")
    gather = _url(f"/api/voice/gather/{call_id}", request)
    nxt = _url(f"/api/voice/twiml/{call_id}?end=1", request) if retry else _url(f"/api/voice/twiml/{call_id}?retry=1", request)
    return _xml(voice.twiml_question(script, gather, nxt, first=not retry))


@voice_router.post("/gather/{call_id}")
async def call_gather(call_id: str, request: Request, background: BackgroundTasks, r: int = 0, n: int = 0, form: dict = Depends(twilio_form)) -> Response:
    """The vendor's spoken answer. Classified within the 3 s Claude cap and answered inside Twilio's 5 s: a closing line and a
    hangup; or (once, r=1 afterwards) a clarifying, confirm-again or "take your time" clip and another Gather; or, for a greeting
    or a "who is this", the question again (n counts those, up to voice.MAX_REPEATS). Applied in the background."""
    answer = (form.get("SpeechResult") or "").strip()
    try:
        confidence: Optional[float] = float(form["Confidence"]) if form.get("Confidence") not in (None, "") else None
    except (TypeError, ValueError):
        confidence = None
    with Session(db.engine) as s:
        call, payment, script = _context(s, call_id)
        if call.outcome is not None:  # Twilio retried, or the 60 s rule already ended the call
            return _xml(voice.twiml_close(script.closing(call.outcome.value)))
    res = await verify.finish_answer(call_id, answer, bool(r), n, confidence)
    if res is None:
        return _xml(voice.twiml_close(script.unclear))
    if res["action"] == "close":
        background.add_task(verify.handle_outcome, call_id, res["outcome"], res["transcript"], None, True,
                            {**res["evidence"], "confidence": form.get("Confidence")})
        return _xml(voice.twiml_close(res["text"]))
    nr, nn = int(res["reasked"]), res["repeats"]
    return _xml(voice.twiml_regather(script, res["text"], _url(f"/api/voice/gather/{call_id}?r={nr}&n={nn}", request),
                                     _url(f"/api/voice/twiml/{call_id}?end=1&r=1", request)))


@webhook_router.post("/status/{call_id}/{t}")
async def call_status_path(call_id: str, t: str, background: BackgroundTasks, form: dict = Depends(twilio_form)) -> dict:
    """The status callback placed calls use: call id and token in the path, so nothing depends on Twilio keeping a query string."""
    return _apply_status(call_id, background, form)


@webhook_router.post("/status")
async def call_status(call_id: str, background: BackgroundTasks, form: dict = Depends(twilio_form)) -> dict:
    """The older query-string form (?call_id=&t=), kept for calls placed before the path form."""
    return _apply_status(call_id, background, form)


def _apply_status(call_id: str, background: BackgroundTasks, form: dict) -> dict:
    """Twilio's call status callback. A call nobody answered (no-answer, busy, failed, canceled) is a no_answer; other
    statuses are ignored (an answered call finishes through the gather route or the 60 s rule)."""
    status = (form.get("CallStatus") or "").lower()
    voice.log_state(call_id, "twilio-status", status=status)
    if status in ("no-answer", "busy", "failed", "canceled"):
        background.add_task(verify.handle_outcome, call_id, CallOutcome.no_answer, None, None, True,
                            {"classifier": "twilio_status", "reason": f"Twilio call status {status}"})
    return {"ok": True}


# ---------------------------------------------------------------- manual call


async def _run_mock_call(payment_id: str, answer: Optional[str]) -> None:
    """Simulate the whole call at about 1 s per line, then pay a confirmed payment through the guard (the run is not here to)."""
    if answer:
        verify.MOCK_ANSWERS[payment_id] = answer
    token = verify.MOCK_PACE.set(1.0)
    try:
        result = await verify.start_verification(payment_id)
        if result.outcome == CallOutcome.confirmed and result.payment_status == PaymentStatus.pending:
            with Session(db.engine) as s:
                await payments.pay_payment(s, payment_id)
        from app.services import late

        await late.after_outcome(payment_id)  # the manual call runs outside a payment run, like a webhook outcome
    except Exception as exc:  # noqa: BLE001
        log.warning("mock verification for %s failed: %s", payment_id, type(exc).__name__)
    finally:
        verify.MOCK_PACE.reset(token)
        verify.MOCK_ANSWERS.pop(payment_id, None)


@verification_router.post("/{payment_id}/call", status_code=202)
async def start_call(payment_id: str, background: BackgroundTasks, answer: Optional[str] = None) -> dict:
    """Start a verification call for a held payment. Real mode places the call and returns its call_id; the outcome arrives
    on the event stream. Mock mode simulates it in the background; `answer` scripts what the vendor says (mock only)."""
    with Session(db.engine) as s:
        payment = s.get(Payment, payment_id)
        if payment is None:
            raise HTTPException(404, "no such payment")
        if payment.status != PaymentStatus.held:
            raise HTTPException(409, f"payment is {payment.status.value}; only a held payment can be verified")
        run_id = payment.run_id
    cfg = get_settings()
    if cfg.mock_twilio or cfg.mock_cartesia or verify.is_seeded_call(payment_id):  # the seeded demo calls are always scripted
        background.add_task(_run_mock_call, payment_id, answer)
        return {"payment_id": payment_id, "run_id": run_id, "mode": "mock", "status": "started"}
    try:
        result = await verify.start_verification(payment_id)
    except (verify.CallNotAllowed, voice.CallNotAllowedError):
        raise HTTPException(403, "number is not in ALLOWED_CALL_NUMBERS")
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(400, str(exc))
    mode = "web" if result.call_id in voice.web_calls else "real"  # web also when twilio failed over to the softphone
    return {"payment_id": payment_id, "run_id": run_id, "mode": mode, "status": "calling", "call_id": result.call_id}


# ---------------------------------------------------------------- browser softphone (VOICE_MODE=web, or failover)


def _vendor_phone_guard(vendor_id: str, k: Optional[str]) -> None:
    if not voice.vendor_phone_key_ok(k):
        raise HTTPException(403, "bad key")
    with Session(db.engine) as s:
        if s.get(Vendor, vendor_id) is None:
            raise HTTPException(404, "no such vendor")


@voice_router.get("/vendor-phone/{vendor_id}")
def vendor_phone_page(vendor_id: str, k: Optional[str] = None) -> FileResponse:
    _vendor_phone_guard(vendor_id, k)
    return FileResponse(STATIC_DIR / "vendor_phone.html", media_type="text/html", headers=NO_STORE)


@voice_router.get("/pending/{vendor_id}")
def vendor_phone_pending(vendor_id: str, k: Optional[str] = None) -> JSONResponse:
    """What the softphone page polls once a second. Also what marks the page as open for failover."""
    _vendor_phone_guard(vendor_id, k)
    voice.note_poll(vendor_id)
    waiting = voice.pending_for(vendor_id)
    body: dict = {"call": None}
    if waiting is not None:
        call_id, c = waiting
        body["call"] = {"call_id": call_id, "token": c["token"], "vendor_name": c["vendor_name"], "clips": c["clips"], "texts": c["texts"]}
    return JSONResponse(body, headers=NO_STORE)


@voice_router.post("/web-answer/{call_id}")
async def web_answer(call_id: str, request: Request, background: BackgroundTasks, t: Optional[str] = None) -> JSONResponse:
    """The softphone's side of the call. Body: {"event": "answered"} on the Answer tap, {"decline": true}, or {"answer": "..."}.
    The per-call token is required in every mode."""
    if not voice.check_call_token(call_id, t):
        log.warning("softphone rejected: missing or wrong call token")
        raise HTTPException(403, "bad call token")
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}
    body = body if isinstance(body, dict) else {}
    entry = voice.web_calls.get(call_id)
    if entry is None:
        raise HTTPException(410, "this call is over (it timed out or was already finished)")
    if body.get("decline"):
        await verify.decline_web_call(call_id)
        return JSONResponse({"action": "close", "final": True, "outcome": "no_answer", "text": "", "clip": None}, headers=NO_STORE)
    if body.get("event") == "answered":
        verify.web_answered(call_id)
        return JSONResponse({"ok": True}, headers=NO_STORE)
    verify.web_answered(call_id)  # an answer implies the Answer tap (idempotent)
    res = await verify.finish_answer(call_id, str(body.get("answer") or "")[:500], entry["reasked"], entry.get("repeats", 0))
    if res is None:
        raise HTTPException(410, "this call is over")
    final = res["action"] == "close"
    if final:
        background.add_task(verify.handle_outcome, call_id, res["outcome"], res["transcript"], None, True, res["evidence"])
    else:
        entry["reasked"], entry["repeats"] = res["reasked"], res["repeats"]
        verify.rearm_answer_watchdog(call_id)  # the call stays open for the next answer
    return JSONResponse({"action": res["action"], "final": final, "outcome": res["outcome"].value if final else None,
                         "text": res["text"], "clip": voice.clip_url(res["text"])}, headers=NO_STORE)



# ---------------------------------------------------------------- vendor identity (CRS)

vendor_identity_router = APIRouter(prefix="/vendors")


_STATUS_WORD = {"verified": "pass", "unverified": "review", "flagged": "fail"}


def _section(sec: dict, at, extra: Optional[dict] = None) -> dict:
    """One section of the card: no PII, no raw response."""
    return {"status": sec.get("status"), "summary": sec.get("summary"), "checks": sec.get("checks", []), "persona": sec.get("persona"),
            "checked_at": sec.get("checked_at") or at.isoformat(), **(extra or {})}


@vendor_identity_router.get("/{vendor_id}/identity")
def vendor_identity(vendor_id: str) -> dict:
    """The vendor card's CRS result, kept apart: `vendor` is the vendor's own standing (reverse phone and the owner's identity check),
    `latest_request` is the newest check of a bank-change request (email risk and the requester's identity), or null. The top-level
    `status` is the vendor's own, for older clients. {"status": null, "vendor": null, "latest_request": null} if no check has run."""
    with Session(db.engine) as s:
        if s.get(Vendor, vendor_id) is None:
            raise HTTPException(404, "no such vendor")
        pay_ids = list(s.exec(select(Payment.id).join(Invoice, Invoice.id == Payment.invoice_id).where(Invoice.vendor_id == vendor_id)))
        wanted = (AuditLog.entity == "vendor") & (AuditLog.entity_id == vendor_id) & (AuditLog.action == "identity_check")
        if pay_ids:
            wanted = wanted | ((AuditLog.entity == "payment") & AuditLog.entity_id.in_(pay_ids) & (AuditLog.action == verify.CRS_ACTION))
        rows = list(s.exec(select(AuditLog).where(wanted).order_by(AuditLog.at.desc(), AuditLog.id.desc())))
    vendor = request = None
    for row in rows:  # newest first
        d = row.detail_json or {}
        if vendor is None:
            if d.get("vendor"):
                vendor = _section(d["vendor"], row.at)
            elif row.action == "identity_check":  # the vendor-level IdentityResult row
                vendor = _section({"status": _STATUS_WORD.get(d.get("status"), d.get("status")), "summary": d.get("summary"),
                                   "persona": d.get("test_identity_id"), "checked_at": d.get("checked_at")}, row.at)
        if request is None and d.get("request"):
            request = _section(d["request"], row.at, {"requested_by_domain": d["request"].get("requested_by_domain"), "payment_id": row.entity_id})
        if vendor is not None and request is not None:
            break
    return {"status": vendor["status"] if vendor else None, "vendor": vendor, "latest_request": request}


router.include_router(voice_router)
router.include_router(webhook_router)
router.include_router(verification_router)
router.include_router(vendor_identity_router)
