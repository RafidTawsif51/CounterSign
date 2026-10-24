"""The independent number check: our Vendor Contact Verifier Actor on Apify decides where the verification call goes."""

import asyncio
import json
import time
from datetime import timedelta
from types import SimpleNamespace

import pytest
from sqlmodel import Session, select

from app import events as ev
from app.config import get_settings
from app.models import AuditLog, Event, Payment, Vendor, VendorContact, utcnow
from app.services import contacts, verify, voice
from tests.test_attacks import CLASSIC, wait
from tests.test_run import env  # noqa: F401  (env is a fixture: a private seeded database + client)

SITE = "https://pages.example/org/summit-concrete/"
ON_FILE = "+14155550142"  # the number the seed gives Summit Concrete in tests (DEMO_VENDOR_PHONE)


def vendor(**kw) -> Vendor:
    return Vendor(id=kw.pop("id", "ven_t1"), name="Summit Concrete", trade="concrete", email_domain="summitconcrete.com", website_url=kw.pop("website_url", SITE), **kw)


def row(phone="+14155550100", agreement="consistent", confidence="high", url=SITE + "contact.html", sources=None):
    return {"name": "Summit Concrete", "website_url": SITE, "primary_phone": phone, "agreement": agreement, "confidence": confidence,
            "confidence_reason": "One number, found in 4 source types.", "site_reachable": True, "pages_crawled": 2,
            "phones": [{"phone": phone, "sources": sources if sources is not None else [{"source_url": url, "found_in": "json_ld"}]}] if phone else []}


def run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def clean(monkeypatch, tmp_path):
    contacts.health.reset()
    contacts.MOCK_OVERRIDES.clear()
    monkeypatch.setattr(get_settings(), "contacts_cache_dir", str(tmp_path / "cc"))
    yield
    contacts.health.reset()
    contacts.MOCK_OVERRIDES.clear()


# ---------------------------------------------------------------- the Actor's row, as data from a website


def test_a_consistent_high_confidence_row_is_a_usable_number_with_its_proof_page():
    r = contacts.parse_actor_row(vendor(), row(), "run1")
    assert r.status == "found" and r.contact.phone == "+14155550100" and r.contact.source == "website"
    assert r.source_url == SITE + "contact.html" and r.confidence == "high" and r.agreement == "consistent" and r.actor_run_id == "run1"


def test_the_proof_page_prefers_the_contact_page_and_must_be_on_the_vendors_own_site():
    srcs = [{"source_url": SITE, "found_in": "footer_text"}, {"source_url": SITE + "contact.html", "found_in": "contact_page_text"},
            {"source_url": "https://evil.example/x", "found_in": "json_ld"}]
    assert contacts.parse_actor_row(vendor(), row(sources=srcs), None).source_url == SITE + "contact.html"
    # a neighbour's folder on the same host, or another host, is not proof
    for url in ("https://pages.example/org/other-vendor/contact.html", "https://evil.example/org/summit-concrete/", "https://pages.example/org/summit-concrete-co/"):
        r = contacts.parse_actor_row(vendor(), row(sources=[{"source_url": url, "found_in": "json_ld"}]), None)
        assert r.status == "not_usable" and r.contact is None, url


@pytest.mark.parametrize("kw", [dict(confidence="low"), dict(agreement="conflicting", confidence="low"), dict(phone=None, agreement="none_found", confidence="low"),
                                dict(phone="not a number"), dict(phone="4155550100")])
def test_low_confidence_conflicting_none_found_or_a_bad_number_is_not_usable(kw):
    r = contacts.parse_actor_row(vendor(), row(**kw), None)
    assert r.status == "not_usable" and r.contact is None


def test_a_malformed_row_is_an_error_not_a_number():
    for bad in ({}, {"agreement": "maybe", "confidence": "high"}, {"agreement": "consistent"}):
        with pytest.raises(ValueError):
            contacts.parse_actor_row(vendor(), bad, None)


# ---------------------------------------------------------------- the real finder, with Apify faked


