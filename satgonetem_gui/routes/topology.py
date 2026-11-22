"""Read-only topology API routes."""

from fastapi import APIRouter, Depends, Query

from .. import schemas
from ..dependencies import get_services
from ..services.container import ApplicationServices

router = APIRouter(
    tags=["topology"],
    responses=schemas.error_responses(404, 500),
)

# Blocking service reads are declared with ``def`` so FastAPI runs them in its
# threadpool instead of on the event loop.


def _page(items: list[dict], limit: int, offset: int) -> list[dict]:
    """Bound a list response to the requested window."""
    return items[offset : offset + limit]


@router.get("/api/satellites", response_model=list[schemas.SatelliteResponse])
def api_satellites(
    limit: int = Query(default=1000, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
    services: ApplicationServices = Depends(get_services),
) -> list[dict]:
    return _page(services.topology.satellites(), limit, offset)


@router.get(
    "/api/ground_stations",
    response_model=list[schemas.GroundStationResponse],
)
def api_ground_stations(
    limit: int = Query(default=1000, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
    services: ApplicationServices = Depends(get_services),
) -> list[dict]:
    return _page(services.topology.ground_stations(), limit, offset)


@router.get("/api/status", response_model=schemas.StatusResponse)
def api_status(
    services: ApplicationServices = Depends(get_services),
) -> schemas.StatusResponse:
    return schemas.StatusResponse(**services.topology.status())


@router.get("/api/links", response_model=list[schemas.LinkResponse])
def api_links(
    limit: int = Query(default=1000, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
    services: ApplicationServices = Depends(get_services),
) -> list[dict]:
    return _page(services.topology.links(), limit, offset)


@router.get("/api/nodes", response_model=list[schemas.NodeSummary])
def api_nodes(
    limit: int = Query(default=1000, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
    services: ApplicationServices = Depends(get_services),
) -> list[dict]:
    return _page(services.topology.nodes(), limit, offset)


@router.get("/api/nodes/{name}", response_model=schemas.NodeDetailResponse)
def api_node_detail(
    name: str,
    services: ApplicationServices = Depends(get_services),
) -> schemas.NodeDetailResponse:
    detail = services.topology.node_detail(name)
    return schemas.NodeDetailResponse(node=schemas.NodeDetail(**detail))
