"""Chat completion endpoint: POST /v1/chat/completions.

The route is the composition boundary: it has the authenticated identity, a DB
session, the request, and the final response/error — so it's the natural place
for the cross-cutting concern of usage logging (Step 11), without pushing DB or
auth into GatewayService or the provider adapters.

Flow:
  1. authenticate (Depends(require_api_key)) -> ClientIdentity
  2. generate a request id
  3. time the gateway call with a MONOTONIC clock
  4. on success: return the standardized response and log usage metadata
     on error:   log the error metadata and re-raise (client behavior unchanged)

Logging is failure-safe: a DB logging failure never alters the API result.
"""

import time

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.api_key import ClientIdentity, require_api_key
from app.core.exceptions import GatewayError
from app.core.request_id import get_request_id
from app.db.database import get_db
from app.schemas.chat import ChatCompletionRequest, ChatCompletionResponse
from app.services import usage
from app.services.gateway import GatewayService

router = APIRouter(prefix="/v1/chat", tags=["chat"])


def get_gateway_service() -> GatewayService:
    """FastAPI dependency that provides a GatewayService.

    Using Depends(...) here means the route asks for a service rather than
    constructing one itself. In tests we can override this dependency to inject a
    gateway wired with fake providers — no network calls needed.
    """
    return GatewayService()


@router.post("/completions", response_model=ChatCompletionResponse)
async def create_chat_completion(
    request: ChatCompletionRequest,
    identity: ClientIdentity = Depends(require_api_key),
    db: Session = Depends(get_db),
    gateway: GatewayService = Depends(get_gateway_service),
    request_id: str = Depends(get_request_id),
) -> ChatCompletionResponse:
    """Handle a chat completion request.

    `request` is already validated (422 otherwise) and the caller is already
    authenticated (401 otherwise) before this body runs — so only successes and
    post-authentication errors reach the logging calls here.

    `request_id` is the single ID resolved by RequestIDMiddleware; the same value
    is stored in the DB, echoed in the response body `id`, and returned in the
    X-Request-ID header, giving one correlation path.
    """
    start = time.monotonic()  # monotonic: correct for elapsed time, immune to clock jumps

    try:
        response = await gateway.complete(request, request_id)
    except GatewayError as exc:
        # Known gateway/provider error (404/502/503, etc.). Log metadata, then
        # re-raise so the global handler returns the correct client response.
        latency_ms = int((time.monotonic() - start) * 1000)
        usage.log_error(
            db,
            request_id=request_id,
            identity=identity,
            model=request.model,
            error_code=exc.error_code,
            latency_ms=latency_ms,
        )
        raise
    except Exception:
        # Unexpected error -> 500 via the global handler. Log with a normalized code.
        latency_ms = int((time.monotonic() - start) * 1000)
        usage.log_error(
            db,
            request_id=request_id,
            identity=identity,
            model=request.model,
            error_code="INTERNAL_ERROR",
            latency_ms=latency_ms,
        )
        raise

    latency_ms = int((time.monotonic() - start) * 1000)
    usage.log_success(
        db,
        request_id=request_id,
        identity=identity,
        response=response,
        latency_ms=latency_ms,
    )
    return response
