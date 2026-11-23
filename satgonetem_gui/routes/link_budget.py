"""Link-budget workbench API routes."""

from fastapi import APIRouter, Depends

from .. import schemas
from ..dependencies import get_services
from ..services.container import ApplicationServices

router = APIRouter(tags=["analysis"], responses=schemas.error_responses(422, 500))

# The RF chain is synchronous and CPU-bound, so this handler stays a plain
# ``def`` and FastAPI runs it in its threadpool.


@router.post(
    "/api/analysis/link-budget",
    response_model=schemas.LinkBudgetResponse,
    tags=["analysis"],
)
def api_link_budget(
    payload: schemas.LinkBudgetRequest,
    services: ApplicationServices = Depends(get_services),
) -> schemas.LinkBudgetResponse:
    return schemas.LinkBudgetResponse(**services.link_budget.calculate(payload))
