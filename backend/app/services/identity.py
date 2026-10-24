# Owner: Teammate B
# Prize track: CRS (Best Overall, Financial AI Agent, Identity / Fraud)
# Contract: async check(vendor: Vendor) -> IdentityResult
#   CRS is central, not bolted on: services/risk.py takes the result in RiskContext.identity, adds a
#   vendor_identity_check signal, and puts result.summary in the hold reasons. The vendor card shows
#   the same result. check() never raises for "not verified"; that is a normal status.
# Flag: MOCK_CRS.
# UNKNOWN: the real CRS sandbox response shape and test identities are not in the spec. The fields
#   below are our own stand-ins. Teammate B must paste a real sandbox response so we can reshape
#   IdentityResult (and the mock) to match before the real version is written.

import hashlib
from datetime import datetime, timedelta
from typing import Literal, Optional, Protocol

from pydantic import BaseModel

from app.config import get_settings
from app.models import Vendor, utcnow


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


class RealIdentityChecker:
    async def check(self, vendor: Vendor) -> IdentityResult:
        raise NotImplementedError("Real CRS check is not built yet; set MOCK_CRS=true")


def get_checker() -> IdentityChecker:
    return MockIdentityChecker() if get_settings().mock_crs else RealIdentityChecker()


async def check(vendor: Vendor) -> IdentityResult:
    return await get_checker().check(vendor)
