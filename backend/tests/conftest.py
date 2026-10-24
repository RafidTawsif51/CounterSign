import os
import tempfile

# Must be set before any app module imports the engine.
_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["UPLOAD_DIR"] = os.path.join(_tmp, "uploads")
os.environ["EXTRACT_CACHE_DIR"] = os.path.join(_tmp, "extract_cache")
os.environ["INJECTION_CACHE_DIR"] = os.path.join(_tmp, "injection_cache")
os.environ["FRONTEND_URL"] = "https://countersign.example"
# Tests never use the live .env: environment variables beat the .env file, so these pin every mock on and the key off.
for _flag in ("NESSIE", "CRS", "APIFY", "TWILIO", "CARTESIA", "CLAUDE", "RISK"):
    os.environ[f"MOCK_{_flag}"] = "true"
os.environ["MOCK_INJECTION"] = "false"
os.environ["ANTHROPIC_API_KEY"] = ""


import shutil  # noqa: E402
import sys  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


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
