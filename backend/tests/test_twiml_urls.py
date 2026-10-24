"""Every URL Twilio is given is under PUBLIC_BASE_URL over https, never taken from the incoming request, and the call token works
for every callback of the call. Twilio trial calls use a proxy, a tunnel and a forwarded host: none of that may leak into a URL."""

import re
from urllib.parse import urlparse
from xml.etree import ElementTree

import pytest
from sqlmodel import Session, select

from app.config import get_settings
from app.models import VendorContact
from app.services import verify, voice
from tests.test_attacks import CLASSIC, wait
from tests.test_run import env  # noqa: F401  (env is a fixture: a private seeded database + client)

BASE = "https://pub.example"
ON_FILE = "+14155550142"  # Summit's number in tests (DEMO_VENDOR_PHONE)
HOSTILE = {"Host": "internal.local:8000", "X-Forwarded-Proto": "http", "X-Forwarded-Host": "evil.example", "Forwarded": "for=1.2.3.4;host=evil.example;proto=http"}


@pytest.fixture
def call(env, monkeypatch, tmp_path):
    """A real-mode verification call placed with the network faked. Returns what Twilio would have been given."""
    client, eng = env
    cfg = get_settings()
    monkeypatch.setattr(voice, "AUDIO_DIR", tmp_path / "audio")
    monkeypatch.setattr(cfg, "mock_twilio", False)
    monkeypatch.setattr(cfg, "mock_cartesia", False)
    monkeypatch.setattr(cfg, "public_base_url", BASE)
    monkeypatch.setattr(cfg, "allowed_call_numbers", ON_FILE)
    monkeypatch.setattr(verify, "arm_answer_watchdog", lambda call_id: None)  # no 60 second timer outliving the test
    given: dict = {}

    async def fake_place(to, url, status_callback=None, settings=None):
        given.update(to=to, twiml_url=url, status_callback=status_callback)
        return "CAtest"

    async def fake_clip(text, settings=None):
        voice._generate_clip(text, cfg.model_copy(update={"mock_cartesia": True}))  # a silent clip on disk, so the TwiML uses Play as a real call does
        return voice.clip_url(text, settings)

    monkeypatch.setattr(voice, "place_call", fake_place)
    monkeypatch.setattr(voice, "tts_clip", fake_clip)
    a = client.post("/api/attacks", json=CLASSIC).json()
    wait(client, a["run_id"])
    given["call_id"] = given["twiml_url"].split("/api/voice/twiml/")[1].split("?")[0]
    given["token"] = voice._token_path(given["call_id"]).read_text().strip()
    return client, eng, given


def path_of(url: str) -> str:
    p = urlparse(url)
    return p.path + (f"?{p.query}" if p.query else "")


def urls_in(xml: str) -> list[str]:
    """Every URL in a TwiML document: Play and Redirect text, and Gather's action."""
    root = ElementTree.fromstring(xml)
    out = [e.text.strip() for e in root.iter() if e.tag in ("Play", "Redirect") and e.text]
    out += [e.attrib["action"] for e in root.iter("Gather") if "action" in e.attrib]
    return out


def under_base(url: str) -> bool:
    return url.startswith(BASE + "/") and urlparse(url).scheme == "https" and urlparse(url).netloc == "pub.example"


def test_the_urls_given_to_twilio_when_the_call_is_placed_are_under_public_base_url(call):
    _, _, given = call
    assert under_base(given["twiml_url"]) and under_base(given["status_callback"])
    assert given["twiml_url"].endswith(f"?t={given['token']}") and given["status_callback"].endswith(f"&t={given['token']}")
    assert given["to"] == ON_FILE


def test_the_question_twiml_has_only_urls_under_public_base_url_even_from_a_hostile_request(call):
    client, _, given = call
    for hdrs in ({}, HOSTILE):
        r = client.post(path_of(given["twiml_url"]), headers=hdrs)
        assert r.status_code == 200 and r.headers["content-type"].startswith("application/xml")
        urls = urls_in(r.text)
        assert len(urls) == 4  # intro clip, Gather action, question clip, Redirect
        assert all(under_base(u) for u in urls), urls
        assert "evil.example" not in r.text and "internal.local" not in r.text and "http://" not in r.text


def test_the_retry_twiml_and_every_url_it_gives_are_under_public_base_url(call):
    client, _, given = call
    first = client.post(path_of(given["twiml_url"]), headers=HOSTILE).text
    retry_url = [u for u in urls_in(first) if "retry=1" in u][0]
    r = client.post(path_of(retry_url), headers=HOSTILE)
    assert r.status_code == 200 and all(under_base(u) for u in urls_in(r.text)), r.text
    end_url = [u for u in urls_in(r.text) if "end=1" in u][0]
    assert "retry=1" not in end_url and under_base(end_url)


