"""Record a real payment run so the frontend can replay it when a live demo cannot run (no Wi-Fi, no server, a call that will not connect).

    cd backend && python -m scripts.record_run                       # the latest full run on the server at http://localhost:8000
    python -m scripts.record_run --run run_ab12cd34ef56 --api http://localhost:8000

What it saves, to ../frontend/public/replay/recorded-run.json:
  * every event of the run exactly as the server stored it (the same wire format the live stream sends), read from the events table;
  * the answers the screens ask for while it plays: each payment's detail, the vendor list, the histories of the vendors involved, the
    system status, the health flags, the red-team results and the leaderboard, fetched from the running server;
  * meta: when it was recorded, which run, and which services were live or simulated at that time (the MOCK_* flags).

Run it against the SAME database the server uses (same DATABASE_URL), right after a run you want to keep, ideally one made with the real services
on. The replay screen says when it was recorded and whether the services were simulated, from this file, so it never overstates what it shows.
Nothing in a recording is secret: money is sandbox money, every name is fictional and account numbers are masked to four digits by the server.
"""

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlmodel import Session, select  # noqa: E402

from app.db import engine  # noqa: E402
from app.events import _wire  # noqa: E402
from app.models import Event, Invoice, Payment, PaymentStatus  # noqa: E402

DEFAULT_OUT = Path(__file__).resolve().parents[2] / "frontend" / "public" / "replay" / "recorded-run.json"
SECRET_SHAPES = re.compile(r"sk-ant-[A-Za-z0-9_-]{10,}|AC[0-9a-f]{32}|[A-Za-z0-9_-]{24,}\.[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{20,}")


def fetch(api: str, path: str):
    try:
        with urllib.request.urlopen(api + path, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError:
        return None  # an optional answer (no red-team results yet): the replay screen handles a missing one


def main() -> int:
    ap = argparse.ArgumentParser(description="Record a payment run for the frontend's replay mode.")
    ap.add_argument("--api", default="http://localhost:8000", help="the running server")
    ap.add_argument("--run", default=None, help="a run id (default: the latest full run)")
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    a = ap.parse_args()

    run_id = a.run or (fetch(a.api, "/api/payment-runs/latest") or {}).get("run_id")
    if not run_id:
        print("No payment run to record. Start a run first (or pass --run).", file=sys.stderr)
        return 1
    status = fetch(a.api, f"/api/payment-runs/{run_id}")
    if not status or status["status"] != "completed":
        print(f"Run {run_id} has not completed; a recording must be a finished run.", file=sys.stderr)
        return 1

    with Session(engine) as s:
        events = [_wire(e.id, e.at, e.type, e.run_id, e.payload or {}) for e in s.exec(select(Event).where(Event.run_id == run_id).order_by(Event.at)).all()]
        payments = s.exec(select(Payment, Invoice.vendor_id).join(Invoice, Invoice.id == Payment.invoice_id).where(Payment.run_id == run_id)).all()
        pay_ids = [p.id for p, _ in payments]
        involved = sorted({v for p, v in payments if v and (p.status != PaymentStatus.paid)})  # vendors whose payments were held or blocked
    if not events or not pay_ids:
        print(f"Run {run_id} has no stored events or payments.", file=sys.stderr)
        return 1

    health = fetch(a.api, "/api/health") or {}
    responses = {f"GET /api/payment-runs/{run_id}": status, "GET /api/health": health}
    for path in ("/api/vendors", "/api/system/status", "/api/redteam/results", "/api/attacks/leaderboard"):
        got = fetch(a.api, path)
        if got is not None:
            responses[f"GET {path}"] = got
    for pid in pay_ids:
        got = fetch(a.api, f"/api/payments/{pid}")
        if got is not None:
            responses[f"GET /api/payments/{pid}"] = got
    for vid in involved:
        got = fetch(a.api, f"/api/vendors/{vid}/history")
        if got is not None:
            responses[f"GET /api/vendors/{vid}/history"] = got

    mocks = health.get("mocks", {})
    services = {k: ("simulated" if mocks.get(k, True) else "live") for k in ("twilio", "cartesia", "apify", "crs", "nessie", "claude")}
    doc = {
        "meta": {"recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "run_id": run_id, "event_count": len(events), "payments": len(pay_ids),
                 "services": services, "all_live": all(v == "live" for v in services.values())},
        "events": events,
        "responses": responses,
    }
    text = json.dumps(doc, separators=(",", ":"))
    if SECRET_SHAPES.search(text):
        print("Refusing to write: the recording contains something shaped like a key or token.", file=sys.stderr)
        return 1
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text)
    print(f"Recorded {run_id}: {len(events)} events, {len(pay_ids)} payments, {len(responses)} answers, {out.stat().st_size // 1024} KB -> {out}")
    print("Services when recorded: " + ", ".join(f"{k} {v}" for k, v in services.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
