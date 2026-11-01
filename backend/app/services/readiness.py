import asyncio
from collections.abc import Awaitable, Callable

import boto3
import structlog
from botocore.config import Config
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings

log = structlog.get_logger()

Check = Callable[[], Awaitable[None]]


def build_checks(settings: Settings, engine: AsyncEngine) -> dict[str, Check]:
    async def database() -> None:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))

    async def redis() -> None:
        client = Redis.from_url(settings.redis_url.get_secret_value())
        try:
            await client.ping()
        finally:
            await client.aclose()

    def head_bucket() -> None:
        timeout = settings.readiness_timeout_seconds
        s3 = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key.get_secret_value(),
            aws_secret_access_key=settings.s3_secret_key.get_secret_value(),
            region_name=settings.s3_region,
            config=Config(
                connect_timeout=timeout,
                read_timeout=timeout,
                retries={"max_attempts": 0},
                s3={"addressing_style": "path"},
            ),
        )
        s3.head_bucket(Bucket=settings.s3_bucket)

    async def storage() -> None:
        await asyncio.to_thread(head_bucket)

    return {"database": database, "redis": redis, "storage": storage}


async def run_checks(checks: dict[str, Check], timeout: float) -> dict[str, str]:
    async def run_one(name: str, check: Check) -> str:
        try:
            await asyncio.wait_for(check(), timeout)
        except Exception:
            # Detail goes to the log only; responses must not expose internals.
            log.warning("readiness_check_failed", check=name, exc_info=True)
            return "error"
        return "ok"

    statuses = await asyncio.gather(*(run_one(name, check) for name, check in checks.items()))
    return dict(zip(checks, statuses, strict=True))
