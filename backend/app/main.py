import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import create_async_engine

from app.api import health
from app.api.auth import require_api_key
from app.api.v1 import cross_verify, documents, jobs
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


def enqueue_extract(document_id: uuid.UUID) -> None:
    from app.workers.tasks import extract_document

    extract_document.delay(str(document_id))


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
    app.state.enqueue_extract = enqueue_extract
    app.state.checks = build_checks(settings, engine)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.web_origin],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestLogMiddleware)
    app.include_router(health.router)
    # Health stays outside /api/v1 and open; every versioned route needs the API key (if set).
    protected = [Depends(require_api_key)]
    app.include_router(documents.router, dependencies=protected)
    app.include_router(cross_verify.router, dependencies=protected)
    app.include_router(jobs.router, dependencies=protected)

    if settings.api_key is None:
        log.warning("auth_disabled", reason="API_KEY is not set, the API is open")
    log.info("startup", settings=settings.model_dump(mode="json"))
    return app
