import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import create_async_engine

from app.api import health
from app.api.v1 import cross_verify, documents
from app.core.config import Settings, get_settings
from app.core.logging import RequestLogMiddleware, configure_logging, log
from app.db.session import make_session_factory
from app.services.readiness import build_checks
from app.services.storage import build_s3_storage


def enqueue_ingest(document_id: uuid.UUID) -> None:
    # Imported lazily: importing the Celery app loads settings, which the API process and
    # tests may not have configured at import time.
    from app.workers.tasks import ingest_document

    ingest_document.delay(str(document_id))


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, "api")
    engine = create_async_engine(settings.database_url.get_secret_value())

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
        yield
        await engine.dispose()

    app = FastAPI(title="AI Document Intelligence", lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = make_session_factory(engine)
    app.state.storage = build_s3_storage(settings)
    # Replaceable in tests, like app.state.checks.
    app.state.enqueue = enqueue_ingest
    app.state.checks = build_checks(settings, engine)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.web_origin],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestLogMiddleware)
    app.include_router(health.router)
    app.include_router(documents.router)
    app.include_router(cross_verify.router)

    log.info("startup", settings=settings.model_dump(mode="json"))
    return app
