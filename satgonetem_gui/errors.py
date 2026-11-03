"""Domain/API exceptions and the shared FastAPI error handlers."""

import logging

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .schemas import ErrorResponse

logger = logging.getLogger(__name__)


class APIError(Exception):
    """Expected API failure with a status code and user-facing message."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def _error_response(
    status_code: int,
    message: str,
    details=None,
) -> JSONResponse:
    body = ErrorResponse(error=message, details=details)
    return JSONResponse(
        status_code=status_code,
        content=body.model_dump(exclude_none=True),
    )


def install_error_handlers(app: FastAPI) -> None:
    """Install handlers that return one error envelope for every failure."""

    @app.exception_handler(APIError)
    async def handle_api_error(_request: Request, exc: APIError) -> JSONResponse:
        return _error_response(exc.status_code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return _error_response(
            422,
            "Invalid request.",
            jsonable_encoder(exc.errors()),
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(
        _request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        message = str(exc.detail) if exc.detail else "Request failed."
        return _error_response(exc.status_code, message)

    @app.exception_handler(Exception)
    async def handle_unexpected_error(_request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled API error.", exc_info=exc)
        return _error_response(500, "Internal server error.")
