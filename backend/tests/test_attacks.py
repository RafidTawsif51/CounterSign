"""Attacks and bounty emails: mini-runs that never fail because a run is active, and queue in order."""

import base64
import time
from datetime import timedelta

import pytest
from sqlmodel import Session, func, select

from app.config import Settings
from app.models import Attack, AuditActor, AuditLog, Event, Invoice, Message, Payment, PaymentRun, PaymentStatus, RiskAssessment, utcnow
from app.services import attacks, run, verify
from seed import seed as seedmod
from tests.test_run import env, go  # noqa: F401  (env is a fixture: a private seeded database + client)

pytestmark = pytest.mark.slow

CLASSIC = {
    "attacker_name": "Judge Priya", "card": "classic_bank_change",
    "payload": {"thread_id": "thr_summit_0919", "from_addr": "ar@summit-concrete.co", "reply_to": "billing@summit-concrete.co", "subject": "Re: Invoice SUM-1253",
                "body": "Hi Maria,\n\nWe switched banks this month. Please send this week's payment to the account below.\n\nBank: Harborline Bank\nRouting number: 996031174\n"
                        "Account number: 4410886213\n\nPlease process today, our month-end close is tomorrow.\n\nThanks,\nSummit Concrete"}}


def ceo(name="Judge Lee"):
    return {"attacker_name": name, "card": "ceo_pressure",
            "payload": {"thread_id": seedmod.PLANTED["ceo_pressure"]["thread"], "from_addr": "dana.whitfield@ridgeline-builders.co", "subject": "pay today",
                        "body": "Maria,\n\nThe CEO approved this. Please pay today, the new account is below.\n\nBank: Pioneer Trust\nRouting number: 994410265\n"
                                "Account number: 7700913046\n\nKeep this quiet until I explain.\n\nDana"}}


@pytest.fixture(autouse=True)
def clean_state():
    run._mini.clear()
    run._claimed.clear()
    yield
    run._mini.clear()
    run._claimed.clear()


def wait(client, run_id, timeout=40):
    t = time.perf_counter()
    while time.perf_counter() - t < timeout:
        g = client.get(f"/api/payment-runs/{run_id}").json()
        if g["status"] != "running":
            return g
        time.sleep(0.02)
    raise AssertionError(f"run {run_id} did not finish")


def evs(eng, run_id):
    with Session(eng) as s:
        return [(e.type, e.at, e.payload or {}) for e in s.exec(select(Event).where(Event.run_id == run_id).order_by(Event.at))]


def types(eng, run_id):
    return [t for t, _, _ in evs(eng, run_id)]


def payment_for(eng, resp):
    with Session(eng) as s:
        return s.exec(select(Payment).where(Payment.invoice_id == resp["invoice_id"])).one()


def slow_calls(monkeypatch, secs=0.3):
    monkeypatch.setattr(verify, "MOCK_STEP_DELAY", secs)  # a verification call takes about a second


# ================================================================ one attack


def test_an_attack_gets_its_own_mini_run_and_is_caught(env):
    client, eng = env
    r = client.post("/api/attacks", json=CLASSIC)
    assert r.status_code == 201
    a = r.json()
    assert a["queued"] is False and a["position"] == 0 and a["run_id"].startswith("run_") and a["attack_id"].startswith("atk_")
    g = wait(client, a["run_id"])
    assert g["status"] == "completed" and g["invoice_count"] == 1 and g["totals"]["blocked"] == 1 and g["totals"]["paid"] == 0
    pay = payment_for(eng, a)
    assert pay.run_id == a["run_id"] and pay.status == PaymentStatus.blocked
    with Session(eng) as s:
        ras = s.exec(select(RiskAssessment).where(RiskAssessment.payment_id == pay.id)).one()
        assert ras.hard_rules_fired == ["destination_changed"] and {x["name"] for x in ras.signals_json} >= {"bank_details_changed", "lookalike_domain", "reply_to_mismatch"}
        atk = s.get(Attack, a["attack_id"])
        assert atk.result.value == "caught" and atk.source.value == "console" and atk.moderation_status.value == "approved" and atk.payload_ref == a["message_id"]
        msg = s.get(Message, a["message_id"])
        assert msg.vendor_id == "ven_summit" and msg.is_attack  # the vendor came from the thread, not the sender
        inv = s.get(Invoice, a["invoice_id"])
        assert inv.remittance_json["account_last4"] == "4213" or inv.remittance_json["account_last4"] == "4410886213"[-4:]
        launched = s.exec(select(AuditLog).where(AuditLog.entity == "attack", AuditLog.entity_id == a["attack_id"])).all()
        assert launched[0].actor == AuditActor.human and launched[0].action == "launched"
    t = types(eng, a["run_id"])
    assert t[0] == "attack.logged" and t[1] == "run.started" and t[-2:] == ["run.completed", "run.report"]
    assert {"invoice.parsed", "risk.scored", "payment.held", "call.started", "call.outcome", "payment.blocked"} <= set(t)
    logged = [p for ty, _, p in evs(eng, a["run_id"]) if ty == "attack.logged"]
    assert [x["result"] for x in logged] == [None, "caught"] and all(x["attack_id"] == a["attack_id"] for x in logged)  # attempt shown at once, result later


