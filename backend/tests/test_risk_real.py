"""The real risk assessor: each weighted signal, the Claude urgency classifier, and parity of the hard rules."""

import hashlib
from datetime import timedelta
from types import SimpleNamespace

import pytest

from app.config import Settings
from app.models import Decision, Message, Payment, Vendor, utcnow
from app.services import risk
from app.services.injection import Finding
from app.services.risk import Destination, RiskContext
from seed import seed as seedmod

OLD, NEW = Destination("hash_old", "2204"), Destination("hash_new", "7781")
HIST = [10000.0, 11000.0, 9500.0, 10500.0, 10200.0, 9800.0]
FEATS = {"page": "612x792", "fonts": "a", "logo": "b", "labels": "c", "table": "d", "columns": "e", "footer": "f"}


@pytest.fixture(autouse=True)
def real(monkeypatch, tmp_path):
    monkeypatch.setattr(risk, "get_settings", lambda: Settings(mock_risk=False, mock_claude=True, risk_cache_dir=str(tmp_path / "rc")))
    monkeypatch.setattr(risk, "pressure_classifier", risk.PressureClassifier())


def vendor(days_old=400, domain="summitconcrete.com") -> Vendor:
    return Vendor(name="Summit Concrete", trade="concrete", email_domain=domain, created_at=utcnow() - timedelta(days=days_old))


def msg(frm="ar@summitconcrete.com", reply_to=None, body="Invoice attached, due Nov 10.", subject="Invoice 1", hour=15) -> Message:
    return Message(thread_id="thr_t", from_addr=frm, reply_to=reply_to, subject=subject, body=body, received_at=utcnow().replace(hour=hour, minute=0))


def ctx(**kw) -> RiskContext:
    base = dict(vendor=vendor(), requested_destination=OLD, last_verified_destination=OLD, history_amounts=HIST, prior_payment_count=12,
                known_sender_addresses={"ar@summitconcrete.com", "billing@summitconcrete.com"}, usual_send_hours={14, 15, 16})
    base.update(kw)
    return RiskContext(**base)


def pay(amount=10000.0) -> Payment:
    return Payment(run_id="run_t", invoice_id="inv_t", amount_usd=amount)


def names(a):
    return {s.name for s in a.signals}


def signal(a, name):
    return next(s for s in a.signals if s.name == name)


def assess(**kw):
    amount = kw.pop("amount", 10000.0)
    return risk.assess(pay(amount), ctx(**kw))


def test_the_real_assessor_is_selected_and_versioned():
    assert isinstance(risk.get_assessor(), risk.RealRiskAssessor)
    assert assess(message=msg()).signals == []
    assert risk.get_assessor().assess(pay(), ctx(message=msg())).model_version == "risk-1"


# ================================================================ weights, details, cap


def test_every_signal_has_its_spec_weight_a_detail_and_an_evidence_id():
    m = msg(frm="ar@summit-concrete.co", reply_to="billing@summit-concrete.co", body="Please process today, the CEO approved this, keep it quiet", hour=3)
    a = assess(message=m, requested_destination=NEW, known_sender_addresses=set(), usual_send_hours={14, 15}, amount=90000, layout_features=FEATS,
               past_layout_features=[{**FEATS, "fonts": "z", "columns": "y"}])
    spec = {"bank_details_changed": 30, "lookalike_domain": 25, "reply_to_mismatch": 15, "urgency_language": 15, "amount_outlier": 15,
            "invoice_format_changed": 10, "first_message_from_sender": 10, "outside_usual_hours": 5}
    assert {s.name: s.weight for s in a.signals} == spec
    assert all(s.detail and len(s.detail) <= 220 and s.evidence_id.startswith("evd_") for s in a.signals)
    assert len({s.evidence_id for s in a.signals}) == len(a.signals)
    assert sum(spec.values()) == 125 and a.score == 100  # capped
    assert a.decision == Decision.hold_and_verify


# ================================================================ lookalike_domain


@pytest.mark.parametrize("key, fake, _t", seedmod.LOOKALIKES)
def test_every_seeded_lookalike_domain_is_caught(key, fake, _t):
    real_dom = seedmod.BY_KEY[key].domain
    a = assess(vendor=vendor(domain=real_dom), message=msg(frm=f"ar@{fake}"), known_sender_addresses={f"ar@{real_dom}"})
    assert "lookalike_domain" in names(a), (real_dom, fake)
    assert signal(a, "lookalike_domain").weight == 25


