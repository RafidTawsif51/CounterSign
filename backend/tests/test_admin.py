"""The admin key: POST /api/demo/reset, POST /api/redteam/run and every /api/dev/* route need the header X-Admin-Key (ADMIN_KEY) and answer
403 without it. In production the dev routes are not registered at all. Read-only routes stay public."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app

KEY = "test-admin-key"
BACKEND = Path(__file__).resolve().parent.parent

# (method, path, a body that is valid when the key is right)
LOCKED = [
    ("POST", "/api/demo/reset", None),
    ("POST", "/api/redteam/run", {"n": 200}),
    ("POST", "/api/dev/mock-run?delay_ms=0", None),
    ("GET", "/api/dev/subscribers", None),
]


def _call(client, method, path, body, headers=None):
    return client.request(method, path, json=body, headers=headers or {})


@pytest.fixture
def anon():
    with TestClient(app) as client:
        client.headers.pop("X-Admin-Key")
        yield client


@pytest.mark.parametrize("method,path,body", LOCKED)
def test_locked_route_without_the_key_is_403(anon, method, path, body):
    r = _call(anon, method, path, body)
    assert r.status_code == 403, r.text


@pytest.mark.parametrize("method,path,body", LOCKED)
def test_locked_route_with_a_wrong_key_is_403(anon, method, path, body):
    for wrong in ("nope", KEY + "x", KEY[:-1], " " + KEY):
        assert _call(anon, method, path, body, {"X-Admin-Key": wrong}).status_code == 403, wrong


@pytest.mark.parametrize("method,path,body", LOCKED)
def test_locked_route_with_the_key_is_not_refused(anon, method, path, body):
    r = _call(anon, method, path, body, {"X-Admin-Key": KEY})
    assert r.status_code not in (401, 403), r.text
    # reset 200, dev mock-run 202, subscribers 200; the red-team run answers 409 on mocks (it spends money and measures nothing there)
    assert r.status_code in (200, 202, 409), r.text


def test_a_blank_admin_key_locks_everyone_out(anon, monkeypatch):
    monkeypatch.setattr(get_settings(), "admin_key", "")
    for method, path, body in LOCKED:
        assert _call(anon, method, path, body, {"X-Admin-Key": ""}).status_code == 403
        assert _call(anon, method, path, body, {"X-Admin-Key": KEY}).status_code == 403  # even the old key: nothing is set to match


def test_the_key_is_checked_before_the_body(anon):
    assert anon.post("/api/redteam/run", json={"n": 5000}).status_code == 403  # not 422: a stranger learns nothing about the body


def test_a_refused_reset_changes_nothing(anon):
    """A stranger's reset must not touch the leaderboard or the board."""
    anon.post("/api/demo/reset", headers={"X-Admin-Key": KEY})  # known state
    r = anon.post("/api/attacks", json={"attacker_name": "Judge Priya", "card": "classic_bank_change", "payload": {"thread_id": "thr_summit_0919", "from_addr": "ar@summit-concrete.co", "body": "We changed banks. New account below."}})
    assert r.status_code == 201
    assert anon.post("/api/demo/reset?keep_leaderboard=false").status_code == 403
    assert len(anon.get("/api/attacks/leaderboard").json()["attempts"]) == 1


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/api/health"),
        ("GET", "/api/redteam/results"),  # stays public: the Red team page reads it
        ("GET", "/api/system/status"),
        ("GET", "/api/attacks/leaderboard"),
        ("GET", "/api/vendors"),
        ("GET", "/api/payment-runs/latest"),
    ],
)
def test_read_routes_stay_public(anon, method, path):
    r = anon.request(method, path)
    assert r.status_code in (200, 404), (path, r.status_code)  # 404 only for results not yet measured; never 401 or 403
    assert r.status_code != 403


def test_routes_a_judge_uses_are_not_behind_the_key(anon):
    """Launching an attack, asking and approving need no admin key (approve answers 404 here only because that payment does not exist)."""
    assert anon.post("/api/payments/pay_nope/ask", json={"question": "Why was this held?"}).status_code == 404
    assert anon.post("/api/payments/pay_nope/approve", json={"approver": "Dev", "reason": "ok"}).status_code in (404, 422)


def test_in_production_the_dev_routes_are_not_registered():
    code = (
        "from app.main import app\n"
        "o = app.openapi()['paths']\n"
        "print(sorted(p for p in o if '/dev' in p))\n"
    )
    def routes(env_value):
        env = {**os.environ, "APP_ENV": env_value}
        return subprocess.run([sys.executable, "-c", code], cwd=BACKEND, env=env, capture_output=True, text=True, timeout=120)

    prod = routes("production")
    assert prod.returncode == 0, prod.stderr
    assert prod.stdout.strip() == "[]", prod.stdout  # nothing under /api/dev in production
    dev = routes("development")
    assert dev.returncode == 0, dev.stderr
    assert "/api/dev/mock-run" in dev.stdout  # and they are there otherwise (behind the key)


def test_in_production_a_dev_request_is_404_even_with_the_key():
    code = (
        "from fastapi.testclient import TestClient\n"
        "from app.main import app\n"
        "with TestClient(app) as c:\n"
        "    print(c.post('/api/dev/mock-run', headers={'X-Admin-Key': 'test-admin-key'}).status_code)\n"
    )
    r = subprocess.run([sys.executable, "-c", code], cwd=BACKEND, env={**os.environ, "APP_ENV": "production"}, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip().splitlines()[-1] == "404"
