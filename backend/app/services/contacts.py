# Owner: Teammate B
# Prize track: Apify (plus Best Actor with a custom Actor)
# Contract: async lookup(vendor: Vendor) -> LookupResult
#   Finds an independent phone number for the vendor from the vendor's OWN public website, never from an email, an invoice or a
#   domain in a request. The real finder (MOCK_APIFY=false) runs our published Vendor Contact Verifier Actor on Apify with
#   vendors.website_url from our own vendor records, and nothing else. Read-only: this module never writes the database;
#   services/verify.py decides whether to store the contact (it is the only writer of vendor_contacts).
# Flag: MOCK_APIFY.

import asyncio
import hashlib
import json
import logging
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal, Optional, Protocol
from urllib.parse import urlparse

from pydantic import BaseModel

from app.config import get_settings
from app.services import liveness
from app.models import Vendor, utcnow

log = logging.getLogger("countersign.contacts")

# Fictional number that is never dialed (the 555-01xx range is reserved for fiction).
MOCK_PHONE = "+14155550100"

TOTAL_TIMEOUT_SECONDS = 20  # the whole lookup, start of the Actor run to the dataset row
ACTOR_RUN_TIMEOUT_SECONDS = 15  # the Actor's own limit, so a stuck run ends on Apify too
CACHE_TTL_SECONDS = 3600
_E164 = re.compile(r"^\+[1-9]\d{6,14}$")


class IndependentContact(BaseModel):
    phone: str  # E.164
    source: Literal["website", "listing"]
    source_url: str  # the page of the vendor's website that shows the number: the proof
    found_at: datetime
    confidence: Optional[Literal["high", "medium", "low"]] = None
    agreement: Optional[Literal["consistent", "conflicting", "none_found"]] = None
    confidence_reason: Optional[str] = None
    actor_run_id: Optional[str] = None


class LookupResult(BaseModel):
    """What the independent check produced. Only `found` carries a number that may be dialed."""

    # found: a usable number (one number, confidence high or medium)
    # not_usable: the Actor ran but found none, conflicting numbers, or low confidence
    # unavailable: the Actor failed or timed out (never a reason to move money or drop a hold)
    # no_website: the vendor record has no website_url, so there is nothing to check
    status: Literal["found", "not_usable", "unavailable", "no_website"]
    contact: Optional[IndependentContact] = None
    agreement: Optional[str] = None
    confidence: Optional[str] = None
    confidence_reason: Optional[str] = None
    source_url: Optional[str] = None
    actor_run_id: Optional[str] = None
    error: Optional[str] = None
    cached: bool = False
    checked_at: datetime


class ContactFinder(Protocol):
    async def lookup(self, vendor: Vendor) -> LookupResult: ...


# Demo and test hook: force "nothing found" or a specific number per vendor id.
MOCK_OVERRIDES: dict[str, Optional[str]] = {}


def _now() -> datetime:
    return utcnow()


def _under(url: str, website_url: str) -> bool:
    """A source_url the Actor reports must be a page of the vendor's own website (same host, inside its folder)."""
    a, b = urlparse(url), urlparse(website_url)
    base = b.path if b.path.endswith("/") else b.path.rsplit("/", 1)[0] + "/" if "." in b.path.rsplit("/", 1)[-1] else b.path + "/"
    return a.scheme in ("http", "https") and a.netloc.lower() == b.netloc.lower() and (a.path if a.path.endswith("/") else a.path + "/").startswith(base)


# ---------------------------------------------------------------- health, shown on /api/system/status


class Health:
    """Whether the last real Apify lookup worked. In memory: it starts clean and changes with every real lookup."""

    def __init__(self) -> None:
        self.degraded = False
        self.last_error: Optional[str] = None
        self.last_ok_at: Optional[datetime] = None
        self.last_failure_at: Optional[datetime] = None
        self.failures = 0

    def ok(self) -> None:
        self.degraded, self.last_ok_at = False, _now()
        liveness.mark("apify", self.last_ok_at)

    def failed(self, error: str) -> None:
        self.degraded, self.last_error, self.last_failure_at = True, error, _now()
        self.failures += 1

    def reset(self) -> None:
        self.__init__()


