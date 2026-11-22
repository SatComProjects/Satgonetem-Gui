"""Topology health and export API routes."""

from typing import Literal

from fastapi import APIRouter, Depends, Query

from .. import schemas
from ..dependencies import get_services
from ..services.container import ApplicationServices

router = APIRouter(
    tags=["topology"],
    responses=schemas.error_responses(404, 422, 500),
)


@router.get("/api/topology/health", response_model=schemas.TopologyHealthResponse)
def api_topology_health(
    services: ApplicationServices = Depends(get_services),
) -> schemas.TopologyHealthResponse:
    return schemas.TopologyHealthResponse(**services.topology_export.health())


@router.get("/api/topology/export", response_model=schemas.TopologyExportResponse)
def api_topology_export(
    export_format: Literal["json", "dot", "graphml"] = Query(
        default="json",
        alias="format",
    ),
    services: ApplicationServices = Depends(get_services),
) -> schemas.TopologyExportResponse:
    return schemas.TopologyExportResponse(**services.topology_export.export(export_format))
