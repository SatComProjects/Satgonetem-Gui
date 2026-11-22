"""Server-side experiment run and artifact API routes."""

from fastapi import APIRouter, Depends

from .. import schemas
from ..dependencies import get_services
from ..services.container import ApplicationServices

router = APIRouter(
    tags=["experiments"],
    responses=schemas.error_responses(404, 409, 422, 429, 500),
)

# Blocking work (scenario validation and worker startup) is declared with
# ``def`` so FastAPI runs it in its threadpool; the run itself is a daemon
# thread polled through the status route.


@router.post("/api/experiments", response_model=schemas.ExperimentStartResponse)
def api_experiment_start(
    payload: schemas.ExperimentStartRequest,
    services: ApplicationServices = Depends(get_services),
) -> schemas.ExperimentStartResponse:
    run_id = services.experiments.start(payload)
    return schemas.ExperimentStartResponse(run_id=run_id)


@router.get("/api/experiments", response_model=schemas.ExperimentRunListResponse)
def api_experiment_list(
    services: ApplicationServices = Depends(get_services),
) -> schemas.ExperimentRunListResponse:
    return schemas.ExperimentRunListResponse(**services.experiments.list_runs())


@router.get(
    "/api/experiments/{run_id}",
    response_model=schemas.ExperimentRunSummary,
)
def api_experiment_status(
    run_id: str,
    services: ApplicationServices = Depends(get_services),
) -> schemas.ExperimentRunSummary:
    return schemas.ExperimentRunSummary(**services.experiments.status(run_id))


@router.get(
    "/api/experiments/{run_id}/artifacts/{name}",
    response_model=schemas.ExperimentArtifactResponse,
)
def api_experiment_artifact(
    run_id: str,
    name: str,
    services: ApplicationServices = Depends(get_services),
) -> schemas.ExperimentArtifactResponse:
    return schemas.ExperimentArtifactResponse(**services.experiments.artifact(run_id, name))