def test_the_vendor_comes_from_the_thread_and_amount_and_bank_from_the_email(env):
    client, eng = env
    body = dict(CLASSIC)
    body["payload"] = {**CLASSIC["payload"], "body": "Revised total $48,900.00 please. Bank: X Bank\nRouting number: 996031174\nAccount number: 0000111122223333"}
    a = client.post("/api/attacks", json=body).json()
    with Session(eng) as s:
        inv = s.get(Invoice, a["invoice_id"])
        assert inv.vendor_id == "ven_summit" and inv.amount_usd == 48900.0 and inv.remittance_json["account_last4"] == "3333" and "223333" not in str(inv.remittance_json)
    wait(client, a["run_id"])
    with Session(eng) as s:
        ras = s.exec(select(RiskAssessment).where(RiskAssessment.payment_id == payment_for(eng, a).id)).one()
        assert "amount_over_max" in ras.hard_rules_fired and "destination_changed" in ras.hard_rules_fired


def test_an_email_with_no_bank_details_keeps_the_vendors_account(env):
    client, eng = env
    a = client.post("/api/attacks", json={"attacker_name": "x", "card": "freestyle", "payload": {"thread_id": "thr_summit_0919", "from_addr": "ar@summitconcrete.com", "body": "Hello, any news?"}}).json()
    wait(client, a["run_id"])
    pay = payment_for(eng, a)
    assert pay.status in (PaymentStatus.paid, PaymentStatus.held)  # not a destination change, so no call
    with Session(eng) as s:
        assert s.get(Invoice, a["invoice_id"]).remittance_json["account_last4"] == "2204"


def test_a_poisoned_pdf_attack_is_quarantined(env):
    client, eng = env
    a = client.post("/api/attacks", json={"attacker_name": "Hacker Sam", "card": "poisoned_invoice", "payload": {
        "thread_id": seedmod.PLANTED["poisoned_pdf"]["thread"], "from_addr": "ar@keystonesteel.com", "subject": "Invoice KEY-9001", "body": "Attached.",
        "pdf": "poisoned_white_text.pdf"}}).json()
    wait(client, a["run_id"])
    pay = payment_for(eng, a)
    assert pay.status == PaymentStatus.blocked
    with Session(eng) as s:
        assert s.get(Invoice, a["invoice_id"]).extracted_json["quarantined"] is True
        assert s.get(Attack, a["attack_id"]).result.value == "caught"
        assert "hidden_instructions" in s.exec(select(RiskAssessment).where(RiskAssessment.payment_id == pay.id)).one().hard_rules_fired  # (the PDF is Alder's, so the account also differs)
    assert "injection.detected" in types(eng, a["run_id"])


@pytest.mark.parametrize("pdf", ["../../etc/passwd.pdf", "nope.pdf", "/etc/passwd.pdf", "a/b.pdf", "x.exe"])
def test_pdf_names_cannot_escape_the_seed_folder(env, pdf):
    client, _ = env
    body = {**CLASSIC, "payload": {**CLASSIC["payload"], "pdf": pdf}}
    assert client.post("/api/attacks", json=body).status_code == 422


