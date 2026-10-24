from collections.abc import Iterator

from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine

from app.config import get_settings


def is_postgres() -> bool:
    return get_settings().database_url.startswith("postgres")


def _make_engine():
    url = get_settings().database_url
    # Accept the common postgres:// and postgresql:// forms and use the psycopg 3 driver.
    if url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url[len("postgres://"):]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    if url.startswith("sqlite"):
        # FastAPI serves requests from a thread pool.
        eng = create_engine(url, connect_args={"check_same_thread": False})

        @event.listens_for(eng, "connect")
        def _pragmas(dbapi_conn, _record):
            # WAL lets the payment run read while event writes commit; busy_timeout waits instead of failing.
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA synchronous=NORMAL")
            cur.execute("PRAGMA busy_timeout=10000")
            cur.close()

        return eng
    return create_engine(url, pool_pre_ping=True)


engine = _make_engine()


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session


def create_all() -> None:
    # Import so every table registers on SQLModel.metadata.
    from app import models  # noqa: F401

    SQLModel.metadata.create_all(engine)
