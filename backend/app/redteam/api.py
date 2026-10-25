# Owner: Backend lead
# Prize track: Armadin (Best Security Hack), Atlassian (Best Security Solution for Agents)
# Contract:
#   POST /api/redteam/run  {n}          start the harness (app/redteam/evaluate.py) in its own process; 202 {job_id, n, status_url}.
#                                       n is the number of attacks (5 to 300, default 200); clean invoices match it.
#                                       409 if a job is already running, or if the server cannot run live (MOCK_CLAUDE true or no
#                                       ANTHROPIC_API_KEY): a run spends Claude API money and measures nothing on mocks.
#                                       401 if REDTEAM_TOKEN is set and the header x-redteam-token does not match.
#   GET  /api/redteam/jobs/{job_id}     {job_id, state: running | done | failed, phase, done, total, ...}
#   GET  /api/redteam/results           the latest measured results, exactly the RedTeamResults shape in frontend/src/lib/types.ts.
#                                       404 until a measured run has finished (the Red team page shows "no results yet" on a 404).
#                                       Read from demo/redteam-results.json, so a committed file serves a deploy that never ran live.
# The harness runs in a separate process on purpose: it forces every phone, bank and lookup mock on, blanks their credentials and uses a
# throwaway database, none of which may leak into this server's own settings. See evaluate.py.

import json
import os
import secrets
import subprocess
import sys
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from app.config import get_settings
from app.redteam import evaluate

router = APIRouter()
_jobs: dict[str, subprocess.Popen] = {}


class RunIn(BaseModel):
    n: int = Field(default=200, ge=5, le=300)


def _running() -> Optional[str]:
    for job_id, proc in _jobs.items():
        if proc.poll() is None:
            return job_id
    return None


@router.post("/redteam/run", status_code=202)
def start_run(body: Optional[RunIn] = None, x_redteam_token: Optional[str] = Header(default=None)) -> dict:
    s = get_settings()
    if s.redteam_token and not secrets.compare_digest(x_redteam_token or "", s.redteam_token):
        raise HTTPException(401, "this route needs the x-redteam-token header")
    if s.mock_claude or not s.anthropic_api_key:
        raise HTTPException(409, "the red team runs live: set MOCK_CLAUDE=false and ANTHROPIC_API_KEY on this server")
    busy = _running()
    if busy:
        raise HTTPException(409, detail={"error": "a red-team job is already running", "job_id": busy})
    n = (body or RunIn()).n
    job_id = datetime.now(timezone.utc).strftime("rt_%Y%m%d_%H%M%S")
    work = evaluate.CACHE_ROOT / job_id
    work.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, **evaluate.forced_env(live=True)}
    with (work / "run.log").open("wb") as log:
        _jobs[job_id] = subprocess.Popen(
            [sys.executable, "-m", "app.redteam.evaluate", "--n", str(n), "--job-id", job_id],
            cwd=evaluate.BACKEND, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
        )
    return {"job_id": job_id, "n": n, "status_url": f"/api/redteam/jobs/{job_id}"}


@router.get("/redteam/jobs/{job_id}")
def job_status(job_id: str) -> dict:
    status_file = evaluate.CACHE_ROOT / job_id / "status.json"
    if not job_id.startswith("rt_") or "/" in job_id or not status_file.is_file():
        raise HTTPException(404, "job not found")
    state = json.loads(status_file.read_text())
    proc = _jobs.get(job_id)
    if state.get("state") == "running" and proc is not None and proc.poll() not in (None, 0):
        state.update(state="failed", message=state.get("message") or f"the process exited with code {proc.poll()}")
    return state


@router.get("/redteam/results")
def results() -> dict:
    try:
        doc = json.loads(evaluate.RESULTS_JSON.read_text())
    except (OSError, ValueError):
        raise HTTPException(404, "no red-team results yet")
    return evaluate.api_shape(doc)
