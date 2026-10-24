# Owner: Teammate B
# Prize track: Apify (plus Best Actor with a custom Actor)
# Contract: async lookup_phone(vendor: Vendor) -> Optional[IndependentContact]
#   Finds a phone number for the vendor from its public website or a business listing, never from an
#   email. Returns None if nothing is found. Read-only: this module never writes the database;
#   services/verify.py decides whether to store the contact (it is the only writer of vendor_contacts).
# Flag: MOCK_APIFY.

import hashlib
from datetime import datetime
from typing import Literal, Optional, Protocol

from pydantic import BaseModel

from app.config import get_settings
from app.models import Vendor, utcnow

# Fictional number that is never dialed (the 555-01xx range is reserved for fiction).
MOCK_PHONE = "+14155550100"


class IndependentContact(BaseModel):
    phone: str  # E.164
    source: Literal["website", "listing"]
    source_url: str
    found_at: datetime


class ContactFinder(Protocol):
    async def lookup_phone(self, vendor: Vendor) -> Optional[IndependentContact]: ...


# Demo and test hook: force "nothing found" or a specific number per vendor id.
MOCK_OVERRIDES: dict[str, Optional[str]] = {}


class MockContactFinder:
    async def lookup_phone(self, vendor: Vendor) -> Optional[IndependentContact]:
        if vendor.id in MOCK_OVERRIDES:
            phone = MOCK_OVERRIDES[vendor.id]
            if phone is None:
                return None
        else:
            # The demo "vendor" is a teammate's phone; otherwise a fictional number.
            phone = get_settings().demo_vendor_phone or MOCK_PHONE
        source = "website" if int(hashlib.sha256(vendor.id.encode()).hexdigest()[:2], 16) % 2 == 0 else "listing"
        if source == "website" and not vendor.website_url:
            source = "listing"  # never build a URL from email_domain: it may belong to a real business
        url = f"{vendor.website_url.rstrip('/')}/contact.html" if source == "website" else f"https://listings.example/biz/{vendor.id}"
        return IndependentContact(phone=phone, source=source, source_url=url, found_at=utcnow())  # type: ignore[arg-type]


class RealContactFinder:
    async def lookup_phone(self, vendor: Vendor) -> Optional[IndependentContact]:
        raise NotImplementedError("Real Apify lookup is not built yet; set MOCK_APIFY=true")


def get_finder() -> ContactFinder:
    return MockContactFinder() if get_settings().mock_apify else RealContactFinder()


async def lookup_phone(vendor: Vendor) -> Optional[IndependentContact]:
    return await get_finder().lookup_phone(vendor)


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
