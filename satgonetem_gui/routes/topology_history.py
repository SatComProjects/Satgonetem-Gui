"""Topology snapshot history and comparison routes."""

from fastapi import APIRouter, Depends, Query

from .. import schemas
from ..dependencies import get_services
from ..services.container import ApplicationServices

router = APIRouter(
    tags=["topology"],
    responses=schemas.error_responses(404, 500),
)


@router.post(
    "/api/topology/snapshots",
    response_model=schemas.TopologyRecordSnapshotResponse,
)
def api_record_topology_snapshot(
    services: ApplicationServices = Depends(get_services),
) -> schemas.TopologyRecordSnapshotResponse:
    return schemas.TopologyRecordSnapshotResponse(**services.topology_history.record())


@router.get(
    "/api/topology/snapshots",
    response_model=schemas.TopologySnapshotListResponse,
)
def api_list_topology_snapshots(
    services: ApplicationServices = Depends(get_services),
) -> schemas.TopologySnapshotListResponse:
    return schemas.TopologySnapshotListResponse(**services.topology_history.list_snapshots())


@router.get(
    "/api/topology/compare",
    response_model=schemas.TopologyCompareResponse,
)
def api_compare_topology(
    from_step: int = Query(ge=0),
    to_step: int = Query(ge=0),
    services: ApplicationServices = Depends(get_services),
) -> schemas.TopologyCompareResponse:
    return schemas.TopologyCompareResponse(**services.topology_history.compare(from_step, to_step))
