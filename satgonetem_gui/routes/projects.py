"""Project lifecycle API routes."""

from fastapi import APIRouter, Depends

from .. import schemas
from ..dependencies import get_services
from ..services.container import ApplicationServices

router = APIRouter(tags=["projects"])


@router.get(
    "/api/ground_stations/presets",
    response_model=list[schemas.GroundStationPreset],
)
async def api_ground_station_presets(
    services: ApplicationServices = Depends(get_services),
) -> list[dict]:
    return services.project.presets()


@router.post("/api/project/create", response_model=schemas.OperationResponse)
async def api_project_create(
    payload: schemas.ProjectCreateRequest,
    services: ApplicationServices = Depends(get_services),
) -> schemas.OperationResponse:
    services.project.start_create(payload)
    return schemas.OperationResponse()


@router.get("/api/project/status", response_model=schemas.ProjectStatusResponse)
async def api_project_status(
    services: ApplicationServices = Depends(get_services),
) -> schemas.ProjectStatusResponse:
    return schemas.ProjectStatusResponse(**services.project.status())


@router.get("/api/project/exists", response_model=schemas.ProjectExistsResponse)
async def api_project_exists(
    name: str,
    services: ApplicationServices = Depends(get_services),
) -> schemas.ProjectExistsResponse:
    return schemas.ProjectExistsResponse(exists=services.project.exists(name))


@router.get("/api/project/config", response_model=schemas.ProjectConfigResponse)
async def api_project_config(
    name: str,
    services: ApplicationServices = Depends(get_services),
) -> schemas.ProjectConfigResponse:
    return schemas.ProjectConfigResponse.model_validate(services.project.config(name))


@router.post("/api/project/load", response_model=schemas.ProjectLoadedResponse)
async def api_project_load(
    payload: schemas.ProjectLoadRequest,
    services: ApplicationServices = Depends(get_services),
) -> schemas.ProjectLoadedResponse:
    name = await services.project.load(payload.content)
    return schemas.ProjectLoadedResponse(name=name)


@router.get("/api/project/save", response_model=schemas.ProjectSaveResponse)
async def api_project_save(
    services: ApplicationServices = Depends(get_services),
) -> schemas.ProjectSaveResponse:
    data = await services.project.save()
    return schemas.ProjectSaveResponse(**data)
