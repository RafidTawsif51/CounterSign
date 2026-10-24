# Owner: Aditya
# Prize track: Microsoft (Built for the Real World), CRS (identity feeds the score), Armadin
# Contract: assess(payment: Payment, context: RiskContext) -> Assessment
#   Synchronous and side-effect free. The caller builds RiskContext from the database (nothing here
#   queries it) and persists with Assessment.to_row(). Hard rules are checked first and always force
#   a hold; no weight, model or context value can lower a decision below what a fired rule requires.
#   Every signal carries an evidence_id so /ask can cite it.
# Flag: MOCK_CLAUDE (the urgency/authority classifier is the Claude part).
# The mock is complete for the hard rules and all eight spec weights; urgency uses the keyword list
# only. Weights are hackathon starting points, not validated values.
#
# Two things NOT in the spec, added on purpose (change or drop them freely):
#   * vendor_identity_check signal (weight 15 when CRS is not "verified", weight 0 info line when the
#     destination changed and CRS verified), so the CRS result visibly feeds the decision.
#   * contacts_differ is treated as a rule that forces a hold, per "any hard rule forces a hold",
#     and carries the action "ignore the new contacts; use only independent numbers".

import statistics
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Protocol

from pydantic import BaseModel
from rapidfuzz.distance import Levenshtein

from app.config import get_settings
from app.models import Decision, Message, Payment, RiskAssessment, Signal, Vendor, utcnow
from app.services.identity import IdentityResult
from app.services.injection import Finding

MODEL_VERSION = "mock-risk-1"

WEIGHTS = {
    "bank_details_changed": 30,
    "lookalike_domain": 25,
    "reply_to_mismatch": 15,
    "urgency_language": 15,
    "amount_outlier": 15,
    "invoice_format_changed": 10,
    "first_message_from_sender": 10,
    "outside_usual_hours": 5,
    "vendor_identity_check": 15,
}

URGENCY_KEYWORDS = [
    "today", "urgent", "immediately", "asap", "right away", "confidential", "keep it quiet",
    "don't tell", "do not tell", "ceo approved", "ceo said", "the ceo", "wire", "overdue", "final notice",
]

# Decision severity, low to high.
_ORDER = [Decision.auto_pay, Decision.controller_review, Decision.hold, Decision.hold_and_verify]

HARD_RULE_ACTIONS = {
    "destination_changed": "Hold and place a verification call",
    "new_vendor": "Hold for controller review",
    "hidden_instructions": "Quarantine the document, hold, flag as attack",
    "contacts_differ": "Ignore the new contacts; use only independent numbers",
    "amount_over_max": "Hold for controller review",
}
_RULE_DECISION = {
    "destination_changed": Decision.hold_and_verify,
    "new_vendor": Decision.controller_review,
    "hidden_instructions": Decision.hold,
    "contacts_differ": Decision.hold,
    "amount_over_max": Decision.controller_review,
}
HIDDEN_RULE_MIN_CONFIDENCE = 0.5


@dataclass(frozen=True)
class Destination:
    routing_hash: str
    account_last4: str


@dataclass
class RiskContext:
    vendor: Vendor
    requested_destination: Optional[Destination]  # where this invoice asks us to pay; None = no bank details
    last_verified_destination: Optional[Destination]  # current vendor_bank_accounts row
    message: Optional[Message] = None  # the email that carried the request, if any
    history_amounts: list[float] = field(default_factory=list)  # vendor's last 12 months
    prior_payment_count: int = 0
    known_sender_addresses: set[str] = field(default_factory=set)
    usual_send_hours: Optional[set[int]] = None  # UTC hours the vendor usually emails
    layout_changed: bool = False
    requested_contacts_differ: bool = False
    injection_findings: list[Finding] = field(default_factory=list)
    identity: Optional[IdentityResult] = None
    now: datetime = field(default_factory=utcnow)


class Assessment(BaseModel):
    payment_id: str
    score: int
    decision: Decision
    hard_rules_fired: list[str]
    hard_rule_actions: dict[str, str]
    signals: list[Signal]
    reasons: list[str]  # human lines for payment.held; CRS result is one of them
    model_version: str

    def to_row(self) -> RiskAssessment:
        return RiskAssessment(
            payment_id=self.payment_id,
            score=self.score,
            decision=self.decision,
            hard_rules_fired=self.hard_rules_fired,
            signals_json=[s.model_dump() for s in self.signals],
            model_version=self.model_version,
        )


class RiskAssessor(Protocol):
    def assess(self, payment: Payment, context: RiskContext) -> Assessment: ...


def _domain(addr: str) -> str:
    return addr.rsplit("@", 1)[-1].lower().strip()


def _skeleton(domain: str) -> str:
    d = domain.replace("rn", "m").replace("vv", "w")
    return d.translate(str.maketrans("0158", "olsb")).replace("-", "")


def _max(a: Decision, b: Decision) -> Decision:
    return a if _ORDER.index(a) >= _ORDER.index(b) else b


