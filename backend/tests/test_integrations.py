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
    ("uh what", CallOutcome.unclear, False),
    ("", CallOutcome.unclear, False),
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
    assert 'input="speech"' in first and 'timeout="6"' in first and "/api/voice/gather/cal_t" in first and "retry=1" in first
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
        res = run(verify.start_verification("pay_t", s))
        s.expire_all()
        assert res.in_progress and res.payment_status == PaymentStatus.held and not res.needs_controller
        calls = s.exec(select(VerificationCall).where(VerificationCall.payment_id == "pay_t")).all()
        assert len(calls) == 2 and sum(c.outcome is None for c in calls) == 2  # the fixture call plus the new one, both open
        new = next(c for c in calls if c.id != "cal_t")
        assert s.get(Payment, "pay_t").status == PaymentStatus.held
    tok = voice._token_path(new.id).read_text().strip()
    assert voice.check_call_token(new.id, tok)
    assert dialed == [("+14155550142", f"https://pub.example/api/voice/twiml/{new.id}?t={tok}",
                       f"https://pub.example/api/webhooks/twilio/status?call_id={new.id}&t={tok}")]
    with Session(eng) as s:
        assert tok not in " ".join(str(a.detail_json) for a in s.exec(select(AuditLog))) and not any(tok in c for c in clips)
    assert len(clips) == 6 and any("9999" in c for c in clips)


def test_real_mode_refuses_a_number_off_the_allow_list(fdb, monkeypatch):
    _, eng = fdb
    cfg = get_settings()
    monkeypatch.setattr(cfg, "mock_twilio", False)
    monkeypatch.setattr(cfg, "mock_cartesia", False)
    monkeypatch.setattr(cfg, "allowed_call_numbers", "+14155550199")
    with Session(eng) as s:
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
