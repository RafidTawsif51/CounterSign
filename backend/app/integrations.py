"""Teammate B's router: voice audio, the Twilio smoke TwiML, the verification call webhooks (TwiML, Gather, status) and
the manual call route, plus integration_status() for /api/system/status. Same pattern as dev.py."""

import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import FileResponse, Response
from sqlmodel import Session

from app import db, events as ev
from app.config import get_settings
from app.models import CallOutcome, Invoice, Payment, PaymentStatus, Vendor, VerificationCall
from app.services import payments, verify, voice

log = logging.getLogger("countersign.integrations")

voice_router = APIRouter(prefix="/voice")
webhook_router = APIRouter(prefix="/webhooks/twilio")
verification_router = APIRouter(prefix="/verifications")
router = APIRouter()  # main.py includes this one; it carries all three

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
        "crs": bool(s.crs_api_key),
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

    1. The per-call secret (?t=) must match the one made when the call was placed, or 403. On by default in real mode.
    2. A Twilio signature is an extra check: required (403) only in strict mode, otherwise logged when present.
    """
    call_id = request.path_params.get("call_id") or request.query_params.get("call_id") or ""
    if call_token_required() and not voice.check_call_token(call_id, request.query_params.get("t")):
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
async def call_twiml(call_id: str, request: Request, background: BackgroundTasks, retry: int = 0, end: int = 0, _form: dict = Depends(twilio_form)) -> Response:
    """Served when the vendor picks up. Intro and question in a speech Gather; silence redirects once to a retry version,
    and silence again ends the call as unclear. Never generates audio: clips were made before dialing."""
    with Session(db.engine) as s:
        call, payment, script = _context(s, call_id)
        if call.outcome is not None:
            return _xml(voice.twiml_close(script.closing(call.outcome.value)))
        if end:
            transcript = await _record_lines(s, call, payment, [
                {"speaker": "agent", "text": script.question}, {"speaker": "vendor", "text": "(no response)"}, {"speaker": "agent", "text": script.unclear}])
            background.add_task(verify.handle_outcome, call_id, CallOutcome.unclear, transcript, None, True,
                                {"classifier": "silence", "reason": "nothing was heard after two prompts"})
            return _xml(voice.twiml_close(script.unclear))
    verify.arm_answer_watchdog(call_id)  # the 60 s rule starts when the vendor picks up
    gather = _url(f"/api/voice/gather/{call_id}", request)
    nxt = _url(f"/api/voice/twiml/{call_id}?end=1", request) if retry else _url(f"/api/voice/twiml/{call_id}?retry=1", request)
    return _xml(voice.twiml_question(script, gather, nxt, first=not retry))


@voice_router.post("/gather/{call_id}")
async def call_gather(call_id: str, background: BackgroundTasks, form: dict = Depends(twilio_form)) -> Response:
    """The vendor's spoken answer. Classified within the 3 s Claude cap, answered with a closing line and a hangup inside
    Twilio's 5 s, then applied in the background by verify.handle_outcome."""
    answer = (form.get("SpeechResult") or "").strip()
    with Session(db.engine) as s:
        call, payment, script = _context(s, call_id)
        if call.outcome is not None:  # Twilio retried, or the 60 s rule already ended the call
            return _xml(voice.twiml_close(script.closing(call.outcome.value)))
        outcome, evidence = await verify.classify_answer(answer)
        evidence = {**evidence, "confidence": form.get("Confidence")}
        transcript = await _record_lines(s, call, payment, [
            {"speaker": "agent", "text": script.question}, {"speaker": "vendor", "text": answer or "(no response)"},
            {"speaker": "agent", "text": script.closing(outcome.value)}])
    background.add_task(verify.handle_outcome, call_id, outcome, transcript, None, True, evidence)
    return _xml(voice.twiml_close(script.closing(outcome.value)))


@webhook_router.post("/status")
async def call_status(call_id: str, background: BackgroundTasks, form: dict = Depends(twilio_form)) -> dict:
    """Twilio's call status callback. A call nobody answered (no-answer, busy, failed, canceled) is a no_answer; other
    statuses are ignored (an answered call finishes through the gather route or the 60 s rule)."""
    status = (form.get("CallStatus") or "").lower()
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
    if cfg.mock_twilio or cfg.mock_cartesia:
        background.add_task(_run_mock_call, payment_id, answer)
        return {"payment_id": payment_id, "run_id": run_id, "mode": "mock", "status": "started"}
    try:
        result = await verify.start_verification(payment_id)
    except (verify.CallNotAllowed, voice.CallNotAllowedError):
        raise HTTPException(403, "number is not in ALLOWED_CALL_NUMBERS")
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(400, str(exc))
    return {"payment_id": payment_id, "run_id": run_id, "mode": "real", "status": "calling", "call_id": result.call_id}


router.include_router(voice_router)
router.include_router(webhook_router)
router.include_router(verification_router)
