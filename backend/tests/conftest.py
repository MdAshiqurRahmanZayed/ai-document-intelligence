import os
import subprocess
import sys
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import Settings, get_settings
from tests.helpers import Api, run_sync, running_api

VALID_ENV = {
    "APP_ENV": "test",
    "LOG_LEVEL": "INFO",
    "WEB_ORIGIN": "http://localhost:3000",
    "S3_REGION": "us-east-1",
    "DATABASE_URL": "postgresql+asyncpg://u:p@localhost:5432/db",
    "REDIS_URL": "redis://localhost:6379/0",
    "S3_ENDPOINT_URL": "http://localhost:9000",
    "S3_ACCESS_KEY": "access-key",
    "S3_SECRET_KEY": "secret-key-1234",
    "S3_BUCKET": "documents",
}


@pytest.fixture
def valid_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    for key, value in VALID_ENV.items():
        monkeypatch.setenv(key, value)
    return monkeypatch


@pytest.fixture(scope="session")
def db_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        # Failing loudly beats skipping: a skipped DB suite looks like a pass.
        pytest.fail("TEST_DATABASE_URL is not set. Run the tests with `make test`.", pytrace=False)
    return url


@pytest.fixture(scope="session")
def migrated_db(db_url: str) -> str:
    # Running the real migration means every DB-backed test also checks it.
    env = {**os.environ, **VALID_ENV, "DATABASE_URL": db_url}
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=Path(__file__).parents[1],
        env=env,
        check=True,
    )
    return db_url


async def _truncate(url: str) -> None:
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "TRUNCATE documents, pages, processing_events, chat_sessions "
                    "RESTART IDENTITY CASCADE"
                )
            )
    finally:
        await engine.dispose()


@pytest.fixture
def db(migrated_db: str, valid_env: pytest.MonkeyPatch) -> Iterator[str]:
    """Empty test database, with DATABASE_URL pointing at it for code that reads settings."""
    run_sync(_truncate(migrated_db))
    valid_env.setenv("DATABASE_URL", migrated_db)
    get_settings.cache_clear()
    yield migrated_db
    get_settings.cache_clear()


@pytest.fixture
async def session(db: str) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(db, poolclass=NullPool)
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        yield session
    await engine.dispose()


@pytest.fixture
async def api(db: str) -> AsyncIterator[Api]:
    async with running_api(Settings()) as running:
        yield running
