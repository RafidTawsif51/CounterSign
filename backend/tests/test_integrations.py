import asyncio
import re
import wave

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from app.config import get_settings
from app import db
from app.db import create_all
from app.models import (
    AuditLog,
    Event,
    Invoice,
    Payment,
    PaymentRun,
    PaymentStatus,
    Vendor,
    VendorBankAccount,
    utcnow,
)
from app.services import contacts, payments, verify, voice

create_all()


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def session():
    engine = create_engine("sqlite://")  # in memory
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


@pytest.fixture
def allowed(monkeypatch):
    monkeypatch.setattr(get_settings(), "allowed_call_numbers", "+14155550142, (628) 555-0199")


def world(session, onboarding=True):
    """A vendor with an optional onboarding account, one invoice and one pending payment."""
    session.add(Vendor(id="ven_t", name="Test Co", trade="x", email_domain="test.example"))
    if onboarding:
        session.add(VendorBankAccount(id="bac_t_1", vendor_id="ven_t", routing_hash="r1", account_last4="1111",
                                      bank_name="B", valid_from=utcnow().replace(year=2024)))
    session.add(PaymentRun(id="run_t"))
    session.add(Invoice(id="inv_t", vendor_id="ven_t", amount_usd=100.0))
    session.commit()


def pending(session, dest):
    session.add(Payment(id="pay_t", run_id="run_t", invoice_id="inv_t", amount_usd=100.0,
                        destination_account_id=dest, status=PaymentStatus.pending))
    session.commit()


# ---------------------------------------------------------------- allow list


@pytest.mark.parametrize("n", ["+14155550142", "(415) 555-0142", "415-555-0142", "14155550142", "+1 415 555 0142"])
def test_allow_list_accepts_other_formats(allowed, n):
    assert voice.assert_call_allowed(n) == "+14155550142"
    assert voice.assert_call_allowed("628.555.0199") == "+16285550199"


@pytest.mark.parametrize("n", ["+14155550143", "", "abc", "+19995550000"])
def test_allow_list_refuses_unknown(allowed, n):
    with pytest.raises(voice.CallNotAllowedError):
        voice.assert_call_allowed(n)


def test_empty_allow_list_refuses_everything(monkeypatch):
    monkeypatch.setattr(get_settings(), "allowed_call_numbers", "")
    with pytest.raises(voice.CallNotAllowedError):
        voice.assert_call_allowed("+14155550142")


# ---------------------------------------------------------------- place_call


def test_place_call_sends_only_trial_parameters(allowed, monkeypatch):
    sent = []
    monkeypatch.setattr(voice, "_create_call", lambda s, kwargs: sent.append(kwargs) or "CAreal")
    s = get_settings().model_copy(update={"mock_twilio": False, "twilio_from_number": "+15005550006"})
    assert run(voice.place_call("(415) 555-0142", "https://x/y", "https://x/cb", settings=s)) == "CAreal"
    run(voice.place_call("+14155550142", "https://x/y", settings=s))
    for kwargs in sent:
        assert set(kwargs) <= {"to", "from_", "url", "status_callback"}
    assert set(sent[0]) == {"to", "from_", "url", "status_callback"} and set(sent[1]) == {"to", "from_", "url"}


def test_recording_is_requested_only_when_enabled_and_only_then_does_the_call_say_recorded(allowed, monkeypatch):
    sent = []
    monkeypatch.setattr(voice, "_create_call", lambda s, kwargs: sent.append(kwargs) or "CAreal")
    off = get_settings().model_copy(update={"mock_twilio": False, "twilio_from_number": "+15005550006", "call_recording_enabled": False})
    on = off.model_copy(update={"call_recording_enabled": True})
    run(voice.place_call("+14155550142", "https://x/y", settings=off))
    run(voice.place_call("+14155550142", "https://x/y", settings=on))
    assert "record" not in sent[0] and sent[1]["record"] is True
    assert voice.disclosure(off) == "This call is being transcribed."
    assert voice.call_intro(settings=on) == "This is an automated assistant calling for Ridgeline Builders accounts payable. This call is being recorded and transcribed."
    assert voice.call_script("Acme", "1234").intro == voice.call_intro()  # the real call, the mock call and the dev mock-run share this line
    assert get_settings().call_recording_enabled is False  # default


def test_place_call_refuses_before_dialing(allowed, monkeypatch):
    sent = []
    monkeypatch.setattr(voice, "_create_call", lambda s, kwargs: sent.append(kwargs) or "CAreal")
    s = get_settings().model_copy(update={"mock_twilio": False})
    with pytest.raises(voice.CallNotAllowedError):
        run(voice.place_call("+14155559999", "https://x/y", settings=s))
    assert sent == []


def test_place_call_mock_returns_fake_sid(allowed):
    assert run(voice.place_call("+14155550142", "https://x/y")).startswith("CAmock")


def test_tts_clip_mock_writes_small_mono_wav_and_caches(monkeypatch, tmp_path):
    monkeypatch.setattr(voice, "AUDIO_DIR", tmp_path)
    s = get_settings().model_copy(update={"public_base_url": "https://pub.example/"})
    url = run(voice.tts_clip("hello there", s))
    assert url == f"https://pub.example/api/voice/audio/{voice._clip_name('hello there')}"
    path = tmp_path / voice._clip_name("hello there")
    with wave.open(str(path)) as w:
        assert w.getnchannels() == 1 and w.getframerate() in (8000, 16000)
    mtime = path.stat().st_mtime_ns
    run(voice.tts_clip("hello there", s))
    assert path.stat().st_mtime_ns == mtime
    assert voice.audio_path("../../etc/passwd") is None


# ---------------------------------------------------------------- verified account


def test_current_verified_account_prefers_latest_verified(session):
    world(session)
    assert verify.current_verified_account(session, "ven_t").id == "bac_t_1"
    session.add(VendorBankAccount(id="bac_t_2", vendor_id="ven_t", routing_hash="r2", account_last4="2222",
                                  bank_name="B", valid_from=utcnow(), verified_by_call_id="cal_x"))
    session.commit()
    assert verify.current_verified_account(session, "ven_t").id == "bac_t_2"


def test_requested_destination_is_unverified_and_not_trusted(session):
    world(session)
    new_id = verify.record_requested_destination(session, "ven_t", "r9", "9999", "Evil Bank")
    acct = session.get(VendorBankAccount, new_id)
    assert acct.verified_by_call_id is None
    assert verify.record_requested_destination(session, "ven_t", "r9", "9999", "Evil Bank") == new_id
    assert verify.current_verified_account(session, "ven_t").id == "bac_t_1"
    assert session.exec(select(AuditLog).where(AuditLog.entity_id == new_id)).first() is not None


def test_new_vendor_first_requested_account_is_not_trusted(session):
    world(session, onboarding=False)
    new_id = verify.record_requested_destination(session, "ven_t", "r9", "9999", "Bank")
    assert verify.current_verified_account(session, "ven_t") is None
    pending(session, new_id)
    with pytest.raises(payments.TransferRefused):
        run(payments.pay_payment(session, "pay_t"))
    assert session.get(Payment, "pay_t").status == PaymentStatus.pending


# ---------------------------------------------------------------- pay_payment and the send_transfer guard


def test_pay_payment_refuses_unverified_destination(session):
    world(session)
    bad = verify.record_requested_destination(session, "ven_t", "r9", "9999", "Evil Bank")
    pending(session, bad)
    with pytest.raises(payments.TransferRefused):
        run(payments.pay_payment(session, "pay_t"))
    p = session.get(Payment, "pay_t")
    assert p.status == PaymentStatus.pending and p.nessie_transfer_id is None


def test_send_transfer_has_the_same_backstop(session, monkeypatch):
    world(session)
    bad = verify.record_requested_destination(session, "ven_t", "r9", "9999", "Evil Bank")
    pay = Payment(id="pay_x", run_id="run_t", invoice_id="inv_t", amount_usd=5.0, destination_account_id=bad,
                  status=PaymentStatus.pending)
    monkeypatch.setattr(db, "engine", session.get_bind())
    with pytest.raises(payments.TransferRefused):
        run(payments.send_transfer(pay))
    pay.destination_account_id = "bac_t_1"
    assert run(payments.send_transfer(pay))


def test_pay_payment_pays_verified_destination(session):
    world(session)
    pending(session, "bac_t_1")
    tid = run(payments.pay_payment(session, "pay_t"))
    p = session.get(Payment, "pay_t")
    assert p.status == PaymentStatus.paid and p.nessie_transfer_id == tid and tid.startswith("mock_tr_")
    assert session.exec(select(AuditLog).where(AuditLog.entity_id == "pay_t", AuditLog.action == "paid")).first()
    assert run(payments.pay_payment(session, "pay_t")) == tid  # idempotent


# ================================================================ the real verification call (all mocks)

import ast  # noqa: E402
import time  # noqa: E402
from pathlib import Path  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from app.models import (  # noqa: E402
    Attack,
    AttackResult,
    AttackSource,
    CallOutcome,
    ContactSource,
    Decision,
    Message,
    RiskAssessment,
    VendorContact,
    VerificationCall,
)
from tests.helpers import use_engine  # noqa: E402

APP = Path(__file__).resolve().parent.parent / "app"


