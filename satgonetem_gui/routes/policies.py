"""Security policy API routes."""

from fastapi import APIRouter, Depends

from .. import schemas
from ..dependencies import get_services
from ..services.container import ApplicationServices

router = APIRouter(tags=["security"])


@router.get(
    "/api/security/policies",
    response_model=schemas.PolicyListResponse,
)
async def api_policy_list(
    services: ApplicationServices = Depends(get_services),
) -> schemas.PolicyListResponse:
    return schemas.PolicyListResponse(nodes=services.policy.applied())


@router.post(
    "/api/security/policies/preview",
    response_model=schemas.PolicyPlanResponse,
)
async def api_policy_preview(
    payload: schemas.NodePolicyRequest,
    services: ApplicationServices = Depends(get_services),
) -> schemas.PolicyPlanResponse:
    return schemas.PolicyPlanResponse(**services.policy.preview(payload))


@router.post(
    "/api/security/policies",
    response_model=schemas.PolicyStatusResponse,
)
async def api_policy_apply(
    payload: schemas.NodePolicyRequest,
    services: ApplicationServices = Depends(get_services),
) -> schemas.PolicyStatusResponse:
    return schemas.PolicyStatusResponse(**services.policy.apply(payload))


@router.get(
    "/api/security/policies/{node}",
    response_model=schemas.PolicyStatusResponse,
)
async def api_policy_status(
    node: str,
    services: ApplicationServices = Depends(get_services),
) -> schemas.PolicyStatusResponse:
    return schemas.PolicyStatusResponse(**services.policy.status(node))


@router.post(
    "/api/security/policies/{node}/clear",
    response_model=schemas.OperationResponse,
)
async def api_policy_clear(
    node: str,
    services: ApplicationServices = Depends(get_services),
) -> schemas.OperationResponse:
    services.policy.clear(node)
    return schemas.OperationResponse()