health = Health()


# ---------------------------------------------------------------- cache, one hour per vendor


def _cache_file(vendor: Vendor) -> Path:
    return Path(get_settings().contacts_cache_dir) / (hashlib.sha256(vendor.id.encode()).hexdigest()[:32] + ".json")


def cache_get(vendor: Vendor) -> Optional[LookupResult]:
    try:
        data = json.loads(_cache_file(vendor).read_text())
        if data["website_url"] != vendor.website_url or data["expires_at"] < time.time():
            return None
        return LookupResult.model_validate(data["result"]).model_copy(update={"cached": True})
    except Exception:  # noqa: BLE001  (a missing or broken cache file is a miss)
        return None


def cache_put(vendor: Vendor, result: LookupResult) -> None:
    try:
        f = _cache_file(vendor)
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({"website_url": vendor.website_url, "expires_at": time.time() + CACHE_TTL_SECONDS, "result": json.loads(result.model_dump_json())}))
    except OSError:
        log.warning("could not write the contacts cache")


# ---------------------------------------------------------------- the mock


class MockContactFinder:
    async def lookup(self, vendor: Vendor) -> LookupResult:
        now = _now()
        if vendor.id in MOCK_OVERRIDES:
            phone = MOCK_OVERRIDES[vendor.id]
            if phone is None:
                return LookupResult(status="not_usable", agreement="none_found", confidence="low", confidence_reason="No phone number found (mock).", checked_at=now)
        else:
            # The demo "vendor" is a teammate's phone; otherwise a fictional number.
            phone = get_settings().demo_vendor_phone or MOCK_PHONE
        # The vendor's own hosted website when it has one; never a URL built from email_domain, which may belong to a real business.
        source = "website" if vendor.website_url else "listing"
        url = f"{vendor.website_url.rstrip('/')}/contact.html" if source == "website" else f"https://listings.example/biz/{vendor.id}"
        contact = IndependentContact(phone=phone, source=source, source_url=url, found_at=now, confidence="high", agreement="consistent",  # type: ignore[arg-type]
                                     confidence_reason="Mock lookup: one number.")
        return LookupResult(status="found", contact=contact, agreement="consistent", confidence="high", confidence_reason=contact.confidence_reason,
                            source_url=url, checked_at=now)


# ---------------------------------------------------------------- the real finder: our published Actor on Apify


def parse_actor_row(vendor: Vendor, row: dict, run_id: Optional[str]) -> LookupResult:
    """Turn one dataset row of the Vendor Contact Verifier into a LookupResult. The row is data from a website: every field is
    checked, the phone must be E.164 and the source_url must be a page of this vendor's own website."""
    now = _now()
    agreement, confidence = row.get("agreement"), row.get("confidence")
    if agreement not in ("consistent", "conflicting", "none_found") or confidence not in ("high", "medium", "low"):
        raise ValueError("unexpected Actor output")
    reason = str(row.get("confidence_reason") or "")[:300]
    phone = row.get("primary_phone")
    sources = [s for p in (row.get("phones") or []) if isinstance(p, dict) and p.get("phone") == phone for s in (p.get("sources") or []) if isinstance(s, dict)]
    # The proof page: prefer the contact page, then JSON-LD, then anything, as long as it is on the vendor's own website.
    ranked = sorted((s for s in sources if isinstance(s.get("source_url"), str) and _under(s["source_url"], vendor.website_url or "")),
                    key=lambda s: (s.get("found_in") != "contact_page_text", s.get("found_in") != "json_ld"))
    proof = ranked[0]["source_url"] if ranked else None
    base = dict(agreement=agreement, confidence=confidence, confidence_reason=reason, source_url=proof, actor_run_id=run_id, checked_at=now)
    if not (isinstance(phone, str) and _E164.match(phone)) or agreement != "consistent" or confidence == "low" or proof is None:
        return LookupResult(status="not_usable", **base)
    contact = IndependentContact(phone=phone, source="website", source_url=proof, found_at=now, confidence=confidence, agreement=agreement,
                                 confidence_reason=reason, actor_run_id=run_id)
    return LookupResult(status="found", contact=contact, **base)


