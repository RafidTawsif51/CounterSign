"""The Rob Countersign bounty inbox: Postmark webhook, secret, limits, moderation, and the same pipeline as every invoice."""

import base64
import time
from datetime import timedelta

import pytest
from sqlmodel import Session, func, select

from app.config import Settings, get_settings
from app.models import (
    Attack,
    AuditLog,
    Event,
    InjectionFinding,
    Invoice,
    Message,
    Payment,
    PaymentStatus,
    RiskAssessment,
    VendorBankAccount,
    VendorContact,
    VerificationCall,
    utcnow,
)
from app.services import bounty as bounty_mod, payments, voice
from seed import seed as seedmod
from tests.test_attacks import SECRET, evs, mail, payment_for, types, wait
from tests.test_run import env, go  # noqa: F401  (env is a fixture: a private seeded database + client)

pytestmark = pytest.mark.slow
URL = "/api/bounty/inbound"
MOD = "mod-token"
MODH = {"x-moderator-token": MOD}


@pytest.fixture()
def secret(monkeypatch):
    s = Settings(bounty_webhook_secret=SECRET, bounty_moderator_token=MOD)
    monkeypatch.setattr(bounty_mod, "get_settings", lambda: s)
    return {"x-webhook-secret": SECRET}


def basic(password=SECRET, user="postmark"):
    return {"Authorization": "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()}


def n_attacks(eng):
    with Session(eng) as s:
        return s.exec(select(func.count()).select_from(Attack)).one()


# ---------------------------------------------------------------- the signature


def test_unsigned_requests_are_rejected_and_create_nothing(env, secret):
    client, eng = env
    before = n_attacks(eng)
    assert client.post(URL, json=mail()).status_code == 401
    assert client.post(URL, json=mail(), headers=basic("wrong")).status_code == 401
    assert client.post(URL, json=mail(), headers={"x-webhook-secret": "wrong"}).status_code == 401
    assert client.post(URL, json=mail(), headers={"Authorization": "Basic !!notbase64!!"}).status_code == 401
    assert client.post(URL, json=mail(), headers={"Authorization": "Bearer " + SECRET}).status_code == 401
    assert n_attacks(eng) == before


def test_postmark_basic_auth_with_the_secret_as_password_is_accepted(env, secret):
    client, _ = env
    assert client.post(URL, json=mail("one@example.com"), headers=basic()).status_code == 200
    assert client.post(URL, json=mail("two@example.com"), headers={"x-webhook-secret": SECRET}).status_code == 200


def test_an_unconfigured_inbox_is_closed(env, monkeypatch):
    client, _ = env
    monkeypatch.setattr(bounty_mod, "get_settings", lambda: Settings(bounty_webhook_secret=""))
    assert client.post(URL, json=mail(), headers=basic("")).status_code == 503
    assert client.post(URL, json=mail(), headers={"x-webhook-secret": ""}).status_code == 503


# ---------------------------------------------------------------- limits


def test_five_per_sender_per_hour_and_variants_of_one_address_are_one_sender(env, secret):
    client, eng = env
    for addr in ("Hunter@example.com", "hunter+a@example.com", "hunter+b@example.com", "HUNTER@EXAMPLE.COM", "hunter+c@example.com"):
        assert client.post(URL, json=mail(addr), headers=secret).status_code == 200
    r = client.post(URL, json=mail("hunter+d@example.com"), headers=secret)
    assert r.status_code == 429 and int(r.headers["retry-after"]) > 3000
    assert client.post(URL, json=mail("someone.else@example.com"), headers=secret).status_code == 200
    gm = [client.post(URL, json=mail(a), headers=secret).status_code for a in ("g.h@gmail.com", "gh@gmail.com", "g.h+x@gmail.com", "gh@googlemail.com", "g.h@gmail.com", "gh@gmail.com")]
    assert gm == [200, 200, 200, 200, 200, 429]  # Gmail ignores dots and +tags: still one sender
    with Session(eng) as s:
        for a in s.exec(select(Attack)):
            a.created_at = utcnow() - timedelta(hours=2)
            s.add(a)
        s.commit()
    assert client.post(URL, json=mail("hunter@example.com"), headers=secret).status_code == 200  # an hour later


def test_body_and_attachment_limits(env, secret):
    client, eng = env
    before = n_attacks(eng)
    ok = {**mail("a1@example.com"), "TextBody": "x" * (50 * 1024)}
    assert client.post(URL, json=ok, headers=secret).status_code == 200
    too_big = {**mail("a2@example.com"), "TextBody": "x" * (50 * 1024 + 1)}
    assert client.post(URL, json=too_big, headers=secret).status_code == 413
    pdf = (seedmod.PDF_DIR / "poisoned_white_text.pdf").read_bytes()

    def att(raw, ctype="application/pdf", name="i.pdf"):
        return {"Name": name, "ContentType": ctype, "Content": base64.b64encode(raw).decode()}

    assert client.post(URL, json={**mail("a3@example.com"), "Attachments": [att(pdf)]}, headers=secret).status_code == 200
    assert client.post(URL, json={**mail("a4@example.com"), "Attachments": [att(b"hello", "text/plain", "n.txt")]}, headers=secret).status_code == 415
    assert client.post(URL, json={**mail("a5@example.com"), "Attachments": [att(b"MZ\x90 not a pdf", "application/pdf")]}, headers=secret).status_code == 415  # the bytes decide
    assert client.post(URL, json={**mail("a6@example.com"), "Attachments": [att(b"%PDF-1.4 " + b"0" * (5 * 1024 * 1024))]}, headers=secret).status_code == 413
    assert client.post(URL, json={**mail("a7@example.com"), "Attachments": [att(pdf)] * 4}, headers=secret).status_code == 413
    assert client.post(URL, json={**mail("a8@example.com"), "Attachments": [att(pdf), att(b"hello", "text/plain")]}, headers=secret).status_code == 415  # one bad file rejects the email
    assert n_attacks(eng) == before + 2  # nothing rejected was stored
    assert client.post(URL, content=b"x" * (8 * 1024 * 1024 + 1), headers={**secret, "content-type": "application/json"}).status_code == 413


def test_a_redelivered_message_id_is_not_a_second_attack(env, secret):
    client, eng = env
    first = client.post(URL, json={**mail("dup@example.com"), "MessageID": "pm-123"}, headers=secret).json()
    again = client.post(URL, json={**mail("dup@example.com"), "MessageID": "pm-123"}, headers=secret)
    assert again.status_code == 200 and again.json() == {"duplicate": True, "attack_id": first["attack_id"]}
    assert n_attacks(eng) == 1


# ---------------------------------------------------------------- saved as a message in a new thread, unverified, pending


def test_it_is_saved_in_a_new_thread_with_an_unverified_vendor_claim(env, secret):
    client, eng = env
    r = client.post(URL, json=mail(), headers=secret).json()
    wait(client, r["run_id"])
    with Session(eng) as s:
        atk = s.get(Attack, r["attack_id"])
        msg = s.get(Message, r["message_id"])
        assert atk.source.value == "bounty_email" and atk.moderation_status.value == "pending"
        assert msg.thread_id.startswith("thr_") and msg.thread_id != "thr_summit_0919"
        assert s.exec(select(func.count()).select_from(Message).where(Message.thread_id == msg.thread_id)).one() == 1  # a thread of its own
        assert atk.detail_json["vendor_claim"] == {"vendor_id": "ven_summit", "verified": False}
        claim = s.exec(select(AuditLog).where(AuditLog.entity == "attack", AuditLog.entity_id == atk.id, AuditLog.action == "bounty_received")).one()
        assert claim.detail_json["vendor_claim"] == "unverified"


# ---------------------------------------------------------------- the same pipeline as every other invoice


def test_a_bounty_email_goes_through_every_stage_of_the_normal_pipeline(env, secret):
    client, eng = env
    pdf = (seedmod.PDF_DIR / "poisoned_white_text.pdf").read_bytes()
    r = client.post(URL, json={**mail("full@example.com"), "Attachments": [{"Name": "i.pdf", "ContentType": "application/pdf", "Content": base64.b64encode(pdf).decode()}]},
                    headers=secret).json()
    wait(client, r["run_id"])
    seq = types(eng, r["run_id"])
    for stage in ("run.started", "invoice.parsed", "injection.detected", "risk.scored", "payment.blocked", "run.completed", "run.report"):
        assert stage in seq, stage
    pay = payment_for(eng, r)
    with Session(eng) as s:
        ras = s.exec(select(RiskAssessment).where(RiskAssessment.payment_id == pay.id)).one()
        assert "hidden_instructions" in ras.hard_rules_fired and ras.model_version  # the real scanner and the real assessor
        assert s.exec(select(InjectionFinding).where(InjectionFinding.invoice_id == r["invoice_id"])).first() is not None
        assert s.get(Invoice, r["invoice_id"]).extracted_json["quarantined"] is True
    assert pay.status == PaymentStatus.blocked and pay.nessie_transfer_id is None
    # the audit trail has the same stages a seeded invoice's payment has
    with Session(eng) as s:
        actions = set(s.exec(select(AuditLog.action).where(AuditLog.entity == "payment", AuditLog.entity_id == pay.id)).all())
    assert {"risk_assessed", "blocked"} <= actions


def test_a_bank_change_email_gets_the_hard_rule_and_a_verification_call(env, secret):
    client, eng = env
    r = client.post(URL, json=mail("bank@example.com"), headers=secret).json()
    wait(client, r["run_id"])
    pay = payment_for(eng, r)
    with Session(eng) as s:
        ras = s.exec(select(RiskAssessment).where(RiskAssessment.payment_id == pay.id)).one()
        assert "destination_changed" in ras.hard_rules_fired and ras.score > 0
        assert s.exec(select(VerificationCall).where(VerificationCall.payment_id == pay.id)).first() is not None
        # the account the email asked for is a candidate, never trusted
        cand = s.get(VendorBankAccount, pay.destination_account_id)
        assert cand.verified_by_call_id is None and cand.account_last4 == "1111"
    assert pay.status != PaymentStatus.paid


# ---------------------------------------------------------------- the leaderboard

def test_it_is_on_the_leaderboard_within_30_seconds_with_only_handle_and_result(env, secret):
    client, eng = env
    t0 = time.perf_counter()
    client.post(URL, json=mail("quick@example.com"), headers=secret)
    row = None
    while time.perf_counter() - t0 < 30:
        rows = client.get("/api/attacks/leaderboard").json()["attempts"]
        if rows and rows[0]["result"]:
            row = rows[0]
            break
        time.sleep(0.05)
    assert row is not None and time.perf_counter() - t0 < 30
    assert row["handle"] == "qu***" and row["result"] == "caught" and row["moderation_status"] == "pending"
    assert row["text"] is None and row["outcome"] is None and row["top_reasons"] == [] and row["amount_usd"] is None and row["paid_usd"] is None
    assert "quick@example.com" not in str(client.get("/api/attacks/leaderboard").json())


# ---------------------------------------------------------------- moderation


def test_queue_and_moderate(env, secret):
    client, eng = env
    a = client.post(URL, json=mail("mod1@example.com"), headers=secret).json()
    b = client.post(URL, json=mail("mod2@example.com"), headers=secret).json()
    wait(client, a["run_id"]), wait(client, b["run_id"])
    q = client.get("/api/bounty/queue", headers=MODH).json()
    assert q["pending_count"] == 2 and [i["id"] for i in q["items"]] == [a["attack_id"], b["attack_id"]]  # oldest first
    first = q["items"][0]
    assert first["subject"] == "Invoice from Summit Concrete" and "Hunter Bank" in first["body"] and first["claimed_vendor"]["verified"] is False
    assert first["sender"] == "mo***@example.com" and "mod1@example.com" not in str(q)

    r = client.post(f"/api/bounty/{a['attack_id']}/moderate", json={"action": "approve", "moderator": "Dev"}, headers=MODH)
    assert r.status_code == 200 and r.json()["moderation_status"] == "approved"
    board = client.get("/api/attacks/leaderboard").json()["attempts"]
    shown = next(x for x in board if x["id"] == a["attack_id"])
    assert shown["text"]["subject"] == "Invoice from Summit Concrete" and shown["top_reasons"]
    hidden = next(x for x in board if x["id"] == b["attack_id"])
    assert hidden["text"] is None and hidden["top_reasons"] == []  # still pending

    assert client.post(f"/api/bounty/{b['attack_id']}/moderate", json={"action": "hide", "moderator": "Dev"}, headers=MODH).json()["moderation_status"] == "hidden"
    assert [x["id"] for x in client.get("/api/attacks/leaderboard").json()["attempts"]] == [a["attack_id"]]
    assert client.get("/api/bounty/queue", headers=MODH).json()["pending_count"] == 0
    assert {i["id"] for i in client.get("/api/bounty/queue?status=hidden", headers=MODH).json()["items"]} == {b["attack_id"]}
    with Session(eng) as s:
        assert s.exec(select(AuditLog).where(AuditLog.entity_id == a["attack_id"], AuditLog.action == "moderation_approved")).one().actor.value == "human"
    logged = [p for ty, _, p in evs(eng, a["run_id"]) if ty == "attack.logged"]
    assert logged[-1]["moderation_status"] == "approved" and logged[-1]["attacker_name"] == "mo***"
    assert client.post("/api/bounty/atk_nope/moderate", json={"action": "hide", "moderator": "Dev"}, headers=MODH).status_code == 404
    assert client.post(f"/api/bounty/{a['attack_id']}/moderate", json={"action": "delete", "moderator": "Dev"}, headers=MODH).status_code == 422


def test_only_bounty_submissions_can_be_moderated_here(env, secret):
    client, _ = env
    judge = client.post("/api/attacks", json={"attacker_name": "Judge", "card": "freestyle", "payload": {"from_addr": "j@example.com", "body": "pay $5"}}).json()
    assert client.post(f"/api/bounty/{judge['attack_id']}/moderate", json={"action": "hide", "moderator": "Dev"}, headers=MODH).status_code == 404


def test_the_moderator_token_guards_the_queue(env, secret):
    client, _ = env
    assert client.get("/api/bounty/queue").status_code == 401
    assert client.post("/api/bounty/atk_x/moderate", json={"action": "hide", "moderator": "Dev"}).status_code == 401
    assert client.get("/api/bounty/queue", headers={"x-moderator-token": "nope"}).status_code == 401
    assert client.get("/api/bounty/queue", headers=MODH).status_code == 200


def test_the_older_attack_moderation_route_is_guarded_too(env, secret):
    client, _ = env
    sent = client.post(URL, json=mail(), headers=secret).json()
    body = {"status": "approved", "moderator": "Dev"}
    assert client.post(f"/api/attacks/{sent['attack_id']}/moderation", json=body).status_code == 401
    assert client.post(f"/api/attacks/{sent['attack_id']}/moderation", json=body, headers=MODH).status_code == 200


def test_a_live_inbox_without_a_moderator_token_closes_moderation(env, monkeypatch):
    client, eng = env
    monkeypatch.setattr(bounty_mod, "get_settings", lambda: Settings(bounty_webhook_secret=SECRET, bounty_moderator_token=""))
    sent = client.post(URL, json=mail(), headers={"x-webhook-secret": SECRET}).json()  # the inbox itself still works
    assert client.get("/api/bounty/queue").status_code == 503
    assert client.get("/api/bounty/queue", headers=MODH).status_code == 503  # a header cannot open it
    assert client.post(f"/api/attacks/{sent['attack_id']}/moderation", json={"status": "approved", "moderator": "Dev"}, headers=MODH).status_code == 503
    r = client.post(f"/api/bounty/{sent['attack_id']}/moderate", json={"action": "approve", "moderator": "Dev"}, headers=MODH)
    assert r.status_code == 503
    with Session(eng) as s:
        assert s.get(Attack, sent["attack_id"]).moderation_status.value == "pending"  # nothing was approved
    # with no inbox configured at all (local dev) the routes are not locked
    monkeypatch.setattr(bounty_mod, "get_settings", lambda: Settings(bounty_webhook_secret="", bounty_moderator_token=""))
    assert client.get("/api/bounty/queue").status_code == 200


def test_global_cap_across_all_senders(env, monkeypatch):
    client, eng = env
    monkeypatch.setattr(bounty_mod, "get_settings", lambda: Settings(bounty_webhook_secret=SECRET, bounty_moderator_token=MOD, bounty_global_limit_per_hour=3))
    h = {"x-webhook-secret": SECRET}
    assert [client.post(URL, json=mail(f"s{i}@example.com"), headers=h).status_code for i in range(3)] == [200, 200, 200]
    r = client.post(URL, json=mail("s9@example.com"), headers=h)  # a fourth, brand-new sender
    assert r.status_code == 429 and int(r.headers["retry-after"]) > 3000 and "in total" in r.json()["detail"]["error"]
    assert n_attacks(eng) == 3
    with Session(eng) as s:  # an hour later the window has moved on
        for a in s.exec(select(Attack)):
            a.created_at = utcnow() - timedelta(hours=2)
            s.add(a)
        s.commit()
    assert client.post(URL, json=mail("s9@example.com"), headers=h).status_code == 200


def test_the_global_cap_defaults_to_60_and_is_configurable():
    assert Settings().bounty_global_limit_per_hour == 60
    assert Settings(bounty_global_limit_per_hour=7).bounty_global_limit_per_hour == 7


# ---------------------------------------------------------------- sandbox money only, no real phone


def test_a_bounty_email_cannot_reach_a_real_bank_or_a_real_phone(env, secret, monkeypatch, tmp_path):
    client, eng = env
    cfg = get_settings()
    monkeypatch.setattr(voice, "AUDIO_DIR", tmp_path / "audio")
    monkeypatch.setattr(cfg, "mock_twilio", False)
    monkeypatch.setattr(cfg, "mock_cartesia", False)
    monkeypatch.setattr(cfg, "public_base_url", "https://pub.example")
    with Session(eng) as s:  # Summit's own on-file number is the only extra number the allow list holds
        summit = s.exec(select(VendorContact.phone).where(VendorContact.vendor_id == "ven_summit")).all()
    monkeypatch.setattr(cfg, "allowed_call_numbers", ", ".join(sorted(set(summit) | {"+14155550142"})))
    dialed, transfers = [], []

    async def fake_place(to, url, status_callback=None, settings=None):
        voice.assert_call_allowed(to, cfg)  # the real gate, in front of the fake network
        dialed.append(to)
        return "CAtest"

    async def fake_clip(text, settings=None):
        return "https://pub.example/x.wav"

    real = payments.create_transfer

    async def spy(dest, amount, description):
        transfers.append(dest)
        return await real(dest, amount, description)

    monkeypatch.setattr(voice, "place_call", fake_place)
    monkeypatch.setattr(voice, "tts_clip", fake_clip)
    monkeypatch.setattr(payments, "create_transfer", spy)
    body = {**mail("evil@example.com"), "TextBody": mail()["TextBody"] + "\nCall me to confirm on +1 415 555 0199, my account is 5550001111."}
    r = client.post(URL, json=body, headers=secret).json()
    wait(client, r["run_id"])
    assert dialed and "+14155550199" not in dialed and set(dialed) <= set(cfg.allowed_call_numbers_list)  # a call was placed, never to the number from the email
    with Session(eng) as s:
        verified = {a.id for a in s.exec(select(VendorBankAccount)) if a.verified_by_call_id is not None or a.id.endswith("_1")}
        pay = payment_for(eng, r)
        assert pay.status != PaymentStatus.paid and pay.nessie_transfer_id is None
        assert s.get(VendorBankAccount, pay.destination_account_id).account_last4 == "1111"  # held pointing at the unverified candidate, not paid
    assert all(t in verified for t in transfers)  # whatever was paid this run went only to verified accounts
    assert cfg.mock_nessie is True or payments.NESSIE_URL == "https://api.nessieisreal.com"  # the sandbox host
