from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import create_async_engine

from app.api import health
from app.core.config import Settings, get_settings
from app.core.logging import RequestLogMiddleware, configure_logging, log
from app.services.readiness import build_checks


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, "api")
    engine = create_async_engine(settings.database_url.get_secret_value())

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await engine.dispose()

    app = FastAPI(title="AI Document Intelligence", lifespan=lifespan)
    app.state.settings = settings
    app.state.checks = build_checks(settings, engine)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.web_origin],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestLogMiddleware)
    app.include_router(health.router)

    log.info("startup", settings=settings.model_dump(mode="json"))
    return app
