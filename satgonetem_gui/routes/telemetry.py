"""Telemetry and detection API routes."""

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse

from .. import schemas
from ..dependencies import get_services
from ..services.container import ApplicationServices

router = APIRouter(tags=["security"])


@router.get(
    "/api/security/telemetry",
    response_model=schemas.TelemetrySnapshotResponse,
)
async def api_telemetry(
    services: ApplicationServices = Depends(get_services),
) -> schemas.TelemetrySnapshotResponse:
    return schemas.TelemetrySnapshotResponse(**services.telemetry.sample())


@router.get("/api/security/telemetry/prometheus", include_in_schema=False)
async def api_telemetry_prometheus(
    services: ApplicationServices = Depends(get_services),
) -> PlainTextResponse:
    return PlainTextResponse(services.telemetry.prometheus())


@router.post(
    "/api/security/telemetry/clear-alerts",
    response_model=schemas.OperationResponse,
)
async def api_telemetry_clear_alerts(
    services: ApplicationServices = Depends(get_services),
) -> schemas.OperationResponse:
    services.telemetry.clear_alerts()
    return schemas.OperationResponse()
