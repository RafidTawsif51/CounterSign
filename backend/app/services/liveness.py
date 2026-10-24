"""When each component last did real work, for the status panel's "Last success" column.

mark(name) after a live call succeeds; last(name) returns its ISO time or None. Kept in memory and in a small JSON file, so a
success recorded by warm_cache (a separate process) still shows after the server starts. Mock paths never call mark().
"""

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

log = logging.getLogger("countersign.liveness")

PATH = Path(os.environ.get("LIVENESS_PATH", "./.cache/last_success.json"))  # tests point this at a temp dir
_lock = threading.Lock()
_seen: dict[str, str] = {}


def _load() -> dict[str, str]:
    try:
        data = json.loads(PATH.read_text())
        return {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, str)}
    except (OSError, ValueError):
        return {}


def mark(name: str, at: Optional[datetime] = None) -> None:
    """Record a success. Never raises: the status column must not break the work it reports on."""
    stamp = (at or datetime.now(timezone.utc)).isoformat()
    with _lock:
        _seen[name] = stamp
        try:
            merged = {**_load(), name: stamp}
            PATH.parent.mkdir(parents=True, exist_ok=True)
            tmp = PATH.with_suffix(".tmp")
            tmp.write_text(json.dumps(merged))
            tmp.replace(PATH)
        except OSError as exc:
            log.warning("could not save last success for %s: %s", name, type(exc).__name__)


def last(name: str) -> Optional[str]:
    with _lock:
        stored = _load().get(name)
        mine = _seen.get(name)
    return max(filter(None, (stored, mine)), default=None)


def reset() -> None:
    """Tests only."""
    with _lock:
        _seen.clear()
        PATH.unlink(missing_ok=True)
