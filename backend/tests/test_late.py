"""Real-mode calls finish after the run: the run holds the payment ("verification call in progress"), the webhook applies the outcome later."""

import asyncio

import pytest
from sqlmodel import Session, select

from app import events as ev
from app.config import Settings, get_settings
from app.models import Attack, AttackResult, AuditLog, Payment, PaymentRun, PaymentStatus, VendorContact, VerificationCall
from app.services import ask, run, verify, voice
from tests.test_run import BANK, CEO, POISON, env, go  # noqa: F401  (env is a fixture: a private seeded database + client)


@pytest.fixture
def real_calls(env, monkeypatch, tmp_path):
    """Real Twilio and Cartesia mode with the network faked: calls are 'placed', nothing is dialed."""
    client, eng = env
    monkeypatch.setattr(voice, "AUDIO_DIR", tmp_path / "audio")
    cfg = get_settings()
    monkeypatch.setattr(cfg, "mock_twilio", False)
    monkeypatch.setattr(cfg, "mock_cartesia", False)
    monkeypatch.setattr(cfg, "public_base_url", "https://pub.example")
    with Session(eng) as s:  # the planted attacks' vendors each have their own on-file number; allow them for the fake calls
        phones = {c.phone for c in s.exec(select(VendorContact).where(VendorContact.vendor_id.in_(["ven_summit", "ven_northside"])))}
    monkeypatch.setattr(cfg, "allowed_call_numbers", ", ".join(sorted(phones | {"+14155550142"})))
    dialed = []

    async def fake_place(to, url, status_callback=None, settings=None):
        dialed.append(to)
        return "CAtest"

    async def fake_clip(text, settings=None):
        return "https://pub.example/x.wav"

    monkeypatch.setattr(voice, "place_call", fake_place)
    monkeypatch.setattr(voice, "tts_clip", fake_clip)
    queue = ev.broadcaster.subscribe(ev.LEADERBOARD)
    yield client, eng, queue, dialed
    ev.broadcaster.unsubscribe(ev.LEADERBOARD, queue)


def drain(queue):
    out = []
    while not queue.empty():
        out.append(queue.get_nowait())
    return out


def open_call(eng, pid):
    with Session(eng) as s:
        return s.exec(select(VerificationCall).where(VerificationCall.payment_id == pid, VerificationCall.outcome.is_(None))).one().id


def answer(client, eng, pid, speech):
    cid = open_call(eng, pid)
    tok = voice._token_path(cid).read_text().strip()
    r = client.post(f"/api/voice/gather/{cid}?t={tok}", data={"SpeechResult": speech})
    assert r.status_code == 200, r.text
    return cid


def totals(client, run_id):
    t = client.get(f"/api/payment-runs/{run_id}").json()["totals"]
    return t["paid"], t["held"], t["blocked"]


def status(eng, pid):
    with Session(eng) as s:
        return s.get(Payment, pid).status


def test_in_progress_calls_leave_the_payments_held_and_the_run_reports_them_held(real_calls):
    client, eng, queue, dialed = real_calls
    body, done = go(client)
    assert totals(client, body["run_id"]) == (37, 2, 1)  # bank change and CEO pressure wait for their calls; the poisoned PDF is blocked
    assert status(eng, BANK) == status(eng, CEO) == PaymentStatus.held and status(eng, POISON) == PaymentStatus.blocked
    assert len(dialed) == 2
    with Session(eng) as s:
        reasons = {e.payload["payment_id"]: e.payload["reasons"] for e in s.exec(select(ev.Event).where(ev.Event.run_id == body["run_id"], ev.Event.type == "payment.held"))}
        assert reasons[BANK][-1] == "verification call in progress"
        assert s.exec(select(AuditLog).where(AuditLog.entity_id == BANK, AuditLog.action == "verification_in_progress")).first()
        assert not any(c.outcome for c in s.exec(select(VerificationCall).where(VerificationCall.payment_id == BANK)))  # the placeholder is not an outcome
    types = [m["type"] for m in drain(queue)]
    assert types.count("call.started") == 2  # the board gets them even though no one is on the run stream


