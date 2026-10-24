"""In-process SSE broadcaster.

One asyncio.Queue per subscriber, keyed by run_id, plus one global channel for the leaderboard.
Every emitted event is saved to the events table first, then pushed to live subscribers, so a
client that connects late can replay a run from the table.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, AsyncIterator, Literal, Optional

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, model_validator
from sqlmodel import Session, select

from app.db import engine
from app.models import (
    AttackResult,
    AttackSource,
    CallOutcome,
    ContactSource,
    Decision,
    Event,
    ModerationStatus,
    Signal,
    new_id,
    utcnow,
)

log = logging.getLogger("countersign.events")

KEEPALIVE_SECONDS = 15
QUEUE_MAX = 1000
LEADERBOARD = "__leaderboard__"

# ---------------------------------------------------------------- event models


class EventBase(BaseModel):
    type: str
    run_id: Optional[str] = None

    def payload(self) -> dict:
        return self.model_dump(mode="json", exclude={"type", "run_id"})


class RunStarted(EventBase):
    type: Literal["run.started"] = "run.started"
    run_id: str
    invoice_count: int


class InvoiceParsed(EventBase):
    type: Literal["invoice.parsed"] = "invoice.parsed"
    run_id: str
    invoice_id: str
    vendor: str
    amount_usd: float


class InjectionDetected(EventBase):
    type: Literal["injection.detected"] = "injection.detected"
    run_id: str
    invoice_id: Optional[str] = None
    message_id: Optional[str] = None
    technique: str
    snippet: str

    @model_validator(mode="after")
    def _one_source(self) -> "InjectionDetected":
        if not (self.invoice_id or self.message_id):
            raise ValueError("injection.detected needs invoice_id or message_id")
        return self


class RiskScored(EventBase):
    type: Literal["risk.scored"] = "risk.scored"
    run_id: str
    payment_id: str
    score: int
    decision: Decision
    top_signals: list[Signal]


class PaymentPaid(EventBase):
    type: Literal["payment.paid"] = "payment.paid"
    run_id: str
    payment_id: str
    nessie_transfer_id: str
    transfer_mode: Optional[Literal["nessie", "mock_fallback", "mock"]] = None  # "mock_fallback": Nessie failed, the id is a mock


class PaymentHeld(EventBase):
    type: Literal["payment.held"] = "payment.held"
    run_id: str
    payment_id: str
    reasons: list[str]


class CallStarted(EventBase):
    type: Literal["call.started"] = "call.started"
    run_id: str
    payment_id: str
    contact_source: ContactSource


class CallTranscript(EventBase):
    type: Literal["call.transcript"] = "call.transcript"
    run_id: str
    payment_id: str
    speaker: Literal["agent", "vendor"]
    text: str


class CallOutcomeEvent(EventBase):
    type: Literal["call.outcome"] = "call.outcome"
    run_id: str
    payment_id: str
    outcome: CallOutcome


class PaymentBlocked(EventBase):
    type: Literal["payment.blocked"] = "payment.blocked"
    run_id: str
    payment_id: str
    reason: str


class AttackQueued(EventBase):
    """An attack arrived while something else was running; it will be processed in order. Sent to the run channel of the
    attack's own run_id (the console subscribes there) and to the leaderboard channel."""

    type: Literal["attack.queued"] = "attack.queued"
    run_id: str
    attack_id: str
    position: int  # 1 = next
    waiting_for: Optional[str] = None  # the run it is waiting behind, if any


class DemoReset(EventBase):
    """The demo was reset to the seeded state. Leaderboard channel only: clients should reload everything."""

    type: Literal["demo.reset"] = "demo.reset"
    run_id: Optional[str] = None
    kept_leaderboard: bool


class PaymentReviewed(EventBase):
    """A person decided a held payment. Followed by payment.paid (approved) or payment.blocked (rejected)."""

    type: Literal["payment.reviewed"] = "payment.reviewed"
    run_id: str
    payment_id: str
    decision: Literal["approved", "rejected"]
    approver: str
    reason: str


class RunCompleted(EventBase):
    type: Literal["run.completed"] = "run.completed"
    run_id: str
    paid: int
    held: int
    blocked: int
    total_usd: float


class RunReport(EventBase):
    """End-of-run summary. Fields beyond run_id are not in the spec; this shape is ours."""

    type: Literal["run.report"] = "run.report"
    run_id: str
    summary: str
    paid: int
    held: int
    blocked: int
    paid_usd: float
    blocked_usd: float
    findings: list[str]


class AttackLogged(EventBase):
    """Goes to the leaderboard channel, and to the run channel too when run_id is set."""

    type: Literal["attack.logged"] = "attack.logged"
    attack_id: str
    attacker_name: str
    source: AttackSource
    card: str
    result: Optional[AttackResult] = None
    moderation_status: ModerationStatus = ModerationStatus.pending


