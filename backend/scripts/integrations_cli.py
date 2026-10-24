"""Integration smoke tests. Run from backend/: python -m scripts.integrations_cli <command>

Smoke commands always use the REAL API regardless of the MOCK flags. They spend trial minutes and
need real keys in .env.
"""

import argparse
import asyncio
import os
import sys
import time

TEMPLATE_URL = "https://webhooks.twilio.com/v1/Voice/Template/voice_text_to_speech"
TERMINAL = {"completed", "failed", "busy", "no-answer", "canceled"}


def _result(ok: bool, message: str) -> int:
    print(f"{'PASS' if ok else 'FAIL'}: {message}")
    return 0 if ok else 1


def _real_settings(*flags: str):
    from app.config import get_settings

    return get_settings().model_copy(update={f"mock_{f}": False for f in flags})


def _poll(settings, sid: str, timeout: int = 90) -> str:
    from twilio.rest import Client

    client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
    end, status = time.time() + timeout, "unknown"
    while time.time() < end:
        status = client.calls(sid).fetch().status
        if status in TERMINAL:
            break
        time.sleep(2)
    return status


def smoke_twilio(_args) -> int:
    from app.integrations import SMOKE_CLIP_TEXT
    from app.services import voice

    s = _real_settings("twilio", "cartesia")
    missing = [n for n, v in {"TWILIO_ACCOUNT_SID": s.twilio_account_sid, "TWILIO_AUTH_TOKEN": s.twilio_auth_token,
                              "TWILIO_FROM_NUMBER": s.twilio_from_number, "DEMO_VENDOR_PHONE": s.demo_vendor_phone,
                              "PUBLIC_BASE_URL": s.public_base_url}.items() if not v]
    if missing:
        return _result(False, "missing in .env: " + ", ".join(missing))
    print("Reminder: uvicorn and ngrok must be running so Twilio can reach PUBLIC_BASE_URL.")

    async def run() -> int:
        print("Call 1: Twilio template TwiML (rings DEMO_VENDOR_PHONE)")
        sid = await voice.place_call(s.demo_vendor_phone, TEMPLATE_URL, settings=s)
        status = await asyncio.to_thread(_poll, s, sid)
        print(f"  call 1 ended: {status}")
        if status != "completed":
            return _result(False, f"call 1 did not complete ({status})")
        await asyncio.to_thread(input, "Press Enter to place call 2 (our own TwiML + Cartesia clip)... ")
        await voice.tts_clip(SMOKE_CLIP_TEXT, s)  # pre-generate before dialing
        sid = await voice.place_call(s.demo_vendor_phone, f"{s.public_base_url.rstrip('/')}/api/voice/smoke-twiml", settings=s)
        status = await asyncio.to_thread(_poll, s, sid)
        print(f"  call 2 ended: {status}")
        if status != "completed":
            return _result(False, f"call 2 did not complete ({status}); check uvicorn and ngrok")
        heard = (await asyncio.to_thread(input, "Did you hear our Say sentence and then the clip? [y/N] ")).strip().lower() == "y"
        if heard:
            return _result(True, "custom TwiML from our own server works on this trial")
        print("Hint: open the ngrok inspector at http://127.0.0.1:4040 and look at Twilio's request to "
              "/api/voice/smoke-twiml and the response it got.")
        return _result(False, "call 2 completed but our custom TwiML was not played")

    return asyncio.run(run())


def smoke_cartesia(_args) -> int:
    from app.services import voice

    s = _real_settings("cartesia")
    if not (s.cartesia_api_key and s.cartesia_voice_id):
        return _result(False, "CARTESIA_API_KEY or CARTESIA_VOICE_ID is empty")
    try:
        path = asyncio.run(voice.tts_file("This is Countersign testing", s))
    except Exception as exc:  # noqa: BLE001
        return _result(False, f"Cartesia request failed: {type(exc).__name__}")
    return _result(path.exists() and path.stat().st_size > 1000, f"wrote {path}")


def smoke_nessie(_args) -> int:
    from app.services import payments

    if not payments.get_settings().nessie_api_key:
        print("SKIP: NESSIE_API_KEY is empty")
        return 0
    try:
        customers = payments._nessie("GET", "/customers")
        print(f"  {len(customers)} customers")
        cust = payments._created(payments._nessie("POST", "/customers", json={
            "first_name": "Smoke", "last_name": "Test",
            "address": {"street_number": "1", "street_name": "Sandbox St", "city": "San Francisco", "state": "CA", "zip": "94123"}}))
        acct = payments._created(payments._nessie("POST", f"/customers/{cust['_id']}/accounts", json={
            "type": "Checking", "nickname": "countersign-smoke", "rewards": 0, "balance": 100}))
        print(f"  created test account {acct['_id']}")
    except Exception as exc:  # noqa: BLE001
        return _result(False, str(exc))
    return _result(True, "Nessie customers listed and a test account created")