class FakeApify:
    """Stands in for apify_client.ApifyClientAsync. Records what was asked and what it was told."""

    calls: list = []
    behaviour = "ok"
    dataset_row = None
    aborted: list = []

    def __init__(self, token):
        FakeApify.token = token

    def actor(self, actor_id):
        outer = self

        class A:
            async def start(self, run_input=None, **kw):
                FakeApify.calls.append((actor_id, run_input, kw))
                return SimpleNamespace(id="run_fake")

        return A()

    def run(self, run_id):
        class R:
            async def wait_for_finish(self, wait_duration=None, **kw):
                if FakeApify.behaviour == "hang":
                    await asyncio.sleep(60)
                if FakeApify.behaviour == "error":
                    raise RuntimeError("apify is down")
                status = "FAILED" if FakeApify.behaviour == "failed" else "SUCCEEDED"
                return SimpleNamespace(status=SimpleNamespace(value=status), default_dataset_id="ds1")

            async def abort(self, **kw):
                FakeApify.aborted.append(run_id)

        return R()

    def dataset(self, dataset_id):
        class D:
            async def list_items(self, **kw):
                return SimpleNamespace(items=[FakeApify.dataset_row] if FakeApify.dataset_row is not None else [])

        return D()


@pytest.fixture
def apify(monkeypatch):
    import apify_client

    FakeApify.calls, FakeApify.aborted, FakeApify.behaviour, FakeApify.dataset_row = [], [], "ok", row()
    monkeypatch.setattr(apify_client, "ApifyClientAsync", FakeApify)
    cfg = get_settings()
    monkeypatch.setattr(cfg, "apify_token", "test-token")
    monkeypatch.setattr(cfg, "mock_apify", False)
    return FakeApify


def test_the_actor_is_called_with_the_vendors_own_website_and_nothing_from_the_request(apify):
    v = vendor()
    result = run(contacts.get_finder().lookup(v))
    assert result.status == "found" and result.contact.phone == "+14155550100" and result.contact.source_url == SITE + "contact.html"
    (actor_id, run_input, kw), = apify.calls
    assert actor_id == "test-user/vendor-contact-verifier" and apify.token == "test-token"
    assert run_input["businesses"] == [{"name": "Summit Concrete", "website_url": SITE}]  # our record: no email, domain or phone from the request
    assert "summitconcrete.com" not in json.dumps(run_input) and "run_timeout" in kw


def test_a_vendor_with_no_website_is_not_looked_up_at_all(apify):
    result = run(contacts.get_finder().lookup(vendor(website_url=None)))
    assert result.status == "no_website" and apify.calls == []


def test_a_lookup_is_cached_for_one_hour_per_vendor_and_website(apify):
    v = vendor()
    first = run(contacts.get_finder().lookup(v))
    second = run(contacts.get_finder().lookup(v))
    assert (first.cached, second.cached) == (False, True) and len(apify.calls) == 1 and second.contact.phone == first.contact.phone
    run(contacts.get_finder().lookup(vendor(id="ven_other")))
    run(contacts.get_finder().lookup(vendor(website_url=SITE + "x/")))  # a changed website is a new lookup
    assert len(apify.calls) == 3
    f = contacts._cache_file(v)
    data = json.loads(f.read_text())
    data["expires_at"] = time.time() - 1  # an hour has passed
    f.write_text(json.dumps(data))
    assert run(contacts.get_finder().lookup(v)).cached is False and len(apify.calls) == 4


def test_a_not_usable_result_is_cached_too_but_a_failure_is_not(apify):
    apify.dataset_row = row(phone=None, agreement="none_found", confidence="low")
    run(contacts.get_finder().lookup(vendor()))
    assert run(contacts.get_finder().lookup(vendor())).cached is True and len(apify.calls) == 1
    apify.behaviour = "error"
    assert run(contacts.get_finder().lookup(vendor(id="ven_fail"))).status == "unavailable"
    run(contacts.get_finder().lookup(vendor(id="ven_fail")))
    assert len(apify.calls) == 3  # the failure was retried


@pytest.mark.parametrize("behaviour", ["error", "failed"])
def test_an_apify_failure_is_unavailable_and_marks_apify_degraded(apify, behaviour):
    apify.behaviour = behaviour
    result = run(contacts.get_finder().lookup(vendor()))
    assert result.status == "unavailable" and result.contact is None and contacts.health.degraded and contacts.health.last_error
    apify.behaviour = "ok"
    run(contacts.get_finder().lookup(vendor(id="ven_recovered")))
    assert contacts.health.degraded is False  # one good lookup clears it


def test_a_lookup_that_takes_longer_than_20_seconds_gives_up_and_ends_the_apify_run(apify, monkeypatch):
    assert contacts.TOTAL_TIMEOUT_SECONDS == 20
    monkeypatch.setattr(contacts, "TOTAL_TIMEOUT_SECONDS", 0.2)
    apify.behaviour = "hang"
    t = time.time()
    result = run(contacts.get_finder().lookup(vendor()))
    assert time.time() - t < 3 and result.status == "unavailable" and result.error == "TimeoutError"
    assert apify.aborted == ["run_fake"] and contacts.health.degraded


