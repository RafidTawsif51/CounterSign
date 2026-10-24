# Owner: Teammate B
# Prize track: CRS (Best Overall, Financial AI Agent, Identity / Fraud)
# Contract: async check(vendor: Vendor) -> IdentityResult
#   CRS is central, not bolted on: services/risk.py takes the result in RiskContext.identity, adds a
#   vendor_identity_check signal, and puts result.summary in the hold reasons. The vendor card shows
#   the same result. check() never raises for "not verified"; that is a normal status.
#   check_vendor(vendor_id, request_context) is the richer entry point used by services/verify.py BEFORE a call is dialed:
#   it runs three real CRS sandbox checks at once and returns {status: pass|review|fail, checks, summary, dial_index}.
#   verify.py releases money after a confirmed call only when status is pass.
# Flag: MOCK_CRS (true keeps the deterministic mock below, exactly as before).
#
# Products used (and only these): Accurate Append reverse lookup by phone, AtData Fraud Finder, TransUnion identity
# verification (basic). No credit report, criminal, eviction or bankruptcy endpoint is ever called: minimum necessary
# data, and we have no permissible purpose for those.
#
# SANDBOX TEST IDENTITIES: the CRS sandbox only returns meaningful data for its published test personas, so our fictional
# vendors and attackers are mapped onto them (SANDBOX_PERSONAS). CRS lookups use the mapped persona's data. The number we
# actually dial is still DEMO_VENDOR_PHONE; the reverse lookup asks CRS about the persona's phone, not that number.
# Response shapes were discovered live against the sandbox; parsers treat anything unexpected as "review", never "pass".
#
# Data handling: only summaries are kept (check name, pass/review/fail, score, short reason strings, CRS request id). No SSN, birth
# date, address or raw response is stored, returned or logged. Every request has an 8 s timeout.

import asyncio
import hashlib
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Awaitable, Callable, Literal, Optional, Protocol

import httpx
from pydantic import BaseModel

from app.config import get_settings
from app.models import Vendor, utcnow

log = logging.getLogger("countersign.identity")

CRS_BASE_URL = "https://api-sandbox.stitchcredit.com:443/api"
REQUEST_TIMEOUT_SECONDS = 8
CHECK_BUDGET_SECONDS = 4  # the run's identity step never waits longer than this; on expiry the vendor is "unverified"
CACHE_TTL_SECONDS = 600


# ---------------------------------------------------------------- sandbox test identities


@dataclass(frozen=True)
class Persona:
    """A CRS sandbox TEST persona (fictional data published in CRS's sandbox collection). Not a real person. These fields are
    sent to the CRS sandbox only; they are never stored, logged or returned by this module."""

    code: str
    first: str
    last: str
    phone: str
    email: str
    ip: str
    ssn: str
    dob: str
    street: str
    city: str
    state: str
    zip: str


# SANDBOX_PERSONAS: our fictional data mapped onto CRS test personas. The exact request fields come from CRS's own collection.
SANDBOX_PERSONAS: dict[str, Persona] = {
    "P01": Persona("P01", "MARGARET", "OKAFOR", "5550101001", "margaret.okafor@example.com", "203.0.113.11", "666701001", "1984-03-14", "1420 WILLOW CREEK DR", "SAN JOSE", "CA", "95125"),
    "P02": Persona("P02", "DANIEL", "WHITFIELD", "5550101002", "daniel.whitfield@example.com", "203.0.113.12", "666701002", "1972-11-02", "88 LAKESHORE BLVD", "AUSTIN", "TX", "78746"),
    "P12": Persona("P12", "VICTOR", "ANAND", "5550101012", "v.anand.1968@example.com", "198.51.100.12", "666701012", "1968-08-08", "55 WATER ST FL 20", "NEW YORK", "NY", "10041"),
    "P13": Persona("P13", "KAYLA", "BRENNAN", "5550101013", "kb.9921x@example.com", "198.51.100.13", "666701013", "1999-12-24", "9021 KINGSTON PIKE", "KNOXVILLE", "TN", "37923"),
    "P19": Persona("P19", "GRACE", "NAKAMURA", "5550101019", "grace.nakamura@example.com", "203.0.113.29", "666701019", "1976-09-16", "1850 SOLANO AVE", "BERKELEY", "CA", "94707"),
}
VENDOR_PERSONA_OVERRIDES = {"ven_summit": "P19"}  # Summit Concrete's owner/contact: small-business owner, APPROVE
APPROVE_PERSONAS = ("P01", "P02", "P19")  # every other demo vendor maps to one of these, stably by vendor id
ATTACKER_PERSONA = "P13"  # synthetic identity / fraud
ATTACKER_ALT_PERSONA = "P12"  # identity mismatch: used when the request's Reply-To differs from its sender


