import asyncio
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlmodel import Session

from app import dev, events, integrations
from app.config import get_settings
from app.db import create_all, get_session, is_postgres
from app.redteam import api as redteam_api
from app.services import ask, attacks, bounty, contacts, ingest, report, reset, review, run, status, vendors


@asynccontextmanager
async def lifespan(_app: FastAPI):
    create_all()
    run.mark_stale_runs()
    await attacks.start()
    warm = None
    if not settings.mock_apify:  # the demo vendor's independent lookup, so the first demo call does not wait for the Actor
        warm = asyncio.create_task(contacts.warm())
    yield
    if warm is not None:
        warm.cancel()
    await attacks.stop()


settings = get_settings()

app = FastAPI(title="Countersign", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api = APIRouter(prefix="/api")


@api.get("/health")
def health(session: Session = Depends(get_session)) -> dict:
    session.exec(text("SELECT 1"))
    return {
        "status": "ok",
        "database": "postgres" if is_postgres() else "sqlite",
        "mocks": settings.mock_flags,
    }


api.include_router(events.router)
api.include_router(ingest.router)
api.include_router(run.router)
api.include_router(report.router)
api.include_router(review.router)
api.include_router(ask.router)
api.include_router(vendors.router)
api.include_router(attacks.router)
api.include_router(bounty.router)
api.include_router(reset.router)
api.include_router(status.router)
api.include_router(dev.router)
api.include_router(integrations.router)
api.include_router(redteam_api.router)

app.include_router(api)