def setup_nessie(_args) -> int:
    os.environ["MOCK_NESSIE"] = "false"
    from app.config import get_settings

    get_settings.cache_clear()
    from sqlmodel import Session

    from app.db import engine
    from app.services import payments

    if not get_settings().nessie_api_key:
        return _result(False, "NESSIE_API_KEY is empty")
    try:
        with Session(engine) as session:
            out = payments.setup_sandbox(session)
    except Exception as exc:  # noqa: BLE001
        return _result(False, str(exc))
    return _result(True, f"sandbox ready: {out}")


def smoke_transfer(_args) -> int:
    """One real $1.00 transfer, operating account to the first vendor account. No mock fallback."""
    os.environ["MOCK_NESSIE"] = "false"
    from app.config import get_settings

    get_settings.cache_clear()
    from sqlmodel import Session, select

    from app.db import engine
    from app.models import VendorBankAccount
    from app.services import payments

    if not get_settings().nessie_api_key:
        return _result(False, "NESSIE_API_KEY is empty")
    try:
        with Session(engine) as session:
            dest = session.exec(select(VendorBankAccount).order_by(VendorBankAccount.id)).first()
        if dest is None:
            return _result(False, "no vendor_bank_accounts rows; seed the database first")
        payments._load_accounts()
        if dest.id not in payments._account_cache or payments.OPERATING_NICKNAME not in payments._account_cache:
            return _result(False, "Nessie accounts missing; run setup-nessie first")
        transfer_id = payments._real_transfer(dest.id, 1.00, "Countersign smoke transfer")
        print(f"  created transfer {transfer_id} to account nicknamed {dest.id}")
        got = payments.fetch_transfer(dest.id, transfer_id)
        if got is None:
            return _result(False, f"transfer {transfer_id} was created but not found on the vendor account")
        print(f"  fetched back: id={got.get('id') or got.get('_id')} status={got.get('status')} amount={got.get('amount')}")
    except Exception as exc:  # noqa: BLE001
        return _result(False, str(exc))  # includes status and response body, never the key
    return _result(True, f"transfer {transfer_id} status {got.get('status')}")


def create_test_hold(_args=None) -> int:
    """A held payment that asks for a new bank account, with the demo vendor phone as the vendor's on-file contact."""
    from datetime import timedelta

    from sqlmodel import Session, select

    from app.config import get_settings
    from app.db import create_all, engine
    from app.models import Invoice, Message, Payment, PaymentRun, PaymentStatus, Vendor, VendorBankAccount, VendorContact, new_id, utcnow
    from app.services import contacts, verify

    s = get_settings()
    if not s.demo_vendor_phone:
        return _result(False, "DEMO_VENDOR_PHONE is empty in .env")
    create_all()
    with Session(engine) as session:
        vendor = session.exec(select(Vendor).where(Vendor.name == "Summit Concrete")).first()
        if vendor is None:
            vendor = Vendor(name="Summit Concrete", trade="concrete", email_domain="summitconcrete.com", created_at=utcnow() - timedelta(days=400))
            session.add(vendor)
            session.flush()
        if verify.current_verified_account(session, vendor.id) is None:  # minimal onboarding account (the seed has its own)
            session.add(VendorBankAccount(vendor_id=vendor.id, routing_hash="hash_cli_onboarding", account_last4="2204", bank_name="Onboarding Bank",
                                          valid_from=utcnow() - timedelta(days=300)))
        phone_row = session.exec(select(VendorContact).where(VendorContact.vendor_id == vendor.id, VendorContact.phone == s.demo_vendor_phone,
                                                              VendorContact.source == "on_file")).first()
        if phone_row is None:
            phone_row = verify._store_contact(session, vendor.id, contacts.IndependentContact.model_construct(
                phone=s.demo_vendor_phone, source="on_file", source_url=None, found_at=utcnow() - timedelta(days=200)))
        phone_row.last_verified = utcnow()  # the most recently verified on-file contact, so select_number picks it
        session.add(phone_row)
        session.commit()
        new_account = verify.record_requested_destination(session, vendor.id, "hash_cli_requested", "7781", "Requested Bank")
        suffix = new_id("cli")[-6:]
        msg = Message(thread_id=new_id("thr"), vendor_id=vendor.id, from_addr="ar@summit-concrete.co", subject="We changed banks", body="Please use our new account.", is_attack=True)
        session.add(msg)
        session.flush()
        inv = Invoice(vendor_id=vendor.id, message_id=msg.id, number=f"CLI-{suffix}", amount_usd=18450.0, due_date=(utcnow() + timedelta(days=7)).date(),
                      remittance_json={"bank_name": "Requested Bank", "routing_hash": "hash_cli_requested", "account_last4": "7781"})
        run = PaymentRun()
        session.add_all([inv, run])
        session.flush()
        pay = Payment(run_id=run.id, invoice_id=inv.id, amount_usd=18450.0, destination_account_id=new_account, status=PaymentStatus.held)
        session.add(pay)
        session.commit()
        print(f"payment_id={pay.id}")
        print(f"run_id={run.id}")
    return _result(True, "held payment created; now run: call-test <payment_id>")


