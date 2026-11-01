from typing import Any

from fastapi import APIRouter, Request, Response

from app.services.readiness import run_checks

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(request: Request, response: Response) -> dict[str, Any]:
    state = request.app.state
    checks = await run_checks(state.checks, state.settings.readiness_timeout_seconds)
    ready = all(status == "ok" for status in checks.values())
    if not ready:
        response.status_code = 503
    return {"status": "ok" if ready else "error", "checks": checks}