def vendor_persona(vendor_id: str) -> Persona:
    code = VENDOR_PERSONA_OVERRIDES.get(vendor_id) or APPROVE_PERSONAS[int(hashlib.sha256(vendor_id.encode()).hexdigest()[:8], 16) % len(APPROVE_PERSONAS)]
    return SANDBOX_PERSONAS[code]


def _domain(addr: Optional[str]) -> str:
    return (addr or "").rsplit("@", 1)[-1].strip().lower().rstrip(">") if addr and "@" in addr else ""


def requester_persona(vendor: Vendor, request_email: Optional[str], reply_to: Optional[str]) -> tuple[Persona, str]:
    """Who stands behind the request: the vendor's own persona if the sender is on the vendor's known domain (or there is no
    request, as on the vendor card), otherwise an attacker persona. Uses the sender address only, never the is_attack label."""
    sender = _domain(request_email)
    if not sender or sender == vendor.email_domain.lower() or sender.endswith("." + vendor.email_domain.lower()):
        return vendor_persona(vendor.id), "vendor"
    if reply_to and _domain(reply_to) != sender:
        return SANDBOX_PERSONAS[ATTACKER_ALT_PERSONA], "requester"
    return SANDBOX_PERSONAS[ATTACKER_PERSONA], "requester"


# ---------------------------------------------------------------- CRS client


class CrsUnavailable(Exception):
    """CRS could not be reached, timed out, or answered with an error. Never carries a body, token or persona field."""


def _env(name: str) -> str:
    """os.getenv first; otherwise the same key from .env (pydantic reads .env without filling os.environ). Only that key is read."""
    val = os.getenv(name)
    if val is not None:
        return val.strip()
    if "PYTEST_CURRENT_TEST" in os.environ:
        return ""  # tests set these through the environment; a developer's .env must not change their results
    try:
        from dotenv import dotenv_values

        for path in (".env", "../.env"):
            got = dotenv_values(path).get(name)
            if got:
                return got.strip()
    except Exception:  # noqa: BLE001
        pass
    return ""