def call_test(args) -> int:
    """Start the verification call through the running server, then print each event until the outcome arrives (120 s max)."""
    import httpx
    from sqlmodel import Session, select

    from app.db import engine
    from app.models import Event

    base = args.api.rstrip("/")
    with Session(engine) as session:
        seen = set(session.exec(select(Event.id)).all())
    try:
        resp = httpx.post(f"{base}/api/verifications/{args.payment_id}/call", timeout=30)
    except httpx.HTTPError as exc:
        return _result(False, f"cannot reach the server at {base}: {type(exc).__name__}")
    if resp.status_code >= 300:
        return _result(False, f"{resp.status_code}: {resp.text[:200]}")
    info = resp.json()
    if info["mode"] == "web":
        print("web mode: open the vendor phone page on your phone (python -m scripts.integrations_cli vendor-phone-url) and tap Answer")
    print(f"started ({info['mode']}), run {info['run_id']}; waiting for events (up to 120 s)")
    deadline, no_answers, final, grace = time.time() + 120, 0, None, None
    while time.time() < deadline:
        with Session(engine) as session:
            rows = session.exec(select(Event).where(Event.run_id == info["run_id"]).order_by(Event.at)).all()
        for e in rows:
            if e.id in seen:
                continue
            seen.add(e.id)
            payload = e.payload or {}
            if payload.get("payment_id") not in (None, args.payment_id):
                continue
            print(f"  {e.type}: " + ", ".join(f"{k}={v}" for k, v in payload.items() if k != "payment_id"))
            if e.type == "call.outcome":
                if payload["outcome"] == "no_answer":
                    no_answers += 1
                if payload["outcome"] != "no_answer" or no_answers >= 2:
                    final, grace = payload["outcome"], time.time() + 8  # a little longer for payment.paid / payment.blocked
        if grace and time.time() > grace:
            break
        time.sleep(1)
    if final is None:
        return _result(False, "no final outcome within 120 s (a no_answer retry may still be pending)")
    return _result(True, f"final outcome: {final}")


def vendor_phone_url(_args) -> int:
    """The softphone link for Summit Concrete. This is the ONLY place VENDOR_PHONE_KEY is printed: treat the output as a secret."""
    from urllib.parse import quote

    from sqlmodel import Session, select

    from app.config import get_settings
    from app.db import engine
    from app.models import Vendor
    from app.services import voice

    base, key = get_settings().public_base_url.rstrip("/"), voice._env("VENDOR_PHONE_KEY")
    missing = [n for n, v in {"PUBLIC_BASE_URL": base, "VENDOR_PHONE_KEY": key}.items() if not v]
    if missing:
        return _result(False, "missing in .env: " + ", ".join(missing))
    with Session(engine) as session:
        vendor = session.exec(select(Vendor).where(Vendor.name == "Summit Concrete")).first()
    if vendor is None:
        return _result(False, "no vendor named Summit Concrete; seed the database or run create-test-hold")
    print(f"{base}/api/voice/vendor-phone/{vendor.id}?k={quote(key)}")
    print("Note: this is the only place the key is printed. Anyone with this link can answer the verification call.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name, fn in {"smoke-twilio": smoke_twilio, "smoke-cartesia": smoke_cartesia,
                     "smoke-nessie": smoke_nessie, "setup-nessie": setup_nessie, "smoke-transfer": smoke_transfer}.items():
        sub.add_parser(name).set_defaults(fn=fn)
    sub.add_parser("create-test-hold").set_defaults(fn=create_test_hold)
    sub.add_parser("vendor-phone-url").set_defaults(fn=vendor_phone_url)
    ct = sub.add_parser("call-test")
    ct.add_argument("payment_id")
    ct.add_argument("--api", default="http://127.0.0.1:8000", help="base URL of the running backend")
    ct.set_defaults(fn=call_test)
    args = parser.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
