"""GET /api/system/status: what is real, simulated or mocked right now, for the status panel."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlmodel import Session, select

from app.config import get_settings
from app.db import get_session, is_postgres
from app.models import Attack, AttackSource, Invoice, Vendor

router = APIRouter()


def _row(name: str, mock: bool, real_detail: str, mock_detail: str, real_mode: str = "real") -> dict:
    return {"name": name, "mode": "mock" if mock else real_mode, "detail": mock_detail if mock else real_detail}


def _nessie_row(s, session: Session) -> dict:
    """Sandbox = real calls to Capital One's Nessie API with sandbox money. Mock only under MOCK_NESSIE; degraded after a fallback."""
    from app.services import payments

    name = "Bank payments (Nessie)"
    if s.mock_nessie:
        return {"name": name, "mode": "mock", "detail": "Mock transfers, no API call", "last_success_at": None}
    h = payments.nessie_health(session)
    last = h.get("last_success_at")
    last_iso = datetime.fromtimestamp(last, timezone.utc).isoformat() if last else None
    if h["state"] == "degraded":
        return {"name": name, "mode": "degraded", "last_success_at": last_iso,
                "detail": f"The last transfer fell back to a mock id ({h.get('last_failure')})"}
    detail = "Real Capital One Nessie API, sandbox money" if last else "Real Capital One Nessie API, sandbox money. No transfer yet this session"
    return {"name": name, "mode": "sandboxed", "detail": detail, "last_success_at": last_iso}


def _apify_row(s) -> dict:
    """The independent number check: our Vendor Contact Verifier Actor on Apify. Degraded after a failed lookup, until one works again."""
    from app.services import contacts

    last_ok = contacts.health.last_ok_at.isoformat() if contacts.health.last_ok_at else None
    if s.mock_apify:
        return {"name": "Vendor phone lookup (Apify)", "mode": "mock", "detail": "Canned lookup", "last_success_at": None}
    if contacts.health.degraded:
        return {"name": "Vendor phone lookup (Apify)", "mode": "degraded", "last_success_at": last_ok,
                "detail": f"The last lookup failed ({contacts.health.last_error}). Calls use the on-file number and the hold says the independent check was unavailable."}
    return {"name": "Vendor phone lookup (Apify)", "mode": "real", "last_success_at": last_ok,
            "detail": "Vendor Contact Verifier Actor reads the vendor's own website"}


@router.get("/system/status")
def system_status(session: Session = Depends(get_session)) -> list[dict]:
    s = get_settings()
    vendors = session.exec(select(func.count()).select_from(Vendor)).one()
    invoices = session.exec(select(func.count()).select_from(Invoice)).one()
    attacks = session.exec(select(func.count()).select_from(Attack).where(Attack.source.in_([AttackSource.console, AttackSource.judge, AttackSource.bounty_email]))).one()
    rows = [
        _row("Claude extraction", s.mock_claude, f"{s.claude_model_main} fills a fixed schema", "Canned extraction"),
        _row("Risk engine", s.mock_risk, "Hard rules and weighted score, running live", "Mock risk assessor"),
        _row("Injection defense", s.mock_injection, "Hidden-content scan and instruction classifier, running live", "Mock injection scanner"),
        _row("Verification call (Twilio)", s.mock_twilio, "Real call to an allow-listed number", "Scripted call, no phone"),
        _row("Call voice (Cartesia)", s.mock_cartesia, "Cartesia text to speech", "No synthesized voice"),
        _apify_row(s),
        _row("Vendor identity (CRS)", s.mock_crs, "CRS sandbox, provided test identities", "Mock identity check", real_mode="sandboxed"),
        _nessie_row(s, session),
        {"name": "Company and vendor history", "mode": "simulated", "detail": f"Ridgeline Builders: {vendors} vendors, {invoices} invoices, generated from realistic patterns"},
        {"name": "Attacks on the leaderboard", "mode": "real", "detail": f"{attacks} {'attempt' if attacks == 1 else 'attempts'} from judges and hackers"},
        {"name": "Database", "mode": "real", "detail": "Postgres" if is_postgres() else "SQLite"},
    ]
    if s.demo_call_route_map:
        rows.append({"name": "Demo call routing", "mode": "simulated", "detail": "Demo: calls routed to team phone"})
    return rows
