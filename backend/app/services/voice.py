# Owner: Teammate B
# Prize track: Cartesia (voice of the call; Twilio carries it)
# Twilio is a NEW-STYLE FREE TRIAL: calls come from a shared number, the Calls API accepts only
#   to, from_, url and status_callback, and only Say, Play, Gather, Redirect, Pause and Hangup are
#   allowed. No recording and no Media Streams, so the stored transcript is the call record. The call therefore says it is
#   "being transcribed". Only with CALL_RECORDING_ENABLED (an account that can record) does place_call request recording and
#   the call say "recorded and transcribed"; see disclosure().
#   Twilio waits 5 s for our TwiML, so audio clips are generated BEFORE dialing (tts_clip).
# Flags: MOCK_TWILIO, MOCK_CARTESIA.

import asyncio
import hashlib
import hmac
import os
import secrets
import logging
import re
import time
import uuid
import wave
from pathlib import Path
from typing import Any, Optional

import httpx

from app.config import Settings, get_settings
from app.services import liveness

log = logging.getLogger("countersign.voice")

AUDIO_DIR = Path(__file__).resolve().parents[2] / ".audio_cache"
AUDIO_NAME_RE = re.compile(r"^[0-9a-f]{64}\.wav$")
SAMPLE_RATE = 16000  # telephone-quality mono keeps clips small so Twilio fetches them fast
CARTESIA_URL = "https://api.cartesia.ai/tts/bytes"
CARTESIA_VERSION = "2026-08-14"
CARTESIA_MODEL = "sonic-3.6"


PLACE_CALL_TIMEOUT_SECONDS = 15  # hard cap around the Twilio call create
HTTP_TIMEOUT_SECONDS = 10  # Twilio REST and Cartesia requests
WEB_RING_SECONDS = 60  # a softphone call nobody answers in this long is a no_answer
VENDOR_PHONE_FRESH_SECONDS = 60  # a softphone page that polled this recently counts as open


class CallNotAllowedError(Exception):
    pass


def log_state(call_id: str, state: str, **info: Any) -> None:
    """One line per call state change (placed, answered, re-asked, outcome, failover, finished). Ids and words only:
    never a token, a phone number or a URL."""
    extra = " ".join(f"{k}={v}" for k, v in info.items())
    log.info("call %s %s%s", call_id, state, f" {extra}" if extra else "")


# ---------------------------------------------------------------- voice mode and softphone key


def _env(name: str) -> str:
    """os.getenv first; otherwise the same key from .env (pydantic reads .env without filling os.environ). Only that key is read."""
    val = os.getenv(name)
    if val is not None:
        return val.strip()
    if "PYTEST_CURRENT_TEST" in os.environ:
        return ""  # tests set these through the environment; a developer's .env must not change their results
    try:
        from dotenv import dotenv_values

        for path in (".env", "../.env"):
            got = dotenv_values(path).get(name)
            if got:
                return got.strip()
    except Exception:  # noqa: BLE001
        pass
    return ""


def voice_mode() -> str:
    """"twilio" (default) or "web" (browser softphone, no phone network)."""
    return "web" if _env("VOICE_MODE").lower() == "web" else "twilio"


def vendor_phone_key_ok(k: Optional[str]) -> bool:
    key = _env("VENDOR_PHONE_KEY")
    return bool(key and k and hmac.compare_digest(key.encode(), k.encode()))


# ---------------------------------------------------------------- allow list


def normalize_e164(number: str) -> str:
    """'(415) 555-0142', '415.555.0142', '14155550142' and '+1 415 555 0142' all become '+14155550142'."""
    raw = (number or "").strip()
    digits = "".join(c for c in raw if c.isdigit())
    if raw.startswith("+"):
        return "+" + digits
    if len(digits) == 10:
        return "+1" + digits
    return "+" + digits if digits else ""


def assert_call_allowed(number: str, settings: Optional[Settings] = None) -> str:
    """Raise unless the normalized number is on ALLOWED_CALL_NUMBERS. Returns the normalized number.
    An empty allow list refuses everything. There is no mock-mode exemption."""
    s = settings or get_settings()
    normalized = normalize_e164(number)
    allowed = {normalize_e164(n) for n in s.allowed_call_numbers_list}
    if not normalized or normalized not in allowed:
        raise CallNotAllowedError("number is not in ALLOWED_CALL_NUMBERS")
    return normalized


# ---------------------------------------------------------------- Twilio


