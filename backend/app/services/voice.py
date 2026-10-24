# Owner: Teammate B
# Prize track: Cartesia (voice of the call; Twilio carries it)
# Twilio is a NEW-STYLE FREE TRIAL: calls come from a shared number, the Calls API accepts only
#   to, from_, url and status_callback, and only Say, Play, Gather, Redirect, Pause and Hangup are
#   allowed. No recording and no Media Streams, so the stored transcript is the call record.
#   Twilio waits 5 s for our TwiML, so audio clips are generated BEFORE dialing (tts_clip).
# Flags: MOCK_TWILIO, MOCK_CARTESIA.

import asyncio
import hashlib
import logging
import re
import uuid
import wave
from pathlib import Path
from typing import Any, Optional

import httpx

from app.config import Settings, get_settings

log = logging.getLogger("countersign.voice")

AUDIO_DIR = Path(__file__).resolve().parents[2] / ".audio_cache"
AUDIO_NAME_RE = re.compile(r"^[0-9a-f]{64}\.wav$")
SAMPLE_RATE = 16000  # telephone-quality mono keeps clips small so Twilio fetches them fast
CARTESIA_URL = "https://api.cartesia.ai/tts/bytes"
CARTESIA_VERSION = "2026-08-14"
CARTESIA_MODEL = "sonic-3.6"


class CallNotAllowedError(Exception):
    pass


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
    from twilio.rest import Client

    return Client(settings.twilio_account_sid, settings.twilio_auth_token)


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
    if status_callback_url:
        kwargs["status_callback"] = status_callback_url
    return await asyncio.to_thread(_create_call, s, kwargs)


# ---------------------------------------------------------------- Cartesia text to speech


def audio_path(name: str) -> Optional[Path]:
    """Resolve a cached clip by name; None if the name is not exactly a hash plus .wav or the file is missing."""
    if not AUDIO_NAME_RE.match(name):
        return None
    path = AUDIO_DIR / name
    return path if path.is_file() else None


def _clip_name(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest() + ".wav"


def clip_url(text: str, settings: Optional[Settings] = None) -> str:
    s = settings or get_settings()
    return f"{s.public_base_url.rstrip('/')}/api/voice/audio/{_clip_name(text)}"


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
        timeout=30,
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
    tmp.replace(path)
    return path


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