def held_world(session, hard_rules=None):
    """A held payment that asks for a NEW account (9999) at a vendor whose verified account is 1111, with a call row."""
    session.add(Vendor(id="ven_t", name="Test Co", trade="x", email_domain="test.example"))
    session.add(VendorBankAccount(id="bac_t_1", vendor_id="ven_t", routing_hash="r1", account_last4="1111", bank_name="B",
                                  valid_from=utcnow().replace(year=2024)))
    session.add(VendorContact(id="con_t", vendor_id="ven_t", phone="+14155550142", source=ContactSource.on_file, last_verified=utcnow()))
    session.add(Message(id="msg_t", thread_id="thr_t", vendor_id="ven_t", from_addr="ar@test-co.example", subject="s", body="b", is_attack=True))
    session.add(PaymentRun(id="run_t"))
    session.commit()
    session.add(Invoice(id="inv_t", vendor_id="ven_t", message_id="msg_t", amount_usd=100.0,
                        remittance_json={"bank_name": "New", "routing_hash": "r9", "account_last4": "9999"}))
    session.commit()
    cand = verify.record_requested_destination(session, "ven_t", "r9", "9999", "New")
    session.add(Payment(id="pay_t", run_id="run_t", invoice_id="inv_t", amount_usd=100.0, destination_account_id=cand, status=PaymentStatus.held))
    session.add(Attack(id="atk_t", attacker_name="J", source=AttackSource.judge, card="classic_bank_change", payload_ref="msg_t"))
    session.add(VerificationCall(id="cal_t", payment_id="pay_t", contact_id="con_t"))
    if hard_rules is not None:
        session.add(RiskAssessment(payment_id="pay_t", score=90, decision=Decision.hold_and_verify, hard_rules_fired=hard_rules, signals_json=[], model_version="t"))
    session.commit()
    return cand


def outcome(session, o, **kw):
    return run(verify.handle_outcome("cal_t", o, [{"speaker": "vendor", "text": "x"}], session, **kw))


def status(session):
    session.expire_all()
    return session.get(Payment, "pay_t")


def actions(session):
    return [a.action for a in session.exec(select(AuditLog).where(AuditLog.entity_id == "pay_t"))]


@pytest.fixture
def fast_retry(monkeypatch):
    monkeypatch.setattr(verify, "RETRY_DELAY_SECONDS", 0)


# ---------------------------------------------------------------- the four outcomes


def test_confirmed_promotes_the_account_and_pays_through_the_guard(session, allowed):
    cand = held_world(session)
    res = outcome(session, CallOutcome.confirmed)
    p = status(session)
    assert p.status == PaymentStatus.paid and p.nessie_transfer_id and p.destination_account_id == cand
    acct = session.get(VendorBankAccount, cand)
    assert acct.verified_by_call_id == "cal_t" and acct.valid_to is None
    assert session.get(VendorBankAccount, "bac_t_1").valid_to is not None
    assert {"paid", "verification_call"} <= set(actions(session))
    assert session.exec(select(AuditLog).where(AuditLog.entity_id == "ven_t", AuditLog.action == "bank_account_verified")).first()
    assert res.outcome == CallOutcome.confirmed and res.payment_status == PaymentStatus.paid


def test_confirmed_with_pay_false_leaves_the_payment_for_the_run(session):
    held_world(session)
    outcome(session, CallOutcome.confirmed, pay=False)
    assert status(session).status == PaymentStatus.pending


def test_confirmed_but_another_hard_rule_stays_held(session):
    held_world(session, hard_rules=["destination_changed", "amount_over_max"])
    outcome(session, CallOutcome.confirmed)
    p = status(session)
    assert p.status == PaymentStatus.held and p.nessie_transfer_id is None
    assert "held_after_verification" in actions(session)


def test_denied_blocks_never_pays_and_marks_fraud(session):
    cand = held_world(session)
    outcome(session, CallOutcome.denied)
    p = status(session)
    assert p.status == PaymentStatus.blocked and p.nessie_transfer_id is None
    assert session.get(VendorBankAccount, cand).valid_to is not None  # the candidate is closed
    assert session.get(Attack, "atk_t").result == AttackResult.caught
    assert session.get(Message, "msg_t").is_attack
    assert {"blocked_by_verification", "request_marked_fraud"} <= set(actions(session))
    with pytest.raises(payments.TransferRefused):
        run(payments.pay_payment(session, "pay_t"))


def test_unclear_keeps_the_hold_for_the_controller(session):
    held_world(session)
    res = outcome(session, CallOutcome.unclear)
    assert status(session).status == PaymentStatus.held and res.needs_controller
    row = session.exec(select(AuditLog).where(AuditLog.action == "needs_controller_review")).first()
    assert row and row.detail_json["transcript"][0]["text"] == "x"


def test_no_answer_retries_once_then_goes_to_the_controller(session, monkeypatch, fast_retry):
    held_world(session)
    placed = []

    async def fake_start(payment_id, session=None):
        placed.append(payment_id)
        session = session or Session(session_engine)
        # the second call row, as begin_real_call would create it
        with Session(session_engine) as s:
            s.add(VerificationCall(id="cal_t2", payment_id=payment_id, contact_id="con_t"))
            s.commit()

    session_engine = session.get_bind()
    monkeypatch.setattr(verify, "start_verification", fake_start)
    monkeypatch.setattr(verify, "engine", session_engine)

    async def go():
        first = await verify.handle_outcome("cal_t", CallOutcome.no_answer, None, session)
        await asyncio.gather(*verify._tasks)  # the retry sleeps, then places the second call: no timeout wraps it
        second = await verify.handle_outcome("cal_t2", CallOutcome.no_answer, None, session)
        await asyncio.sleep(0.05)
        return first, second

    first, second = run(go())
    assert placed == ["pay_t"]  # exactly one retry
    assert not first.needs_controller and second.needs_controller and second.attempts == 2
    assert status(session).status == PaymentStatus.held
    assert "needs_controller_review" in actions(session)


def test_handle_outcome_is_idempotent(session):
    held_world(session)
    first = outcome(session, CallOutcome.confirmed)
    again = outcome(session, CallOutcome.denied)  # a late duplicate must change nothing
    assert first is not None and again is None
    assert status(session).status == PaymentStatus.paid
    assert actions(session).count("verification_call") == 1 and actions(session).count("paid") == 1


# ---------------------------------------------------------------- classification


@pytest.mark.parametrize("text,expected", [
    ("No we never changed banks", CallOutcome.denied),
    ("Yes we did", CallOutcome.confirmed),
    ("Yes, that's right", CallOutcome.confirmed),
    ("we did not do that", CallOutcome.denied),
    ("uh what", CallOutcome.unclear),
    ("", CallOutcome.unclear),
    ("this is a scam", CallOutcome.denied),
    ("yes... no wait, we didn't", CallOutcome.denied),  # negations win
])
def test_keyword_classifier(text, expected):
    assert verify.classify_keywords(text) == expected


def _claude_on(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "mock_claude", False)
    monkeypatch.setattr(s, "anthropic_api_key", "test-key")


