import os
import tempfile

# Must be set before any app module imports the engine.
_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["UPLOAD_DIR"] = os.path.join(_tmp, "uploads")
os.environ["EXTRACT_CACHE_DIR"] = os.path.join(_tmp, "extract_cache")
os.environ["INJECTION_CACHE_DIR"] = os.path.join(_tmp, "injection_cache")
os.environ["RISK_CACHE_DIR"] = os.path.join(_tmp, "risk_cache")
os.environ["REPORT_CACHE_DIR"] = os.path.join(_tmp, "report_cache")
os.environ["CONTACTS_CACHE_DIR"] = os.path.join(_tmp, "contacts_cache")
os.environ["LIVENESS_PATH"] = os.path.join(_tmp, "last_success.json")
os.environ["FRONTEND_URL"] = "https://countersign.example"
os.environ["PAGES_BASE_URL"] = "https://aayushswami123.github.io/Countersign"  # the published base URL; the path is case-sensitive
# Tests never use the live .env: environment variables beat the .env file, so these pin every mock on and the key off.
for _flag in ("NESSIE", "CRS", "APIFY", "TWILIO", "CARTESIA", "CLAUDE"):
    os.environ[f"MOCK_{_flag}"] = "true"
os.environ["ADMIN_KEY"] = "test-admin-key"  # the routes behind the admin key (reset, red-team run, dev); every test client sends it unless a test removes it
os.environ["APP_ENV"] = "development"
os.environ["MOCK_INJECTION"] = "false"
os.environ["MOCK_RISK"] = "false"  # the real assessor; its Claude classifier stays off because MOCK_CLAUDE is true
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["APIFY_ACTOR_ID"] = "test-user/vendor-contact-verifier"
# Same for every other value a real .env might hold: fixed fake values (fiction-range phone numbers), blank keys.
os.environ["DEMO_VENDOR_PHONE"] = "+14155550142"
os.environ["ALLOWED_CALL_NUMBERS"] = "+14155550142"
for _blank in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM_NUMBER", "PUBLIC_BASE_URL", "CARTESIA_API_KEY", "CARTESIA_VOICE_ID", "STT_API_KEY",
               "NESSIE_API_KEY", "APIFY_TOKEN", "CRS_API_KEY", "BOUNTY_WEBHOOK_SECRET", "DEMO_CALL_ROUTES"):
    os.environ[_blank] = ""


import shutil  # noqa: E402
import sys  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Every TestClient sends the admin key, so the many tests that reset the demo need no change. test_admin.py removes it to test the lock.
from starlette.testclient import TestClient  # noqa: E402

_client_init = TestClient.__init__


def _client_init_with_admin_key(self, *args, **kwargs):
    _client_init(self, *args, **kwargs)
    self.headers.setdefault("X-Admin-Key", os.environ["ADMIN_KEY"])


TestClient.__init__ = _client_init_with_admin_key


@pytest.fixture(scope="session")
def seed_template(tmp_path_factory):
    """Seed once per test session into a template database file. Tests copy it instead of reseeding.

    Returns (path, SeedSummary). The seed also writes the PDFs under backend/seed/invoices, which the
    copies refer to by relative path."""
    from sqlalchemy import create_engine
    from sqlmodel import Session, SQLModel

    from seed import seed as seedmod

    path = tmp_path_factory.mktemp("template") / "seeded.sqlite"
    engine = create_engine(f"sqlite:///{path}")  # rollback-journal mode: one self-contained file, safe to copy
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        summary = seedmod.seed_database(s)
    engine.dispose()
    return path, summary


def copy_seeded(seed_template, dest_dir: Path, name: str = "db.sqlite") -> Path:
    """A private copy of the seeded database for one test or module."""
    dest = Path(dest_dir) / name
    shutil.copyfile(seed_template[0], dest)
    return dest


@pytest.fixture(autouse=True)
def _private_liveness(tmp_path, monkeypatch):
    """Successes recorded under test must never reach the running server's status panel (backend/.cache/last_success.json)."""
    from app.services import liveness

    monkeypatch.setattr(liveness, "PATH", tmp_path / "last_success.json")
    monkeypatch.setattr(liveness, "_seen", {})
