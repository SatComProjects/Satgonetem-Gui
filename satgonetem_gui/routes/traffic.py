"""Traffic generator API routes."""

from fastapi import APIRouter, Depends

from .. import schemas
from ..dependencies import get_services
from ..services.container import ApplicationServices

router = APIRouter(tags=["traffic"])

# Blocking service calls are declared with ``def`` so FastAPI runs them in its
# threadpool instead of on the event loop.


@router.get("/api/traffic/nodes", response_model=schemas.TrafficNodesResponse)
def api_traffic_nodes(
    services: ApplicationServices = Depends(get_services),
) -> schemas.TrafficNodesResponse:
    return schemas.TrafficNodesResponse(nodes=services.traffic.nodes())


@router.post("/api/traffic/iperf3", response_model=schemas.TrafficStartResponse)
def api_traffic_iperf3(
    payload: schemas.Iperf3Request,
    services: ApplicationServices = Depends(get_services),
) -> schemas.TrafficStartResponse:
    job_id = services.traffic.start("iperf3", payload)
    return schemas.TrafficStartResponse(job_id=job_id)


@router.post("/api/traffic/ping", response_model=schemas.TrafficStartResponse)
def api_traffic_ping(
    payload: schemas.PingRequest,
    services: ApplicationServices = Depends(get_services),
) -> schemas.TrafficStartResponse:
    job_id = services.traffic.start("ping", payload)
    return schemas.TrafficStartResponse(job_id=job_id)


@router.post("/api/traffic/hping3", response_model=schemas.TrafficStartResponse)
def api_traffic_hping3(
    payload: schemas.Hping3Request,
    services: ApplicationServices = Depends(get_services),
) -> schemas.TrafficStartResponse:
    job_id = services.traffic.start("hping3", payload)
    return schemas.TrafficStartResponse(job_id=job_id)


@router.get("/api/traffic/status", response_model=schemas.TrafficStatusResponse)
def api_traffic_status(
    job_id: str,
    services: ApplicationServices = Depends(get_services),
) -> schemas.TrafficStatusResponse:
    return schemas.TrafficStatusResponse(**services.traffic.status(job_id))


@router.post("/api/traffic/cancel", response_model=schemas.OperationResponse)
def api_traffic_cancel(
    payload: schemas.TrafficCancelRequest,
    services: ApplicationServices = Depends(get_services),
) -> schemas.OperationResponse:
    services.traffic.cancel(payload.job_id)
    return schemas.OperationResponse()
