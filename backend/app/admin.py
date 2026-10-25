"""Admin key for the routes that can wipe the demo or spend money: POST /api/demo/reset, POST /api/redteam/run and every /api/dev/* route.

A request must carry the header `X-Admin-Key` with the value of ADMIN_KEY. Without it, or with the wrong one, the answer is 403. While
ADMIN_KEY is blank on the server the routes stay locked (403 for everyone): a deploy that forgot the key is closed, not open.
Read-only routes and the attack and approve routes a judge uses are not behind it.
"""

import secrets
from typing import Optional

from fastapi import Header, HTTPException

from app.config import get_settings


def require_admin(x_admin_key: Optional[str] = Header(default=None)) -> None:
    key = get_settings().admin_key
    if not key:
        raise HTTPException(403, "admin routes are locked: ADMIN_KEY is not set on this server")
    if not x_admin_key or not secrets.compare_digest(x_admin_key.encode(), key.encode()):
        raise HTTPException(403, "this route needs the X-Admin-Key header")
