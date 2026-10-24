import os
import time
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.config import get_settings
from app.db import engine
from app.main import app
from app.models import AuditLog, Invoice, Message, Vendor, new_id, utcnow

PDF = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def vendor():
    """A vendor with an existing thread, like Summit Concrete's invoice thread."""
    with Session(engine) as s:
        v = Vendor(name=f"Summit Concrete {new_id('t')}", trade="concrete", email_domain="summitconcrete.com")
        s.add(v)
        s.commit()
        thread = new_id("thr")
        s.add(
            Message(
                thread_id=thread,
                vendor_id=v.id,
                from_addr="ar@summitconcrete.com",
                subject="Invoice 1042",
                body="Please find invoice 1042 attached.",
                received_at=utcnow() - timedelta(days=1),
            )
        )
        s.commit()
        s.refresh(v)
        return {"id": v.id, "name": v.name, "thread": thread}


def audit_rows(entity: str, entity_id: str) -> list[AuditLog]:
    with Session(engine) as s:
        return list(s.exec(select(AuditLog).where(AuditLog.entity == entity, AuditLog.entity_id == entity_id)))


def post_msg(client, **over):
    payload = {"from_addr": "a@b.com", "subject": "Hi", "body": "hello"}
    payload.update(over)
    return client.post("/api/inbox/messages", json=payload)


# ---------------------------------------------------------------- GET /inbox/threads


def test_threads_grouped_newest_first_with_summary(client, vendor):
    older = vendor["thread"]
    r = post_msg(client, thread_id=older, from_addr="ar@summit-concrete.co",
                 subject="Re: Invoice 1042", body="<p>We changed banks.</p><!-- hidden -->", is_attack=True)
    assert r.status_code == 201
    time.sleep(0.01)
    newer = new_id("thr")
    post_msg(client, thread_id=newer, subject="Other thread", body="x " * 200)

    threads = client.get("/api/inbox/threads").json()
    ids = [t["thread_id"] for t in threads]
    assert ids.index(newer) < ids.index(older)
    assert ids.count(older) == 1

    t = next(t for t in threads if t["thread_id"] == older)
    assert t["count"] == 2
    assert t["has_attack"] is True
    assert t["subject"] == "Invoice 1042"  # subject of the first message
    assert t["vendor"] == {"id": vendor["id"], "name": vendor["name"]}
    assert t["preview"] == "We changed banks."  # latest message, HTML stripped, comment dropped

    n = next(t for t in threads if t["thread_id"] == newer)
    assert n["vendor"] is None and n["has_attack"] is False
    assert len(n["preview"]) <= 140 and n["preview"].endswith("...")


def test_threads_limit(client, vendor):
    assert len(client.get("/api/inbox/threads?limit=1").json()) == 1
    assert client.get("/api/inbox/threads?limit=0").status_code == 422


# ---------------------------------------------------------------- GET /inbox/threads/{id}


def test_thread_detail_in_order(client, vendor):
    t = vendor["thread"]
    post_msg(client, thread_id=t, subject="second", body="two")
    time.sleep(0.01)
    post_msg(client, thread_id=t, subject="third", body="<b>three</b>")
    d = client.get(f"/api/inbox/threads/{t}").json()
    assert [m["subject"] for m in d["messages"]] == ["Invoice 1042", "second", "third"]
    assert d["count"] == 3
    assert [m["is_html"] for m in d["messages"]] == [False, False, True]
    assert d["messages"][2]["body"] == "<b>three</b>"  # stored raw


def test_thread_detail_lists_invoice_ids(client, vendor):
    mid = client.get(f"/api/inbox/threads/{vendor['thread']}").json()["messages"][0]["id"]
    inv = client.post("/api/invoices/upload", files={"file": ("a.pdf", PDF)}, data={"message_id": mid}).json()
    d = client.get(f"/api/inbox/threads/{vendor['thread']}").json()
    assert d["messages"][0]["invoice_ids"] == [inv["invoice_id"]]


def test_thread_detail_404(client):
    assert client.get("/api/inbox/threads/thr_nope").status_code == 404


# ---------------------------------------------------------------- POST /inbox/messages


def test_post_message_matches_vendor_by_thread_not_sender(client, vendor):
    start = time.perf_counter()
    r = post_msg(client, thread_id=vendor["thread"], from_addr="ar@summit-concrete.co",
                 reply_to="billing@summit-concrete.co", subject="Re: Invoice 1042", is_attack=True)
    assert time.perf_counter() - start < 2
    assert r.status_code == 201
    m = r.json()
    assert m["vendor_id"] == vendor["id"]
    assert m["from_addr"] == "ar@summit-concrete.co"
    assert m["reply_to"] == "billing@summit-concrete.co"
    assert m["is_attack"] is True and m["id"].startswith("msg_")


