# Owner: Backend lead
# Prize track: Hyphenate (a judge can try again), the demo's "reset in under 5 seconds"
# Contract: POST /api/demo/reset[?keep_leaderboard=true]   (or {"keep_leaderboard": true} in the body)
#   Stops whatever is running, then rebuilds the seeded state with seed_database (Aditya's seed). Attacks are cleared unless
#   keep_leaderboard is true; the kept rows carry their own text, outcome and reasons, so the leaderboard still reads.
#   What it stops: running payment runs and attack mini-runs are cancelled, the attack queue is emptied, claims are released.
#   Uploaded attack PDFs are deleted. Extraction and classifier caches are kept, so the next run is as fast as before.
#   Returns {status, seconds, kept_attacks, counts}. One reset at a time (a second gets 409).
#   Emits demo.reset on the leaderboard channel so screens reload.

import asyncio
import importlib
import logging
import sys
import time
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlmodel import Session, select

from app import events as ev
from app.config import get_settings
from app.db import engine
from app.models import Attack, AttackSource
from app.services import attacks, run

log = logging.getLogger("countersign.reset")
router = APIRouter()

BACKEND = Path(__file__).resolve().parents[2]
_busy = False  # one reset at a time (a flag, not a lock: the event loop is single-threaded, and a lock would bind to one loop)


class ResetIn(BaseModel):
    keep_leaderboard: bool = False


def _seed_module():
    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))
    return importlib.import_module("seed.seed")


def _reseed(keep: bool):
    with Session(engine) as session:
        summary = _seed_module().seed_database(session, keep_attacks=keep)
        for a in session.exec(select(Attack).where(Attack.source == AttackSource.seeded)).all():  # planted attacks are not part of the leaderboard
            session.delete(a)
        session.commit()
        kept = session.exec(select(func.count()).select_from(Attack)).one()
    return summary, kept


async def _stop_work() -> None:
    """Cancel runs and attack mini-runs and empty the queue, so nothing writes into the fresh database."""
    tasks = [t for t in list(run._tasks) if not t.done()]
    for t in tasks:
        t.cancel()
    await attacks.stop()  # cancels the worker (and the mini-run it is awaiting); the queued attacks are dropped
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    run._active.clear()
    run._mini.clear()
    run._claimed.clear()
    await attacks.start()
    await asyncio.sleep(0.05)  # let an event write that was already on its way finish before the tables are wiped


def _clear_uploads() -> int:
    folder = Path(get_settings().upload_dir)
    n = 0
    if folder.is_dir():
        for p in folder.glob("*.pdf"):
            p.unlink(missing_ok=True)
            n += 1
    return n


@router.post("/demo/reset")
async def demo_reset(keep_leaderboard: bool = False, body: Optional[ResetIn] = Body(default=None)) -> dict:
    keep = keep_leaderboard or bool(body and body.keep_leaderboard)
    global _busy
    if _busy:
        raise HTTPException(409, "a reset is already in progress")
    _busy = True
    try:
        started = time.perf_counter()
        await _stop_work()
        t_stopped = time.perf_counter()
        summary, kept = await asyncio.to_thread(_reseed, keep)
        removed = _clear_uploads()
        t_seeded = time.perf_counter()
        await ev.emit(ev.DemoReset(kept_leaderboard=keep))
        seconds = round(time.perf_counter() - started, 2)
    finally:
        _busy = False
    log.info("demo reset in %ss (stop %.2fs, seed %.2fs, keep_leaderboard=%s)", seconds, t_stopped - started, t_seeded - t_stopped, keep)
    return {"status": "ok", "seconds": seconds, "stop_seconds": round(t_stopped - started, 2), "seed_seconds": round(t_seeded - t_stopped, 2),
            "kept_leaderboard": keep, "kept_attacks": kept, "uploads_removed": removed, "open_invoices": 40, "counts": summary.counts}