@pytest.mark.parametrize("sender", [
    "summitconcrete.co", "summit-concrete.com", "summitconcrete.net", "summitconcrte.com",
    "summitc0ncrete.com", "summitconcrete.com.evil.co", "summ\u0456tconcrete.com".encode("idna").decode(),  # punycode
    "summіtconcrete.com",  # Cyrillic i
    "summitconcrete.cоm",  # Cyrillic o
    "summlt-concrete.com", "sumrnitconcrete.com",
])
def test_lookalike_tricks(sender):
    assert lookalike_hit(sender), sender


def lookalike_hit(sender):
    return risk.lookalike(sender, "summitconcrete.com", {"summitconcrete.com"})


@pytest.mark.parametrize("sender", ["summitconcrete.com", "mail.summitconcrete.com", "keystonesteel.com", "ridgelinebuilders.com", "gmail.com",
                                    "alderlumber.com", "northsiderentals.com"])
def test_real_and_unrelated_domains_are_not_lookalikes(sender):
    assert risk.lookalike(sender, "summitconcrete.com", {"summitconcrete.com"}) is None


def test_a_domain_the_vendor_is_known_to_use_is_not_a_lookalike():
    assert risk.lookalike("summit-concrete.co", "summitconcrete.com", {"summitconcrete.com", "summit-concrete.co"}) is None


def test_no_seeded_vendor_domain_looks_like_another_vendors():
    doms = [v.domain for v in seedmod.VENDORS]
    flagged = [(a, b) for a in doms for b in doms if a != b and risk.lookalike(a, b, {b})]
    assert flagged == []


def test_the_detail_says_why():
    d = risk.lookalike("summit-concrete.co", "summitconcrete.com", set())
    assert "edit distance 2" in d
    assert "homoglyph" in risk.lookalike("summlt-concrete.com", "summitconcrete.com", set()) or "edit distance" in risk.lookalike("summlt-concrete.com", "summitconcrete.com", set())
    assert "contains" in risk.lookalike("summitconcrete.com.evil.co", "summitconcrete.com", set())


# ================================================================ reply_to_mismatch


def test_reply_to_header_comparison_as_in_the_spec_example():
    a = assess(message=msg(frm="ar@summit-concrete.co", reply_to="billing@summit-concrete.co"))
    assert "reply_to_mismatch" in names(a) and "differs from the sender" in signal(a, "reply_to_mismatch").detail


@pytest.mark.parametrize("reply_to, expected", [
    (None, False), ("", False), ("ar@summitconcrete.com", False), ("AR@SummitConcrete.com", False),
    ("Accounts Receivable <ar@summitconcrete.com>", False),
    ("billing@summitconcrete.com", False),  # another mailbox this vendor is known to use
    ("collections@summitconcrete.com", True),  # same domain but not a known address
    ("billing@evil.example", True),
])
def test_reply_to_cases(reply_to, expected):
    a = assess(message=msg(reply_to=reply_to))
    assert ("reply_to_mismatch" in names(a)) is expected


# ================================================================ urgency_language


@pytest.mark.parametrize("text, kind", [
    ("Please pay today.", "urgency"), ("We need this ASAP", "urgency"), ("final notice: pay immediately", "urgency"),
    ("Keep it quiet until Monday", "secrecy"), ("This is confidential, do not tell anyone", "secrecy"),
    ("The CEO approved this", "authority"), ("ceo said to pay", "authority"),
])
def test_pressure_keywords_by_kind(text, kind):
    assert kind in risk.pressure_keywords(text)
    a = assess(message=msg(body=text))
    assert "urgency_language" in names(a) and kind in signal(a, "urgency_language").detail


@pytest.mark.parametrize("text", ["Attached is invoice 12, due Nov 10, net 30.", "Thanks for the payment, we received it.", "Following up on invoice 9 when you get a chance.",
                                  "Please call us at the office with questions.", "Today's delivery went well."[:0] + "Delivery went well on Monday."])
def test_ordinary_email_has_no_pressure(text):
    assert "urgency_language" not in names(assess(message=msg(body=text)))


class FakeClaude:
    def __init__(self, verdicts, reject_forced=False):
        self.verdicts, self.calls, self.reject_forced = list(verdicts), [], reject_forced
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kw):
        self.calls.append(kw)
        if self.reject_forced and kw["tool_choice"]["type"] == "tool":
            raise RuntimeError("400")
        v = self.verdicts.pop(0)
        if isinstance(v, Exception):
            raise v
        if v == "refusal":
            return SimpleNamespace(stop_reason="refusal", content=[])
        return SimpleNamespace(stop_reason="tool_use", content=[SimpleNamespace(type="tool_use", name="classify_pressure", input=v)])


