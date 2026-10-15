"""Usage/request logging service (Step 11).

Records per-request METADATA into the `requests` table. It consumes already-
normalized data (from ChatCompletionResponse / ClientIdentity) and never parses
provider payloads, never touches provider adapters, and is never called from
inside GatewayService — it lives at the HTTP route boundary.

Privacy: only metadata is stored — no prompts, no responses, no raw/hashed keys
here (we store the api_key_id foreign key, not any key material).

Failure-safety: logging must NEVER change the user-facing result. Every write is
wrapped so a database failure is rolled back and downgraded to a server-side
warning; the original response/error the client receives is untouched.
"""

import logging

from sqlalchemy.orm import Session

from app.auth.api_key import ClientIdentity
from app.db.repositories import create_request_log
from app.schemas.chat import ChatCompletionResponse

logger = logging.getLogger("llm_gateway")

STATUS_SUCCESS = "success"
STATUS_ERROR = "error"


def log_success(
    db: Session,
    *,
    request_id: str,
    identity: ClientIdentity,
    response: ChatCompletionResponse,
    latency_ms: int,
) -> None:
    """Log a successful request using normalized response data. Failure-safe."""
    _safe_log(
        db,
        request_id=request_id,
        user_id=int(identity.id),
        api_key_id=identity.api_key_id,
        model=response.model,
        provider=response.provider,
        provider_model=response.provider_model,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        total_tokens=response.usage.total_tokens,
        latency_ms=latency_ms,
        status=STATUS_SUCCESS,
        error_code=None,
    )


def log_error(
    db: Session,
    *,
    request_id: str,
    identity: ClientIdentity,
    model: str,
    error_code: str,
    latency_ms: int,
    provider: str | None = None,
    provider_model: str | None = None,
) -> None:
    """Log a failed (post-authentication) request. Failure-safe.

    provider/provider_model may be None when the failure occurred before the
    model was resolved (e.g. UnknownModelError). Token fields are None on errors.
    """
    _safe_log(
        db,
        request_id=request_id,
        user_id=int(identity.id),
        api_key_id=identity.api_key_id,
        model=model,
        provider=provider,
        provider_model=provider_model,
        input_tokens=None,
        output_tokens=None,
        total_tokens=None,
        latency_ms=latency_ms,
        status=STATUS_ERROR,
        error_code=error_code,
    )


def _safe_log(db: Session, **fields) -> None:
    """Persist a request-log row, swallowing any error.

    A logging/database failure is rolled back and logged as a warning. It never
    propagates, so it cannot replace or alter the original API response.
    """
    try:
        create_request_log(db, **fields)
    except Exception:  # noqa: BLE001 - logging must never break the request
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
        logger.warning(
            "Failed to persist usage log for request_id=%s (status=%s)",
            fields.get("request_id"),
            fields.get("status"),
            exc_info=True,
        )
