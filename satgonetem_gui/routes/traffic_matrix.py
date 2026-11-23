"""Bounded throughput-matrix routes."""

from typing import Literal

from fastapi import APIRouter, Depends, Query

from .. import schemas
from ..dependencies import get_services
from ..services.container import ApplicationServices

router = APIRouter(
    tags=["traffic"],
    responses=schemas.error_responses(404, 409, 422, 429, 500),
)


@router.post(
    "/api/traffic/matrix",
    response_model=schemas.TrafficMatrixStartResponse,
)
def api_start_traffic_matrix(
    payload: schemas.TrafficMatrixRequest,
    services: ApplicationServices = Depends(get_services),
) -> schemas.TrafficMatrixStartResponse:
    return schemas.TrafficMatrixStartResponse(job_id=services.traffic_matrix.start(payload))


@router.get(
    "/api/traffic/matrix/{job_id}",
    response_model=schemas.TrafficMatrixStatusResponse,
)
def api_traffic_matrix_status(
    job_id: str,
    services: ApplicationServices = Depends(get_services),
) -> schemas.TrafficMatrixStatusResponse:
    return schemas.TrafficMatrixStatusResponse(**services.traffic_matrix.status(job_id))


@router.get(
    "/api/traffic/matrix/{job_id}/export",
    response_model=schemas.TrafficMatrixExportResponse,
)
def api_traffic_matrix_export(
    job_id: str,
    export_format: Literal["csv", "json"] = Query("csv", alias="format"),
    services: ApplicationServices = Depends(get_services),
) -> schemas.TrafficMatrixExportResponse:
    return schemas.TrafficMatrixExportResponse(
        **services.traffic_matrix.export(job_id, export_format)
    )