class CrsClient:
    """Bearer-token client for the CRS sandbox. The token is cached in memory; on a 401 it is refreshed, or the client logs in
    again (the refresh endpoint rejects a token that is not near expiry as "premature", so re-login is the normal path)."""

    def __init__(self, transport: Optional[httpx.AsyncBaseTransport] = None, base_url: str = CRS_BASE_URL):
        self.base_url = base_url
        self.transport = transport
        self._token: Optional[str] = None
        self._refresh: Optional[str] = None
        self._expires_at = 0.0
        self._lock: Optional[asyncio.Lock] = None
        self._lock_loop: Optional[asyncio.AbstractEventLoop] = None
        self.requests = 0  # every HTTP request made, for the run-speed measurement

    def _http(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS, transport=self.transport)

    def _login_lock(self) -> asyncio.Lock:
        loop = asyncio.get_running_loop()
        if self._lock is None or self._lock_loop is not loop:
            self._lock, self._lock_loop = asyncio.Lock(), loop
        return self._lock

    def _store(self, data: dict) -> bool:
        token = data.get("token")
        if not token:
            return False
        self._token, self._refresh = token, data.get("refreshToken") or self._refresh
        self._expires_at = time.monotonic() + max(60, int(data.get("expires") or 3600)) - 60
        return True

    async def _post_raw(self, path: str, json_body: dict, token: Optional[str] = None) -> httpx.Response:
        self.requests += 1
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        try:
            async with self._http() as http:
                return await http.post(f"{self.base_url}{path}", json=json_body, headers=headers)
        except httpx.HTTPError as exc:
            log.warning("CRS %s failed: %s", path, type(exc).__name__)
            raise CrsUnavailable(type(exc).__name__) from None

    async def login(self) -> None:
        user, pw = _env("CRS_USERNAME"), _env("CRS_PASSWORD")
        if not user or not pw:
            raise CrsUnavailable("CRS credentials are not set")
        resp = await self._post_raw("/users/login", {"username": user, "password": pw})
        data = resp.json() if resp.status_code < 300 else {}
        if not self._store(data if isinstance(data, dict) else {}):
            log.warning("CRS login failed: HTTP %s", resp.status_code)
            raise CrsUnavailable(f"login HTTP {resp.status_code}")

    async def _ensure_token(self, force: bool = False) -> str:
        async with self._login_lock():
            if force or not self._token or time.monotonic() >= self._expires_at:
                stale = self._token
                refreshed = False
                if force and self._refresh:
                    resp = await self._post_raw("/users/refresh-token", {"refreshToken": self._refresh})
                    data = resp.json() if resp.status_code < 300 else {}
                    refreshed = self._store(data if isinstance(data, dict) else {})
                if not refreshed:
                    self._token = None
                    await self.login()
                log.info("CRS token %s", "refreshed" if refreshed else "obtained" if not stale else "renewed by login")
            assert self._token
            return self._token

    async def post(self, path: str, body: dict) -> tuple[dict, Optional[str]]:
        """POST a product request. Returns (parsed JSON, CRS RequestID header). One refresh/re-login retry on 401."""
        token = await self._ensure_token()
        resp = await self._post_raw(path, body, token)
        if resp.status_code == 401:
            token = await self._ensure_token(force=True)
            resp = await self._post_raw(path, body, token)
        if resp.status_code >= 300:
            log.warning("CRS %s answered HTTP %s", path, resp.status_code)
            raise CrsUnavailable(f"HTTP {resp.status_code}")
        try:
            data = resp.json()
        except ValueError:
            raise CrsUnavailable("response was not JSON") from None
        return (data if isinstance(data, dict) else {}), resp.headers.get("requestid")


_client: Optional[CrsClient] = None
_cache: dict[tuple, tuple[float, dict]] = {}
_inflight: dict[tuple, tuple[asyncio.AbstractEventLoop, asyncio.Task]] = {}


def get_client() -> CrsClient:
    global _client
    if _client is None:
        _client = CrsClient()
    return _client


def set_transport(transport: Optional[httpx.AsyncBaseTransport]) -> CrsClient:
    """Test hook: use a mock transport, with a fresh token and an empty cache."""
    global _client
    _client = CrsClient(transport=transport)
    reset_cache()
    return _client


def reset_cache() -> None:
    _cache.clear()
    _inflight.clear()


async def _cached(key: tuple, factory: Callable[[], Awaitable[dict]]) -> dict:
    """One live CRS request per (check, subject) per 10 minutes, shared by every caller (the payment run, the vendor card,
    the pre-dial gate). Callers that arrive while a request is in flight wait for it instead of sending another."""
    hit = _cache.get(key)
    if hit and hit[0] > time.monotonic():
        return hit[1]
    loop = asyncio.get_running_loop()
    cur = _inflight.get(key)
    if cur is None or cur[0] is not loop:
        task = loop.create_task(factory())
        _inflight[key] = cur = (loop, task)

        def done(t: asyncio.Task, key=key) -> None:
            if _inflight.get(key, (None, None))[1] is t:
                _inflight.pop(key, None)
            if not t.cancelled() and t.exception() is None and "crs_unavailable" not in t.result()["reasons"]:
                _cache[key] = (time.monotonic() + CACHE_TTL_SECONDS, t.result())

        task.add_done_callback(done)
    return await asyncio.shield(cur[1])


# ---------------------------------------------------------------- the three checks (summaries only)


def _check(name: str, result: str, reasons: list[str], request_id: Optional[str], score: Optional[int] = None) -> dict:
    out: dict = {"name": name, "result": result, "reasons": reasons, "crs_request_id": request_id}
    if score is not None:
        out["score"] = score
    return out


def _unavailable(name: str) -> dict:
    return _check(name, "review", ["crs_unavailable"], None)