def test_the_call_token_is_not_consumed_every_callback_of_the_call_is_accepted(call, monkeypatch):
    client, eng, given = call
    first = client.post(path_of(given["twiml_url"]))
    assert first.status_code == 200
    again = client.post(path_of(given["twiml_url"]))  # Twilio retries a fetch, or the same URL is fetched twice
    assert again.status_code == 200
    gather_url = [e.attrib["action"] for e in ElementTree.fromstring(first.text).iter("Gather")][0]
    retry_url = [u for u in urls_in(first.text) if "retry=1" in u][0]
    assert client.post(path_of(retry_url)).status_code == 200  # the redirect to the retry carries the token
    assert client.post(path_of(given["status_callback"])).status_code == 200  # status callback
    assert client.post(path_of(given["status_callback"]), data={"CallStatus": "completed"}).status_code == 200
    answered = client.post(path_of(gather_url), data={"SpeechResult": "No, we never changed banks."})  # the spoken answer, after all of the above
    assert answered.status_code == 200 and "Hangup" in answered.text
    assert client.post(path_of(gather_url), data={"SpeechResult": "No."}).status_code == 200  # Twilio retrying the same answer is fine too
    assert client.post(path_of(given["status_callback"]), data={"CallStatus": "completed"}).status_code == 200  # and the final status after the call
    assert voice.check_call_token(given["call_id"], given["token"])  # still valid


def test_a_missing_or_wrong_token_is_refused_on_every_route(call):
    client, _, given = call
    cid = given["call_id"]
    for path in (f"/api/voice/twiml/{cid}", f"/api/voice/gather/{cid}", f"/api/webhooks/twilio/status?call_id={cid}"):
        assert client.post(path).status_code == 403
        sep = "&" if "?" in path else "?"
        assert client.post(f"{path}{sep}t=wrong").status_code == 403


def test_the_gather_listens_for_speech_long_enough_and_posts_to_our_answer_route(call):
    client, _, given = call
    root = ElementTree.fromstring(client.post(path_of(given["twiml_url"])).text)
    g = next(root.iter("Gather"))
    assert g.attrib["input"] == "speech" and g.attrib["method"] == "POST" and g.attrib["speechTimeout"] == "auto"
    assert int(g.attrib["timeout"]) >= 10  # seconds of waiting for the vendor to start talking, after the question
    assert g.attrib["speechModel"] == "phone_call" and "yes" in g.attrib["hints"] and "no" in g.attrib["hints"]
    assert urlparse(g.attrib["action"]).path == f"/api/voice/gather/{given['call_id']}"
    assert [c.tag for c in root] == ["Play", "Gather", "Redirect"]  # silence falls through to the retry
    assert next(g.iter("Play")).text.startswith(BASE + "/api/voice/audio/")  # the question plays inside the Gather: speech is heard while it plays


def test_the_worst_case_call_stays_inside_the_60_second_rule(call):
    from app.services.voice import GATHER_TIMEOUT_SECONDS, call_script

    s = call_script("Summit Concrete", "6213")
    seconds = lambda text: len(text.split()) / 2.6  # a generous speaking rate for the synthesized voice
    worst = seconds(s.intro) + seconds(s.question) + GATHER_TIMEOUT_SECONDS + seconds(s.retry) + GATHER_TIMEOUT_SECONDS + seconds(s.unclear)
    assert worst < 60, worst


def test_public_url_refuses_anything_but_https_and_never_reads_a_request(monkeypatch):
    cfg = get_settings()
    for bad in ("", "http://pub.example", "pub.example", "https://"):
        monkeypatch.setattr(cfg, "public_base_url", bad)
        with pytest.raises(RuntimeError):
            voice.public_url("/api/voice/twiml/cal_x")
    monkeypatch.setattr(cfg, "public_base_url", " https://pub.example/ ")  # a stray space or slash in .env is tolerated
    assert voice.public_url("/a") == "https://pub.example/a"
    with pytest.raises(ValueError):
        voice.public_url("no-leading-slash")


def test_no_voice_code_builds_a_url_from_the_incoming_request():
    from pathlib import Path

    for f in ("app/integrations.py", "app/services/voice.py", "app/services/verify.py"):
        text = Path(f).read_text()
        assert not re.search(r"request\.base_url|\.url_for\(|X-Forwarded|request\.headers\[.host", text, re.I), f
        for m in re.finditer(r"request\.url\b[^\n]*", text):  # the path of the request, for a log line or the signature check, is fine
            assert "request.url.path" in m.group(0) or "request.url.query" in m.group(0), (f, m.group(0))