def test_claude_timing_out_falls_back_to_keywords(monkeypatch):
    _claude_on(monkeypatch)
    monkeypatch.setattr(verify, "CLAUDE_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(verify, "_ask_claude", lambda text: time.sleep(0.5) or (CallOutcome.confirmed, "late"))
    out, evidence = run(verify.classify_answer("No we never changed banks"))
    assert out == CallOutcome.denied and evidence["classifier"] == "keywords" and "timed out" in evidence["claude"]


def test_claude_answer_is_used_when_it_arrives_in_time(monkeypatch):
    _claude_on(monkeypatch)
    monkeypatch.setattr(verify, "_ask_claude", lambda text: (CallOutcome.confirmed, "says it was them"))
    out, evidence = run(verify.classify_answer("uh what"))
    assert out == CallOutcome.confirmed and evidence["classifier"] == "claude" and evidence["reason"] == "says it was them"


def test_claude_cannot_turn_a_keyword_denial_into_a_confirmation(monkeypatch):
    _claude_on(monkeypatch)
    monkeypatch.setattr(verify, "_ask_claude", lambda text: (CallOutcome.confirmed, "ok"))
    out, _ = run(verify.classify_answer("no, never"))
    assert out == CallOutcome.unclear


# ---------------------------------------------------------------- the webhooks


@pytest.fixture
def fdb(tmp_path, monkeypatch):
    """A file database shared by the app, the event log and verify, plus a held payment and a call row."""
    eng = create_engine(f"sqlite:///{tmp_path}/t.db")
    SQLModel.metadata.create_all(eng)
    use_engine(monkeypatch, eng)
    monkeypatch.setattr(verify, "arm_answer_watchdog", lambda call_id: None)
    monkeypatch.setenv("VOICE_MODE", "twilio")  # os.getenv wins over .env, so a developer's VOICE_MODE=web cannot leak into tests
    monkeypatch.setattr(get_settings(), "public_base_url", "https://pub.example")
    monkeypatch.setattr(get_settings(), "allowed_call_numbers", "+14155550142")
    with Session(eng) as s:
        held_world(s)
    from app.main import app

    return TestClient(app), eng


def _call_row(eng):
    with Session(eng) as s:
        return s.get(VerificationCall, "cal_t"), s.get(Payment, "pay_t")


@pytest.mark.parametrize("speech,expected,paid", [
    ("No we never changed banks", CallOutcome.denied, False),
    ("Yes we did", CallOutcome.confirmed, True),
    ("", CallOutcome.unclear, False),  # silence is never re-asked (it already had its own retry)
])
def test_gather_endpoint(fdb, speech, expected, paid):
    client, eng = fdb
    r = client.post("/api/voice/gather/cal_t", data={"SpeechResult": speech, "Confidence": "0.9"})
    assert r.status_code == 200 and r.text.endswith("<Hangup/></Response>")
    call, pay = _call_row(eng)  # the background task has run
    assert call.outcome == expected
    assert [l["speaker"] for l in call.transcript] == ["agent", "vendor", "agent"]
    assert call.transcript[1]["text"] == (speech or "(no response)")
    assert (pay.status == PaymentStatus.paid) == paid
    with Session(eng) as s:
        classifier = s.exec(select(AuditLog).where(AuditLog.action == "verification_call")).first().detail_json
        assert classifier["classifier"] == "keywords"
        types = [e.type for e in s.exec(select(Event).where(Event.run_id == "run_t").order_by(Event.at))]
    assert types.count("call.transcript") == 3 and "call.outcome" in types


def test_gather_twice_does_nothing_the_second_time(fdb):
    client, eng = fdb
    client.post("/api/voice/gather/cal_t", data={"SpeechResult": "Yes we did"})
    client.post("/api/voice/gather/cal_t", data={"SpeechResult": "No never"})
    call, pay = _call_row(eng)
    assert call.outcome == CallOutcome.confirmed and pay.status == PaymentStatus.paid and len(call.transcript) == 3


def test_status_callback_no_answer_and_ignored_statuses(fdb, monkeypatch):
    client, eng = fdb
    monkeypatch.setattr(verify, "RETRY_DELAY_SECONDS", 3600)  # the retry task is not what this test is about
    assert client.post("/api/webhooks/twilio/status?call_id=cal_t", data={"CallStatus": "ringing"}).status_code == 200
    assert _call_row(eng)[0].outcome is None
    assert client.post("/api/webhooks/twilio/status?call_id=cal_t", data={"CallStatus": "no-answer"}).status_code == 200
    assert _call_row(eng)[0].outcome == CallOutcome.no_answer and _call_row(eng)[1].status == PaymentStatus.held


def test_twiml_flow_first_retry_end(fdb):
    client, eng = fdb
    first = client.post("/api/voice/twiml/cal_t").text
    assert 'input="speech"' in first and 'timeout="10"' in first and "/api/voice/gather/cal_t" in first and "retry=1" in first
    retry = client.post("/api/voice/twiml/cal_t?retry=1").text
    assert "end=1" in retry and "<Gather" in retry
    end = client.post("/api/voice/twiml/cal_t?end=1")
    assert "<Hangup/>" in end.text
    assert _call_row(eng)[0].outcome == CallOutcome.unclear


def test_only_last4_is_ever_spoken():
    sc = voice.call_script("Summit Concrete", "123456789")
    assert "6789" in sc.question and "12345" not in " ".join(sc.all_texts())
    assert sc.intro == "This is an automated assistant calling for Ridgeline Builders accounts payable. This call is being transcribed."
    assert "recorded" not in " ".join(sc.all_texts())  # the trial account does not record, so the call must not say it does


def test_twiml_uses_only_allowed_verbs(fdb):
    client, _ = fdb
    pages = [client.post(u).text for u in ("/api/voice/twiml/cal_t", "/api/voice/twiml/cal_t?retry=1")]
    pages.append(client.post("/api/voice/gather/cal_t", data={"SpeechResult": "yes"}).text)
    pages.append(client.post("/api/voice/twiml/cal_t?end=1").text)
    for page in pages:
        tags = set(re.findall(r"<([A-Za-z]+)", page)) - {"Response"}
        assert tags <= {"Say", "Play", "Gather", "Redirect", "Pause", "Hangup"}, tags
        assert not re.search(r"<(Record|Stream|Start)", page)


def test_bad_signature_is_rejected_when_validation_is_on(fdb, monkeypatch):
    from twilio.request_validator import RequestValidator

    client, _ = fdb
    monkeypatch.setattr(get_settings(), "twilio_validate_signatures", True)
    monkeypatch.setattr(get_settings(), "twilio_auth_token", "secret-token")
    for path in ("/api/voice/twiml/cal_t", "/api/voice/gather/cal_t", "/api/webhooks/twilio/status?call_id=cal_t"):
        assert client.post(path, data={"CallStatus": "no-answer"}, headers={"X-Twilio-Signature": "bad"}).status_code == 403
        assert client.post(path, data={"CallStatus": "no-answer"}).status_code == 403
    form = {"CallStatus": "ringing"}
    url = "https://pub.example/api/webhooks/twilio/status?call_id=cal_t"
    good = RequestValidator("secret-token").compute_signature(url, form)
    assert client.post("/api/webhooks/twilio/status?call_id=cal_t", data=form, headers={"X-Twilio-Signature": good}).status_code == 200


def test_defaults_per_mode(fdb, monkeypatch):
    from app import integrations

    monkeypatch.setattr(get_settings(), "twilio_validate_signatures", False)
    monkeypatch.setattr(get_settings(), "twilio_require_call_token", None)
    assert integrations.call_token_required() is False and integrations.signature_validation_on() is False
    monkeypatch.setattr(get_settings(), "mock_twilio", False)
    assert integrations.call_token_required() is True  # protection is on by default in real mode
    assert integrations.signature_validation_on() is False  # trial TwiML fetches carry no signature
    monkeypatch.setattr(get_settings(), "twilio_require_call_token", False)
    assert integrations.call_token_required() is False


@pytest.fixture
def real_hooks(fdb, monkeypatch, tmp_path):
    """Real mode webhooks: tokens required, with a token minted for the call cal_t."""
    monkeypatch.setattr(voice, "AUDIO_DIR", tmp_path / "audio")
    monkeypatch.setattr(get_settings(), "twilio_validate_signatures", False)
    monkeypatch.setattr(get_settings(), "twilio_require_call_token", None)
    monkeypatch.setattr(get_settings(), "mock_twilio", False)
    client, eng = fdb
    return client, eng, voice.new_call_token("cal_t")


def test_right_token_passes_and_travels_through_the_call(real_hooks):
    client, eng, tok = real_hooks
    first = client.post(f"/api/voice/twiml/cal_t?t={tok}")
    assert first.status_code == 200
    assert f"/api/voice/gather/cal_t?t={tok}" in first.text and f"retry=1&amp;t={tok}" in first.text  # the next hops keep it
    retry = client.post(f"/api/voice/twiml/cal_t?retry=1&t={tok}")
    assert f"end=1&amp;t={tok}" in retry.text
    assert client.post(f"/api/webhooks/twilio/status?call_id=cal_t&t={tok}", data={"CallStatus": "ringing"}).status_code == 200
    assert client.post(f"/api/webhooks/twilio/status/cal_t/{tok}", data={"CallStatus": "ringing"}).status_code == 200  # token in the path
    assert client.post(f"/api/voice/gather/cal_t?t={tok}", data={"SpeechResult": "no never"}).status_code == 200
    assert _call_row(eng)[0].outcome == CallOutcome.denied


@pytest.mark.parametrize("suffix", ["", "?t=wrong", "?t=", "?t=" + "a" * 32])
def test_wrong_or_missing_token_is_403_on_every_route(real_hooks, suffix):
    client, eng, tok = real_hooks
    join = "&" if suffix and False else ""
    assert client.post(f"/api/voice/twiml/cal_t{suffix}").status_code == 403
    assert client.post(f"/api/voice/gather/cal_t{suffix}", data={"SpeechResult": "yes"}).status_code == 403
    status_url = "/api/webhooks/twilio/status?call_id=cal_t" + (suffix.replace("?", "&") if suffix else "")
    assert client.post(status_url, data={"CallStatus": "no-answer"}).status_code == 403
    assert client.post("/api/webhooks/twilio/status/cal_t/" + (suffix.split("=", 1)[-1] or "x"), data={"CallStatus": "no-answer"}).status_code == 403
    assert _call_row(eng)[0].outcome is None and _call_row(eng)[1].status == PaymentStatus.held


def test_a_token_for_one_call_does_not_open_another(real_hooks):
    client, eng, tok = real_hooks
    other = voice.new_call_token("cal_aaaaaaaaaaaa")
    assert client.post(f"/api/voice/twiml/cal_t?t={other}").status_code == 403
    assert client.post(f"/api/voice/twiml/cal_aaaaaaaaaaaa?t={tok}").status_code == 403
    assert voice.check_call_token("../../etc/passwd", tok) is False


def test_strict_signature_mode_still_requires_a_valid_signature(real_hooks, monkeypatch):
    from twilio.request_validator import RequestValidator

    client, _, tok = real_hooks
    monkeypatch.setattr(get_settings(), "twilio_validate_signatures", True)
    monkeypatch.setattr(get_settings(), "twilio_auth_token", "secret-token")
    path = f"/api/webhooks/twilio/status?call_id=cal_t&t={tok}"
    form = {"CallStatus": "ringing"}
    assert client.post(path, data=form).status_code == 403
    assert client.post(path, data=form, headers={"X-Twilio-Signature": "bad"}).status_code == 403
    good = RequestValidator("secret-token").compute_signature("https://pub.example" + path, form)
    assert client.post(path, data=form, headers={"X-Twilio-Signature": good}).status_code == 200


def test_missing_signature_is_fine_when_the_token_is_right(real_hooks):
    client, _, tok = real_hooks  # trial TwiML fetches carry no X-Twilio-Signature at all
    assert client.post(f"/api/voice/twiml/cal_t?t={tok}").status_code == 200


def test_token_never_reaches_logs_events_or_the_database(real_hooks, caplog):
    import logging as _logging

    client, eng, tok = real_hooks
    caplog.set_level(_logging.DEBUG)
    client.post(f"/api/voice/twiml/cal_t?t={tok}")
    client.post(f"/api/voice/twiml/cal_t?t=wrong{tok}")
    client.post(f"/api/voice/gather/cal_t?t={tok}", data={"SpeechResult": "no"})
    ours = [r.getMessage() for r in caplog.records if r.name.startswith(("countersign", "uvicorn"))]  # not the test client's own httpx line
    assert ours and not any(tok in m for m in ours)
    with Session(eng) as s:
        blob = " ".join(str(e.payload) for e in s.exec(select(Event))) + " ".join(str(a.detail_json) for a in s.exec(select(AuditLog)))
    assert tok not in blob
    # uvicorn's access log line is redacted
    rec = _logging.LogRecord("uvicorn.access", _logging.INFO, "", 0, '%s - "%s %s HTTP/%s" %d',
                             ("1.2.3.4:5", "POST", f"/api/voice/twiml/cal_t?retry=1&t={tok}", "1.1", 200), None)
    for f in _logging.getLogger("uvicorn.access").filters:
        f.filter(rec)
    assert tok not in rec.getMessage() and "t=***" in rec.getMessage()


def test_mock_mode_needs_no_token(fdb, monkeypatch):
    client, _ = fdb
    monkeypatch.setattr(get_settings(), "twilio_require_call_token", None)
    assert client.post("/api/voice/twiml/cal_t").status_code == 200


# ---------------------------------------------------------------- real mode places the call and returns at once


def test_real_mode_start_verification_returns_at_once(fdb, monkeypatch, tmp_path):
    client, eng = fdb
    monkeypatch.setattr(voice, "AUDIO_DIR", tmp_path / "audio")
    cfg = get_settings()
    monkeypatch.setattr(cfg, "mock_twilio", False)
    monkeypatch.setattr(cfg, "mock_cartesia", False)
    dialed, clips = [], []

    async def fake_place(to, url, status_callback=None, settings=None):
        dialed.append((to, url, status_callback))
        return "CAtest"

    async def fake_clip(text, settings=None):
        clips.append(text)
        return "https://pub.example/x.wav"

    monkeypatch.setattr(voice, "place_call", fake_place)
    monkeypatch.setattr(voice, "tts_clip", fake_clip)
    with Session(eng) as s:
        s.get(VerificationCall, "cal_t").outcome = CallOutcome.no_answer  # the fixture call is settled, so a new one may start
        s.commit()
        res = run(verify.start_verification("pay_t", s))
        s.expire_all()
        assert res.in_progress and res.payment_status == PaymentStatus.held and not res.needs_controller
        calls = s.exec(select(VerificationCall).where(VerificationCall.payment_id == "pay_t")).all()
        assert len(calls) == 2 and sum(c.outcome is None for c in calls) == 1  # the settled fixture call plus the new open one
        new = next(c for c in calls if c.id != "cal_t")
        assert s.get(Payment, "pay_t").status == PaymentStatus.held
    tok = voice._token_path(new.id).read_text().strip()
    assert voice.check_call_token(new.id, tok)
    assert dialed == [("+14155550142", f"https://pub.example/api/voice/twiml/{new.id}?t={tok}",
                       f"https://pub.example/api/webhooks/twilio/status/{new.id}/{tok}")]
    with Session(eng) as s:
        assert tok not in " ".join(str(a.detail_json) for a in s.exec(select(AuditLog))) and not any(tok in c for c in clips)
    assert len(clips) == 8 and any("9999" in c for c in clips)


def test_real_mode_refuses_a_number_off_the_allow_list(fdb, monkeypatch):
    _, eng = fdb
    cfg = get_settings()
    monkeypatch.setattr(cfg, "mock_twilio", False)
    monkeypatch.setattr(cfg, "mock_cartesia", False)
    monkeypatch.setattr(cfg, "allowed_call_numbers", "+14155550199")
    with Session(eng) as s:
        s.get(VerificationCall, "cal_t").outcome = CallOutcome.no_answer  # settled, so a new start reaches the allow list check
        s.commit()
        with pytest.raises(verify.CallNotAllowed):
            run(verify.start_verification("pay_t", s))
        assert len(s.exec(select(VerificationCall)).all()) == 1  # no new call row


def test_answer_watchdog_ends_an_answered_call_as_unclear_after_the_limit(tmp_path, monkeypatch):
    eng = create_engine(f"sqlite:///{tmp_path}/w.db")
    SQLModel.metadata.create_all(eng)
    use_engine(monkeypatch, eng)
    with Session(eng) as s:
        held_world(s)
    monkeypatch.setattr(verify, "CALL_TIMEOUT_SECONDS", 0.05)

    async def go():
        verify.arm_answer_watchdog("cal_t")
        verify.arm_answer_watchdog("cal_t")  # only the first fetch arms it
        assert len(verify._watchdogs) == 1
        await asyncio.sleep(0.4)

    run(go())
    with Session(eng) as s:
        assert s.get(VerificationCall, "cal_t").outcome == CallOutcome.unclear
        assert s.get(Payment, "pay_t").status == PaymentStatus.held
    assert not verify._watchdogs


def test_answering_disarms_the_watchdog(tmp_path, monkeypatch):
    eng = create_engine(f"sqlite:///{tmp_path}/w2.db")
    SQLModel.metadata.create_all(eng)
    use_engine(monkeypatch, eng)
    with Session(eng) as s:
        held_world(s)
    monkeypatch.setattr(verify, "CALL_TIMEOUT_SECONDS", 0.2)

    async def go():
        verify.arm_answer_watchdog("cal_t")
        await verify.handle_outcome("cal_t", CallOutcome.denied, None)
        await asyncio.sleep(0.4)

    run(go())
    with Session(eng) as s:
        assert s.get(VerificationCall, "cal_t").outcome == CallOutcome.denied  # the watchdog did not overwrite it


# ---------------------------------------------------------------- manual route, mock mode


def test_manual_call_route_in_mock_mode(fdb, monkeypatch):
    client, eng = fdb
    monkeypatch.setattr(verify, "MOCK_STEP_DELAY", 0)
    monkeypatch.setattr(contacts, "MOCK_OVERRIDES", {"ven_t": "+14155550142"})
    with Session(eng) as s:
        s.get(VerificationCall, "cal_t").outcome = CallOutcome.no_answer  # the fixture call is settled; an open one blocks a second start
        s.commit()
    r = client.post("/api/verifications/pay_t/call?answer=Yes%20we%20did")
    assert r.status_code == 202 and r.json()["mode"] == "mock"
    with Session(eng) as s:
        assert s.get(Payment, "pay_t").status == PaymentStatus.paid  # confirmed mock call pays through the guard
        types = [e.type for e in s.exec(select(Event).where(Event.run_id == "run_t").order_by(Event.at))]
    assert types[0] == "call.started" and "call.outcome" in types and types.index("payment.paid") > types.index("call.outcome")
    assert client.post("/api/verifications/pay_t/call").status_code == 409  # no longer held
    assert client.post("/api/verifications/nope/call").status_code == 404


# ---------------------------------------------------------------- least privilege


def test_only_verify_writes_verified_by_call_id_and_vendor_contacts():
    offenders = []
    for path in APP.rglob("*.py"):
        if path.name == "verify.py":
            continue
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, (ast.Assign, ast.AugAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                if any(isinstance(t, ast.Attribute) and t.attr == "verified_by_call_id" for t in targets):
                    offenders.append(f"{path.name}:{node.lineno} assigns verified_by_call_id")
            if isinstance(node, ast.Call):
                if any(k.arg == "verified_by_call_id" for k in node.keywords):
                    offenders.append(f"{path.name}:{node.lineno} passes verified_by_call_id")
                if getattr(node.func, "id", None) == "VendorContact" or getattr(node.func, "attr", None) == "VendorContact":
                    offenders.append(f"{path.name}:{node.lineno} builds VendorContact")
    assert offenders == []


# ---------------------------------------------------------------- create-test-hold

def test_create_test_hold_on_a_seeded_database(seed_template, tmp_path, monkeypatch, capsys):
    from tests.conftest import copy_seeded
    from scripts import integrations_cli

    eng = create_engine(f"sqlite:///{copy_seeded(seed_template, tmp_path)}")
    use_engine(monkeypatch, eng)
    monkeypatch.setattr(get_settings(), "demo_vendor_phone", "+14155550142")
    monkeypatch.setattr(get_settings(), "allowed_call_numbers", "+14155550142")

    assert integrations_cli.create_test_hold() == 0
    assert integrations_cli.create_test_hold() == 0  # repeatable
    out = capsys.readouterr().out
    pay_id = re.findall(r"payment_id=(\S+)", out)[0]
    with Session(eng) as s:
        pay = s.get(Payment, pay_id)
        inv = s.get(Invoice, pay.invoice_id)
        assert pay.status == PaymentStatus.held and inv.due_date is not None and inv.number and inv.amount_usd
        cand = s.get(VendorBankAccount, pay.destination_account_id)
        assert cand.account_last4 == "7781" and cand.verified_by_call_id is None  # unverified candidate
        assert verify.current_verified_account(s, inv.vendor_id).id != cand.id
        phones = [c.phone for c in s.exec(select(VendorContact).where(VendorContact.vendor_id == inv.vendor_id, VendorContact.source == ContactSource.on_file))]
        assert "+14155550142" in phones
    monkeypatch.setattr(verify, "MOCK_STEP_DELAY", 0)
    verify.MOCK_OUTCOMES[pay_id] = CallOutcome.denied
    try:
        res = run(verify.start_verification(pay_id))  # a mock call on the created hold works end to end
    finally:
        verify.MOCK_OUTCOMES.pop(pay_id, None)
    assert res.outcome == CallOutcome.denied and res.payment_status == PaymentStatus.blocked


# ---------------------------------------------------------------- re-ask and "hold on"


def _gather(client, speech, r=0):
    return client.post(f"/api/voice/gather/cal_t{'?r=1' if r else ''}", data={"SpeechResult": speech}).text


def test_unclear_answer_is_re_asked_once_then_finalizes_unclear(fdb):
    client, eng = fdb
    first = _gather(client, "who is this?")
    assert "ending 9999" in first and "<Gather" in first and "<Hangup/>" not in first and "gather/cal_t?r=1" in first
    assert _call_row(eng)[0].outcome is None
    second = _gather(client, "what account?", r=1)
    assert second.endswith("<Hangup/></Response>") and "ending 9999" not in second
    call, pay = _call_row(eng)
    assert call.outcome == CallOutcome.unclear and pay.status == PaymentStatus.held
    assert [l["speaker"] for l in call.transcript] == ["agent", "vendor", "agent", "vendor", "agent"]


def test_re_ask_then_clear_answer_resolves(fdb):
    client, eng = fdb
    _gather(client, "who is this?")
    assert _gather(client, "No, never", r=1).endswith("<Hangup/></Response>")
    assert _call_row(eng)[0].outcome == CallOutcome.denied


def test_hold_on_regathers_and_uses_up_the_single_re_ask(fdb):
    client, eng = fdb
    page = _gather(client, "hold on a second")
    assert "take your time" in page.lower() or "<Play>" in page
    assert "<Gather" in page and _call_row(eng)[0].outcome is None
    assert _call_row(eng)[0].transcript[-1]["text"] == "Sure, take your time."
    assert _gather(client, "umm", r=1).endswith("<Hangup/></Response>")  # no second re-ask
    assert _call_row(eng)[0].outcome == CallOutcome.unclear


def test_silence_after_a_re_ask_ends_the_call_unclear(fdb):
    client, eng = fdb
    _gather(client, "what?")
    assert "<Hangup/>" in client.post("/api/voice/twiml/cal_t?end=1&r=1").text
    call = _call_row(eng)[0]
    assert call.outcome == CallOutcome.unclear and [l["speaker"] for l in call.transcript] == ["agent", "vendor", "agent", "vendor", "agent"]


def test_decide_rules():
    assert voice.decide("who is this", "unclear", False) == "reask"
    assert voice.decide("who is this", "unclear", True) == "close"
    assert voice.decide("", "unclear", False) == "close"
    assert voice.decide("one moment please", "unclear", False) == "hold"
    assert voice.decide("wait, no we never did", "denied", False) == "hold"  # asked to wait: let them finish
    assert voice.decide("yes", "confirmed", False) == "close"


def test_regather_twiml_uses_only_allowed_verbs(fdb):
    client, _ = fdb
    for speech in ("who is this", "hold on"):
        tags = set(re.findall(r"<([A-Za-z]+)", _gather(client, speech))) - {"Response"}
        assert tags <= {"Say", "Play", "Gather", "Redirect", "Pause", "Hangup"}, tags
        client.post("/api/voice/twiml/cal_t?end=1&r=1")
        break


# ---------------------------------------------------------------- double start


def test_second_start_returns_the_call_already_going(fdb):
    _, eng = fdb
    with Session(eng) as s:
        res = run(verify.start_verification("pay_t", s))  # the fixture's cal_t is still open
        again = run(verify.start_verification("pay_t", s))
        assert res.call_id == again.call_id == "cal_t" and res.in_progress
        assert len(s.exec(select(VerificationCall).where(VerificationCall.payment_id == "pay_t")).all()) == 1


# ---------------------------------------------------------------- browser softphone

KEY = "phone-key-123"


@pytest.fixture
def web(fdb, monkeypatch, tmp_path):
    """Real mode with VOICE_MODE=web. The fixture's call is settled, then a web call is started through start_verification."""
    client, eng = fdb
    cfg = get_settings()
    monkeypatch.setattr(voice, "AUDIO_DIR", tmp_path / "audio")
    monkeypatch.setattr(cfg, "mock_twilio", False)
    monkeypatch.setattr(cfg, "mock_cartesia", False)
    monkeypatch.setattr(cfg, "twilio_require_call_token", None)
    monkeypatch.setenv("VOICE_MODE", "web")
    monkeypatch.setenv("VENDOR_PHONE_KEY", KEY)
    monkeypatch.setattr(voice, "web_calls", {})
    monkeypatch.setattr(verify, "RETRY_DELAY_SECONDS", 3600)

    async def fake_clip(text, settings=None):
        return voice.clip_url(text, settings)

    async def no_dial(*a, **k):
        raise AssertionError("web mode must not dial")

    monkeypatch.setattr(voice, "tts_clip", fake_clip)
    monkeypatch.setattr(voice, "place_call", no_dial)
    with Session(eng) as s:
        s.get(VerificationCall, "cal_t").outcome = CallOutcome.no_answer
        s.commit()

    async def go():
        with Session(eng) as s:
            return await verify.start_verification("pay_t", s)

    res = asyncio.run(go())
    return client, eng, res


def _pending(client, k=KEY):
    return client.get(f"/api/voice/pending/ven_t?k={k}")


def _web_state(eng, call_id):
    with Session(eng) as s:
        return s.get(VerificationCall, call_id), s.get(Payment, "pay_t")


def test_web_call_shows_as_pending_and_never_dials(web):
    client, eng, res = web
    assert res.in_progress and res.call_id in voice.web_calls
    body = _pending(client).json()["call"]
    assert body["call_id"] == res.call_id and body["vendor_name"] == "Test Co" and set(body["clips"]) >= {"intro", "question", "clarify", "hold", "confirmed", "denied"}
    assert voice.check_call_token(res.call_id, body["token"])
    with Session(eng) as s:
        placed = [a for a in s.exec(select(AuditLog).where(AuditLog.action == "verification_call_placed"))]
        assert placed and placed[-1].detail_json["channel"] == "web" and body["token"] not in str([a.detail_json for a in s.exec(select(AuditLog))])


def _answer(client, res, text, token=None):
    tok = token or _pending(client).json()["call"]["token"]
    return client.post(f"/api/voice/web-answer/{res.call_id}?t={tok}", json={"answer": text})


def test_web_denied_blocks_the_payment(web):
    client, eng, res = web
    r = _answer(client, res, "No we never changed banks")
    assert r.status_code == 200 and r.json()["final"] and r.json()["outcome"] == "denied" and r.json()["clip"]
    call, pay = _web_state(eng, res.call_id)
    assert call.outcome == CallOutcome.denied and pay.status == PaymentStatus.blocked
    assert res.call_id not in voice.web_calls and _pending(client).json()["call"] is None


def test_web_confirmed_pays(web):
    client, eng, res = web
    r = _answer(client, res, "Yes we did")
    assert r.json()["outcome"] == "confirmed"
    call, pay = _web_state(eng, res.call_id)
    assert call.outcome == CallOutcome.confirmed and pay.status == PaymentStatus.paid


def test_web_decline_is_no_answer(web):
    client, eng, res = web
    tok = _pending(client).json()["call"]["token"]
    r = client.post(f"/api/voice/web-answer/{res.call_id}?t={tok}", json={"decline": True})
    assert r.status_code == 200 and r.json()["outcome"] == "no_answer"
    call, pay = _web_state(eng, res.call_id)
    assert call.outcome == CallOutcome.no_answer and pay.status == PaymentStatus.held


def test_web_re_ask_once_then_unclear(web):
    client, eng, res = web
    tok = _pending(client).json()["call"]["token"]
    first = _answer(client, res, "who is this?", tok).json()
    assert first["action"] == "reask" and not first["final"] and "ending 9999" in first["text"]
    assert _web_state(eng, res.call_id)[0].outcome is None
    second = _answer(client, res, "what account?", tok).json()
    assert second["final"] and second["outcome"] == "unclear"
    assert _web_state(eng, res.call_id)[1].status == PaymentStatus.held


def test_web_hold_on_listens_again(web):
    client, _, res = web
    tok = _pending(client).json()["call"]["token"]
    first = _answer(client, res, "hold on", tok).json()
    assert first["action"] == "hold" and first["text"] == "Sure, take your time." and not first["final"]
    assert _answer(client, res, "No never", tok).json()["outcome"] == "denied"


def test_answered_call_stops_ringing_the_page(web):
    client, _, res = web
    tok = _pending(client).json()["call"]["token"]
    assert client.post(f"/api/voice/web-answer/{res.call_id}?t={tok}", json={"event": "answered"}).json() == {"ok": True}
    assert _pending(client).json()["call"] is None and res.call_id in voice.web_calls


def test_softphone_page_and_pending_need_the_key(web, monkeypatch):
    client, _, _ = web
    for k in ("", "wrong", KEY + "x"):
        assert client.get(f"/api/voice/vendor-phone/ven_t?k={k}").status_code == 403
        assert _pending(client, k).status_code == 403
    assert client.get("/api/voice/vendor-phone/ven_t").status_code == 403
    ok = client.get(f"/api/voice/vendor-phone/ven_t?k={KEY}")
    assert ok.status_code == 200 and "ngrok-skip-browser-warning" in ok.text and "Disconnected" in ok.text
    monkeypatch.setenv("VENDOR_PHONE_KEY", "")
    monkeypatch.setattr(voice, "_env", lambda name: "")  # no key configured anywhere: nothing opens
    assert client.get("/api/voice/vendor-phone/ven_t?k=").status_code == 403
    assert client.get("/api/voice/vendor-phone/ven_missing?k=anything").status_code == 403


def test_web_answer_rejects_a_wrong_token(web):
    client, eng, res = web
    for suffix in ("", "?t=wrong", "?t="):
        r = client.post(f"/api/voice/web-answer/{res.call_id}{suffix}", json={"answer": "Yes we did"})
        assert r.status_code == 403
    assert _web_state(eng, res.call_id)[0].outcome is None


def test_pending_marks_the_page_as_open(web):
    client, _, _ = web
    monkey_vendor = "ven_t"
    voice._last_poll.pop(monkey_vendor, None)
    assert not voice.vendor_phone_recent(monkey_vendor)
    _pending(client)
    assert voice.vendor_phone_recent(monkey_vendor)


# ---------------------------------------------------------------- failover


@pytest.fixture
def twilio_down(fdb, monkeypatch, tmp_path):
    client, eng = fdb
    cfg = get_settings()
    monkeypatch.setattr(voice, "AUDIO_DIR", tmp_path / "audio")
    monkeypatch.setattr(cfg, "mock_twilio", False)
    monkeypatch.setattr(cfg, "mock_cartesia", False)
    monkeypatch.setenv("VOICE_MODE", "twilio")
    monkeypatch.setenv("VENDOR_PHONE_KEY", KEY)
    monkeypatch.setattr(voice, "web_calls", {})
    monkeypatch.setattr(voice, "_last_poll", {})
    monkeypatch.setattr(verify, "RETRY_DELAY_SECONDS", 3600)

    async def fake_clip(text, settings=None):
        return voice.clip_url(text, settings)

    async def broken(*a, **k):
        raise RuntimeError("twilio is down")

    monkeypatch.setattr(voice, "tts_clip", fake_clip)
    monkeypatch.setattr(voice, "place_call", broken)
    with Session(eng) as s:
        s.get(VerificationCall, "cal_t").outcome = CallOutcome.no_answer
        s.commit()
    return client, eng


def test_twilio_failure_fails_over_to_the_softphone_when_the_page_is_open(twilio_down):
    client, eng = twilio_down
    voice.note_poll("ven_t")
    with Session(eng) as s:
        res = run(verify.start_verification("pay_t", s))
        assert res.in_progress and res.call_id in voice.web_calls
        actions = [a.action for a in s.exec(select(AuditLog))]
        assert "voice_failover_to_web" in actions
        placed = [a for a in s.exec(select(AuditLog).where(AuditLog.action == "verification_call_placed"))][-1]
        assert placed.detail_json["channel"] == "web"


def test_twilio_failure_without_an_open_page_keeps_the_old_behavior(twilio_down):
    _, eng = twilio_down
    with Session(eng) as s:
        with pytest.raises(RuntimeError):
            run(verify.start_verification("pay_t", s))
        assert len(s.exec(select(VerificationCall)).all()) == 1 and not voice.web_calls


def test_a_stale_poll_does_not_count(twilio_down, monkeypatch):
    _, eng = twilio_down
    voice.note_poll("ven_t")
    monkeypatch.setattr(voice, "VENDOR_PHONE_FRESH_SECONDS", -1)
    with Session(eng) as s:
        with pytest.raises(RuntimeError):
            run(verify.start_verification("pay_t", s))


def test_voice_mode_defaults_to_twilio(monkeypatch):
    monkeypatch.delenv("VOICE_MODE", raising=False)
    monkeypatch.setattr(voice, "_env", lambda name: "")
    assert voice.voice_mode() == "twilio"
    monkeypatch.setattr(voice, "_env", lambda name: "WEB")
    assert voice.voice_mode() == "web"


def test_logs_for_the_softphone_carry_no_token(web, caplog):
    import logging

    client, _, res = web
    tok = _pending(client).json()["call"]["token"]
    with caplog.at_level(logging.INFO):
        _answer(client, res, "Yes we did", tok)
        client.post(f"/api/voice/web-answer/{res.call_id}?t=nope", json={})
    ours = "\n".join(r.getMessage() for r in caplog.records if r.name.startswith("countersign"))  # the test client logs its own URLs
    assert tok not in ours and KEY not in ours and "finished" in ours


# ---------------------------------------------------------------- softphone: the call stays open after a re-ask or hold


def test_web_re_ask_keeps_the_call_open_then_no_is_denied_and_blocked(web):
    client, eng, res = web
    tok = _pending(client).json()["call"]["token"]
    first = _answer(client, res, "Who is this", tok)
    assert first.status_code == 200 and first.json()["action"] == "reask" and not first.json()["final"]
    assert res.call_id in voice.web_calls and _web_state(eng, res.call_id)[0].outcome is None
    second = _answer(client, res, "No", tok)  # exactly one more answer, and no 410
    assert second.status_code == 200 and second.json()["final"] and second.json()["outcome"] == "denied"
    call, pay = _web_state(eng, res.call_id)
    assert call.outcome == CallOutcome.denied and pay.status == PaymentStatus.blocked


def test_web_hold_keeps_the_call_open_then_yes_is_confirmed_and_paid(web):
    client, eng, res = web
    tok = _pending(client).json()["call"]["token"]
    first = _answer(client, res, "hold on one moment", tok)
    assert first.status_code == 200 and first.json()["action"] == "hold"
    assert res.call_id in voice.web_calls
    second = _answer(client, res, "Yes", tok)
    assert second.status_code == 200 and second.json()["outcome"] == "confirmed"
    call, pay = _web_state(eng, res.call_id)
    assert call.outcome == CallOutcome.confirmed and pay.status == PaymentStatus.paid


@pytest.mark.parametrize("speech,action", [("Who is this", "reask"), ("hold on", "hold"), ("No we never did", "close"), ("Yes we did", "close")])
def test_web_answer_always_names_the_clip_to_play(web, speech, action):
    client, _, res = web
    body = _answer(client, res, speech).json()
    assert body["action"] == action
    assert re.fullmatch(r"https://pub\.example/api/voice/audio/[0-9a-f]{64}\.wav", body["clip"] or ""), body
    assert body["clip"] == voice.clip_url(body["text"])  # the clip is the text that was recorded in the transcript


def test_a_re_ask_or_hold_gives_the_vendor_a_fresh_60_seconds(web, monkeypatch):
    client, _, res = web
    armed = []
    monkeypatch.setattr(verify, "arm_answer_watchdog", lambda cid: armed.append(cid))
    tok = _pending(client).json()["call"]["token"]
    _answer(client, res, "who is this", tok)
    assert armed == [res.call_id, res.call_id]  # once for the first answer, once more for the re-ask
    _answer(client, res, "No", tok)  # a final answer is not re-armed
    assert armed == [res.call_id, res.call_id]


def test_a_finished_call_answers_410_with_a_reason(web):
    client, _, res = web
    tok = _pending(client).json()["call"]["token"]
    _answer(client, res, "Yes we did", tok)
    r = _answer(client, res, "No", tok)
    assert r.status_code == 410 and "over" in r.json()["detail"]


def test_softphone_page_plays_every_clip_through_one_unlocked_player(web):
    client, _, _ = web
    html = client.get(f"/api/voice/vendor-phone/ven_t?k={KEY}").text
    assert html.count("<audio id=") == 1 and "unlockPlayer()" in html and "Tap to hear the question" in html
    assert "stopListening()" in html and 'id="yes"' in html and "new Audio(" not in html


# ================================================================ CRS sandbox integration (all HTTP mocked)

import json as _json  # noqa: E402
import logging  # noqa: E402

import httpx  # noqa: E402

from app.services import identity  # noqa: E402

CRS_SECRETS = ("tok-secret-1", "ref-secret-1", "pw-secret", "666701019", "666701013", "1976-09-16", "SOLANO", "KINGSTON")


class Crs:
    """A fake CRS sandbox behind httpx.MockTransport. Counts requests; `reverse_script` answers reverse lookups in order."""

    def __init__(self, delay=0.0, fraud_p19=9, expire_first_token=False, fail_all=False, reverse_script=None):
        self.delay, self.fraud_p19, self.fail_all = delay, fraud_p19, fail_all
        self.expire_first_token, self.reverse_script = expire_first_token, list(reverse_script or [])
        self.calls: list[str] = []
        self.tokens = 0
        self.refresh_ok = False

    def transport(self):
        return httpx.MockTransport(self.handle)

    async def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix("/api")
        self.calls.append(path)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.fail_all and path != "/users/login":
            raise httpx.ReadTimeout("slow")
        body = _json.loads(request.content or b"{}")
        if path == "/users/login":
            assert body == {"username": "crs-user", "password": "pw-secret"}
            self.tokens += 1
            return httpx.Response(200, json={"token": f"tok-secret-{self.tokens}", "refreshToken": "ref-secret-1", "expires": 3600})
        if path == "/users/refresh-token":
            if not self.refresh_ok:
                return httpx.Response(400, json={"messages": ["Refresh Token Premature"]})
            self.tokens += 1
            return httpx.Response(200, json={"token": f"tok-secret-{self.tokens}", "refreshToken": "ref-secret-2", "expires": 3600})
        if self.expire_first_token and request.headers.get("authorization") == "Bearer tok-secret-1":
            return httpx.Response(401, json={"messages": ["Token Required"]})
        head = {"requestid": f"req-{len(self.calls)}"}
        if path == "/accurate-append/reverse":
            if self.reverse_script:
                recs = self.reverse_script.pop(0)
            else:
                recs = [{"firstName": "GRACE", "lastName": "NAKAMURA"}] if body["phoneNumber"] == "5550101019" else []
            return httpx.Response(200, json={"success": True, "data": {"records": recs}}, headers=head)
        if path == "/fraud-finder/fraud-finder":
            score = self.fraud_p19 if body["email"] == "grace.nakamura@example.com" else 88
            return httpx.Response(200, json={"risk": {"score": str(score), "phone": {"prepaid": "False", "owner": {"last_name_match": "match"}}}}, headers=head)
        if path == "/transunion/identity-manager-verification/basic":
            msgs = [] if body["ssn"] == "666701019" else [{"code": "2201", "text": "x"}, {"code": "2101", "text": "y"}]
            return httpx.Response(200, json={
                "addOnProducts": [{"idManagerVerification": {"messages": msgs}}],
                "custom": {"idmanagerVerAnalysisV2": {"verificationAnalysises": [{"verificationStatus": "SUBJECT_FOUND", "firstNameVerification": "MATCH",
                                                                                  "lastNameVerification": "MATCH", "ssnVerification": "MATCH"}]}}}, headers=head)
        return httpx.Response(404)


@pytest.fixture
def crs(monkeypatch):
    monkeypatch.setenv("CRS_USERNAME", "crs-user")
    monkeypatch.setenv("CRS_PASSWORD", "pw-secret")
    monkeypatch.setitem(identity.VENDOR_PERSONA_OVERRIDES, "ven_t", "P19")
    fake = Crs()
    identity.set_transport(fake.transport())
    yield fake
    identity.set_transport(None)


def use_crs(monkeypatch, fake=None):
    """Real CRS (mocked HTTP), mock phone: the call itself is simulated."""
    if fake is not None:
        identity.set_transport(fake.transport())
    monkeypatch.setattr(get_settings(), "mock_crs", False)


def vendor_t():
    return Vendor(id="ven_t", name="Test Co", trade="x", email_domain="test.example")


def settle_fixture_call(session):
    session.get(VerificationCall, "cal_t").outcome = CallOutcome.no_answer  # so a new call may start
    session.commit()


def crs_audit(session):
    return [a for a in session.exec(select(AuditLog).where(AuditLog.entity_id == "pay_t", AuditLog.action == verify.CRS_ACTION))]


# ---------------------------------------------------------------- login, token cache, refresh


def test_crs_login_once_and_the_token_is_cached(crs):
    for _ in range(3):
        run(identity.get_client().post("/fraud-finder/fraud-finder", {"email": "grace.nakamura@example.com"}))
    assert crs.calls.count("/users/login") == 1 and crs.tokens == 1


def test_crs_401_refreshes_the_token_or_logs_in_again(crs):
    crs.expire_first_token = True
    out, rid = run(identity.get_client().post("/fraud-finder/fraud-finder", {"email": "grace.nakamura@example.com"}))
    assert out["risk"]["score"] == "9" and rid and crs.calls.count("/users/refresh-token") == 1 and crs.tokens == 2  # refresh refused (premature): re-login
    identity.set_transport(None)
    crs2 = Crs(expire_first_token=True)
    crs2.refresh_ok = True
    identity.set_transport(crs2.transport())
    run(identity.get_client().post("/fraud-finder/fraud-finder", {"email": "grace.nakamura@example.com"}))
    assert crs2.calls.count("/users/login") == 1 and crs2.calls.count("/users/refresh-token") == 1  # the refresh worked: no second login


def test_crs_without_credentials_is_unavailable_not_a_pass(monkeypatch):
    monkeypatch.setenv("CRS_USERNAME", "")
    monkeypatch.setenv("CRS_PASSWORD", "")
    identity.set_transport(Crs().transport())
    out = run(identity.check_vendor_for(vendor_t()))
    assert out["status"] == "review" and all(c["reasons"] == ["crs_unavailable"] for c in out["checks"])
    identity.set_transport(None)


# ---------------------------------------------------------------- the three checks


def test_crs_three_checks_for_the_vendor_pass_and_keep_no_personal_data(crs):
    out = run(identity.check_vendor_for(vendor_t(), {"request_email": "ar@test.example", "phones": ["+14155550142"]}))
    assert out["status"] == "pass" and out["persona"] == "P19" and out["subject"] == "vendor" and out["dial_index"] == 0
    assert [c["name"] for c in out["checks"]] == ["reverse_phone", "fraud_finder", "identity_verification"]
    assert all(c["result"] == "pass" and c["crs_request_id"].startswith("req-") for c in out["checks"]) and out["checks"][1]["score"] == 9
    dumped = _json.dumps(out)
    assert not any(secret in dumped for secret in CRS_SECRETS) and "NAKAMURA" not in dumped and "GRACE" not in dumped


def test_crs_lookalike_requester_uses_the_attacker_persona_and_fails(crs):
    out = run(identity.check_vendor_for(vendor_t(), {"request_email": "ar@test-co.example", "phones": ["+14155550142"]}))
    assert out["status"] == "fail" and out["persona"] == "P13" and out["subject"] == "requester"
    by = {c["name"]: c for c in out["checks"]}
    assert by["reverse_phone"]["result"] == "pass" and by["fraud_finder"]["result"] == "fail" and by["fraud_finder"]["score"] == 88
    assert by["identity_verification"]["result"] == "fail" and "SSN not associated with the name" in by["identity_verification"]["reasons"]
    reasons = identity.hold_reasons(out)
    assert any(r.startswith("CRS fraud finder fail") for r in reasons) and not any("KAYLA" in r or "666" in r for r in reasons)
    alt = run(identity.check_vendor_for(vendor_t(), {"request_email": "ar@test-co.example", "reply_to": "boss@elsewhere.example"}))
    assert alt["persona"] == "P12"  # Reply-To differs from the sender: the second attacker case


def test_crs_unexpected_answers_are_review_never_pass():
    assert identity.parse_reverse({}, identity.SANDBOX_PERSONAS["P19"], None)["result"] == "review"
    assert identity.parse_fraud_finder({"risk": {}}, None)["result"] == "review"
    assert identity.parse_transunion({"addOnProducts": []}, None)["result"] == "review"
    assert identity.parse_fraud_finder({"risk": {"score": "45"}}, None)["result"] == "review"


def test_crs_timeout_is_review_and_never_pass(crs):
    crs.fail_all = True
    out = run(identity.check_vendor_for(vendor_t(), {"request_email": "ar@test.example", "phones": ["+14155550142"]}))
    assert out["status"] == "review" and all(c["reasons"] == ["crs_unavailable"] for c in out["checks"]) and out["dial_index"] == 0  # still calls
    assert identity.hold_reasons(out)[0] == "CRS reverse phone review: CRS unavailable"
    res = run(identity.RealIdentityChecker().check(vendor_t()))
    assert res.status == "unverified"  # the IdentityResult path used by the payment run and the vendor card


def test_crs_results_are_cached_and_shared_between_concurrent_callers(crs):
    async def go():
        return await asyncio.gather(*(identity.check_vendor_for(vendor_t(), {"request_email": "ar@test.example", "phones": ["+14155550142"]}) for _ in range(5)))

    run(go())
    assert sorted(set(crs.calls)) == ["/accurate-append/reverse", "/fraud-finder/fraud-finder", "/transunion/identity-manager-verification/basic", "/users/login"]
    assert len(crs.calls) == 4  # one login and one request per check for five callers
    run(identity.check_vendor_for(vendor_t(), {"request_email": "ar@test.example", "phones": ["+14155550142"]}))
    assert len(crs.calls) == 4  # and a later caller hits the cache


def test_crs_real_checker_maps_to_the_identity_result(crs):
    res = run(identity.RealIdentityChecker().check(vendor_t()))
    assert res.status == "verified" and res.source == "crs-sandbox" and res.test_identity_id == "P19" and res.summary.startswith("CRS identity check: pass")


# ---------------------------------------------------------------- the call decision


def call_world(session, monkeypatch, sender="ar@test-co.example", answer="Yes, we did"):
    held_world(session)
    settle_fixture_call(session)
    session.get(Message, "msg_t").from_addr = sender
    session.get(Message, "msg_t").is_attack = sender != "ar@test.example"
    session.commit()
    monkeypatch.setattr(verify, "MOCK_STEP_DELAY", 0)
    verify.MOCK_ANSWERS["pay_t"] = answer


@pytest.fixture
def phones(monkeypatch, allowed):
    monkeypatch.setattr(contacts, "MOCK_OVERRIDES", {"ven_t": "+14155550100"})
    yield
    verify.MOCK_ANSWERS.clear()


def held_events(monkeypatch):
    seen = []
    orig = verify.ev.emit

    async def spy(e):
        seen.append(e)
        return await orig(e)

    monkeypatch.setattr(verify.ev, "emit", spy)
    return seen


def test_crs_pass_and_a_confirmed_call_releases_and_pays(session, crs, phones, monkeypatch):
    use_crs(monkeypatch)
    call_world(session, monkeypatch, sender="ar@test.example")
    res = run(verify.start_verification("pay_t", session))
    assert res.outcome == CallOutcome.confirmed and res.payment_status == PaymentStatus.pending  # released
    assert crs_audit(session)[0].detail_json["status"] == "pass"
    run(payments.pay_payment(session, "pay_t"))
    assert status(session).status == PaymentStatus.paid


@pytest.mark.parametrize("fraud_score,expected", [(88, "fail"), (45, "review")])
def test_crs_review_or_fail_keeps_a_confirmed_call_held_with_the_crs_reasons(session, crs, phones, monkeypatch, fraud_score, expected):
    crs.fraud_p19 = fraud_score
    use_crs(monkeypatch)
    call_world(session, monkeypatch, sender="ar@test.example" if expected == "review" else "ar@test-co.example")
    seen = held_events(monkeypatch)
    res = run(verify.start_verification("pay_t", session))
    assert res.outcome == CallOutcome.confirmed and res.payment_status == PaymentStatus.held  # the call happened, money did not move
    assert crs_audit(session)[0].detail_json["status"] == expected
    reasons = " | ".join(r for e in seen if e.type == "payment.held" for r in e.reasons)
    assert "CRS fraud finder" in reasons and f"the CRS identity check is {expected}" in reasons
    with pytest.raises(payments.TransferRefused):
        run(payments.pay_payment(session, "pay_t"))
    assert "held_after_verification" in actions(session)


def test_crs_denied_call_blocks_whatever_crs_said(session, crs, phones, monkeypatch):
    use_crs(monkeypatch)
    call_world(session, monkeypatch, sender="ar@test.example", answer="No, we never changed banks")
    res = run(verify.start_verification("pay_t", session))
    assert res.outcome == CallOutcome.denied and status(session).status == PaymentStatus.blocked


def test_crs_timeout_still_calls_and_a_confirmed_call_stays_held(session, crs, phones, monkeypatch):
    crs.fail_all = True
    use_crs(monkeypatch)
    call_world(session, monkeypatch, sender="ar@test.example")
    res = run(verify.start_verification("pay_t", session))
    assert res.outcome == CallOutcome.confirmed and res.payment_status == PaymentStatus.held
    assert crs_audit(session)[0].detail_json["status"] == "review"


class SpyCaller:
    dialed: list[str] = []

    async def call(self, phone, question_last4, vendor_name, is_attack, payment_id):
        SpyCaller.dialed.append(phone)
        return CallOutcome.confirmed, [{"speaker": "vendor", "text": "Yes"}]


def test_crs_reverse_fail_means_that_number_is_not_dialed_and_the_next_one_is(session, crs, phones, monkeypatch):
    crs.reverse_script = [[]]  # the first number is not listed to the contact; the second is (the default answer)
    use_crs(monkeypatch)
    call_world(session, monkeypatch, sender="ar@test.example")
    SpyCaller.dialed = []
    monkeypatch.setattr(verify, "get_caller", lambda: SpyCaller())
    res = run(verify.start_verification("pay_t", session))
    assert SpyCaller.dialed == ["+14155550100"] and res.number_flagged  # the on-file +14155550142 was skipped
    assert crs_audit(session)[0].detail_json["dial_index"] == 1


def test_crs_reverse_fail_on_every_number_dials_nothing_and_holds_for_the_controller(session, crs, phones, monkeypatch):
    crs.reverse_script = [[], []]
    use_crs(monkeypatch)
    call_world(session, monkeypatch, sender="ar@test.example")
    SpyCaller.dialed = []
    monkeypatch.setattr(verify, "get_caller", lambda: SpyCaller())
    seen = held_events(monkeypatch)
    res = run(verify.start_verification("pay_t", session))
    assert SpyCaller.dialed == [] and res.needs_controller and res.payment_status == PaymentStatus.held and not res.in_progress
    assert "verification_not_dialed" in actions(session)
    assert any("does not belong to the vendor's known contact" in r for e in seen if e.type == "payment.held" for r in e.reasons)
    assert not [e for e in seen if e.type == "call.started"]


def test_mock_crs_behaves_exactly_as_before(session, crs, phones, monkeypatch):
    assert get_settings().mock_crs is True  # the default
    call_world(session, monkeypatch, sender="ar@test-co.example")  # a lookalike sender: only a real CRS would object
    res = run(verify.start_verification("pay_t", session))
    assert res.outcome == CallOutcome.confirmed and res.payment_status == PaymentStatus.pending
    assert crs.calls == [] and crs_audit(session) == []


def test_crs_logs_and_audit_never_hold_a_token_password_or_personal_field(session, crs, phones, monkeypatch, caplog):
    caplog.set_level(logging.DEBUG)
    crs.expire_first_token = True
    use_crs(monkeypatch)
    call_world(session, monkeypatch, sender="ar@test-co.example")
    run(verify.start_verification("pay_t", session))
    audit = " ".join(str(a.detail_json) for a in session.exec(select(AuditLog)))
    for secret in CRS_SECRETS + ("KAYLA", "BRENNAN", "grace.nakamura", "kb.9921x"):
        assert secret not in caplog.text and secret not in audit, secret


def test_vendor_identity_endpoint_keeps_the_vendor_and_the_request_apart(fdb, crs, monkeypatch):
    client, eng = fdb
    assert client.get("/api/vendors/ven_nope/identity").status_code == 404
    assert client.get("/api/vendors/ven_t/identity").json() == {"status": None, "vendor": None, "latest_request": None}
    use_crs(monkeypatch)
    monkeypatch.setattr(verify, "MOCK_STEP_DELAY", 0)
    monkeypatch.setattr(contacts, "MOCK_OVERRIDES", {"ven_t": "+14155550100"})
    monkeypatch.setattr(get_settings(), "allowed_call_numbers", "+14155550142")
    with Session(eng) as s:
        settle_fixture_call(s)
        run(verify.start_verification("pay_t", s))  # the request comes from the lookalike ar@test-co.example
    body = client.get("/api/vendors/ven_t/identity").json()
    v, r = body["vendor"], body["latest_request"]
    assert body["status"] == v["status"] == "pass" and v["persona"] == "P19"  # the vendor itself is fine
    assert [c["name"] for c in v["checks"]] == ["reverse_phone", "owner_identity_verification"]
    assert v["summary"].startswith("vendor Test Co clear")
    assert r["status"] == "fail" and r["persona"] == "P13" and r["requested_by_domain"] == "test-co.example" and r["payment_id"] == "pay_t"
    assert [c["name"] for c in r["checks"]] == ["fraud_finder", "identity_verification"]
    assert r["summary"].startswith("request from test-co.example flagged: ") and "email risk score 88" in r["summary"]
    assert not any(secret in _json.dumps(body) for secret in CRS_SECRETS + ("KAYLA", "BRENNAN"))


def test_vendor_identity_endpoint_for_a_clean_request_shows_both_clear(fdb, crs, monkeypatch):
    client, eng = fdb
    use_crs(monkeypatch)
    monkeypatch.setattr(verify, "MOCK_STEP_DELAY", 0)
    monkeypatch.setattr(contacts, "MOCK_OVERRIDES", {"ven_t": "+14155550100"})
    monkeypatch.setattr(get_settings(), "allowed_call_numbers", "+14155550142")
    with Session(eng) as s:
        settle_fixture_call(s)
        s.get(Message, "msg_t").from_addr = "ar@test.example"
        s.commit()
        run(verify.start_verification("pay_t", s))
    body = client.get("/api/vendors/ven_t/identity").json()
    assert body["status"] == "pass" and body["vendor"]["status"] == "pass" and body["latest_request"]["status"] == "pass"
    assert body["latest_request"]["summary"].startswith("request from test.example clear")


def test_crs_summaries_say_which_subject_each_result_is_about(crs):
    out = run(identity.check_vendor_for(vendor_t(), {"request_email": "ar@test-co.example", "phones": ["+14155550142"]}))
    assert out["vendor"]["status"] == "pass" and out["request"]["status"] == "fail"
    assert out["request"]["summary"].startswith("request from test-co.example flagged: fraud finder: email risk score 88")
    assert "vendor fraud finder" not in out["summary"] and "request fraud finder fail" in out["summary"]
    assert any(r.endswith("(request from test-co.example)") for r in identity.hold_reasons(out))
    assert not any(r.endswith(")") and "reverse phone" in r for r in identity.hold_reasons(out))  # vendor-side reasons carry no request tag
    clean = run(identity.check_vendor_for(vendor_t()))  # no request: the vendor's own standing only
    assert clean["request"] is None and clean["vendor"]["summary"] == "vendor Test Co clear (2/2 checks passed)"


def test_the_old_crs_stub_message_is_gone():
    assert "not built yet" not in Path(identity.__file__).read_text()


# ---------------------------------------------------------------- the payment run is not slowed down by CRS


def _timed_run(tmp_path, monkeypatch, seed_template, label: str, real: bool):
    """One seeded payment run. Returns (seconds, run body, CRS requests made). CRS is mocked HTTP with 1 s of latency per request."""
    from sqlalchemy import event as sa_event

    from app.main import app
    from tests.conftest import copy_seeded

    eng = create_engine(f"sqlite:///{copy_seeded(seed_template, tmp_path, label + '.sqlite')}", connect_args={"check_same_thread": False})

    @sa_event.listens_for(eng, "connect")
    def _wal(conn, _):
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=10000")

    use_engine(monkeypatch, eng)
    monkeypatch.setattr(verify, "MOCK_STEP_DELAY", 0)
    monkeypatch.setattr(get_settings(), "mock_crs", not real)
    fake = Crs(delay=1.0)
    identity.set_transport(fake.transport())
    with TestClient(app) as client:
        t0 = time.perf_counter()
        r = client.post("/api/payment-runs")
        assert r.status_code == 202, r.text
        rid = r.json()["run_id"]
        while time.perf_counter() - t0 < 60:
            g = client.get(f"/api/payment-runs/{rid}").json()
            if g["status"] != "running":
                break
            time.sleep(0.02)
        else:
            raise AssertionError("run did not finish")
        return time.perf_counter() - t0, g, len(fake.calls)


@pytest.mark.slow
def test_a_full_run_with_real_crs_makes_few_requests_and_changes_no_outcome(tmp_path, monkeypatch, seed_template):
    """Wall-clock times are printed for information only (they swing a lot on a shared machine); the assertions test the design."""
    import statistics

    monkeypatch.setenv("CRS_USERNAME", "crs-user")
    monkeypatch.setenv("CRS_PASSWORD", "pw-secret")
    mock = [_timed_run(tmp_path, monkeypatch, seed_template, f"mock{i}", real=False) for i in range(3)]
    real = [_timed_run(tmp_path, monkeypatch, seed_template, f"real{i}", real=True) for i in range(3)]
    m_s, r_s = [x[0] for x in mock], [x[0] for x in real]
    print(f"\nrun timing (info only): MOCK_CRS=true {[round(x, 2) for x in m_s]} median {statistics.median(m_s):.2f}s; "
          f"real CRS at 1 s/request {[round(x, 2) for x in r_s]} median {statistics.median(r_s):.2f}s; "
          f"median difference {statistics.median(r_s) - statistics.median(m_s):+.2f}s; CRS requests per run {[x[2] for x in real]}")
    for _, body, n in real:
        assert n <= 8, n  # a whole seeded run makes at most 8 live CRS requests
        assert body["totals"] == mock[0][1]["totals"]  # 37 paid, 1 held, 2 blocked, as with the mock
    identity.set_transport(None)


def test_the_three_checks_of_one_vendor_run_at_the_same_time(crs):
    run(identity.get_client().post("/fraud-finder/fraud-finder", {"email": "x@example.com"}))  # log in first, so only the checks are timed
    crs.delay = 1.0
    t = time.perf_counter()
    out = run(identity.check_vendor_for(vendor_t(), {"request_email": "ar@test.example", "phones": ["+14155550142"]}))
    took = time.perf_counter() - t
    assert out["status"] == "pass" and took < 1.5, took  # three 1 s requests side by side, not 3 s one after another


def test_a_second_identity_check_for_the_same_subject_makes_no_new_requests(crs):
    run(identity.check_vendor_for(vendor_t(), {"request_email": "ar@test.example", "phones": ["+14155550142"]}))
    before = len(crs.calls)
    run(identity.check_vendor_for(vendor_t(), {"request_email": "ar@test.example", "phones": ["+14155550142"]}))
    assert len(crs.calls) == before
    assert run(identity.RealIdentityChecker().check(vendor_t())).status == "verified" and len(crs.calls) == before  # the run's path shares the cache


def test_the_runs_identity_step_gives_up_after_4_seconds_and_says_unverified(crs, monkeypatch):
    crs.delay = 30.0  # CRS hangs
    t = time.perf_counter()
    res = run(identity.RealIdentityChecker().check(vendor_t()))
    took = time.perf_counter() - t
    assert res.status == "unverified" and "crs_unavailable" in res.flags and 3.5 <= took < 4.5, took
