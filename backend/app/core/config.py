"""Application configuration.

All configuration lives here and is loaded from environment variables (or a
local .env file during development). This keeps secrets and environment-specific
values OUT of the source code — one of the core design principles of the project.

We use pydantic-settings, which reads env vars, validates their types, and gives
us a single typed `settings` object to import anywhere in the app.
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed application settings, populated from the environment."""

    # --- General app metadata ---
    app_name: str = "LLM Gateway"
    app_version: str = "0.1.0"
    environment: str = "development"

    # --- CORS ---
    # Which frontend origins are allowed to call this API from a browser.
    # Vite's dev server defaults to port 5173.
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # --- Provider API keys ---
    # Loaded from the environment / .env. Optional: the app starts even if a key
    # is missing — that provider simply won't be registered, and requests for it
    # return 503 (PROVIDER_UNAVAILABLE). NEVER hardcode real keys here.
    gemini_api_key: str | None = None
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    groq_api_key: str | None = None

    # --- Database ---
    # SQLAlchemy connection URL, e.g.
    #   postgresql+psycopg://user:password@localhost:5432/gateway
    # Loaded from the environment; credentials never live in code. Optional at
    # import time so the app/tests can import without a live database — code that
    # actually needs a connection validates it lazily.
    database_url: str | None = None

    # --- Gateway (client) authentication ---
    # Comma-separated list of CLIENT API keys that may call our protected
    # endpoints (e.g. "gw_dev_abc,gw_dev_xyz"). These authenticate clients TO US
    # and are entirely separate from the provider keys above. Loaded from the
    # environment; the auth layer stores only their SHA-256 hashes, never the raw
    # values. If empty, protected endpoints reject every request (fail closed).
    gateway_api_keys: str = ""

    # --- Networking ---
    # How long (seconds) to wait for an upstream LLM provider before giving up.
    # Prevents a slow or hung provider from hanging the gateway forever. One
    # common timeout is used for all providers in V1. Must be > 0 — a zero or
    # negative value is rejected at startup. Override via LLM_TIMEOUT_SECONDS.
    llm_timeout_seconds: float = Field(default=30.0, gt=0)

    # --- Provider model names ---
    # The actual provider-specific model each public identifier maps to. These
    # are defaults; any of them can be overridden via environment variables
    # (e.g. GEMINI_MODEL=gemini-2.5-flash) without touching code. The model
    # registry reads these values.
    openai_model: str = "gpt-4o-mini"
    # Google's current flash-LITE model (alias that tracks the latest). Chosen for
    # low, predictable latency: unlike the full "thinking" flash models
    # (e.g. gemini-3.6-flash), it does minimal/no reasoning, so simple prompts
    # return in ~1-2s instead of 15-60s (which was tripping the request timeout).
    # Override via GEMINI_MODEL.
    gemini_model: str = "gemini-flash-lite-latest"
    anthropic_model: str = "claude-3-5-haiku-latest"
    # Groq serves open-weight models via an OpenAI-compatible API. This default
    # was verified against Groq's live model list. Override via GROQ_MODEL.
    groq_model: str = "openai/gpt-oss-20b"

    # pydantic-settings config: read a .env file if present, ignore unknown keys.
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance.

    Using lru_cache means the .env file and environment are read only once, and
    every caller shares the same Settings object. This is also the seam we'll
    use for dependency injection and for overriding settings in tests.
    """
    return Settings()


# Convenience singleton for simple imports: `from app.core.config import settings`
settings = get_settings()