def _twilio_client(settings: Settings) -> Any:
    from twilio.http.http_client import TwilioHttpClient
    from twilio.rest import Client

    return Client(settings.twilio_account_sid, settings.twilio_auth_token, http_client=TwilioHttpClient(timeout=HTTP_TIMEOUT_SECONDS))


def _create_call(settings: Settings, kwargs: dict) -> str:
    return _twilio_client(settings).calls.create(**kwargs).sid


async def place_call(
    to_number: str,
    twiml_url: str,
    status_callback_url: Optional[str] = None,
    settings: Optional[Settings] = None,
) -> str:
    """Dial one call and return its sid. THE ONLY place a Twilio call is created.

    Trial accounts accept only to, from_, url and status_callback: no record, time_limit, machine
    detection or inline twiml.
    """
    s = settings or get_settings()
    to = assert_call_allowed(to_number, s)
    if s.mock_twilio:
        sid = "CAmock" + uuid.uuid4().hex[:26]
        log.info("mock call placed: %s", sid)
        return sid
    kwargs: dict = {"to": to, "from_": s.twilio_from_number, "url": twiml_url}
    if s.call_recording_enabled:
        kwargs["record"] = True  # the only place recording is requested, and the only case in which the call says "recorded"
    if status_callback_url:
        kwargs["status_callback"] = status_callback_url
    sid = await asyncio.wait_for(asyncio.to_thread(_create_call, s, kwargs), PLACE_CALL_TIMEOUT_SECONDS)
    liveness.mark("twilio")
    return sid


# ---------------------------------------------------------------- Cartesia text to speech


def audio_path(name: str) -> Optional[Path]:
    """Resolve a cached clip by name; None if the name is not exactly a hash plus .wav or the file is missing."""
    if not AUDIO_NAME_RE.match(name):
        return None
    path = AUDIO_DIR / name
    return path if path.is_file() else None