EVENT_MODELS: dict[str, type[EventBase]] = {
    m.model_fields["type"].default: m
    for m in (
        RunStarted,
        InvoiceParsed,
        InjectionDetected,
        RiskScored,
        PaymentPaid,
        PaymentHeld,
        CallStarted,
        CallTranscript,
        CallOutcomeEvent,
        PaymentBlocked,
        PaymentReviewed,
        AttackQueued,
        DemoReset,
        RunCompleted,
        RunReport,
        AttackLogged,
    )
}

# ---------------------------------------------------------------- broadcaster


def _wire(event_id: str, at: datetime, event_type: str, run_id: Optional[str], payload: dict) -> dict:
    return {"id": event_id, "type": event_type, "run_id": run_id, "at": at.isoformat(), **payload}


def _persist(msg_id: str, at: datetime, event: EventBase) -> None:
    with Session(engine) as session:
        session.add(
            Event(id=msg_id, at=at, run_id=event.run_id, type=event.type, payload=event.payload())
        )
        session.commit()


def stored_messages(run_id: str) -> list[dict]:
    with Session(engine) as session:
        rows = session.exec(select(Event).where(Event.run_id == run_id).order_by(Event.at)).all()
        return [_wire(r.id, r.at, r.type, r.run_id, r.payload or {}) for r in rows]


class Broadcaster:
    def __init__(self) -> None:
        self._subs: dict[str, set[asyncio.Queue]] = {}

    def subscribe(self, key: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(QUEUE_MAX)
        self._subs.setdefault(key, set()).add(queue)
        return queue

    def unsubscribe(self, key: str, queue: asyncio.Queue) -> None:
        subs = self._subs.get(key)
        if subs:
            subs.discard(queue)
            if not subs:
                del self._subs[key]

    def subscriber_count(self) -> dict[str, int]:
        return {k: len(v) for k, v in self._subs.items()}

    def _publish(self, key: str, msg: dict) -> None:
        for queue in list(self._subs.get(key, ())):
            if queue.full():  # slow client: drop its oldest message rather than block the run
                queue.get_nowait()
            queue.put_nowait(msg)

    async def emit(self, event: EventBase) -> dict:
        """Save the event, then push it to the run channel (and the leaderboard for attacks)."""
        msg_id, at = new_id("evt"), utcnow()
        msg = _wire(msg_id, at, event.type, event.run_id, event.payload())
        try:
            await asyncio.to_thread(_persist, msg_id, at, event)
        except Exception:
            log.exception("could not persist event %s", event.type)
        if event.run_id:
            self._publish(event.run_id, msg)
        if isinstance(event, (AttackLogged, AttackQueued, DemoReset)) and getattr(event, "source", None) != AttackSource.seeded:
            self._publish(LEADERBOARD, msg)  # (a seeded attack's events stay on its run channel)
        return msg


broadcaster = Broadcaster()


async def emit(event: EventBase) -> dict:
    return await broadcaster.emit(event)


# ---------------------------------------------------------------- SSE


def _sse(msg: dict) -> str:
    # No "event:" line, so a browser EventSource.onmessage receives everything; type is in the data.
    return f"id: {msg['id']}\ndata: {json.dumps(msg)}\n\n"


async def _stream(request: Request, key: str, replay: bool) -> AsyncIterator[str]:
    queue = broadcaster.subscribe(key)  # subscribe before replay so nothing is missed
    try:
        seen: set[str] = set()
        yield "retry: 3000\n\n: connected\n\n"
        if replay:
            for msg in await asyncio.to_thread(stored_messages, key):
                seen.add(msg["id"])
                yield _sse(msg)
        while True:
            try:
                msg = await asyncio.wait_for(queue.get(), KEEPALIVE_SECONDS)
            except asyncio.TimeoutError:
                if await request.is_disconnected():
                    break
                yield ": keepalive\n\n"
                continue
            if msg["id"] not in seen:
                yield _sse(msg)
    finally:
        broadcaster.unsubscribe(key, queue)


def _response(request: Request, key: str, replay: bool) -> StreamingResponse:
    return StreamingResponse(
        _stream(request, key, replay),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


router = APIRouter()


@router.get("/payment-runs/{run_id}/events")
async def run_events(run_id: str, request: Request) -> StreamingResponse:
    """Replays stored events for the run, then streams live ones."""
    return _response(request, run_id, replay=True)


@router.get("/leaderboard/events")
async def leaderboard_events(request: Request) -> StreamingResponse:
    """Live attack.logged events. No replay; read GET /api/attacks/leaderboard for history."""
    return _response(request, LEADERBOARD, replay=False)
