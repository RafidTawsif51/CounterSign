"""Teammate B's router: voice audio and the Twilio smoke TwiML, plus integration_status() for
/api/system/status. Same pattern as dev.py."""

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response

from app.config import get_settings
from app.services import voice

router = APIRouter(prefix="/voice")

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


@router.get("/audio/{name}")
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


@router.get("/smoke-twiml")
def smoke_twiml_get() -> Response:
    return _smoke_twiml()


@router.post("/smoke-twiml")
def smoke_twiml_post() -> Response:
    return _smoke_twiml()
