"""FastAPI app entrypoint. Run: uvicorn app.main:app"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlmodel import Session
from starlette.middleware.sessions import SessionMiddleware

from app import auth, botcache, services, ui, webhook
from app.config import get_settings
from app.db import create_db_and_tables, engine
from app.queue import Worker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    # Best-effort: re-apply webhooks for all active bots on startup.
    if get_settings().resync_webhooks_on_startup:
        try:
            with Session(engine) as session:
                await services.resync_all_webhooks(session)
        except Exception as exc:
            logger.error("webhook resync on startup failed: %s", exc)

    # Start the durable outbox worker (delivers queued forwards).
    worker = Worker(engine, send_fn=botcache.send_job)
    worker_task = asyncio.create_task(worker.run())
    app.state.worker = worker

    yield

    # Graceful shutdown: stop worker, close bot clients.
    worker.stop()
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass
    await botcache.shutdown_all()


settings = get_settings()

app = FastAPI(title="Bot Forward Panel", lifespan=lifespan)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret,
    https_only=(settings.environment == "prod"),
    same_site="lax",
    max_age=86400,  # 1 day; re-login required after expiry
)

app.include_router(auth.router)
app.include_router(ui.router)
app.include_router(webhook.router)


@app.get("/healthz")
async def healthz():
    return {"ok": True}
