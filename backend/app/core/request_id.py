"""Request ID: generation, validation, propagation, and response header.

One request == one request ID. The ID is resolved exactly once by
RequestIDMiddleware and stored on `request.state.request_id`. Everything else
(the chat route, usage logging, the response body `id`, error handlers, and the
X-Request-ID response header) reuses that single value, giving one correlation
path from client -> logs -> PostgreSQL.

The request ID is metadata for tracing/debugging only. It is NOT authentication
and must never contain secrets (keys, prompts, emails, etc.).
"""

import re
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

#: Header used both to accept a client-provided ID and to return the ID.
REQUEST_ID_HEADER = "X-Request-ID"

#: Accept a client-provided ID only if it is safe: non-empty, <=128 chars, and
#: limited to URL-safe characters. This prevents header abuse (huge/odd values)
#: while allowing clients to supply their own correlation IDs.
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


def generate_request_id() -> str:
    """Return a fresh server-generated request ID: 'req_' + uuid4 hex."""
    return f"req_{uuid.uuid4().hex}"


def resolve_request_id(raw: str | None) -> str:
    """Use a valid client-provided ID, otherwise generate a server-side one.

    A provided value is trusted only if it passes _SAFE_REQUEST_ID; anything
    missing, empty, too long, or containing unsafe characters is replaced by a
    generated ID.
    """
    if raw is not None:
        candidate = raw.strip()
        if _SAFE_REQUEST_ID.fullmatch(candidate):
            return candidate
    return generate_request_id()


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Resolve the request ID once, expose it, and echo it on the response.

    Runs for every request that reaches the app, so the ID is available to
    dependencies, the route, and (via request.state) the exception handlers.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = resolve_request_id(request.headers.get(REQUEST_ID_HEADER))
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response


def get_request_id(request: Request) -> str:
    """FastAPI dependency returning the request's ID (set by the middleware).

    Falls back to generating one if the middleware somehow didn't run, so the
    route always has a valid ID.
    """
    return getattr(request.state, "request_id", None) or generate_request_id()
