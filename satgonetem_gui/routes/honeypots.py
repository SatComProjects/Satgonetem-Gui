"""Honeypot API routes."""

from fastapi import APIRouter, Depends

from .. import schemas
from ..dependencies import get_services
from ..services.container import ApplicationServices

router = APIRouter(tags=["security"])


@router.post("/api/security/honeypots", response_model=schemas.HoneypotStatus)
async def api_honeypot_start(
    payload: schemas.HoneypotRequest,
    services: ApplicationServices = Depends(get_services),
) -> schemas.HoneypotStatus:
    return schemas.HoneypotStatus(**services.honeypot.start(payload))


@router.get(
    "/api/security/honeypots/{node}/{port}",
    response_model=schemas.HoneypotStatus,
)
async def api_honeypot_status(
    node: str,
    port: int,
    services: ApplicationServices = Depends(get_services),
) -> schemas.HoneypotStatus:
    return schemas.HoneypotStatus(**services.honeypot.status(node, port))


@router.post(
    "/api/security/honeypots/{node}/{port}/stop",
    response_model=schemas.OperationResponse,
)
async def api_honeypot_stop(
    node: str,
    port: int,
    services: ApplicationServices = Depends(get_services),
) -> schemas.OperationResponse:
    services.honeypot.stop(node, port)
    return schemas.OperationResponse()
