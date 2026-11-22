"""Simulation transport API routes."""

from fastapi import APIRouter, Depends

from .. import schemas
from ..dependencies import get_services
from ..services.container import ApplicationServices

router = APIRouter(
    tags=["simulation"],
    responses=schemas.error_responses(404, 409, 422, 500),
)


@router.post("/api/simulation/start", response_model=schemas.OperationResponse)
async def api_simulation_start(
    services: ApplicationServices = Depends(get_services),
) -> schemas.OperationResponse:
    await services.simulation.start()
    return schemas.OperationResponse()


@router.post("/api/simulation/stop", response_model=schemas.OperationResponse)
async def api_simulation_stop(
    services: ApplicationServices = Depends(get_services),
) -> schemas.OperationResponse:
    await services.simulation.stop()
    return schemas.OperationResponse()


@router.post("/api/simulation/step", response_model=schemas.OperationResponse)
async def api_simulation_step(
    services: ApplicationServices = Depends(get_services),
) -> schemas.OperationResponse:
    await services.simulation.step()
    return schemas.OperationResponse()


@router.post("/api/simulation/reset", response_model=schemas.OperationResponse)
async def api_simulation_reset(
    services: ApplicationServices = Depends(get_services),
) -> schemas.OperationResponse:
    await services.simulation.reset()
    return schemas.OperationResponse()


@router.post("/api/simulation/seek", response_model=schemas.OperationResponse)
async def api_simulation_seek(
    payload: schemas.SimulationSeekRequest,
    services: ApplicationServices = Depends(get_services),
) -> schemas.OperationResponse:
    await services.simulation.seek(payload.step)
    return schemas.OperationResponse()


@router.post("/api/simulation/speed", response_model=schemas.OperationResponse)
async def api_simulation_speed(
    payload: schemas.SimulationSpeedRequest,
    services: ApplicationServices = Depends(get_services),
) -> schemas.OperationResponse:
    await services.simulation.change_speed(payload.direction)
    return schemas.OperationResponse()