def _clip_name(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest() + ".wav"


def public_url(path: str, settings: Optional[Settings] = None) -> str:
    """THE one way a URL for Twilio is made: PUBLIC_BASE_URL plus a path, nothing from the incoming request (a proxy or a forwarded
    header can make a request's own URL say http or an internal host). Twilio only reaches an https address, so anything else is
    refused here, before a call is placed."""
    base = (settings or get_settings()).public_base_url.strip().rstrip("/")
    if not base.startswith("https://") or len(base) <= len("https://"):
        raise RuntimeError("PUBLIC_BASE_URL must be the public https address Twilio can reach (for example the ngrok https link)")
    if not path.startswith("/"):
        raise ValueError("a path starts with /")
    return base + path


def clip_url(text: str, settings: Optional[Settings] = None) -> str:
    return public_url(f"/api/voice/audio/{_clip_name(text)}", settings)


def _write_silent_wav(path: Path, seconds: float = 0.5) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(b"\x00\x00" * int(SAMPLE_RATE * seconds))


def _cartesia_wav(text: str, s: Settings) -> bytes:
    resp = httpx.post(
        CARTESIA_URL,
        headers={"Authorization": f"Bearer {s.cartesia_api_key}", "Cartesia-Version": CARTESIA_VERSION},
        json={
            "model_id": CARTESIA_MODEL,
            "transcript": text,
            "voice": {"id": s.cartesia_voice_id},
            "language": "en",
            "output_format": {"container": "wav", "encoding": "pcm_s16le", "sample_rate": SAMPLE_RATE},
        },
        timeout=HTTP_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    return resp.content


def _generate_clip(text: str, s: Settings) -> Path:
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    path = AUDIO_DIR / _clip_name(text)
    if path.exists():
        return path
    tmp = path.with_suffix(".tmp")
    if s.mock_cartesia:
        _write_silent_wav(tmp)
    else:
        tmp.write_bytes(_cartesia_wav(text, s))
        liveness.mark("cartesia")
    tmp.replace(path)
    return path


async def ensure_clip(text: str, seconds: float, settings: Optional[Settings] = None) -> bool:
    """Voice a line during the call (a conversational reply), within `seconds`. True if the clip is ready to play. On a timeout or
    an error the caller falls back to a scripted line, whose clip was made before dialing."""
    s = settings or get_settings()
    if audio_path(_clip_name(text)) is not None:
        return True
    try:
        await asyncio.wait_for(asyncio.to_thread(_generate_clip, text, s), seconds)
    except Exception:  # noqa: BLE001
        log.warning("in-call clip was late or failed; a scripted line is used instead")
        return False
    return audio_path(_clip_name(text)) is not None


async def tts_clip(text: str, settings: Optional[Settings] = None) -> str:
    """Generate (or reuse) a mono 16 kHz WAV for this text and return its public URL.

    Call this before dialing, never while Twilio is waiting on a TwiML response.
    """
    s = settings or get_settings()
    if not s.public_base_url:
        raise RuntimeError("PUBLIC_BASE_URL is not set; Twilio cannot fetch audio")
    await asyncio.to_thread(_generate_clip, text, s)
    return clip_url(text, s)


async def tts_file(text: str, settings: Optional[Settings] = None) -> Path:
    """Same as tts_clip but returns the local path (for smoke tests; needs no PUBLIC_BASE_URL)."""
    return await asyncio.to_thread(_generate_clip, text, settings or get_settings())


# ---------------------------------------------------------------- the verification call script and its TwiML

# Rules of the call (CLAUDE.md): say it is automated, only the last 4 digits of an account, accept no new details,
# never confirm on the vendor's behalf. California needs all-party consent, so the intro discloses what is true: transcribed, and
# recorded only when recording is on.

COMPANY_NAME = "Ridgeline Builders"


def disclosure(settings: Optional[Settings] = None) -> str:
    """What the call may truthfully say about itself. "Recorded" appears only when place_call requests recording."""
    s = settings or get_settings()
    return "This call is being recorded and transcribed." if s.call_recording_enabled else "This call is being transcribed."


def call_intro(company: str = COMPANY_NAME, settings: Optional[Settings] = None) -> str:
    return f"This is an automated assistant calling for {company} accounts payable. {disclosure(settings)}"



class CallScript:
    """Every sentence the verification call can speak. All of them are generated as clips before dialing.

    Talking over the agent: the intro, the disclosure and the question always play in full, because Twilio is not listening
    while they play. Listening starts on `listen`, a short cue the vendor may talk over (anything said then is an answer).
    "Hello?", "Who is this?" or "Sorry, what?" is not an answer: the agent says who it is if asked and repeats the question
    (`repeat`, `repeat_who`), without using up the one re-ask."""

    def __init__(self, vendor_name: str, last4: str) -> None:
        self.vendor_name, self.last4 = vendor_name, last4  # the facts the conversational replies may use (services/conversation.py)
        self.intro = call_intro()
        ask = (f"We received a request to change where we send {vendor_name}'s payments, to an account ending {last4}. "
               "Did your company make this change?")
        self.question = ask
        self.listen = "A simple yes or no is all I need."
        self.retry = "Sorry, I didn't quite catch that. Did your company ask us to change its bank account?"
        self.clarify = f"Thanks. Just so I record it correctly: did your company ask us to send payments to a new account ending {last4}?"
        self.repeat = f"Sure. {ask}"
        self.repeat_who = f"This is an automated assistant for {COMPANY_NAME} accounts payable, calling about {vendor_name}'s bank account. {ask}"
        self.confirm_again = f"Just to confirm: did your company ask us to change {vendor_name}'s bank account to the one ending {last4}?"
        self.hold = "Of course, take your time."
        self.confirmed = "Thank you, that's very helpful. I've noted your answer for our accounts payable team. Have a good day."
        self.denied = "Thank you for letting us know. We will not make that change, and our controller has been alerted. Have a good day."
        self.unclear = "Thanks for your time. Someone from our accounts payable team will follow up with you. Goodbye."

    def all_texts(self) -> list[str]:
        return [self.intro, self.question, self.listen, self.retry, self.clarify, self.repeat, self.repeat_who, self.confirm_again,
                self.hold, self.confirmed, self.denied, self.unclear]

    def closing(self, outcome: str) -> str:
        return {"confirmed": self.confirmed, "denied": self.denied}.get(outcome, self.unclear)


_HOLD_RE = re.compile(r"\b(hold on|hold up|one moment|one sec|just a (moment|minute|sec|second)|hang on|wait|give me a (moment|minute|second))\b")


def is_hold(text: str) -> bool:
    return bool(_HOLD_RE.search((text or "").lower().replace("\u2019", "'")))


# Not an answer: a greeting, a question about who is calling, or a request to hear it again. Checked before any yes or no, so a
# "Yes? Who is this?" over the question can never confirm a bank change.
_WHO_RE = re.compile(r"\b(who('s| is| are)? (this|calling|you)|who am i speaking|what (company|is this|'s this)|where are you calling from|what is this (about|regarding)|what's this (about|regarding))\b")
_REPEAT_RE = re.compile(r"\b(repeat|say (that|it) again|come again|pardon|didn't (hear|catch)|did not (hear|catch)|can't hear|cannot hear|what did you say|sorry what|excuse me)\b|^\W*(what|sorry|huh|hello|hi|hey)\W*$|^\W*(hello|hi|hey)\b")
MAX_REPEATS = 2  # repeats of the question per call, on top of the one re-ask; the 60 s rule still ends the call


def interjection(text: str) -> Optional[str]:
    """'who' (asked who is calling), 'repeat' (a greeting or did not hear), or None (it may be an answer)."""
    s = " ".join(re.sub(r"[^\w' ]+", " ", (text or "").lower().replace("\u2019", "'")).split())  # punctuation is speech-engine noise
    if not s:
        return None
    if _WHO_RE.search(s):
        return "who"
    if _REPEAT_RE.search(s) and not re.search(r"\b(no|never|not|didn't|did not|we did|changed|correct|that's right|that is right)\b", s):
        return "repeat"
    return None


# A "yes" this unsure is asked once more before it can confirm a bank change (a confirmed call writes a verified account).
# Our real one-word "Yes." came back at 0.67.
MIN_CONFIRM_CONFIDENCE = 0.45


def decide(answer: str, outcome: str, reasked: bool, repeats: int = 0, confidence: Optional[float] = None) -> str:
    """What the call does with an answer, the same in both modes. "close" ends it with `outcome`; "hold" plays the wait clip
    and listens again; "reask" plays the clarifying (or confirm-again) clip once; "repeat" says who is calling if asked and asks
    the question again, up to MAX_REPEATS times, without using the re-ask. An empty answer never re-asks (silence already had
    its own retry)."""
    text = (answer or "").strip()
    if not text:
        return "close"
    if interjection(text) and repeats < MAX_REPEATS:
        return "repeat"
    if reasked:
        return "close"
    if is_hold(text):
        return "hold"
    if outcome == "confirmed" and confidence is not None and confidence < MIN_CONFIRM_CONFIDENCE:
        return "reask"
    return "reask" if outcome == "unclear" else "close"


def call_script(vendor_name: str, last4: str) -> CallScript:
    return CallScript(vendor_name, last4[-4:])


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _speak(text: str, settings: Optional[Settings] = None) -> str:
    """<Play> of the pre-generated clip, or <Say> if the clip file is missing (so a call is never silent). Never generates audio."""
    if audio_path(_clip_name(text)) is not None:
        return f"<Play>{_esc(clip_url(text, settings))}</Play>"
    return f"<Say>{_esc(text)}</Say>"


def _twiml(body: str) -> str:
    return f'<?xml version="1.0" encoding="UTF-8"?><Response>{body}</Response>'


# How long Twilio waits for the vendor to START talking once the question has finished. A person needs a moment after a question,
# and a phone line adds more: 6 s was short. speechTimeout="auto" ends the answer by itself when they stop. The worst case for a call
# (intro, question, 10 s of silence, retry, 10 s of silence, closing line) stays well inside the 60 second rule.
GATHER_TIMEOUT_SECONDS = 10
# Words a phone speech model should expect: short answers like "yes" and "no" are the hardest to catch without them.
GATHER_HINTS = "yes, no, yeah, nope, correct, that is right, we did, we did not, we never changed banks, I don't know"


def _listen(script: CallScript, gather_url: str, timeout: int, settings: Optional[Settings] = None, cue: bool = True) -> str:
    """The listening window: a speech Gather around the short cue. Talking over the cue is fine: whatever is said is the answer."""
    return (
        f'<Gather input="speech" speechTimeout="auto" timeout="{timeout}" speechModel="phone_call" language="en-US" hints="{_esc(GATHER_HINTS)}" '
        f'action="{_esc(gather_url)}" method="POST">'
        f"{_speak(script.listen, settings) if cue else ''}</Gather>"
    )


def twiml_question(script: CallScript, gather_url: str, retry_url: str, settings: Optional[Settings] = None, first: bool = True) -> str:
    """Intro (first pass only) and the question (or the retry prompt), played in full with Twilio not listening, so talking over
    them cannot cut them off or be taken as the answer. Then the listening window. Silence redirects to retry_url."""
    prompt = script.question if first else script.retry
    return _twiml((_speak(script.intro, settings) if first else "") + _speak(prompt, settings)
                  + _listen(script, gather_url, GATHER_TIMEOUT_SECONDS, settings) + f'<Redirect method="POST">{_esc(retry_url)}</Redirect>')


def twiml_regather(script: CallScript, text: str, gather_url: str, end_url: str, settings: Optional[Settings] = None,
                   hold: bool = False, cue: Optional[bool] = None) -> str:
    """Say `text` in full (a repeat of the question, a conversational reply, the clarifying or confirm-again line, or the hold
    line), then listen again. After a hold the window opens without the cue and waits longer, so a vendor finding their notes is
    not prompted; a conversational reply already ends by asking, so it needs no cue either. Silence goes to end_url."""
    hold = hold or text == script.hold
    cue = (not hold) if cue is None else cue
    return _twiml(_speak(text, settings) + _listen(script, gather_url, GATHER_TIMEOUT_SECONDS if hold else 8, settings, cue=cue)
                  + f'<Redirect method="POST">{_esc(end_url)}</Redirect>')


def twiml_close(text: str, settings: Optional[Settings] = None) -> str:
    return _twiml(f"{_speak(text, settings)}<Hangup/>")


# ---------------------------------------------------------------- per-call webhook secret
# Trial calls fetch our TwiML through a Twilio proxy that sends no X-Twilio-Signature, so a signature cannot protect
# those routes. Each call gets a random secret instead. It lives in a file (not the database, so no model change and it
# survives a restart), is carried in the webhook URLs as ?t=..., and is compared in constant time. It is never logged.

TOKEN_RE = re.compile(r"^cal_[0-9A-Za-z]{1,32}$")  # no slashes or dots: the id is part of a file name


def _token_path(call_id: str) -> Optional[Path]:
    return (AUDIO_DIR / "tokens" / f"{call_id}.token") if TOKEN_RE.match(call_id or "") else None


def new_call_token(call_id: str) -> str:
    path = _token_path(call_id)
    if path is None:
        raise ValueError("not a call id")
    path.parent.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(24)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(token)
    return token


def check_call_token(call_id: str, token: Optional[str]) -> bool:
    path = _token_path(call_id)
    if path is None or not token or not path.is_file():
        return False
    return hmac.compare_digest(path.read_text().strip().encode(), token.encode())


def with_token(url: str, token: str) -> str:
    return f"{url}{'&' if '?' in url else '?'}t={token}"


_TOKEN_IN_URL = re.compile(r"([?&]t=|/api/webhooks/twilio/status/[A-Za-z0-9_]+/)[A-Za-z0-9_\-]+")


class RedactCallToken(logging.Filter):
    """Keeps the per-call secret out of uvicorn's access log lines."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = _TOKEN_IN_URL.sub(r"\1***", str(record.msg))
        if isinstance(record.args, tuple):
            record.args = tuple(_TOKEN_IN_URL.sub(r"\1***", a) if isinstance(a, str) else a for a in record.args)
        return True


logging.getLogger("uvicorn.access").addFilter(RedactCallToken())


# ---------------------------------------------------------------- browser softphone registry
# In-memory on purpose: a softphone call lives for under two minutes and a restart ends it as no_answer anyway.

web_calls: dict[str, dict] = {}  # call_id -> {vendor_id, vendor_name, token, clips, texts, reasked, answered, created}
_last_poll: dict[str, float] = {}  # vendor_id -> time.monotonic() of the page's last poll


def register_web_call(call_id: str, vendor_id: str, vendor_name: str, token: str, script: CallScript, settings: Optional[Settings] = None) -> None:
    texts = {"intro": script.intro, "question": script.question, "listen": script.listen, "clarify": script.clarify, "hold": script.hold,
             "repeat": script.repeat, "repeat_who": script.repeat_who, "confirm_again": script.confirm_again,
             "confirmed": script.confirmed, "denied": script.denied, "unclear": script.unclear}
    web_calls[call_id] = {"vendor_id": vendor_id, "vendor_name": vendor_name, "token": token, "texts": texts,
                          "clips": {k: clip_url(v, settings) for k, v in texts.items()}, "reasked": False, "answered": False,
                          "created": time.monotonic()}


def note_poll(vendor_id: str) -> None:
    _last_poll[vendor_id] = time.monotonic()


def vendor_phone_recent(vendor_id: str) -> bool:
    t = _last_poll.get(vendor_id)
    return t is not None and time.monotonic() - t <= VENDOR_PHONE_FRESH_SECONDS


def pending_for(vendor_id: str) -> Optional[tuple[str, dict]]:
    """The oldest web call for this vendor that has not been answered yet."""
    waiting = [(cid, c) for cid, c in web_calls.items() if c["vendor_id"] == vendor_id and not c["answered"]]
    return min(waiting, key=lambda kv: kv[1]["created"], default=None)