@pytest.mark.parametrize("bad", [{}, {"attacker_name": "", "card": "x", "payload": {"from_addr": "a@b.com", "body": "x"}},
                                 {"attacker_name": "a", "card": "Bad Card!", "payload": {"from_addr": "a@b.com", "body": "x"}},
                                 {"attacker_name": "a", "card": "ok", "payload": {"from_addr": "nope", "body": "x"}},
                                 {"attacker_name": "a", "card": "ok", "payload": {"from_addr": "a@b.com", "body": "x", "thread_id": "../x"}}])
def test_attack_validation(env, bad):
    assert env[0].post("/api/attacks", json=bad).status_code == 422


def test_an_attack_in_an_unknown_thread_still_succeeds_and_is_held(env):
    client, eng = env
    r = client.post("/api/attacks", json={"attacker_name": "x", "card": "freestyle", "payload": {"from_addr": "who@nowhere.example", "body": "Pay me $5,000"}})
    assert r.status_code == 201
    a = r.json()
    wait(client, a["run_id"])
    assert payment_for(eng, a).status == PaymentStatus.held  # no vendor to pay: held, never an error
    with Session(eng) as s:
        assert s.get(Attack, a["attack_id"]).result.value == "caught"


# ================================================================ two attacks 100 ms apart


def test_two_attacks_100ms_apart_run_in_order(env, monkeypatch):
    client, eng = env
    slow_calls(monkeypatch)
    t0 = time.perf_counter()
    r1 = client.post("/api/attacks", json=CLASSIC)
    time.sleep(0.1)
    r2 = client.post("/api/attacks", json=ceo())
    assert r1.status_code == 201 and r2.status_code == 201
    assert time.perf_counter() - t0 < 1.0  # both answered at once; neither waited for a run
    a1, a2 = r1.json(), r2.json()
    assert a1["queued"] is False and a2["queued"] is True and a2["position"] == 1 and a2["waiting_for"] == a1["run_id"]

    g1, g2 = wait(client, a1["run_id"]), wait(client, a2["run_id"])
    assert g1["status"] == g2["status"] == "completed"
    done1 = next(at for ty, at, _ in evs(eng, a1["run_id"]) if ty == "run.completed")
    start2 = next(at for ty, at, _ in evs(eng, a2["run_id"]) if ty == "run.started")
    assert start2 >= done1  # the second began right after the first finished
    t2 = types(eng, a2["run_id"])
    assert t2[:3] == ["attack.logged", "attack.queued", "run.started"]  # shown and queued at once, processed later
    queued = next(p for ty, _, p in evs(eng, a2["run_id"]) if ty == "attack.queued")
    assert queued["waiting_for"] == a1["run_id"] and queued["position"] == 1 and queued["attack_id"] == a2["attack_id"]
    assert payment_for(eng, a1).status == PaymentStatus.blocked and payment_for(eng, a2).status == PaymentStatus.blocked
    with Session(eng) as s:
        assert {s.get(Attack, a["attack_id"]).result.value for a in (a1, a2)} == {"caught"}


def test_a_burst_is_processed_strictly_in_arrival_order(env):
    client, eng = env
    resp = []
    for i in range(6):
        r = client.post("/api/attacks", json=ceo(f"Burst {i}"))
        assert r.status_code == 201, r.text
        resp.append(r.json())
    for a in resp:
        assert wait(client, a["run_id"])["status"] == "completed"
    starts = [next(at for ty, at, _ in evs(eng, a["run_id"]) if ty == "run.started") for a in resp]
    assert starts == sorted(starts)
    ends = [next(at for ty, at, _ in evs(eng, a["run_id"]) if ty == "run.completed") for a in resp]
    assert all(ends[i] <= starts[i + 1] for i in range(5))  # never two at once
    with Session(eng) as s:
        assert s.exec(select(func.count()).select_from(Attack)).one() == 6
    assert sum(1 for a in resp if a["queued"]) >= 1


# ================================================================ an attack during a full seeded run


