"""The vendor talks over the agent. The question always plays in full before Twilio listens; a greeting or "who is this" is not
an answer (the question is repeated, the one re-ask is kept); a "yes" heard with low confidence is asked once more before it can
confirm a bank change."""

import re
from urllib.parse import parse_qs, urlparse
from xml.etree import ElementTree

import pytest

from app.models import CallOutcome, PaymentStatus
from app.services import voice
from tests.test_integrations import _answer, _call_row, _web_state, fdb, web  # noqa: F401  (fdb and web are fixtures)


def gather(client, speech, r=0, n=0, confidence=None):
    data = {"SpeechResult": speech}
    if confidence is not None:
        data["Confidence"] = str(confidence)
    return client.post(f"/api/voice/gather/cal_t?r={r}&n={n}", data=data).text


def next_gather(twiml: str) -> dict:
    """The r and n the agent will listen with next, from the Gather action in the reply."""
    g = next(ElementTree.fromstring(twiml).iter("Gather"))
    q = parse_qs(urlparse(g.attrib["action"]).query)
    return {"r": int(q.get("r", ["0"])[0]), "n": int(q.get("n", ["0"])[0])}


@pytest.mark.parametrize("speech,kind", [
    ("Hello?", "repeat"), ("hi", "repeat"), ("Sorry, what?", "repeat"), ("Can you repeat that?", "repeat"), ("Excuse me?", "repeat"),
    ("Hello? Who is this?", "who"), ("Yes? Who is this?", "who"), ("who's calling", "who"), ("What is this about?", "who"),
    ("Yes.", None), ("yeah", None), ("No, we never changed banks.", None), ("Hello, yes we did", None), ("we did not", None),
])
def test_what_counts_as_an_interjection(speech, kind):
    assert voice.interjection(speech) == kind


def test_the_question_plays_in_full_before_twilio_listens():
    s = voice.call_script("Summit Concrete", "6213")
    root = ElementTree.fromstring(voice.twiml_question(s, "https://x/g", "https://x/r"))
    # No clips in this test, so each line is a <Say> with its text: intro, then the whole question, outside any Gather.
    assert [c.tag for c in root] == ["Say", "Say", "Gather", "Redirect"]
    assert root[0].text == s.intro and root[1].text.replace("&#x27;", "'") == s.question
    g = next(root.iter("Gather"))
    assert [c.text for c in g] == [s.listen]  # only the short cue can be talked over


def test_a_greeting_over_the_question_is_never_a_confirmation(fdb):
    client, eng = fdb
    reply = gather(client, "Yes? Who is this?")
    assert "automated assistant for Ridgeline Builders" in reply and "Did your company make this change?" in reply  # who, then the question
    assert "<Hangup/>" not in reply and next_gather(reply) == {"r": 0, "n": 1}  # the re-ask is not used up
    call, pay = _call_row(eng)
    assert call.outcome is None and pay.status == PaymentStatus.held


def test_after_a_repeat_a_real_no_is_denied_and_the_question_is_in_the_transcript_once(fdb):
    client, eng = fdb
    gather(client, "Hello?")
    final = gather(client, "No, we never changed banks", n=1)
    assert final.endswith("<Hangup/></Response>")
    call, pay = _call_row(eng)
    assert call.outcome == CallOutcome.denied and pay.status == PaymentStatus.blocked
    agent_lines = [l["text"] for l in call.transcript if l["speaker"] == "agent"]
    assert sum("Did your company make this change?" in t and not t.startswith(("Sure.", "This is an automated")) for t in agent_lines) == 1


def test_repeats_are_capped_then_an_interjection_is_treated_as_unclear(fdb):
    client, eng = fdb
    reply = gather(client, "Hello?", n=voice.MAX_REPEATS)
    assert "<Hangup/>" not in reply and next_gather(reply)["r"] == 1  # the cap is reached: the one clarifying re-ask
    final = gather(client, "hello?", r=1, n=voice.MAX_REPEATS)
    assert final.endswith("<Hangup/></Response>")
    assert _call_row(eng)[0].outcome == CallOutcome.unclear


def test_an_unsure_yes_is_asked_once_more_before_it_confirms(fdb):
    client, eng = fdb
    reply = gather(client, "Yes", confidence=0.3)
    assert "Just to confirm" in reply
    assert next_gather(reply)["r"] == 1 and _call_row(eng)[0].outcome is None
    final = gather(client, "Yes, we did", r=1, confidence=0.9)
    assert final.endswith("<Hangup/></Response>")
    assert _call_row(eng)[0].outcome == CallOutcome.confirmed


def test_a_clear_yes_confirms_at_once(fdb):
    client, eng = fdb
    assert gather(client, "Yes, we did", confidence=0.67).endswith("<Hangup/></Response>")  # our real call's confidence
    assert _call_row(eng)[0].outcome == CallOutcome.confirmed


def test_the_softphone_repeats_without_using_the_re_ask(web):
    client, eng, res = web
    first = _answer(client, res, "Hello? Who is this?").json()
    assert first["action"] == "repeat" and not first["final"] and re.search(r"/api/voice/audio/[0-9a-f]{64}\.wav$", first["clip"])
    entry = voice.web_calls[res.call_id]
    assert entry["reasked"] is False and entry["repeats"] == 1
    second = _answer(client, res, "No", entry["token"]).json()
    assert second["final"] and second["outcome"] == "denied"
    assert _web_state(eng, res.call_id)[0].outcome == CallOutcome.denied


def test_the_question_is_on_the_board_from_pickup_and_never_twice(fdb):
    client, eng = fdb
    client.post("/api/voice/twiml/cal_t")  # the vendor picks up
    call, _ = _call_row(eng)
    s = voice.call_script("x", "0000")
    assert [l["speaker"] for l in call.transcript] == ["agent"] and call.transcript[0]["text"].endswith("Did your company make this change?")
    client.post("/api/voice/twiml/cal_t")  # Twilio fetches it again: still once
    gather(client, "No, we never changed banks")
    call, _ = _call_row(eng)
    asks = [l for l in call.transcript if l["speaker"] == "agent" and l["text"].endswith("Did your company make this change?")]
    assert len(asks) == 1 and [l["speaker"] for l in call.transcript] == ["agent", "vendor", "agent"]