def test_a_late_denial_blocks_updates_everything_and_reaches_the_global_channel(real_calls):
    client, eng, queue, _ = real_calls
    body, _ = go(client)
    run_id = body["run_id"]
    ask.clear_cache()
    first = client.post(f"/api/payments/{BANK}/ask", json={"question": "why was this held"}).json()
    drain(queue)
    answer(client, eng, BANK, "No, we never changed banks")
    assert status(eng, BANK) == PaymentStatus.blocked
    assert totals(client, run_id) == (37, 1, 2)  # the run's totals follow the late outcome
    with Session(eng) as s:
        assert s.exec(select(AuditLog).where(AuditLog.entity_id == BANK, AuditLog.action == "blocked_by_verification")).first()
        assert s.exec(select(AuditLog).where(AuditLog.entity == "run", AuditLog.entity_id == run_id, AuditLog.action == "totals_updated")).first()
        atk = s.exec(select(Attack).where(Attack.payload_ref == "msg_atk_bank_change")).one()
        assert atk.result == AttackResult.caught and atk.detail_json["outcome"] == "blocked"
        saved = s.get(PaymentRun, run_id).totals_json
        assert (saved["paid"], saved["held"], saved["blocked"]) == (37, 1, 2)
    msgs = drain(queue)
    types = [m["type"] for m in msgs]
    assert "call.outcome" in types and "payment.blocked" in types and "run.updated" in types and "call.transcript" in types
    upd = next(m for m in msgs if m["type"] == "run.updated")
    assert (upd["run_id"], upd["paid"], upd["held"], upd["blocked"]) == (run_id, 37, 1, 2)
    with Session(eng) as s:  # and they were stored on the run channel too
        stored = [e.type for e in s.exec(select(ev.Event).where(ev.Event.run_id == run_id).order_by(ev.Event.at))]
    assert stored[-1] in ("run.updated", "attack.logged") and "run.updated" in stored
    second = client.post(f"/api/payments/{BANK}/ask", json={"question": "why was this held"}).json()
    assert "blocked" in second["answer"] and second["answer"] != first["answer"]  # re-warmed for the seeded attack, so it may be a cache hit
    ask.invalidate(BANK)
    assert not [k for k in ask._cache if k[0] == BANK]


def test_a_late_confirmation_pays_and_the_attack_counts_as_missed(real_calls):
    client, eng, queue, _ = real_calls
    body, _ = go(client)
    drain(queue)
    answer(client, eng, BANK, "Yes, that change is correct")
    assert status(eng, BANK) == PaymentStatus.paid
    assert totals(client, body["run_id"]) == (38, 1, 1)
    with Session(eng) as s:
        atk = s.exec(select(Attack).where(Attack.payload_ref == "msg_atk_bank_change")).one()
        assert atk.result == AttackResult.missed and atk.detail_json["outcome"] == "paid"
    types = [m["type"] for m in drain(queue)]
    assert "payment.paid" in types and "run.updated" in types and "call.outcome" in types


def test_an_unclear_late_answer_keeps_the_hold_and_changes_no_totals(real_calls):
    client, eng, queue, _ = real_calls
    body, _ = go(client)
    drain(queue)
    cid = open_call(eng, CEO)
    tok = voice._token_path(cid).read_text().strip()
    # r=1: the call has already used its single clarifying re-ask, so this unclear answer is final
    r = client.post(f"/api/voice/gather/{cid}?r=1&t={tok}", data={"SpeechResult": "um, who is this?"})
    assert r.status_code == 200, r.text
    assert status(eng, CEO) == PaymentStatus.held and totals(client, body["run_id"]) == (37, 2, 1)
    types = [m["type"] for m in drain(queue)]
    assert "call.outcome" in types and "run.updated" not in types  # nothing in the run changed


def test_the_run_stream_still_works_in_mock_mode_and_global_channel_gets_call_events(env):
    client, eng = env
    queue = ev.broadcaster.subscribe(ev.LEADERBOARD)
    try:
        body, _ = go(client)
        types = [m["type"] for m in drain(queue)]
    finally:
        ev.broadcaster.unsubscribe(ev.LEADERBOARD, queue)
    assert totals(client, body["run_id"]) == (37, 1, 2)
    assert types.count("call.started") == 2 and "call.outcome" in types and "payment.blocked" in types
    assert "payment.paid" not in types  # clean payments are not call-linked, so they stay on the run channel


def test_config_flags_replace_the_environment_reads(monkeypatch):
    assert Settings(mock_twilio=True).call_token_required is False
    assert Settings(mock_twilio=False).call_token_required is True
    assert Settings(mock_twilio=False, twilio_require_call_token=False).call_token_required is False
    assert Settings(twilio_validate_signatures=False).twilio_validate_signatures is False
    monkeypatch.setenv("TWILIO_REQUIRE_CALL_TOKEN", "")  # a blank line in .env means "default"
    assert Settings(mock_twilio=False).twilio_require_call_token is None
    monkeypatch.setenv("TWILIO_VALIDATE_SIGNATURES", "true")
    assert Settings().twilio_validate_signatures is True
    import inspect

    from app import integrations
    assert "getenv" not in inspect.getsource(integrations)
