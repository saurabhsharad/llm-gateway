"""Centralized exception handlers — the single place that turns errors into HTTP.

Design (Step 13):
  - Business code RAISES typed exceptions (GatewayError subclasses); it never
    builds HTTP responses. These handlers decide status code + serialization.
  - Every error response uses ONE consistent envelope:
        {"error": {"code": "<STABLE_CODE>", "message": "<safe message>"}}
  - Known errors (GatewayError) map to their intended status + stable code.
  - Validation errors (422) are normalized into the same envelope, with the
    offending fields described but the raw input value stripped (so we never
    echo prompt content back).
  - Unknown errors are logged server-side and returned as a generic 500 — no
    tracebacks, SQL, secrets, or internal details reach the client.
  - The Step 12 request ID is attached to every error response via X-Request-ID,
    reusing request.state.request_id (never generating a new one).
"""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.exceptions import GatewayError
from app.core.request_id import REQUEST_ID_HEADER

logger = logging.getLogger("llm_gateway")


def _request_id_header(request: Request) -> dict[str, str]:
    """Return the X-Request-ID header from request.state, if present.

    Set explicitly because the unhandled-exception (500) path runs in Starlette's
    outermost middleware, outside RequestIDMiddleware.
    """
    request_id = getattr(request.state, "request_id", None)
    return {REQUEST_ID_HEADER: request_id} if request_id else {}


def _error_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    details: list | None = None,
) -> JSONResponse:
    """Build the standard error envelope with the request-ID header."""
    error: dict = {"code": code, "message": message}
    if details is not None:
        error["details"] = details
    return JSONResponse(
        status_code=status_code,
        content={"error": error},
        headers=_request_id_header(request),
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register all exception handlers on the app."""

    @app.exception_handler(GatewayError)
    async def handle_gateway_error(request: Request, exc: GatewayError) -> JSONResponse:
        """Known, client-safe error: use its intended status + stable code."""
        return _error_response(
            request,
            status_code=exc.status_code,
            code=exc.error_code,
            message=exc.message,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """Normalize FastAPI/Pydantic 422 into our envelope.

        We report which fields failed (type/location/message) but deliberately
        DROP the 'input' value Pydantic includes, so request content (e.g. the
        prompt) is never echoed back in the error response.
        """
        details = [
            {"type": e.get("type"), "loc": list(e.get("loc", [])), "msg": e.get("msg")}
            for e in exc.errors()
        ]
        return _error_response(
            request,
            status_code=422,
            code="VALIDATION_ERROR",
            message="Request validation failed.",
            details=details,
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        """Unknown error: log the real cause server-side, return a generic 500."""
        logger.exception(
            "Unhandled error on %s %s", request.method, request.url.path
        )
        return _error_response(
            request,
            status_code=500,
            code="INTERNAL_ERROR",
            message="An internal error occurred.",
        )
