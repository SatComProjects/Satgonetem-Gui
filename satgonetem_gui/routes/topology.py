"""Read-only topology API routes."""

from fastapi import APIRouter, Depends

from .. import schemas
from ..dependencies import get_services
from ..services.container import ApplicationServices

router = APIRouter(
    tags=["topology"],
    responses=schemas.error_responses(404, 500),
)

# Blocking service reads are declared with ``def`` so FastAPI runs them in its
# threadpool instead of on the event loop.


@router.get("/api/satellites", response_model=list[schemas.SatelliteResponse])
def api_satellites(
    services: ApplicationServices = Depends(get_services),
) -> list[dict]:
    return services.topology.satellites()


@router.get(
    "/api/ground_stations",
    response_model=list[schemas.GroundStationResponse],
)
def api_ground_stations(
    services: ApplicationServices = Depends(get_services),
) -> list[dict]:
    return services.topology.ground_stations()


@router.get("/api/status", response_model=schemas.StatusResponse)
def api_status(
    services: ApplicationServices = Depends(get_services),
) -> schemas.StatusResponse:
    return schemas.StatusResponse(**services.topology.status())


@router.get("/api/links", response_model=list[schemas.LinkResponse])
def api_links(
    services: ApplicationServices = Depends(get_services),
) -> list[dict]:
    return services.topology.links()


@router.get("/api/nodes", response_model=list[schemas.NodeSummary])
def api_nodes(
    services: ApplicationServices = Depends(get_services),
) -> list[dict]:
    return services.topology.nodes()


@router.get("/api/nodes/{name}", response_model=schemas.NodeDetailResponse)
def api_node_detail(
    name: str,
    services: ApplicationServices = Depends(get_services),
) -> schemas.NodeDetailResponse:
    detail = services.topology.node_detail(name)
    return schemas.NodeDetailResponse(node=schemas.NodeDetail(**detail))
