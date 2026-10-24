"""AP inbox and invoice PDF intake.

Everything stored here is untrusted: bodies and PDFs are saved as-is and only read later by the
injection scanner and the schema-locked extractor. Nothing in this module interprets their text.
"""

import re
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator
from sqlmodel import Session, select

from app.audit import write_audit
from app.config import get_settings
from app.db import get_session
from app.models import Invoice, Message, Vendor, new_id, payment_id_for_invoice

router = APIRouter()

MAX_PDF_BYTES = 5 * 1024 * 1024
MAX_BODY_CHARS = 200_000
PREVIEW_CHARS = 140

_EMAIL_RE = re.compile(r"^[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+$")
_HTML_RE = re.compile(r"<\s*(html|body|div|p|br|span|a|table|b|i|font|style)\b", re.I)
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


# ---------------------------------------------------------------- helpers


class _TextOnly(HTMLParser):
    """Visible-ish text of an HTML body. Drops tags, comments, script and style."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def is_html(body: str) -> bool:
    return bool(_HTML_RE.search(body))


def plain_text(body: str) -> str:
    if is_html(body):
        parser = _TextOnly()
        parser.feed(body)
        body = " ".join(parser.parts)
    return re.sub(r"\s+", " ", body).strip()


def preview(body: str) -> str:
    text = plain_text(body)
    return text if len(text) <= PREVIEW_CHARS else text[: PREVIEW_CHARS - 3].rstrip() + "..."


def vendor_for_thread(session: Session, thread_id: str) -> Optional[str]:
    """The vendor is whoever the thread already belongs to, never whoever the sender claims to be."""
    return session.exec(
        select(Message.vendor_id)
        .where(Message.thread_id == thread_id, Message.vendor_id.is_not(None))
        .order_by(Message.received_at)
        .limit(1)
    ).first()


# ---------------------------------------------------------------- response models


class VendorRef(BaseModel):
    id: str
    name: str


class ThreadSummary(BaseModel):
    thread_id: str
    vendor: Optional[VendorRef]
    subject: str
    preview: str
    count: int
    has_attack: bool
    last_received_at: datetime
    attachment_count: int = 0  # invoice PDFs in the thread


class InvoiceRef(BaseModel):
    id: str
    payment_id: str  # the id its payment has, or will have once a run reads the invoice
    has_pdf: bool


class MessageOut(BaseModel):
    id: str
    thread_id: str
    vendor_id: Optional[str]
    from_addr: str
    reply_to: Optional[str]
    subject: str
    body: str
    is_html: bool
    received_at: datetime
    is_attack: bool
    invoice_ids: list[str]
    invoices: list[InvoiceRef] = []


class ThreadDetail(ThreadSummary):
    messages: list[MessageOut]


def _summary(thread_id: str, msgs: list[Message], vendors: dict[str, Vendor], attachments: int = 0) -> ThreadSummary:
    """msgs must be oldest first."""
    vendor_id = next((m.vendor_id for m in msgs if m.vendor_id), None)
    vendor = vendors.get(vendor_id) if vendor_id else None
    return ThreadSummary(
        thread_id=thread_id,
        vendor=VendorRef(id=vendor.id, name=vendor.name) if vendor else None,
        subject=msgs[0].subject,
        preview=preview(msgs[-1].body),
        count=len(msgs),
        has_attack=any(m.is_attack for m in msgs),
        last_received_at=msgs[-1].received_at,
        attachment_count=attachments,
    )


def _vendors_by_id(session: Session, ids: set[str]) -> dict[str, Vendor]:
    if not ids:
        return {}
    return {v.id: v for v in session.exec(select(Vendor).where(Vendor.id.in_(ids))).all()}


# ---------------------------------------------------------------- inbox


@router.get("/inbox/threads", response_model=list[ThreadSummary])
def list_threads(
    limit: int = Query(200, ge=1, le=1000), session: Session = Depends(get_session)
) -> list[ThreadSummary]:
    """Threads grouped by thread_id, newest activity first."""
    rows = session.exec(select(Message).order_by(Message.received_at, Message.id)).all()
    grouped: dict[str, list[Message]] = {}
    for m in rows:
        grouped.setdefault(m.thread_id, []).append(m)
    vendors = _vendors_by_id(session, {m.vendor_id for m in rows if m.vendor_id})
    pdfs: dict[str, int] = {}  # thread id -> invoices with a PDF
    thread_of = {m.id: m.thread_id for m in rows}
    for msg_id in session.exec(select(Invoice.message_id).where(Invoice.pdf_path.is_not(None), Invoice.message_id.is_not(None))).all():
        if msg_id in thread_of:
            pdfs[thread_of[msg_id]] = pdfs.get(thread_of[msg_id], 0) + 1
    out = [_summary(tid, msgs, vendors, pdfs.get(tid, 0)) for tid, msgs in grouped.items()]
    out.sort(key=lambda t: t.last_received_at, reverse=True)
    return out[:limit]


@router.get("/inbox/threads/{thread_id}", response_model=ThreadDetail)
def get_thread(thread_id: str, session: Session = Depends(get_session)) -> ThreadDetail:
    msgs = session.exec(
        select(Message).where(Message.thread_id == thread_id).order_by(Message.received_at, Message.id)
    ).all()
    if not msgs:
        raise HTTPException(404, "thread not found")
    vendors = _vendors_by_id(session, {m.vendor_id for m in msgs if m.vendor_id})
    invoices = session.exec(
        select(Invoice.id, Invoice.message_id, Invoice.pdf_path).where(Invoice.message_id.in_([m.id for m in msgs]))
    ).all()
    by_msg: dict[str, list[InvoiceRef]] = {}
    for inv_id, msg_id, pdf_path in invoices:
        by_msg.setdefault(msg_id, []).append(InvoiceRef(id=inv_id, payment_id=payment_id_for_invoice(inv_id), has_pdf=bool(pdf_path)))
    return ThreadDetail(
        **_summary(thread_id, msgs, vendors, sum(r.has_pdf for refs in by_msg.values() for r in refs)).model_dump(),
        messages=[
            MessageOut(
                id=m.id,
                thread_id=m.thread_id,
                vendor_id=m.vendor_id,
                from_addr=m.from_addr,
                reply_to=m.reply_to,
                subject=m.subject,
                body=m.body,
                is_html=is_html(m.body),
                received_at=m.received_at,
                is_attack=m.is_attack,
                invoice_ids=[r.id for r in by_msg.get(m.id, [])],
                invoices=by_msg.get(m.id, []),
            )
            for m in msgs
        ],
    )


class MessageIn(BaseModel):
    # Omit thread_id to start a new thread (it will have no vendor).
    thread_id: Optional[str] = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,64}$")
    from_addr: str = Field(max_length=254)
    reply_to: Optional[str] = Field(default=None, max_length=254)
    subject: str = Field(min_length=1, max_length=300)
    body: str = Field(max_length=MAX_BODY_CHARS)  # plain text or HTML
    is_attack: bool = False

    @field_validator("from_addr", "reply_to")
    @classmethod
    def _addr(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        if not _EMAIL_RE.match(v):
            raise ValueError("not a valid email address")
        return v

    @field_validator("from_addr")
    @classmethod
    def _from_required(cls, v: Optional[str]) -> str:
        if not v:
            raise ValueError("from_addr is required")
        return v

    @field_validator("subject")
    @classmethod
    def _subject(cls, v: str) -> str:
        if _CONTROL_RE.search(v):
            raise ValueError("subject must be a single line")
        return v.strip()


@router.post("/inbox/messages", response_model=MessageOut, status_code=201)
def add_message(body: MessageIn, session: Session = Depends(get_session)) -> MessageOut:
    thread_id = body.thread_id or new_id("thr")
    # Vendor comes from the thread, never from from_addr: a lookalike domain must not pick the vendor.
    vendor_id = vendor_for_thread(session, thread_id)
    msg = Message(
        thread_id=thread_id,
        vendor_id=vendor_id,
        from_addr=body.from_addr,
        reply_to=body.reply_to,
        subject=body.subject,
        body=body.body,
        is_attack=body.is_attack,
    )
    session.add(msg)
    write_audit(
        "message",
        msg.id,
        "system",
        "created",
        {
            "thread_id": thread_id,
            "vendor_id": vendor_id,
            "from_addr": msg.from_addr,
            "reply_to": msg.reply_to,
            "is_attack": msg.is_attack,
            "body_chars": len(msg.body),
        },
        session=session,
    )
    session.commit()
    session.refresh(msg)
    return MessageOut(
        id=msg.id,
        thread_id=msg.thread_id,
        vendor_id=msg.vendor_id,
        from_addr=msg.from_addr,
        reply_to=msg.reply_to,
        subject=msg.subject,
        body=msg.body,
        is_html=is_html(msg.body),
        received_at=msg.received_at,
        is_attack=msg.is_attack,
        invoice_ids=[],
    )


# ---------------------------------------------------------------- invoice upload


class UploadOut(BaseModel):
    invoice_id: str
    payment_id: str
    message_id: Optional[str]
    vendor_id: Optional[str]
    size_bytes: int


@router.post("/invoices/upload", response_model=UploadOut, status_code=201)
async def upload_invoice(
    file: UploadFile = File(...),
    message_id: Optional[str] = Form(None),
    session: Session = Depends(get_session),
) -> UploadOut:
    """Save a PDF under a generated name. The client's filename is never used or stored."""
    vendor_id = None
    if message_id:
        msg = session.get(Message, message_id)
        if msg is None:
            raise HTTPException(404, "message not found")
        vendor_id = msg.vendor_id

    invoice = Invoice(vendor_id=vendor_id, message_id=message_id)
    upload_dir = Path(get_settings().upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    path = upload_dir / f"{invoice.id}.pdf"

    size = 0
    try:
        with open(path, "xb") as out:
            while chunk := await file.read(64 * 1024):
                if size == 0 and not chunk.startswith(b"%PDF-"):
                    raise HTTPException(415, "file is not a PDF")
                size += len(chunk)
                if size > MAX_PDF_BYTES:
                    raise HTTPException(413, "PDF is larger than 5 MB")
                out.write(chunk)
        if size == 0:
            raise HTTPException(422, "file is empty")

        invoice.pdf_path = path.as_posix()
        session.add(invoice)
        write_audit(
            "invoice",
            invoice.id,
            "system",
            "uploaded",
            {"message_id": message_id, "vendor_id": vendor_id, "size_bytes": size},
            session=session,
        )
        session.commit()
    except BaseException:
        session.rollback()
        path.unlink(missing_ok=True)
        raise

    return UploadOut(
        invoice_id=invoice.id, payment_id=payment_id_for_invoice(invoice.id), message_id=message_id, vendor_id=vendor_id, size_bytes=size
    )


# ---------------------------------------------------------------- the stored PDF


@router.get("/invoices/{invoice_id}/pdf")
def invoice_pdf(invoice_id: str, session: Session = Depends(get_session)) -> FileResponse:
    """The original PDF as stored, for the inbox preview. Looked up by invoice id only: the file path comes from our own
    record, never from the request. The bytes are untrusted: served inline with sniffing off."""
    from app.services.run import _resolve  # lazy: run imports this module's siblings

    inv = session.get(Invoice, invoice_id)
    path = _resolve(inv.pdf_path) if inv and inv.pdf_path else None
    if path is None or not path.is_file():
        raise HTTPException(404, "no PDF for this invoice")
    return FileResponse(path, media_type="application/pdf", content_disposition_type="inline", filename=f"{inv.number or inv.id}.pdf",
                        headers={"X-Content-Type-Options": "nosniff"})
