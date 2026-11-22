"""Satellite traffic-addressability API routes."""

from fastapi import APIRouter, Depends

from .. import schemas
from ..dependencies import get_services
from ..services.container import ApplicationServices

router = APIRouter(
    tags=["addressability"],
    responses=schemas.error_responses(404, 409, 422, 500),
)

# The addressability service is synchronous, so these handlers stay plain
# ``def`` and FastAPI runs them in its threadpool.


@router.get(
    "/api/satellites/addressable",
    response_model=schemas.SatelliteAddressabilityResponse,
)
def api_satellite_addressability(
    services: ApplicationServices = Depends(get_services),
) -> schemas.SatelliteAddressabilityResponse:
    return schemas.SatelliteAddressabilityResponse(**services.addressability.status())


@router.post(
    "/api/satellites/addressable",
    response_model=schemas.AddressabilityUpdateResponse,
)
def api_set_satellite_addressability(
    payload: schemas.AddressabilityUpdateRequest,
    services: ApplicationServices = Depends(get_services),
) -> schemas.AddressabilityUpdateResponse:
    return schemas.AddressabilityUpdateResponse(**services.addressability.set_all(payload.enabled))


@router.post(
    "/api/nodes/{name}/addressable",
    response_model=schemas.AddressabilityUpdateResponse,
)
def api_set_node_addressability(
    name: str,
    payload: schemas.AddressabilityUpdateRequest,
    services: ApplicationServices = Depends(get_services),
) -> schemas.AddressabilityUpdateResponse:
    return schemas.AddressabilityUpdateResponse(
        **services.addressability.set_one(name, payload.enabled)
    )
