"""Routing and GoNetem API routes."""

from fastapi import APIRouter, Depends

from .. import schemas
from ..dependencies import get_services
from ..services.container import ApplicationServices

router = APIRouter(tags=["routing"])


@router.get("/api/routing/status", response_model=schemas.RoutingStatusResponse)
async def api_routing_status(
    services: ApplicationServices = Depends(get_services),
) -> schemas.RoutingStatusResponse:
    return schemas.RoutingStatusResponse(**services.routing.status())


@router.post("/api/routing/apply", response_model=schemas.OperationResponse)
async def api_routing_apply(
    payload: schemas.RoutingApplyRequest,
    services: ApplicationServices = Depends(get_services),
) -> schemas.OperationResponse:
    await services.routing.apply(payload.method)
    return schemas.OperationResponse()


@router.post("/api/routing/delete", response_model=schemas.OperationResponse)
async def api_routing_delete(
    services: ApplicationServices = Depends(get_services),
) -> schemas.OperationResponse:
    await services.routing.delete()
    return schemas.OperationResponse()


@router.post("/api/gonetem/start", response_model=schemas.OperationResponse)
async def api_gonetem_start(
    services: ApplicationServices = Depends(get_services),
) -> schemas.OperationResponse:
    await services.routing.start_gonetem()
    return schemas.OperationResponse()


@router.post("/api/gonetem/stop", response_model=schemas.OperationResponse)
async def api_gonetem_stop(
    services: ApplicationServices = Depends(get_services),
) -> schemas.OperationResponse:
    await services.routing.stop_gonetem()
    return schemas.OperationResponse()
