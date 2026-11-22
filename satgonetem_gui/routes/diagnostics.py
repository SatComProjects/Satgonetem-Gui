"""Preflight diagnostics API routes."""

from fastapi import APIRouter, Depends

from .. import schemas
from ..dependencies import get_services
from ..services.container import ApplicationServices

router = APIRouter(
    tags=["diagnostics"],
    responses=schemas.error_responses(422, 500),
)


@router.post(
    "/api/diagnostics/preflight",
    response_model=schemas.PreflightResponse,
)
def api_preflight(
    payload: schemas.PreflightRequest | None = None,
    services: ApplicationServices = Depends(get_services),
) -> schemas.PreflightResponse:
    return schemas.PreflightResponse(**services.preflight.run(payload))