def test_an_attack_during_a_full_run_is_queued_and_the_run_is_unchanged(env, monkeypatch):
    client, eng = env
    slow_calls(monkeypatch)
    full = client.post("/api/payment-runs")
    assert full.status_code == 202
    full_id = full.json()["run_id"]
    r = client.post("/api/attacks", json=CLASSIC)
    assert r.status_code == 201  # never a 409
    a = r.json()
    assert a["queued"] is True and a["waiting_for"] == full_id and a["position"] >= 1
    assert client.post("/api/payment-runs").status_code == 409  # a second FULL run is still refused

    gf = wait(client, full_id)
    assert full.json()["invoice_count"] == 40 and gf["invoice_count"] == 40
    assert (gf["totals"]["paid"], gf["totals"]["held"], gf["totals"]["blocked"]) == (37, 1, 2)  # untouched by the attack
    ga = wait(client, a["run_id"])
    assert ga["status"] == "completed" and ga["totals"]["blocked"] == 1
    assert payment_for(eng, a).run_id == a["run_id"]
    full_done = next(at for ty, at, _ in evs(eng, full_id) if ty == "run.completed")
    atk_start = next(at for ty, at, _ in evs(eng, a["run_id"]) if ty == "run.started")
    assert atk_start >= full_done  # processed right after the full run, not during it
    t = types(eng, a["run_id"])
    assert t[:2] == ["attack.logged", "attack.queued"]
    with Session(eng) as s:
        assert s.get(Attack, a["attack_id"]).result.value == "caught"
        assert s.exec(select(func.count()).select_from(Payment).where(Payment.invoice_id == a["invoice_id"])).one() == 1  # processed exactly once


def test_an_attack_that_arrives_mid_run_also_appears_on_the_leaderboard_channel_events(env, monkeypatch):
    client, eng = env
    slow_calls(monkeypatch)
    full_id = client.post("/api/payment-runs").json()["run_id"]
    a = client.post("/api/attacks", json=ceo()).json()
    wait(client, full_id), wait(client, a["run_id"])
    with Session(eng) as s:
        rows = s.exec(select(Event).where(Event.type.in_(["attack.logged", "attack.queued"]), Event.run_id == a["run_id"]).order_by(Event.at)).all()
    assert [e.type for e in rows][:2] == ["attack.logged", "attack.queued"] and rows[-1].payload["result"] in ("caught", "missed")


def test_a_mini_run_never_blocks_a_full_run_and_nothing_is_processed_twice(env, monkeypatch):
    client, eng = env
    slow_calls(monkeypatch)
    a = client.post("/api/attacks", json=CLASSIC).json()  # starts at once and takes a second
    full = client.post("/api/payment-runs")
    assert full.status_code == 202 and full.json()["invoice_count"] == 40  # the attack's invoice is not in the full run
    gf = wait(client, full.json()["run_id"])
    ga = wait(client, a["run_id"])
    assert (gf["totals"]["paid"], gf["totals"]["held"], gf["totals"]["blocked"]) == (37, 1, 2) and ga["totals"]["blocked"] == 1
    with Session(eng) as s:
        assert s.exec(select(func.count()).select_from(Payment).where(Payment.invoice_id == a["invoice_id"])).one() == 1
        assert s.exec(select(func.count()).select_from(Payment)).one() == 1159 + 41


def test_a_queued_attack_that_is_not_processed_stays_open_for_the_next_full_run(env, monkeypatch):
    """If the server stops with attacks still queued, nothing is lost: their invoices are simply open."""
    client, eng = env
    with Session(eng) as s:
        msg = Message(thread_id="thr_summit_0919", vendor_id="ven_summit", from_addr="ar@summit-concrete.co", subject="s", body="Bank: B\nRouting number: 996031174\nAccount number: 4410886213", is_attack=True)
        s.add(msg)
        s.add(Invoice(id="inv_left_open", vendor_id="ven_summit", message_id=msg.id, number="ATK-1", amount_usd=5000.0, due_date=(utcnow() + timedelta(days=9)).date(),
                      remittance_json={"bank_name": "B", "routing_hash": "f" * 64, "account_last4": "4213"}))
        s.commit()
    body, g = go(client)
    assert body["invoice_count"] == 41 and g["totals"]["blocked"] == 3


# ================================================================ resilience