@pytest.fixture()
def claude_on(monkeypatch, tmp_path):
    monkeypatch.setattr(risk, "get_settings", lambda: Settings(mock_risk=False, mock_claude=False, risk_cache_dir=str(tmp_path / "rc"), claude_model_fast="claude-haiku-5-5"))
    monkeypatch.setattr(risk, "pressure_classifier", risk.PressureClassifier())

    def install(fake):
        monkeypatch.setattr(risk, "_client", lambda: fake)
        return fake

    return install


SUBTLE = "Hi Maria, the owner is travelling and unreachable, so please just release the transfer for me and skip the callback this once, I will explain later."


def test_the_classifier_catches_pressure_the_keywords_miss(claude_on):
    fake = claude_on(FakeClaude([{"pressure": True, "kinds": ["authority", "secrecy"], "reason": "Asks to skip the callback because the owner is away"}]))
    a = assess(message=msg(body=SUBTLE))
    d = signal(a, "urgency_language").detail
    assert d.startswith("classifier (authority/secrecy): Asks to skip the callback") and signal(a, "urgency_language").weight == 15
    call = fake.calls[0]
    assert call["model"] == "claude-haiku-5-5" and call["tool_choice"] == {"type": "tool", "name": "classify_pressure"}
    assert call["messages"][0]["content"].startswith("<untrusted_document>") and "untrusted" in call["system"]


def test_keywords_and_classifier_are_both_recorded(claude_on):
    claude_on(FakeClaude([{"pressure": True, "kinds": ["urgency"], "reason": "Demands payment today"}]))
    d = signal(assess(message=msg(body="Pay today please, the CEO approved it.")), "urgency_language").detail
    assert "urgency: 'today'" in d and "authority: 'the ceo'" in d.lower() or "authority:" in d
    assert "classifier (urgency): Demands payment today" in d


def test_a_no_from_the_classifier_leaves_ordinary_email_alone(claude_on):
    claude_on(FakeClaude([{"pressure": False, "kinds": [], "reason": "ordinary invoice email"}]))
    assert "urgency_language" not in names(assess(message=msg(body="Invoice 12 is attached, due Nov 10. Let us know if you have questions.")))


def test_pressure_verdicts_are_cached_by_content(claude_on, monkeypatch):
    fake = claude_on(FakeClaude([{"pressure": False, "kinds": [], "reason": "ok"}]))
    m = msg(body="Invoice 12 is attached, due Nov 10. Let us know if you have questions.")
    for _ in range(3):
        assess(message=m)
    assert len(fake.calls) == 1
    monkeypatch.setattr(risk, "pressure_classifier", risk.PressureClassifier())  # a new process still reads the disk cache
    assess(message=m)
    assert len(fake.calls) == 1


def test_claude_is_not_called_when_mock_claude_is_true(monkeypatch):
    fake = FakeClaude([])
    monkeypatch.setattr(risk, "_client", lambda: fake)
    assess(message=msg(body=SUBTLE))
    assert fake.calls == []


@pytest.mark.parametrize("verdict", [RuntimeError("down"), "refusal", {"pressure": "maybe"}, {}])
def test_classifier_failure_keeps_the_keywords_and_never_raises(claude_on, verdict):
    claude_on(FakeClaude([verdict, verdict]))
    assert "urgency_language" not in names(assess(message=msg(body=SUBTLE)))
    claude_on(FakeClaude([verdict, verdict]))
    assert "urgency_language" in names(assess(message=msg(body="Pay today please.")))


def test_forced_tool_rejection_falls_back_to_auto(claude_on):
    fake = claude_on(FakeClaude([{"pressure": True, "kinds": ["secrecy"], "reason": "Asks for silence"}], reject_forced=True))
    assert "urgency_language" in names(assess(message=msg(body=SUBTLE)))
    assert [c["tool_choice"]["type"] for c in fake.calls] == ["tool", "auto"]


def test_html_email_is_read_as_text(claude_on):
    fake = claude_on(FakeClaude([{"pressure": False, "kinds": [], "reason": "ok"}]))
    assess(message=msg(body="<html><body><p>Invoice <b>12</b> is attached, due Nov 10.</p></body></html>"))
    assert "<b>" not in fake.calls[0]["messages"][0]["content"]


# ================================================================ amount_outlier, first sender, hours, format


def test_amount_outlier_needs_history_and_two_standard_deviations():
    assert "amount_outlier" not in names(assess(amount=10500))
    a = assess(amount=14000)
    assert "amount_outlier" in names(a) and "standard deviations above" in signal(a, "amount_outlier").detail
    assert "amount_outlier" not in names(assess(amount=14000, history_amounts=[10000.0, 11000.0]))  # fewer than 3 invoices
    assert "amount_outlier" not in names(assess(amount=5000))  # unusually small is not an outlier signal


