"""FastAPI application entrypoint.

This module builds and configures the FastAPI `app`:
  - creates the application with metadata (title, version)
  - enables CORS so the browser frontend can call us
  - adds request-ID handling (Step 12)
  - registers routers
  - registers centralized exception handlers (Step 13)

We keep this file thin on purpose. It wires components together but contains no
business logic — that lives in services, providers, route modules, and (for
error serialization) app/core/error_handlers.py.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import chat, health, models
from app.core.config import settings
from app.core.error_handlers import register_exception_handlers
from app.core.request_id import RequestIDMiddleware
from app.providers.bootstrap import configure_providers


def create_app() -> FastAPI:
    """Application factory.

    Building the app inside a function (rather than at import time) makes it easy
    to create fresh, independently-configured instances in tests.
    """
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
    )

    # CORS: allow the browser frontend's origin to call this API.
    # expose_headers lets the browser JS READ our X-Request-ID response header
    # (needed to show the request ID on error responses, where it isn't in the
    # body). Not a wildcard — only this one header is exposed.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    # Resolve one request ID per request and echo it as X-Request-ID. Added after
    # CORS so it wraps the app and sees the final response.
    app.add_middleware(RequestIDMiddleware)

    # Register the provider adapters that have API keys configured.
    configure_providers()

    # Register routers. /health and /v1/models are public; /v1/chat/completions
    # is protected via a per-route dependency declared in chat.py.
    app.include_router(health.router)
    app.include_router(chat.router)
    app.include_router(models.router)

    # Centralized error handling: one place turns exceptions into the standard
    # JSON error envelope (+ X-Request-ID), for known, validation, and unexpected
    # errors alike.
    register_exception_handlers(app)

    return app


# The ASGI app object that uvicorn runs: `uvicorn app.main:app`
app = create_app()