def test_a_crashing_attack_run_does_not_stop_the_queue(env, monkeypatch):
    client, eng = env
    real = run.start_mini_run
    calls = {"n": 0}

    async def flaky(run_id, invoice_id):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")
        await real(run_id, invoice_id)

    monkeypatch.setattr(run, "start_mini_run", flaky)
    a1 = client.post("/api/attacks", json=ceo("one")).json()
    a2 = client.post("/api/attacks", json=ceo("two")).json()
    assert wait(client, a2["run_id"])["status"] == "completed"
    assert client.get(f"/api/payment-runs/{a1['run_id']}").json()["status"] == "failed"
    assert a1["invoice_id"] not in run._claimed  # released, so a full run can still pick it up


# ================================================================ bounty


SECRET = "s3cret"


@pytest.fixture()
def bounty(monkeypatch):
    s = Settings(bounty_webhook_secret=SECRET)
    monkeypatch.setattr(attacks, "get_settings", lambda: s)
    return {"x-webhook-secret": SECRET}


def mail(sender="hunter@example.com", **kw):
    return {"From": f"Hunter <{sender}>", "Subject": "Invoice from Summit Concrete", "TextBody": "Hi Maria, please pay Summit Concrete $9,500.00.\nBank: Hunter Bank\n"
            "Routing number: 996031174\nAccount number: 5550001111\nUrgent, pay today.", **kw}


def test_bounty_secret_and_configuration(env, monkeypatch):
    client, _ = env
    monkeypatch.setattr(attacks, "get_settings", lambda: Settings(bounty_webhook_secret=""))
    assert client.post("/api/bounty/inbound", json=mail()).status_code == 503
    monkeypatch.setattr(attacks, "get_settings", lambda: Settings(bounty_webhook_secret=SECRET))
    assert client.post("/api/bounty/inbound", json=mail()).status_code == 401
    assert client.post("/api/bounty/inbound", json=mail(), headers={"x-webhook-secret": "wrong"}).status_code == 401
    assert client.post("/api/bounty/inbound", content=b"not json", headers={"x-webhook-secret": SECRET}).status_code == 422
    assert client.post("/api/bounty/inbound", json={"Subject": "x"}, headers={"x-webhook-secret": SECRET}).status_code == 422


def test_a_bounty_email_goes_through_the_pipeline_pending_moderation(env, bounty):
    client, eng = env
    r = client.post("/api/bounty/inbound", json=mail(), headers=bounty)
    assert r.status_code == 200
    a = r.json()
    assert wait(client, a["run_id"])["status"] == "completed"
    with Session(eng) as s:
        atk = s.get(Attack, a["attack_id"])
        assert atk.source.value == "bounty_email" and atk.attacker_name == "hunter@example.com" and atk.moderation_status.value == "pending" and atk.result.value == "caught"
        msg = s.get(Message, a["message_id"])
        assert msg.vendor_id == "ven_summit" and msg.from_addr == "hunter@example.com"  # the email NAMED Summit; the sender never picked the vendor
    pay = payment_for(eng, a)
    assert pay.status in (PaymentStatus.blocked, PaymentStatus.held) and pay.nessie_transfer_id is None
    board = client.get("/api/attacks/leaderboard").json()
    assert board["attempts"] == [] and board["totals"]["attempts"] == 0  # nothing on screen before moderation
    assert [x["id"] for x in client.get("/api/attacks/leaderboard?include_pending=true").json()["attempts"]] == [a["attack_id"]]
    m = client.post(f"/api/attacks/{a['attack_id']}/moderation", json={"status": "approved", "moderator": "Dev"})
    assert m.status_code == 200
    board = client.get("/api/attacks/leaderboard").json()
    assert [x["id"] for x in board["attempts"]] == [a["attack_id"]] and board["totals"]["caught"] == 1 and board["attempts"][0]["outcome"] in ("blocked", "held")
    logged = [p for ty, _, p in evs(eng, a["run_id"]) if ty == "attack.logged"]
    assert logged[-1]["moderation_status"] == "approved"
    assert client.post(f"/api/attacks/{a['attack_id']}/moderation", json={"status": "hidden", "moderator": "Dev"}).status_code == 200
    assert client.get("/api/attacks/leaderboard").json()["attempts"] == []
    assert client.post("/api/attacks/atk_nope/moderation", json={"status": "hidden", "moderator": "Dev"}).status_code == 404


