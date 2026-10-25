"""The run report: written from structured database fields only, by Claude when it works, otherwise the basic report."""

import asyncio
import json
import time

import pytest
from sqlmodel import Session, select

from app.config import get_settings
from app.models import AuditLog, Event, Invoice, Message, Payment, PaymentRun, PaymentStatus, RunStatus
from app.services import late, report, run
from tests.test_run import BANK, CEO, POISON, env, go  # noqa: F401  (env is a fixture: a private seeded database + client)

pytestmark = pytest.mark.slow  # every test here runs the whole payment run

STOPPED_KEYS = {"payment_id", "vendor", "amount_usd", "status", "decision", "score", "hard_rules", "signals", "hidden_text_techniques", "crs", "call",
                "controller_decision", "waiting_for"}


@pytest.fixture()
def finished(env):
    client, eng = env
    body, _ = go(client)
    report.clear_cache()
    return client, eng, body["run_id"]


def report_events(eng, run_id):
    with Session(eng) as s:
        return [e.payload for e in s.exec(select(Event).where(Event.run_id == run_id, Event.type == "run.report").order_by(Event.at)).all()]


def saved(eng, run_id):
    with Session(eng) as s:
        return (s.get(PaymentRun, run_id).totals_json or {}).get("report")


def live(monkeypatch, fake):
    """Claude 'on' for the report only (the run is already over), with the model call replaced."""
    cfg = get_settings()
    monkeypatch.setattr(cfg, "mock_claude", False)
    monkeypatch.setattr(cfg, "anthropic_api_key", "test-key")
    monkeypatch.setattr(report, "_call_claude", fake)


def good(facts, **over):
    t = facts["totals"]
    out = {
        "paid": f"{t['paid']} payments went out, ${t['paid_usd']:,.2f} in all.",
        "stopped": "Summit Concrete was blocked: the bank details changed and the vendor denied it on the call.",
        "needs_decision": ["Northside Rentals: the controller has to decide after the call result was unclear."],
        "protected": f"${t['blocked_usd']:,.2f} was blocked and ${t['held_usd']:,.2f} is held.",
    }
    return {**out, **over}


def facts_of(eng, run_id):
    with Session(eng) as s:
        return report.build_facts(s, run_id)


# ---------------------------------------------------------------- what the run emits and saves


def test_a_run_saves_the_basic_report_and_keeps_the_event(finished):
    client, eng, run_id = finished
    (ev,) = report_events(eng, run_id)
    assert ev["paid"] == 37 and ev["held"] == 1 and ev["blocked"] == 2 and len(ev["findings"]) == 3  # the original fields, unchanged
    assert ev["summary"].startswith("40 invoices processed: 37 paid") and "protected" in ev["summary"]
    assert ev["report_source"] == "basic" and ev["report"] == ev["summary"] and ev["sections"] is None and ev["updated"] is False
    assert ev["held_usd"] > 0
    rep = saved(eng, run_id)
    assert rep["source"] == "basic" and rep["fallback_reason"] == "claude_off" and rep["text"] == ev["summary"]
    got = client.get(f"/api/payment-runs/{run_id}/report")
    assert got.status_code == 200 and got.json()["report"]["text"] == ev["summary"] and got.json()["status"] == "completed"


def test_the_report_has_no_em_dash(finished):
    _, eng, run_id = finished
    assert "\u2014" not in json.dumps(saved(eng, run_id))


# ---------------------------------------------------------------- only structured fields reach Claude