def parse_reverse(body: dict, persona: Persona, request_id: Optional[str]) -> dict:
    """Accurate Append: does the number belong to the vendor's known contact? Pass only if a record carries the contact's name."""
    records = (body.get("data") or {}).get("records") if isinstance(body.get("data"), dict) else None
    if not isinstance(records, list):
        return _check("reverse_phone", "review", ["unexpected_response"], request_id)
    if not records:
        return _check("reverse_phone", "fail", ["number not listed to any person"], request_id)
    for r in records:
        if isinstance(r, dict) and str(r.get("firstName", "")).upper() == persona.first and str(r.get("lastName", "")).upper() == persona.last:
            return _check("reverse_phone", "pass", ["number is listed to the vendor contact"], request_id)
    return _check("reverse_phone", "fail", ["number is listed to a different person"], request_id)


def parse_fraud_finder(body: dict, request_id: Optional[str]) -> dict:
    """AtData Fraud Finder: risk score 0 to 100. Under 30 pass, 30 to 59 review, 60 and up fail (starting points, not validated)."""
    risk = body.get("risk") if isinstance(body.get("risk"), dict) else {}
    try:
        score = int(risk["score"])
    except (KeyError, TypeError, ValueError):
        return _check("fraud_finder", "review", ["unexpected_response"], request_id)
    reasons = [f"email risk score {score}"]
    owner = (risk.get("phone") or {}).get("owner") or {}
    if owner.get("last_name_match") == "no_match":
        reasons.append("phone owner does not match the name")
    if (risk.get("phone") or {}).get("prepaid") in (True, "True", "true"):
        reasons.append("prepaid phone")
    return _check("fraud_finder", "fail" if score >= 60 else "review" if score >= 30 else "pass", reasons, request_id, score)


_TU_MESSAGES = {"2201": ("fail", "SSN not associated with the name"), "2202": ("fail", "date of birth does not match"), "2101": ("review", "address does not match")}


def parse_transunion(body: dict, request_id: Optional[str]) -> dict:
    """TransUnion identity verification (basic): fail if the SSN or birth date does not belong to the name, review for an address-only
    mismatch or an incomplete answer, pass when the subject is found with matching name and SSN and no alert messages."""
    try:
        idm = body["addOnProducts"][0]["idManagerVerification"]
        first = body["custom"]["idmanagerVerAnalysisV2"]["verificationAnalysises"][0]
    except (KeyError, IndexError, TypeError):
        return _check("identity_verification", "review", ["unexpected_response"], request_id)
    codes = [str(m.get("code")) for m in (idm.get("messages") or []) if isinstance(m, dict)]
    result, reasons = "pass", []
    for code in codes:
        sev, why = _TU_MESSAGES.get(code, ("review", f"alert code {code}"))
        reasons.append(why)
        result = "fail" if "fail" in (sev, result) else "review"
    ok = first.get("verificationStatus") == "SUBJECT_FOUND" and first.get("firstNameVerification") == "MATCH" \
        and first.get("lastNameVerification") == "MATCH" and first.get("ssnVerification") == "MATCH"
    if not ok:
        if first.get("ssnVerification") in ("NO_MATCH", "NOT_FOUND"):
            result = "fail"
        elif result == "pass":
            result = "review"
        reasons.append("subject, name or SSN not confirmed")
    return _check("identity_verification", result, reasons or ["subject, name and SSN confirmed"], request_id)


async def _run_check(name: str, path: str, body: dict, parse: Callable[[dict, Optional[str]], dict]) -> dict:
    try:
        data, request_id = await get_client().post(path, body)
        return parse(data, request_id)
    except CrsUnavailable:
        return _unavailable(name)
    except Exception as exc:  # noqa: BLE001  (a surprise in parsing must never become a pass)
        log.warning("CRS %s could not be read: %s", name, type(exc).__name__)
        return _unavailable(name)


async def reverse_phone(persona: Persona, candidate: str = "") -> dict:
    """Does the number we are about to dial belong to the vendor's known contact? (Sandbox: asks about the persona's phone.)"""
    key = ("reverse", persona.code, hashlib.sha256(candidate.encode()).hexdigest()[:10])
    return await _cached(key, lambda: _run_check("reverse_phone", "/accurate-append/reverse", {"phoneNumber": persona.phone}, lambda b, r: parse_reverse(b, persona, r)))