def test_the_token_is_never_logged_or_stored(apify, caplog):
    apify.behaviour = "error"
    with caplog.at_level("DEBUG"):
        run(contacts.get_finder().lookup(vendor()))
    assert "test-token" not in caplog.text and "test-token" not in json.dumps(contacts.health.__dict__, default=str)


# ---------------------------------------------------------------- the spec's number rule


def on_file(phone, days_ago=100):
    now = utcnow()
    return VendorContact(vendor_id="ven_t1", phone=phone, source="on_file", first_seen=now - timedelta(days=400), last_verified=now - timedelta(days=days_ago))


def found(phone, url=SITE + "contact.html", confidence="high"):
    now = utcnow()
    c = contacts.IndependentContact(phone=phone, source="website", source_url=url, found_at=now, confidence=confidence, agreement="consistent")
    return contacts.LookupResult(status="found", contact=c, agreement="consistent", confidence=confidence, source_url=url, checked_at=now)


def test_they_match_the_website_is_the_source_and_its_url_is_the_proof():
    c = verify.choose_number([on_file("+14155550100")], found("+1 (415) 555-0100"))
    assert (c.phone, c.source.value, c.flagged, c.hold_reasons) == ("+14155550100", "website", False, [])
    assert c.source_url == SITE + "contact.html" and c.record is not None


def test_the_most_recently_verified_on_file_contact_is_the_one_compared():
    old, new = on_file("+14155550101", 300), on_file("+14155550100", 10)
    assert verify.choose_number([old, new], found("+14155550100")).flagged is False
    assert verify.choose_number([old, new], found("+14155550101")).flagged is True  # the older number is not the one compared


def test_they_differ_the_one_verified_longest_ago_wins_and_the_disagreement_is_a_hold_reason_with_an_evidence_id():
    c = verify.choose_number([on_file("+14155550100")], found("+14155550166"))
    assert (c.phone, c.source.value, c.flagged) == ("+14155550100", "on_file", True)
    (h,) = c.hold_reasons
    assert h["reason"] == "contact sources disagree" and h["evidence_id"].startswith("evd_") and "0100" in h["detail"] and "0166" in h["detail"]
    assert c.record.phone == "+14155550166"  # recorded, not used


@pytest.mark.parametrize("status,agreement,confidence", [("not_usable", "none_found", "low"), ("not_usable", "conflicting", "low")])
def test_low_confidence_or_none_found_uses_the_on_file_number_and_says_so(status, agreement, confidence):
    lk = contacts.LookupResult(status=status, agreement=agreement, confidence=confidence, confidence_reason="x", checked_at=utcnow())
    c = verify.choose_number([on_file("+14155550100")], lk)
    assert (c.phone, c.source.value, c.record) == ("+14155550100", "on_file", None)
    assert [h["reason"] for h in c.hold_reasons] == ["independent contact check found no usable number"] and c.hold_reasons[0]["evidence_id"].startswith("evd_")


def test_apify_unavailable_uses_the_on_file_number_and_says_so():
    lk = contacts.LookupResult(status="unavailable", error="TimeoutError", checked_at=utcnow())
    c = verify.choose_number([on_file("+14155550100")], lk)
    assert c.phone == "+14155550100" and [h["reason"] for h in c.hold_reasons] == ["independent contact check unavailable"]


def test_with_no_on_file_number_and_nothing_found_there_is_nothing_to_dial():
    with pytest.raises(ValueError):
        verify.choose_number([], contacts.LookupResult(status="unavailable", checked_at=utcnow()))


# ---------------------------------------------------------------- demo routing


def test_route_parsing_ignores_bad_pairs(monkeypatch):
    cfg = get_settings()
    monkeypatch.setattr(cfg, "demo_call_routes", "+14155550100=+14155550177, nonsense, +1415=+1, +14155550101=+14155550178")
    assert cfg.demo_call_route_map == {"+14155550100": "+14155550177", "+14155550101": "+14155550178"}
    assert verify.route_number("+14155550100") == ("+14155550177", True) and verify.route_number("+14155550199") == ("+14155550199", False)


# ---------------------------------------------------------------- the whole verification, through the API


def detail(client, pid):
    return client.get(f"/api/payments/{pid}").json()