def test_facts_are_structured_fields_and_carry_no_document_text(finished):
    _, eng, run_id = finished
    facts = facts_of(eng, run_id)
    blob = json.dumps(facts)
    with Session(eng) as s:
        stopped = {p.id: s.get(Invoice, p.invoice_id) for p in s.exec(select(Payment).where(Payment.run_id == run_id, Payment.status != PaymentStatus.paid)).all()}
        attack_messages = s.exec(select(Message).where(Message.is_attack.is_(True))).all()
    assert len(facts["stopped"]) == 3 and all(set(p) == STOPPED_KEYS for p in facts["stopped"])
    assert all(set(sig) == {"name", "weight"} for p in facts["stopped"] for sig in p["signals"])  # names and weights, never the detail line
    for m in attack_messages:  # no subject, body, sender or snippet from any attack email
        assert m.subject not in blob and m.body[:40] not in blob and m.from_addr not in blob
    for inv in stopped.values():
        assert inv.number not in blob  # invoice numbers come from the document
    for phrase in ("keep this quiet", "ai assistant", "ignore previous", "please process today", "http", "@"):
        assert phrase not in blob.lower()
    bank = next(p for p in facts["stopped"] if p["payment_id"] == BANK)
    assert bank["status"] == "blocked" and "destination_changed" in bank["hard_rules"] and bank["call"]["outcome"] == "denied"
    assert bank["call"]["contact_source"] in ("on_file", "website", "listing")
    assert next(p for p in facts["stopped"] if p["payment_id"] == POISON)["hidden_text_techniques"]
    ceo = next(p for p in facts["stopped"] if p["payment_id"] == CEO)
    assert ceo["status"] == "held" and ceo["waiting_for"]


# ---------------------------------------------------------------- Claude path


def test_claude_report_is_saved_emitted_and_audited(finished, monkeypatch):
    client, eng, run_id = finished
    facts = facts_of(eng, run_id)
    seen = []

    def fake(model, f):
        seen.append((model, f))
        return good(f, paid="37 payments went out \u2014 all clean.")

    live(monkeypatch, fake)
    rep = client.portal.call(report.finish, run_id)
    assert seen[0][0] == get_settings().claude_model_main and seen[0][1] == facts  # CLAUDE_MODEL_MAIN, and exactly the structured facts
    assert rep["source"] == "claude" and rep["text"].startswith("Paid: 37 payments went out, all clean.")  # the em dash was replaced
    assert "\u2014" not in rep["text"] and "Needs a decision:\n- Northside" in rep["text"] and rep["text"].endswith(".")
    assert saved(eng, run_id)["sections"]["protected"] == rep["sections"]["protected"]
    ev = report_events(eng, run_id)[-1]
    assert ev["report_source"] == "claude" and ev["report"] == rep["text"] and ev["sections"]["needs_decision"] and ev["updated"] is False
    assert ev["paid"] == 37 and ev["summary"].startswith("40 invoices processed")  # the basic fields ride along
    with Session(eng) as s:
        row = s.exec(select(AuditLog).where(AuditLog.entity == "run", AuditLog.entity_id == run_id, AuditLog.action == "report_written")).one()
    assert row.detail_json["source"] == "claude"
    assert client.get(f"/api/payment-runs/{run_id}/report").json()["report"]["source"] == "claude"


def test_a_figure_that_is_not_in_the_data_is_rejected(finished, monkeypatch):
    client, eng, run_id = finished
    live(monkeypatch, lambda model, f: good(f, protected="$999,999.99 was protected."))
    rep = client.portal.call(report.finish, run_id)
    assert rep["source"] == "basic" and rep["fallback_reason"] == "rejected_figure_not_in_data"
    assert report_events(eng, run_id)[-1]["report_source"] == "basic"


@pytest.mark.parametrize("bad, why", [
    ({"paid": "ok see https://evil.example"}, "markup_or_link"),
    ({"paid": "<b>ok</b>"}, "markup_or_link"),
    ({"stopped": ""}, "empty_section"),
    ({"paid": "x" * 800}, "too_long"),
])
def test_other_unusable_answers_fall_back(finished, monkeypatch, bad, why):
    client, _, run_id = finished
    live(monkeypatch, lambda model, f: good(f, **bad))
    rep = client.portal.call(report.finish, run_id)
    assert rep["source"] == "basic" and rep["fallback_reason"] == f"rejected_{why}"


def test_claude_failure_falls_back_to_the_basic_report(finished, monkeypatch):
    client, eng, run_id = finished
    live(monkeypatch, lambda model, f: None)  # the call failed or refused
    rep = client.portal.call(report.finish, run_id)
    assert rep["source"] == "basic" and rep["fallback_reason"] == "claude_error" and rep["text"].startswith("40 invoices processed")
    assert report_events(eng, run_id)[-1]["report_source"] == "basic"


def test_a_slow_claude_is_cut_off_at_the_deadline(finished, monkeypatch):
    client, _, run_id = finished
    monkeypatch.setattr(report, "DEADLINE_SECONDS", 0.3)

    def slow(model, f):
        time.sleep(1.5)
        return good(f)

    live(monkeypatch, slow)
    t0 = time.perf_counter()
    rep = client.portal.call(report.finish, run_id)
    assert time.perf_counter() - t0 < 1.2 and rep["source"] == "basic" and rep["fallback_reason"] == "timeout"