class MockRiskAssessor:
    def assess(self, payment: Payment, ctx: RiskContext) -> Assessment:
        signals = self._signals(payment, ctx)
        fired = self._hard_rules(payment, ctx)

        score = min(100, sum(s.weight for s in signals))
        decision = Decision.auto_pay
        if score >= 60:
            decision = Decision.hold_and_verify if "destination_changed" in fired else Decision.hold
        elif score >= 30:
            decision = Decision.controller_review
        for rule in fired:  # hard rules can only raise the decision
            decision = _max(decision, _RULE_DECISION[rule])

        return Assessment(
            payment_id=payment.id,
            score=score,
            decision=decision,
            hard_rules_fired=fired,
            hard_rule_actions={r: HARD_RULE_ACTIONS[r] for r in fired},
            signals=sorted(signals, key=lambda s: -s.weight),
            reasons=self._reasons(payment, ctx, fired, signals),
            model_version=MODEL_VERSION,
        )

    # -- hard rules (spec table) -------------------------------------------------------------
    def _hard_rules(self, payment: Payment, ctx: RiskContext) -> list[str]:
        fired = []
        req, last = ctx.requested_destination, ctx.last_verified_destination
        if req is not None and req != last:  # includes "no verified account yet": a new destination
            fired.append("destination_changed")
        created = ctx.vendor.created_at
        if (ctx.now - created).days < 30 or ctx.prior_payment_count == 0:
            fired.append("new_vendor")
        if any(f.confidence >= HIDDEN_RULE_MIN_CONFIDENCE for f in ctx.injection_findings):
            fired.append("hidden_instructions")
        if ctx.requested_contacts_differ:
            fired.append("contacts_differ")
        if ctx.history_amounts and payment.amount_usd > 1.5 * max(ctx.history_amounts):
            fired.append("amount_over_max")
        return fired

    # -- weighted signals (spec table) -------------------------------------------------------
    def _signals(self, payment: Payment, ctx: RiskContext) -> list[Signal]:
        out: list[Signal] = []

        def add(name: str, detail: str, weight: Optional[int] = None) -> None:
            out.append(Signal(name=name, weight=WEIGHTS[name] if weight is None else weight, detail=detail))

        req, last = ctx.requested_destination, ctx.last_verified_destination
        if req is not None and req != last:
            add("bank_details_changed", f"New account ending {req.account_last4}; last verified ending {last.account_last4 if last else 'none'}")

        msg = ctx.message
        if msg:
            sender_dom, vendor_dom = _domain(msg.from_addr), ctx.vendor.email_domain.lower()
            if sender_dom != vendor_dom and (
                Levenshtein.distance(sender_dom, vendor_dom) <= 2 or _skeleton(sender_dom) == _skeleton(vendor_dom)
            ):
                add("lookalike_domain", f"{sender_dom} vs {vendor_dom}")
            if msg.reply_to and msg.reply_to.lower() != msg.from_addr.lower():
                add("reply_to_mismatch", f"Reply-To: {msg.reply_to}")
            text = f"{msg.subject} {msg.body}".lower()
            hits = [k for k in URGENCY_KEYWORDS if k in text]
            if hits:
                add("urgency_language", "matched " + ", ".join(f"'{h}'" for h in hits[:4]))
            if msg.from_addr.lower() not in {a.lower() for a in ctx.known_sender_addresses}:
                add("first_message_from_sender", f"{msg.from_addr} not seen in vendor history")
            if ctx.usual_send_hours is not None and msg.received_at.hour not in ctx.usual_send_hours:
                add("outside_usual_hours", f"Sent at {msg.received_at.hour:02d}:00 UTC, outside the vendor's usual hours")

        hist = ctx.history_amounts
        if len(hist) >= 3:
            mean = statistics.fmean(hist)
            sd = max(statistics.pstdev(hist), 0.05 * mean)  # floor so a flat history is not infinitely sensitive
            z = (payment.amount_usd - mean) / sd
            if z > 2:
                add("amount_outlier", f"${payment.amount_usd:,.2f} is {z:.1f} standard deviations above the ${mean:,.2f} average")
        if ctx.layout_changed:
            add("invoice_format_changed", "Layout fingerprint differs from the vendor's past invoices")

        ident = ctx.identity
        if ident is not None:
            if ident.status != "verified":
                add("vendor_identity_check", ident.summary)
            elif req is not None and req != last:
                add("vendor_identity_check", ident.summary, weight=0)
        return out

    def _reasons(self, payment: Payment, ctx: RiskContext, fired: list[str], signals: list[Signal]) -> list[str]:
        reasons = []
        for rule in fired:
            reasons.append(f"{rule}: {HARD_RULE_ACTIONS[rule]}")
        for s in sorted(signals, key=lambda s: -s.weight)[:4]:
            if s.weight > 0 and s.name != "vendor_identity_check":
                reasons.append(f"{s.name}: {s.detail}")
        if ctx.identity is not None:
            reasons.append(ctx.identity.summary)  # CRS result always appears in the hold reasons
        return reasons


class RealRiskAssessor(MockRiskAssessor):
    """Same rules, with the Claude urgency/authority classifier in place of the keyword list."""

    def assess(self, payment: Payment, context: RiskContext) -> Assessment:
        raise NotImplementedError("Real risk assessor is not built yet; set MOCK_CLAUDE=true")


def get_assessor() -> RiskAssessor:
    return MockRiskAssessor() if get_settings().mock_claude else RealRiskAssessor()


def assess(payment: Payment, context: RiskContext) -> Assessment:
    return get_assessor().assess(payment, context)