async def fraud_finder(persona: Persona) -> dict:
    """Is the email address that asked for the change risky?"""
    body = {"firstName": persona.first, "lastName": persona.last, "phoneNumber": persona.phone, "email": persona.email, "ipAddress": persona.ip,
            "address": {"addressLine1": persona.street, "city": persona.city, "state": persona.state, "postalCode": persona.zip}}
    return await _cached(("fraud", persona.code), lambda: _run_check("fraud_finder", "/fraud-finder/fraud-finder", body, parse_fraud_finder))


async def identity_verification(persona: Persona) -> dict:
    """Is the vendor's owner or contact (or whoever stands behind the request) a verified identity?"""
    body = {"firstName": persona.first, "lastName": persona.last, "ssn": persona.ssn, "dob": persona.dob,
            "street1": persona.street, "city": persona.city, "state": persona.state, "zip": persona.zip}
    return await _cached(("tu", persona.code), lambda: _run_check("identity_verification", "/transunion/identity-manager-verification/basic", body, parse_transunion))


def _label(c: dict) -> str:
    return c["name"].replace("_", " ")


_WORD = {"pass": "clear", "review": "needs review", "fail": "flagged"}


def _status_of(checks: list[dict]) -> str:
    results = {c["result"] for c in checks}
    return "fail" if "fail" in results else "review" if "review" in results else "pass"


def _why(c: dict) -> str:
    return "CRS unavailable" if c["reasons"] == ["crs_unavailable"] else ", ".join(c["reasons"][:2])


def section_summary(subject: str, status: str, checks: list[dict]) -> str:
    """One line that says which subject it is about: 'vendor Summit Concrete clear (2/2 checks passed)' or
    'request from summit-concrete.co flagged: email risk score 88; ...'. `subject` is the words before the verdict."""
    if status == "pass":
        return f"{subject} clear ({len(checks)}/{len(checks)} checks passed)"
    return f"{subject} {_WORD[status]}: " + "; ".join(f"{_label(c)}: {_why(c)}" for c in checks if c["result"] != "pass")


def summarize(status: str, checks: list[dict]) -> str:
    """Legacy one-liner over all checks, each failing check tagged with its subject."""
    if status == "pass":
        return f"CRS identity check: pass ({len(checks)}/{len(checks)} checks passed)"
    bad = [f"{'request' if c.get('subject') == 'request' else 'vendor'} {_label(c)} {c['result']} ({c['reasons'][0]})" for c in checks if c["result"] != "pass" and c["reasons"]]
    return f"CRS identity check: {status}; " + "; ".join(bad)


def hold_reasons(result: dict) -> list[str]:
    """Short CRS reasons for payment.held, one per check that did not pass. No PII. Checks about the request name its domain."""
    domain = (result.get("request") or {}).get("requested_by_domain")
    out = []
    for c in result.get("checks", []):
        if c["result"] == "pass":
            continue
        tail = f" (request from {domain})" if domain and c.get("subject") == "request" else ""
        out.append(f"CRS {_label(c)} {c['result']}: {_why(c)}{tail}")
    return out


