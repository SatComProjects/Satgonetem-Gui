"""Security lab API routes."""

from fastapi import APIRouter, Depends, Response

from .. import schemas
from ..dependencies import get_services
from ..services.container import ApplicationServices

router = APIRouter(tags=["security"])


@router.get(
    "/api/security/preset",
    response_model=schemas.ProjectCreateRequest,
)
async def api_security_preset(
    services: ApplicationServices = Depends(get_services),
) -> dict:
    return services.security.preset()


@router.get("/api/security/range", response_model=schemas.SecurityRangeResponse)
async def api_security_range(
    services: ApplicationServices = Depends(get_services),
) -> schemas.SecurityRangeResponse:
    return schemas.SecurityRangeResponse(**services.security.range())


@router.post("/api/security/links/{key}/fail", response_model=schemas.OperationResponse)
async def api_security_fail_link(
    key: str,
    services: ApplicationServices = Depends(get_services),
) -> schemas.OperationResponse:
    services.security.fail_link(key)
    return schemas.OperationResponse()


@router.post("/api/security/reset", response_model=schemas.OperationResponse)
async def api_security_reset(
    services: ApplicationServices = Depends(get_services),
) -> schemas.OperationResponse:
    await services.security.reset()
    return schemas.OperationResponse()


@router.get(
    "/api/security/captures",
    response_model=list[schemas.SecurityCapture],
)
async def api_security_captures(
    services: ApplicationServices = Depends(get_services),
) -> list[dict]:
    return services.security.list_captures()


@router.post(
    "/api/security/captures",
    response_model=schemas.SecurityCapture,
)
async def api_security_start_capture(
    payload: schemas.CaptureStartRequest,
    services: ApplicationServices = Depends(get_services),
) -> dict:
    return services.security.start_capture(payload)


@router.post(
    "/api/security/captures/{capture_id}/stop",
    response_model=schemas.SecurityCapture,
)
async def api_security_stop_capture(
    capture_id: str,
    services: ApplicationServices = Depends(get_services),
) -> dict:
    return services.security.stop_capture(capture_id)


@router.get(
    "/api/security/captures/{capture_id}",
    responses={
        200: {
            "content": {
                "application/vnd.tcpdump.pcap": {
                    "schema": {"type": "string", "format": "binary"}
                }
            }
        }
    },
)
async def api_security_download_capture(
    capture_id: str,
    services: ApplicationServices = Depends(get_services),
) -> Response:
    payload, filename = services.security.capture_bytes(capture_id)
    return Response(
        content=payload,
        media_type="application/vnd.tcpdump.pcap",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