def test_sender_matching_a_vendor_domain_does_not_pick_the_vendor(client, vendor):
    # Sender is the real vendor's address, but the thread is new: still no vendor.
    m = post_msg(client, from_addr="ar@summitconcrete.com").json()
    assert m["vendor_id"] is None
    assert m["thread_id"].startswith("thr_")  # generated when omitted


def test_post_message_html_body_and_new_thread(client):
    m = post_msg(client, thread_id=new_id("thr"), body="<html><body><p>Hi</p></body></html>").json()
    assert m["is_html"] is True
    assert client.get("/api/inbox/threads/" + m["thread_id"]).json()["preview"] == "Hi"


def test_post_message_writes_audit(client, vendor):
    m = post_msg(client, thread_id=vendor["thread"], body="secret body text").json()
    rows = audit_rows("message", m["id"])
    assert len(rows) == 1
    assert rows[0].action == "created" and rows[0].actor.value == "system"
    assert rows[0].detail_json["vendor_id"] == vendor["id"]
    assert "secret body text" not in str(rows[0].detail_json)  # body is not copied into the log


@pytest.mark.parametrize(
    "over",
    [
        {"from_addr": "not-an-email"},
        {"from_addr": ""},
        {"reply_to": "bad@"},
        {"subject": ""},
        {"subject": "line1\r\nBcc: x@y.com"},
        {"thread_id": "../etc"},
        {"body": "x" * 200_001},
    ],
)
def test_post_message_validation(client, over):
    assert post_msg(client, **over).status_code == 422


def test_post_message_missing_fields(client):
    assert client.post("/api/inbox/messages", json={"subject": "x"}).status_code == 422


# ---------------------------------------------------------------- POST /invoices/upload


def test_upload_saves_under_generated_name(client, vendor):
    mid = client.get(f"/api/inbox/threads/{vendor['thread']}").json()["messages"][0]["id"]
    r = client.post("/api/invoices/upload", files={"file": ("../../evil name.pdf", PDF, "application/pdf")},
                    data={"message_id": mid})
    assert r.status_code == 201
    body = r.json()
    assert body["vendor_id"] == vendor["id"] and body["message_id"] == mid and body["size_bytes"] == len(PDF)

    with Session(engine) as s:
        inv = s.get(Invoice, body["invoice_id"])
    saved = Path(inv.pdf_path)
    assert saved.name == f"{inv.id}.pdf"
    assert saved.read_bytes() == PDF
    assert saved.resolve().parent == Path(get_settings().upload_dir).resolve()
    assert "evil" not in inv.pdf_path
    assert inv.number is None and inv.amount_usd is None  # filled by extraction later

    rows = audit_rows("invoice", inv.id)
    assert len(rows) == 1 and rows[0].action == "uploaded"
    assert rows[0].detail_json["size_bytes"] == len(PDF)
    assert "evil" not in str(rows[0].detail_json)


def test_upload_without_message(client):
    r = client.post("/api/invoices/upload", files={"file": ("x.pdf", PDF)})
    assert r.status_code == 201
    assert r.json()["message_id"] is None and r.json()["vendor_id"] is None


def test_upload_rejects_non_pdf_even_with_pdf_name_and_type(client):
    before = set(os.listdir(get_settings().upload_dir))
    r = client.post("/api/invoices/upload", files={"file": ("x.pdf", b"<html>nope</html>", "application/pdf")})
    assert r.status_code == 415
    assert set(os.listdir(get_settings().upload_dir)) == before  # nothing left behind


def test_upload_rejects_empty(client):
    assert client.post("/api/invoices/upload", files={"file": ("x.pdf", b"")}).status_code == 422


def test_upload_size_limit(client):
    before = set(os.listdir(get_settings().upload_dir))
    ok = PDF + b"0" * (5 * 1024 * 1024 - len(PDF))
    assert len(ok) == 5 * 1024 * 1024
    assert client.post("/api/invoices/upload", files={"file": ("ok.pdf", ok)}).status_code == 201
    r = client.post("/api/invoices/upload", files={"file": ("big.pdf", ok + b"0")})
    assert r.status_code == 413
    after = set(os.listdir(get_settings().upload_dir))
    assert len(after - before) == 1  # only the accepted file exists


def test_upload_unknown_message_404(client):
    r = client.post("/api/invoices/upload", files={"file": ("x.pdf", PDF)}, data={"message_id": "msg_nope"})
    assert r.status_code == 404


def test_upload_requires_file(client):
    assert client.post("/api/invoices/upload").status_code == 422