def attack(client, **over):
    a = client.post("/api/attacks", json=CLASSIC).json()
    wait(client, a["run_id"])
    return a["payment_id"], a


def events_of(eng, pid, kind):
    with Session(eng) as s:
        return [e.payload for e in s.exec(select(Event).where(Event.type == kind)) if (e.payload or {}).get("payment_id") == pid]


def test_payment_detail_and_call_started_show_the_number_source_url_confidence_and_agreement(env):
    client, eng = env
    pid, _ = attack(client)
    ic = detail(client, pid)["independent_contact"]
    assert ic["provider"] == "Apify Vendor Contact Verifier" and ic["status"] == "found" and ic["number_source"] == "website"
    assert ic["source_url"].startswith("https://aayushswami123.github.io/Countersign/summit-concrete/") and ic["confidence"] == "high" and ic["agreement"] == "consistent"
    assert ic["sources_agree"] is True and ic["hold_reasons"] == [] and ic["evidence_id"].startswith("aud_")
    started = events_of(eng, pid, "call.started")[0]
    assert started["contact_source"] == "website" and started["source_url"] == ic["source_url"] and started["confidence"] == "high"
    assert started["agreement"] == "consistent" and started["sources_agree"] is True and started["hold_reasons"] == []
    call = detail(client, pid)["calls"][0]
    assert call["contact"]["source"] == "website" and call["contact"]["source_url"] == ic["source_url"]
    with Session(eng) as s:
        row_ = s.exec(select(VendorContact).where(VendorContact.vendor_id == "ven_summit", VendorContact.source == "website")).first()
        assert row_.source_url == ic["source_url"] and row_.last_verified is not None
        assert s.exec(select(AuditLog).where(AuditLog.entity_id == pid, AuditLog.action == "independent_contact_checked")).one()
        assert s.exec(select(AuditLog).where(AuditLog.entity == "vendor_contact", AuditLog.action == "contact_recorded")).first()


def test_disagreeing_sources_call_the_on_file_number_and_hold_with_a_reason_ask_can_cite(env):
    client, eng = env
    contacts.MOCK_OVERRIDES["ven_summit"] = "+14155550166"  # the website shows another number
    pid, _ = attack(client)
    d = detail(client, pid)
    ic = d["independent_contact"]
    assert ic["sources_agree"] is False and ic["number_source"] == "on_file" and d["payment"]["status"] in ("blocked", "held")
    (h,) = ic["hold_reasons"]
    assert h["reason"] == "contact sources disagree" and "contact sources disagree" in d["risk"]["reasons"]
    assert d["calls"][0]["contact"]["source"] == "on_file"  # the call went to the number on file
    assert events_of(eng, pid, "call.started")[0]["hold_reasons"] == ["contact sources disagree"]
    answer = client.post(f"/api/payments/{pid}/ask", json={"question": "Where did you get this number?"}).json()
    ids = {e["id"] for e in answer["evidence"]}
    assert ic["evidence_id"] in ids and h["evidence_id"] in ids
    assert answer["claims"] and all(c["evidence_id"] in ids for c in answer["claims"])


def test_ask_where_did_you_get_this_number_answers_with_the_source_url(env):
    client, eng = env
    pid, _ = attack(client)
    a = client.post(f"/api/payments/{pid}/ask", json={"question": "Where did you get this number?"}).json()
    assert "https://aayushswami123.github.io/Countersign/summit-concrete/contact.html" in a["answer"] and "Apify Vendor Contact Verifier" in a["answer"]
    assert a["claims"] and any(e["kind"] == "independent_contact" for e in a["evidence"])


def test_an_apify_failure_never_stops_the_call_or_removes_the_hold(env, monkeypatch):
    client, eng = env

    async def boom(self, vendor):
        raise RuntimeError("apify is down")

    monkeypatch.setattr(contacts.RealContactFinder, "_run", boom)
    monkeypatch.setattr(contacts, "get_finder", lambda: contacts.RealContactFinder())
    pid, _ = attack(client)
    d = detail(client, pid)
    assert d["payment"]["status"] == "blocked" and d["payment"]["nessie_transfer_id"] is None  # the vendor denied on the call: blocked, nothing paid
    assert d["calls"] and d["calls"][0]["contact"]["source"] == "on_file"
    assert d["independent_contact"]["status"] == "unavailable" and [h["reason"] for h in d["independent_contact"]["hold_reasons"]] == ["independent contact check unavailable"]
    assert contacts.health.degraded
    st = {r["name"]: r for r in client.get("/api/system/status").json()}
    monkeypatch.setattr(get_settings(), "mock_apify", False)
    st = {r["name"]: r for r in client.get("/api/system/status").json()}
    assert st["Vendor phone lookup (Apify)"]["mode"] == "degraded" and "failed" in st["Vendor phone lookup (Apify)"]["detail"]