async def check_vendor_for(vendor: Vendor, request_context: Optional[dict] = None) -> dict:
    """CRS checks at once. request_context: {request_email, reply_to, phones: [candidate numbers, preferred first]}.
    Returns {status, checks, summary, subject, persona, dial_index, vendor, request, source, checked_at}.
    `vendor` is the vendor's own standing (reverse phone + owner identity); `request` is about whoever asked (email risk + requester
    identity), or None when there was no request. status/checks/summary cover both. dial_index is the first candidate whose
    reverse lookup did not fail (an unavailable CRS does not stop the call), or None if every candidate failed."""
    ctx = request_context or {}
    persona, subject = requester_persona(vendor, ctx.get("request_email"), ctx.get("reply_to"))
    owner = vendor_persona(vendor.id)
    phones = list(ctx.get("phones") or [""])
    has_request = bool(ctx.get("request_email"))

    async def reverse_all() -> tuple[dict, Optional[int]]:
        last = None
        for i, phone in enumerate(phones):
            last = await reverse_phone(owner, phone if i else "")  # the preferred number shares the vendor-level lookup (same sandbox persona)
            if last["result"] != "fail":
                return last, i
        return last, None  # type: ignore[return-value]

    other = persona.code != owner.code
    (rev, dial_index), ff, tu, owner_tu = await asyncio.gather(
        reverse_all(), fraud_finder(persona), identity_verification(persona), identity_verification(owner) if other else asyncio.sleep(0))
    who = "request" if (has_request and other) else "vendor"  # copies: the cached check dicts are shared
    rev, ff, tu = dict(rev, subject="vendor"), dict(ff, subject=who), dict(tu, subject=who)
    vendor_checks = [rev]
    checks = [rev, ff, tu]
    if other:
        owner_tu = dict(owner_tu, name="owner_identity_verification", subject="vendor")
        checks.append(owner_tu)
        vendor_checks.append(owner_tu)
    else:
        vendor_checks.append(tu)
    request_checks = [ff, tu] if has_request else []
    status = _status_of(checks)
    vstatus = _status_of(vendor_checks)
    now = utcnow().isoformat()
    domain = _domain(ctx.get("request_email")) or None
    section_vendor = {"status": vstatus, "summary": section_summary(f"vendor {vendor.name}", vstatus, vendor_checks), "checks": vendor_checks,
                      "persona": owner.code, "checked_at": now}
    section_request = None
    if has_request:
        rstatus = _status_of(request_checks)
        section_request = {"status": rstatus, "summary": section_summary(f"request from {domain or 'unknown sender'}", rstatus, request_checks),
                           "checks": request_checks, "persona": persona.code, "requested_by_domain": domain, "checked_at": now}
    return {"status": status, "checks": checks, "summary": summarize(status, checks), "subject": subject, "persona": persona.code,
            "dial_index": dial_index, "vendor": section_vendor, "request": section_request, "source": "crs-sandbox", "checked_at": now}


class IdentityResult(BaseModel):
    vendor_id: str
    status: Literal["verified", "unverified", "flagged"]
    match_score: float  # 0 to 1
    test_identity_id: str  # id of the CRS sandbox test identity matched
    flags: list[str]
    summary: str  # one line, safe to show in hold reasons
    checked_at: datetime
    source: Literal["crs-sandbox", "crs-sandbox-mock"]


class IdentityChecker(Protocol):
    async def check(self, vendor: Vendor) -> IdentityResult: ...


# Demo and test hook: force a status for a vendor id.
MOCK_OVERRIDES: dict[str, Literal["verified", "unverified", "flagged"]] = {}


class MockIdentityChecker:
    async def check(self, vendor: Vendor) -> IdentityResult:
        digest = hashlib.sha256(vendor.id.encode()).hexdigest()
        score = 0.90 + (int(digest[:2], 16) % 10) / 100  # stable per vendor
        flags: list[str] = []
        status = "verified"
        created = vendor.created_at if vendor.created_at.tzinfo else vendor.created_at.replace(tzinfo=utcnow().tzinfo)
        if utcnow() - created < timedelta(days=30):
            status, score = "unverified", 0.40
            flags.append("recently_created_entity")
        override = MOCK_OVERRIDES.get(vendor.id)
        if override:
            status = override
            if override == "flagged":
                score = 0.20
                flags.append("sandbox_fraud_flag")
        summary = f"CRS identity check: {status} (match {score:.2f})" + (f"; {', '.join(flags)}" if flags else "")
        return IdentityResult(
            vendor_id=vendor.id,
            status=status,  # type: ignore[arg-type]
            match_score=round(score, 2),
            test_identity_id=f"crs_test_{digest[:8]}",
            flags=flags,
            summary=summary,
            checked_at=utcnow(),
            source="crs-sandbox-mock",
        )


def _open_request_sender(vendor_id: str) -> Optional[tuple[Optional[str], Optional[str]]]:
    """(from_addr, reply_to) of the newest message from this vendor's thread behind an open, unverified requested bank account, or None.
    Read-only. This is what lets the CRS step look ahead to the sender the verification gate will check."""
    try:
        from sqlmodel import Session, select

        from app.db import engine
        from app.models import AuditLog, Invoice, Message, VendorBankAccount

        with Session(engine) as s:
            requested = {a.entity_id for a in s.exec(select(AuditLog).where(AuditLog.entity == "vendor_bank_account", AuditLog.action == "requested_destination_recorded"))}
            open_ids = [a.id for a in s.exec(select(VendorBankAccount).where(VendorBankAccount.vendor_id == vendor_id, VendorBankAccount.verified_by_call_id.is_(None),
                                                                              VendorBankAccount.valid_to.is_(None))) if a.id in requested]
            if not open_ids:
                return None
            msg = s.exec(select(Message).join(Invoice, Invoice.message_id == Message.id).where(Invoice.vendor_id == vendor_id).order_by(Message.received_at.desc())).first()
            return (msg.from_addr, msg.reply_to) if msg else None
    except Exception:  # noqa: BLE001  (a hint only)
        return None