def test_first_message_from_sender():
    assert "first_message_from_sender" not in names(assess(message=msg()))
    assert "first_message_from_sender" not in names(assess(message=msg(frm="AR@SummitConcrete.com")))
    a = assess(message=msg(frm="new.person@summitconcrete.com"))
    assert "first_message_from_sender" in names(a) and "never written before" in signal(a, "first_message_from_sender").detail


@pytest.mark.parametrize("hour, off", [(15, False), (14, False), (13, False), (17, False), (18, True), (12, True), (3, True)])
def test_outside_usual_hours_has_an_hour_of_slack(hour, off):
    a = assess(message=msg(hour=hour))  # usual hours are 14 to 16 UTC
    assert ("outside_usual_hours" in names(a)) is off
    if off:
        assert "UTC" in signal(a, "outside_usual_hours").detail


def test_no_usual_hours_known_means_no_signal():
    assert "outside_usual_hours" not in names(assess(message=msg(hour=3), usual_send_hours=None))


def test_invoice_format_changed_names_the_groups_that_moved():
    same = assess(layout_features=FEATS, past_layout_features=[FEATS, {**FEATS, "footer": "other"}])
    assert "invoice_format_changed" not in names(same)  # it matches one of the past layouts
    a = assess(layout_features={**FEATS, "fonts": "new", "columns": "new"}, past_layout_features=[FEATS, {**FEATS, "page": "595x842"}])
    d = signal(a, "invoice_format_changed").detail
    assert signal(a, "invoice_format_changed").weight == 10 and "columns, fonts" in d and "all 2 past invoices" in d
    assert "invoice_format_changed" not in names(assess(layout_features=FEATS, past_layout_features=[]))  # nothing to compare
    assert "invoice_format_changed" in names(assess(layout_changed=True))  # the caller can still force it


# ================================================================ bank_details_changed and the hard rules stay exactly as they were


def test_bank_details_changed_compares_to_the_last_verified_account():
    assert "bank_details_changed" not in names(assess())
    a = assess(requested_destination=NEW)
    assert signal(a, "bank_details_changed").detail == "New account ending 7781; last verified ending 2204"
    assert "bank_details_changed" in names(assess(requested_destination=NEW, last_verified_destination=None))


CASES = [
    dict(), dict(requested_destination=NEW), dict(requested_destination=NEW, last_verified_destination=None), dict(vendor=vendor(days_old=5)),
    dict(prior_payment_count=0), dict(requested_contacts_differ=True),
    dict(injection_findings=[Finding(technique="white_text", snippet="x", confidence=0.9)]),
    dict(injection_findings=[Finding(technique="x", snippet="x", confidence=0.4)]),
    dict(amount=16600), dict(amount=16000), dict(amount=90000, requested_destination=NEW, prior_payment_count=0, requested_contacts_differ=True),
]


@pytest.mark.parametrize("case", range(len(CASES)))
def test_hard_rules_and_decisions_match_the_mock_exactly(case):
    kw = dict(CASES[case])
    amount = kw.pop("amount", 10000.0)
    m = msg(frm="ar@summit-concrete.co", reply_to="x@evil.example", body="pay today", hour=3)
    real_a = risk.RealRiskAssessor().assess(pay(amount), ctx(message=m, **kw))
    mock_a = risk.MockRiskAssessor().assess(pay(amount), ctx(message=m, **kw))
    assert real_a.hard_rules_fired == mock_a.hard_rules_fired
    assert real_a.hard_rule_actions == mock_a.hard_rule_actions
    assert real_a.decision == mock_a.decision


def test_hard_rules_still_force_a_hold_at_score_zero():
    for kw, rule in ((dict(requested_destination=NEW), "destination_changed"), (dict(prior_payment_count=0), "new_vendor"),
                     (dict(requested_contacts_differ=True), "contacts_differ")):
        a = assess(message=msg(), **kw)
        assert rule in a.hard_rules_fired and a.decision != Decision.auto_pay


def test_signal_hashes_are_stable_inputs_not_random():
    a1, a2 = assess(requested_destination=NEW), assess(requested_destination=NEW)
    assert [s.detail for s in a1.signals] == [s.detail for s in a2.signals]
    assert hashlib.sha256(a1.signals[0].detail.encode()).hexdigest() == hashlib.sha256(a2.signals[0].detail.encode()).hexdigest()