def test_the_real_deadline_is_eight_seconds():
    assert report.DEADLINE_SECONDS == 8.0


def test_reports_are_cached_by_their_facts(finished, monkeypatch):
    client, eng, run_id = finished
    calls = []
    live(monkeypatch, lambda model, f: (calls.append(1), good(f))[1])
    client.portal.call(report.finish, run_id)
    client.portal.call(report.finish, run_id)
    assert len(calls) == 1  # same facts: one model call
    report.clear_cache()
    client.portal.call(report.finish, run_id)
    assert len(calls) == 1  # and the on-disk copy survives a restart
    with Session(eng) as s:  # the facts change: a call outcome moved a payment
        pay = s.get(Payment, CEO)
        pay.status = PaymentStatus.blocked
        s.add(pay)
        s.commit()
    client.portal.call(report.finish, run_id)
    assert len(calls) == 2


def test_a_failed_report_is_not_cached(finished, monkeypatch):
    client, _, run_id = finished
    calls = []
    live(monkeypatch, lambda model, f: (calls.append(1), None)[1])
    client.portal.call(report.finish, run_id)
    client.portal.call(report.finish, run_id)
    assert len(calls) == 2  # a fallback is retried next time, not remembered


# ---------------------------------------------------------------- late outcomes and other kinds of run


def test_a_late_outcome_rewrites_the_report_and_sends_it_again(finished, monkeypatch):
    client, eng, run_id = finished
    live(monkeypatch, lambda model, f: good(f))
    client.portal.call(report.finish, run_id)
    before = len(report_events(eng, run_id))
    with Session(eng) as s:  # what a webhook outcome does: the held payment is now blocked
        pay = s.get(Payment, CEO)
        pay.status = PaymentStatus.blocked
        s.add(pay)
        s.commit()

    async def after():
        await late.after_outcome(CEO)
        await asyncio.gather(*list(run._tasks))

    client.portal.call(after)
    evs = report_events(eng, run_id)
    assert len(evs) == before + 1
    last = evs[-1]
    assert last["updated"] is True and last["held"] == 0 and last["blocked"] == 3 and last["report_source"] == "claude"
    assert saved(eng, run_id)["late"] is True and saved(eng, run_id)["blocked_usd"] == last["blocked_usd"]
    with Session(eng) as s:
        assert s.exec(select(AuditLog).where(AuditLog.entity == "run", AuditLog.entity_id == run_id, AuditLog.action == "report_updated")).one()


def test_attack_runs_and_red_team_batches_always_get_the_basic_report(finished, monkeypatch):
    client, eng, run_id = finished

    def boom(model, f):
        raise AssertionError("no model call for a one-invoice attack run")

    live(monkeypatch, boom)
    for kind in ("attack", "redteam"):
        with Session(eng) as s:
            pr = s.get(PaymentRun, run_id)
            pr.totals_json = {**pr.totals_json, "kind": kind}
            s.add(pr)
            s.commit()
        rep = client.portal.call(report.finish, run_id)
        assert rep["source"] == "basic" and rep["fallback_reason"] == "basic_only_run"


# ---------------------------------------------------------------- the route


def test_report_route_statuses(finished):
    client, eng, run_id = finished
    assert client.get("/api/payment-runs/run_nope/report").status_code == 404
    with Session(eng) as s:
        s.add(PaymentRun(id="run_going", status=RunStatus.running))
        s.commit()
    assert client.get("/api/payment-runs/run_going/report").status_code == 409
    before = len(report_events(eng, run_id))
    with Session(eng) as s:  # a run from before reports existed
        pr = s.get(PaymentRun, run_id)
        pr.totals_json = {k: v for k, v in pr.totals_json.items() if k != "report"}
        s.add(pr)
        s.commit()
    r = client.get(f"/api/payment-runs/{run_id}/report")
    assert r.status_code == 200 and r.json()["report"]["source"] == "basic" and r.json()["report"]["text"].startswith("40 invoices processed")
    assert len(report_events(eng, run_id)) == before  # written quietly: no event
    assert saved(eng, run_id) is not None
