"""Application error types.

Instead of returning ad-hoc error dictionaries from deep inside the code, we
RAISE typed exceptions. A single exception handler (registered in main.py) turns
any GatewayError into a consistent JSON error response with the right HTTP status
code. This keeps error formatting in one place and error *meaning* at the call
site.

Each error carries:
  - status_code: the HTTP status to return
  - error_code:  a stable, machine-readable string (e.g. "UNKNOWN_MODEL")
  - message:     a human-readable, client-safe description

These describe the error; the centralized handlers in app/core/error_handlers.py
decide how to serialize them into an HTTP response (status + JSON envelope +
X-Request-ID). Business code raises these and never builds responses itself.
"""


class GatewayError(Exception):
    """Base class for all expected, client-facing gateway errors."""

    status_code: int = 500
    error_code: str = "INTERNAL_ERROR"

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class AuthenticationError(GatewayError):
    """Raised when a client's gateway API key is missing, malformed, or invalid.

    This is about identity ("who are you?"), so it maps to HTTP 401. It is NOT
    403 (Forbidden), which would mean "we know who you are, but you may not do
    this" — that's authorization/RBAC, out of scope for Step 9.
    """

    status_code = 401
    error_code = "UNAUTHORIZED"


class UnknownModelError(GatewayError):
    """Raised when a request asks for a model the registry doesn't know.

    The request itself was valid (well-formed JSON, correct types) — the client
    just asked for something we don't serve — so this is a 404, not a 422.
    """

    status_code = 404
    error_code = "UNKNOWN_MODEL"


class ProviderUnavailableError(GatewayError):
    """Raised when the provider that should serve a model isn't available.

    Typically this means the provider hasn't been configured (e.g. its API key is
    missing, so no adapter was registered). The model is valid and the request is
    valid — we just can't fulfil it right now — which maps to HTTP 503.
    """

    status_code = 503
    error_code = "PROVIDER_UNAVAILABLE"


class ProviderError(GatewayError):
    """Raised when an upstream provider call fails (bad status, network error,
    timeout, or an unparseable/empty response).

    From the client's perspective the gateway itself is fine, but the thing it
    depends on (the LLM provider) failed — that's HTTP 502 (Bad Gateway). We
    NEVER leak the provider's raw error, keys, or internals to the client; the
    real cause is logged server-side. Step 14 splits timeouts into their own type.
    """

    status_code = 502
    error_code = "PROVIDER_ERROR"
