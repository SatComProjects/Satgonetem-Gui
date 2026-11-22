"""Project workspace/catalog API routes."""

from fastapi import APIRouter, Depends

from .. import schemas
from ..dependencies import get_services
from ..services.container import ApplicationServices

router = APIRouter(
    tags=["workspace"],
    responses=schemas.error_responses(400, 404, 409, 422, 500),
)

# Catalog reads and file mutations are blocking service calls; only save/load
# handlers stay ``async def`` because the service awaits serialization.


@router.get("/api/projects", response_model=schemas.ProjectListResponse)
def api_projects(
    services: ApplicationServices = Depends(get_services),
) -> schemas.ProjectListResponse:
    return schemas.ProjectListResponse(**services.catalog.list_projects())


@router.post(
    "/api/projects/{project_id}/load",
    response_model=schemas.ProjectLoadedResponse,
)
async def api_load_project(
    project_id: str,
    services: ApplicationServices = Depends(get_services),
) -> schemas.ProjectLoadedResponse:
    name = await services.catalog.load_project(project_id)
    return schemas.ProjectLoadedResponse(name=name)


@router.post(
    "/api/projects/{project_id}/duplicate",
    response_model=schemas.ProjectSavedResponse,
)
def api_duplicate_project(
    project_id: str,
    payload: schemas.ProjectDuplicateRequest,
    services: ApplicationServices = Depends(get_services),
) -> schemas.ProjectSavedResponse:
    data = services.catalog.duplicate_project(project_id, payload.name)
    return schemas.ProjectSavedResponse(**data)


@router.delete(
    "/api/projects/{project_id}",
    response_model=schemas.OperationResponse,
)
def api_delete_project(
    project_id: str,
    services: ApplicationServices = Depends(get_services),
) -> schemas.OperationResponse:
    services.catalog.delete_project(project_id)
    return schemas.OperationResponse()


@router.post("/api/project/save-to", response_model=schemas.ProjectSavedResponse)
async def api_save_to(
    payload: schemas.ProjectSaveToRequest,
    services: ApplicationServices = Depends(get_services),
) -> schemas.ProjectSavedResponse:
    data = await services.catalog.save_current_to(payload.name, payload.overwrite)
    return schemas.ProjectSavedResponse(**data)


@router.post(
    "/api/project/save-in-place",
    response_model=schemas.ProjectSavedResponse,
)
async def api_save_in_place(
    services: ApplicationServices = Depends(get_services),
) -> schemas.ProjectSavedResponse:
    data = await services.catalog.save_current_in_place()
    return schemas.ProjectSavedResponse(**data)
