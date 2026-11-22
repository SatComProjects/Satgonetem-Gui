"""Coverage analytics API routes."""

from fastapi import APIRouter, Depends

from .. import schemas
from ..dependencies import get_services
from ..services.container import ApplicationServices

router = APIRouter(tags=["analysis"])

# The coverage computation is synchronous and CPU-bound, so this handler stays
# a plain ``def`` and FastAPI runs it in its threadpool.


@router.post(
    "/api/analysis/coverage",
    response_model=schemas.CoverageResponse,
    responses=schemas.error_responses(404, 422, 500),
)
def api_coverage(
    payload: schemas.CoverageRequest,
    services: ApplicationServices = Depends(get_services),
) -> schemas.CoverageResponse:
    return schemas.CoverageResponse(**services.coverage.analyze(payload))