class RealContactFinder:
    async def lookup(self, vendor: Vendor) -> LookupResult:
        s = get_settings()
        now = _now()
        if not vendor.website_url:
            return LookupResult(status="no_website", confidence_reason="The vendor record has no website_url.", checked_at=now)
        if (hit := cache_get(vendor)) is not None:
            return hit
        try:
            result = await asyncio.wait_for(self._run(vendor), TOTAL_TIMEOUT_SECONDS)
        except Exception as exc:  # noqa: BLE001  (timeout, network, Apify error, unexpected output: all the same to the caller)
            name = type(exc).__name__
            health.failed(name)
            log.warning("Apify lookup failed for %s: %s", vendor.id, name)
            return LookupResult(status="unavailable", error=name, checked_at=now)
        health.ok()
        cache_put(vendor, result)  # a result is cached, a failure is not: the next call tries again
        return result

    async def _run(self, vendor: Vendor) -> LookupResult:
        from apify_client import ApifyClientAsync

        s = get_settings()
        if not s.apify_token:
            raise RuntimeError("APIFY_TOKEN is not set")
        client = ApifyClientAsync(s.apify_token)
        # Only our own record goes in: the vendor's name and website_url. Nothing from a request, an email or an invoice.
        run_input = {"businesses": [{"name": vendor.name, "website_url": vendor.website_url}], "maxPagesPerSite": 6, "requestTimeoutSecs": 6}
        run = await client.actor(s.apify_actor_id).start(run_input=run_input, run_timeout=timedelta(seconds=ACTOR_RUN_TIMEOUT_SECONDS))
        try:
            finished = await client.run(run.id).wait_for_finish(wait_duration=timedelta(seconds=TOTAL_TIMEOUT_SECONDS - 2))
        except BaseException:  # includes the 20 second cancel: end the run on Apify too
            await _abort(client, run.id)
            raise
        status = getattr(getattr(finished, "status", None), "value", getattr(finished, "status", None))
        if finished is None or status != "SUCCEEDED":
            await _abort(client, run.id)
            raise RuntimeError(f"Actor run {status or 'did not finish'}")
        page = await client.dataset(finished.default_dataset_id).list_items(limit=1)
        items = page.items
        if not items or not isinstance(items[0], dict):
            raise ValueError("the Actor returned no row")
        return parse_actor_row(vendor, items[0], run.id)


async def _abort(client, run_id: str) -> None:
    try:
        await asyncio.wait_for(client.run(run_id).abort(), 3)
    except Exception:  # noqa: BLE001  (best effort: the Actor's own timeout ends it anyway)
        pass


def get_finder() -> ContactFinder:
    return MockContactFinder() if get_settings().mock_apify else RealContactFinder()


async def lookup(vendor: Vendor) -> LookupResult:
    return await get_finder().lookup(vendor)


async def lookup_phone(vendor: Vendor) -> Optional[IndependentContact]:
    """The usable independent number, or None. Kept for callers that only need the number."""
    return (await lookup(vendor)).contact


async def find_independent_number(vendor_id: str) -> dict:
    """{phone, source, source_url} for a vendor id, or {} if nothing is found. Read-only."""
    from sqlmodel import Session

    from app.db import engine

    with Session(engine) as s:
        vendor = s.get(Vendor, vendor_id)
        if vendor is None:
            raise ValueError("vendor not found")
        s.expunge(vendor)
    found = await lookup_phone(vendor)
    return {"phone": found.phone, "source": found.source, "source_url": found.source_url} if found else {}


async def warm(vendor_ids: tuple[str, ...] = ("ven_summit",)) -> dict[str, str]:
    """Run the lookup for the demo vendors so the demo call starts fast. Never raises. Returns {vendor_id: status}."""
    from sqlmodel import Session

    from app.db import engine

    out: dict[str, str] = {}
    for vid in vendor_ids:
        try:
            with Session(engine) as s:
                vendor = s.get(Vendor, vid)
                if vendor is None:
                    continue
                s.expunge(vendor)
            out[vid] = (await lookup(vendor)).status
        except Exception as exc:  # noqa: BLE001
            out[vid] = type(exc).__name__
    return out