_STATUS = {"pass": "verified", "review": "unverified", "fail": "flagged"}


class RealIdentityChecker:
    """CRS sandbox. check(vendor) has no request in hand (the payment run and the vendor card), so it checks the vendor's own
    persona; the pre-dial gate in verify.py passes the request and so can meet an attacker persona."""

    async def _with_gate_prefetch(self, vendor: Vendor) -> dict:
        """The vendor's own checks, plus (while they run) the checks the pre-dial gate in verify.py will need for the sender of an
        open bank-change request. The gate then finds them in the cache instead of waiting for a second round of CRS requests.
        Prefetch failures are ignored: the gate asks again."""
        sender = await asyncio.to_thread(_open_request_sender, vendor.id)
        if sender is None:
            return await check_vendor_for(vendor)
        persona, _ = requester_persona(vendor, sender[0], sender[1])
        own, _ = await asyncio.gather(check_vendor_for(vendor), asyncio.gather(fraud_finder(persona), identity_verification(persona), return_exceptions=True))
        return own

    async def check(self, vendor: Vendor) -> IdentityResult:
        try:
            r = await asyncio.wait_for(self._with_gate_prefetch(vendor), CHECK_BUDGET_SECONDS)
        except asyncio.TimeoutError:
            r = {"status": "review", "checks": [_unavailable("reverse_phone"), _unavailable("fraud_finder"), _unavailable("identity_verification")],
                 "persona": vendor_persona(vendor.id).code}
            r["summary"] = summarize("review", r["checks"])
        flags = sorted({why for c in r["checks"] if c["result"] != "pass" for why in c["reasons"]})
        scores = [c["score"] for c in r["checks"] if "score" in c]
        passed = sum(c["result"] == "pass" for c in r["checks"])
        return IdentityResult(
            vendor_id=vendor.id,
            status=_STATUS[r["status"]],  # type: ignore[arg-type]
            match_score=round(passed / len(r["checks"]), 2),
            test_identity_id=r["persona"],
            flags=flags,
            summary=r["summary"],
            checked_at=utcnow(),
            source="crs-sandbox",
        )


def get_checker() -> IdentityChecker:
    return MockIdentityChecker() if get_settings().mock_crs else RealIdentityChecker()


async def check(vendor: Vendor) -> IdentityResult:
    return await get_checker().check(vendor)


async def check_for(vendor: Vendor, request_context: Optional[dict] = None) -> dict:
    """check_vendor for a vendor row already in hand. Under MOCK_CRS the answer comes from the mock, shaped the same way."""
    if get_settings().mock_crs:
        r = await MockIdentityChecker().check(vendor)
        status = {"verified": "pass", "unverified": "review", "flagged": "fail"}[r.status]
        checks = [{"name": n, "result": status, "reasons": r.flags, "crs_request_id": None} for n in ("reverse_phone", "fraud_finder", "identity_verification")]
        return {"status": status, "checks": checks, "summary": r.summary, "subject": "vendor", "persona": r.test_identity_id,
                "dial_index": 0, "vendor": {"status": status, "summary": f"vendor {vendor.name} {_WORD[status]} (mock)", "checks": checks,
                                            "persona": r.test_identity_id, "checked_at": r.checked_at.isoformat()},
                "request": None, "source": r.source, "checked_at": r.checked_at.isoformat()}
    return await check_vendor_for(vendor, request_context)


async def check_vendor(vendor_id: str, request_context: Optional[dict] = None) -> dict:
    """{status: pass|review|fail, checks: [{name, result, score?, reasons, crs_request_id}], summary, dial_index, ...} for a vendor id.
    request_context: {request_email, reply_to, phones}."""
    from sqlmodel import Session

    from app.db import engine

    with Session(engine) as s:
        vendor = s.get(Vendor, vendor_id)
        if vendor is None:
            raise ValueError("vendor not found")
        s.expunge(vendor)
    return await check_for(vendor, request_context)
