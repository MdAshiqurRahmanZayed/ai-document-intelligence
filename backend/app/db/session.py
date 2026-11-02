from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.core.config import get_settings


def make_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    # expire_on_commit=False keeps loaded rows readable after commit without a refresh query.
    return async_sessionmaker(engine, expire_on_commit=False)


@asynccontextmanager
async def worker_session() -> AsyncGenerator[AsyncSession]:
    # Celery tasks call asyncio.run(), which makes a fresh event loop per task, and asyncpg
    # connections cannot move between loops. So each task gets its own short-lived engine.
    engine = create_async_engine(get_settings().database_url.get_secret_value(), poolclass=NullPool)
    try:
        async with make_session_factory(engine)() as session:
            yield session
    finally:
        await engine.dispose()
