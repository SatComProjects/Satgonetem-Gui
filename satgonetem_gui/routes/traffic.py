"""Traffic generator API routes."""

from fastapi import APIRouter, Depends

from .. import schemas
from ..dependencies import get_services
from ..services.container import ApplicationServices

router = APIRouter(tags=["traffic"])


@router.get("/api/traffic/nodes", response_model=schemas.TrafficNodesResponse)
async def api_traffic_nodes(
    services: ApplicationServices = Depends(get_services),
) -> schemas.TrafficNodesResponse:
    return schemas.TrafficNodesResponse(nodes=services.traffic.nodes())


@router.post("/api/traffic/iperf3", response_model=schemas.TrafficStartResponse)
async def api_traffic_iperf3(
    payload: schemas.Iperf3Request,
    services: ApplicationServices = Depends(get_services),
) -> schemas.TrafficStartResponse:
    job_id = services.traffic.start_iperf3(payload)
    return schemas.TrafficStartResponse(job_id=job_id)


@router.post("/api/traffic/ping", response_model=schemas.TrafficStartResponse)
async def api_traffic_ping(
    payload: schemas.PingRequest,
    services: ApplicationServices = Depends(get_services),
) -> schemas.TrafficStartResponse:
    job_id = services.traffic.start_ping(payload)
    return schemas.TrafficStartResponse(job_id=job_id)


@router.post("/api/traffic/hping3", response_model=schemas.TrafficStartResponse)
async def api_traffic_hping3(
    payload: schemas.Hping3Request,
    services: ApplicationServices = Depends(get_services),
) -> schemas.TrafficStartResponse:
    job_id = services.traffic.start_hping3(payload)
    return schemas.TrafficStartResponse(job_id=job_id)


@router.get("/api/traffic/status", response_model=schemas.TrafficStatusResponse)
async def api_traffic_status(
    job_id: str,
    services: ApplicationServices = Depends(get_services),
) -> schemas.TrafficStatusResponse:
    return schemas.TrafficStatusResponse(**services.traffic.status(job_id))


@router.post("/api/traffic/cancel", response_model=schemas.OperationResponse)
async def api_traffic_cancel(
    payload: schemas.TrafficCancelRequest,
    services: ApplicationServices = Depends(get_services),
) -> schemas.OperationResponse:
    services.traffic.cancel(payload.job_id)
    return schemas.OperationResponse()
