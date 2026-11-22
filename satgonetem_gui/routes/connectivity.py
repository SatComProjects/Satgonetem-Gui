"""Full-mesh connectivity diagnostics API routes."""

from typing import Literal

from fastapi import APIRouter, Depends

from .. import schemas
from ..dependencies import get_services
from ..services.container import ApplicationServices

router = APIRouter(
    tags=["diagnostics"],
    responses=schemas.error_responses(404, 409, 422, 429, 500),
)

# Blocking service calls are declared with ``def`` so FastAPI runs them in its
# threadpool instead of on the event loop. Starting a check only launches the
# background worker; progress is polled through the status route.


@router.post(
    "/api/diagnostics/connectivity",
    response_model=schemas.ConnectivityStartResponse,
)
def api_connectivity_start(
    payload: schemas.ConnectivityStartRequest,
    services: ApplicationServices = Depends(get_services),
) -> schemas.ConnectivityStartResponse:
    job_id = services.connectivity.start(payload)
    return schemas.ConnectivityStartResponse(job_id=job_id)


@router.get(
    "/api/diagnostics/connectivity/{job_id}",
    response_model=schemas.ConnectivityStatusResponse,
)
def api_connectivity_status(
    job_id: str,
    services: ApplicationServices = Depends(get_services),
) -> schemas.ConnectivityStatusResponse:
    return schemas.ConnectivityStatusResponse(**services.connectivity.status(job_id))


@router.get(
    "/api/diagnostics/connectivity/{job_id}/export",
    response_model=schemas.ConnectivityExportResponse,
)
def api_connectivity_export(
    job_id: str,
    format: Literal["csv", "json"] = "csv",
    services: ApplicationServices = Depends(get_services),
) -> schemas.ConnectivityExportResponse:
    return schemas.ConnectivityExportResponse(**services.connectivity.export(job_id, format))
