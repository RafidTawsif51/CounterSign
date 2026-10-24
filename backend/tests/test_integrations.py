import asyncio
import wave

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from app.config import get_settings
from app import db
from app.db import create_all
from app.models import (
    AuditLog,
    Invoice,
    Payment,
    PaymentRun,
    PaymentStatus,
    Vendor,
    VendorBankAccount,
    utcnow,
)
from app.services import payments, verify, voice

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
