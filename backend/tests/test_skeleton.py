import os
import tempfile

# Must be set before app modules import the engine.
_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["FRONTEND_URL"] = "https://countersign.example"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import Session, select  # noqa: E402

from app.audit import write_audit  # noqa: E402
from app.db import create_all, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import AuditLog, Event, Signal, Vendor  # noqa: E402


def test_health():
    with TestClient(app) as client:
        r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["database"] == "sqlite"
    assert set(body["mocks"]) == {"nessie", "crs", "apify", "twilio", "cartesia", "claude"}


def test_cors_allows_localhost_and_frontend_url():
    with TestClient(app) as client:
        for origin in ("http://localhost:5173", "https://countersign.example"):
            r = client.get("/api/health", headers={"Origin": origin})
            assert r.headers["access-control-allow-origin"] == origin
        r = client.get("/api/health", headers={"Origin": "https://evil.example"})
        assert "access-control-allow-origin" not in r.headers


def test_id_prefixes():
    assert Vendor(name="a", trade="b", email_domain="c.com").id.startswith("ven_")
    assert Signal(name="x", weight=1, detail="d").evidence_id.startswith("evd_")


def test_audit_is_append_only():
    create_all()
    write_audit("payment", "pay_1", "agent", "scored", {"score": 85})
    with Session(engine) as s:
        row = s.exec(select(AuditLog)).one()
        assert row.actor.value == "agent"
        row.action = "tampered"
        s.add(row)
        with pytest.raises(Exception, match="append-only"):
            s.commit()
        s.rollback()
        s.delete(row)
        with pytest.raises(Exception, match="append-only"):
            s.commit()


def test_composite_primary_keys():
    assert [c.name for c in AuditLog.__table__.primary_key.columns] == ["id", "at"]
    assert [c.name for c in Event.__table__.primary_key.columns] == ["id", "at"]