def test_bounty_rate_limit_is_five_per_sender_per_hour(env, bounty):
    client, eng = env
    ids = []
    for i in range(5):
        r = client.post("/api/bounty/inbound", json=mail(), headers=bounty)
        assert r.status_code == 200
        ids.append(r.json())
    r = client.post("/api/bounty/inbound", json=mail(), headers=bounty)
    assert r.status_code == 429 and r.headers["retry-after"].isdigit() and r.json()["detail"]["retry_after_seconds"] > 3000
    assert client.post("/api/bounty/inbound", json=mail("someone.else@example.com"), headers=bounty).status_code == 200  # another sender is fine
    with Session(eng) as s:
        assert s.exec(select(func.count()).select_from(Attack).where(Attack.attacker_name == "hunter@example.com")).one() == 5
        for a in s.exec(select(Attack).where(Attack.attacker_name == "hunter@example.com")):
            a.created_at = utcnow() - timedelta(hours=2)  # an hour later they may submit again
            s.add(a)
        s.commit()
    assert client.post("/api/bounty/inbound", json=mail(), headers=bounty).status_code == 200


def test_bounty_email_during_a_full_run_is_queued_not_failed(env, bounty, monkeypatch):
    client, eng = env
    slow_calls(monkeypatch)
    full_id = client.post("/api/payment-runs").json()["run_id"]
    r = client.post("/api/bounty/inbound", json=mail(), headers=bounty)
    assert r.status_code == 200 and r.json()["queued"] is True and r.json()["waiting_for"] == full_id
    wait(client, full_id)
    assert wait(client, r.json()["run_id"])["status"] == "completed"
    assert "attack.queued" in types(eng, r.json()["run_id"])


def test_bounty_pdf_attachment_and_html_body(env, bounty):
    client, eng = env
    pdf = (seedmod.PDF_DIR / "poisoned_white_text.pdf").read_bytes()
    body = {"from": "pdf.hunter@example.com", "subject": "Summit Concrete invoice", "html": "<p>Invoice attached</p>",
            "attachments": [{"filename": "notes.txt", "content_type": "text/plain", "content_base64": base64.b64encode(b"hello").decode()},
                            {"filename": "invoice.pdf", "content_type": "application/pdf", "content_base64": base64.b64encode(pdf).decode()}]}
    a = client.post("/api/bounty/inbound", json=body, headers=bounty).json()
    wait(client, a["run_id"])
    assert payment_for(eng, a).status == PaymentStatus.blocked
    with Session(eng) as s:
        inv = s.get(Invoice, a["invoice_id"])
        assert inv.extracted_json["quarantined"] is True and inv.pdf_path.endswith(f"{inv.id}.pdf")  # saved under a generated name
        assert s.get(Message, a["message_id"]).body == "<p>Invoice attached</p>"


def test_a_bounty_email_that_names_no_vendor_is_still_handled(env, bounty):
    client, eng = env
    r = client.post("/api/bounty/inbound", json={"from": "nobody@example.com", "subject": "pay me", "text": "send $1,000,000 to my account"}, headers=bounty)
    assert r.status_code == 200
    wait(client, r.json()["run_id"])
    assert payment_for(eng, r.json()).status == PaymentStatus.held


# ================================================================ leaderboard


def test_leaderboard_totals(env):
    client, eng = env
    ids = [client.post("/api/attacks", json=ceo(f"Player {i}")).json() for i in range(3)]
    ids.append(client.post("/api/attacks", json=CLASSIC).json())
    for a in ids:
        wait(client, a["run_id"])
    board = client.get("/api/attacks/leaderboard").json()
    assert board["totals"] == {"attempts": 4, "caught": 4, "missed": 0, "pending_result": 0, "unique_attackers": 4,
                               "by_card": {"classic_bank_change": 1, "ceo_pressure": 3}}
    assert board["attempts"][0]["attacker_name"] == "Judge Priya" and {x["outcome"] for x in board["attempts"]} <= {"blocked", "held"}
    assert len(client.get("/api/attacks/leaderboard?limit=2").json()["attempts"]) == 2