def test_the_payment_agent_still_cannot_write_contacts():
    import inspect

    from app.services import payments, run

    for module in (payments, run, contacts):
        assert "VendorContact(" not in inspect.getsource(module), module.__name__
    assert "VendorContact(" in inspect.getsource(verify)


def test_status_shows_routing_only_when_routes_are_set(env, monkeypatch):
    client, eng = env
    names = {r["name"]: r for r in client.get("/api/system/status").json()}
    assert "Demo call routing" not in names
    monkeypatch.setattr(get_settings(), "demo_call_routes", f"{ON_FILE}=+14155550177")
    r = {r["name"]: r for r in client.get("/api/system/status").json()}["Demo call routing"]
    assert r["detail"] == "Demo: calls routed to team phone" and "0177" not in json.dumps(r)


# ---------------------------------------------------------------- routing at dial time


@pytest.fixture
def real_dial(env, monkeypatch, tmp_path):
    """Real Twilio mode with the network faked: records the number each call is placed to."""
    client, eng = env
    cfg = get_settings()
    monkeypatch.setattr(voice, "AUDIO_DIR", tmp_path / "audio")
    monkeypatch.setattr(cfg, "mock_twilio", False)
    monkeypatch.setattr(cfg, "mock_cartesia", False)
    monkeypatch.setattr(cfg, "public_base_url", "https://pub.example")
    dialed = []

    async def fake_place(to, url, status_callback=None, settings=None):
        voice.assert_call_allowed(to, cfg)  # the real gate
        dialed.append(to)
        return "CAtest"

    async def fake_clip(text, settings=None):
        return "https://pub.example/x.wav"

    monkeypatch.setattr(voice, "place_call", fake_place)
    monkeypatch.setattr(voice, "tts_clip", fake_clip)
    return client, eng, dialed, cfg


def test_a_route_replaces_the_number_at_dial_time_only(real_dial, monkeypatch):
    client, eng, dialed, cfg = real_dial
    team = "+14155550177"
    monkeypatch.setattr(cfg, "allowed_call_numbers", team)  # only the team phone is allowed: the fictional number is not
    monkeypatch.setattr(cfg, "demo_call_routes", f"{ON_FILE}={team}")
    pid, _ = attack(client)
    assert dialed == [team]
    d = detail(client, pid)
    blob = json.dumps(d) + json.dumps(events_of(eng, pid, "call.started"))
    assert "0177" not in blob  # payment detail and events show the fictional number, never the team phone
    assert d["calls"][0]["contact"]["phone"].endswith("0142")
    with Session(eng) as s:
        rows = s.exec(select(AuditLog).where(AuditLog.entity_id == pid, AuditLog.action == "demo routing: call delivered to team phone")).all()
        assert len(rows) == 1 and rows[0].detail_json["verified_number_ending"] == "0142"
        assert "0177" not in json.dumps(rows[0].detail_json)  # nothing of the team phone is written
        every = json.dumps([e.payload for e in s.exec(select(Event))])
        assert "0177" not in every


def test_the_allow_list_applies_to_the_routed_number(real_dial, monkeypatch):
    client, eng, dialed, cfg = real_dial
    monkeypatch.setattr(cfg, "allowed_call_numbers", ON_FILE)  # the verified number is allowed, the route target is not
    monkeypatch.setattr(cfg, "demo_call_routes", f"{ON_FILE}=+14085551234")
    pid, _ = attack(client)
    assert dialed == []  # refused before anything was dialed
    with Session(eng) as s:
        assert s.exec(select(AuditLog).where(AuditLog.entity_id == pid, AuditLog.action == "verification_unavailable")).first()
        assert not s.exec(select(AuditLog).where(AuditLog.action.like("demo routing%"))).all()
    assert detail(client, pid)["payment"]["status"] == "held"  # the hold stays


def test_without_a_route_the_verified_number_is_dialed_as_before(real_dial, monkeypatch):
    client, eng, dialed, cfg = real_dial
    monkeypatch.setattr(cfg, "allowed_call_numbers", ON_FILE)
    attack(client)
    assert dialed == [ON_FILE]
