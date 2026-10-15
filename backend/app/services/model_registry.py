"""Model registry: the single source of truth mapping public model identifiers
to a provider and a provider-specific model name.

Clients call the gateway with a stable public id like "gemini". The registry
translates that into WHICH provider to use and WHAT model string to send it.
Because this mapping lives in exactly one place:
  - adding a model is a one-line change,
  - upgrading the underlying model is a config change,
  - and nothing else in the codebase hardcodes provider/model strings.
"""

from dataclasses import dataclass

from app.core.config import settings
from app.core.exceptions import UnknownModelError
from app.schemas.common import Provider


@dataclass(frozen=True)
class ModelConfig:
    """Everything the gateway needs to know to serve one public model id.

    `frozen=True` makes instances immutable — registry entries can't be mutated
    by accident at runtime.
    """

    public_id: str          # what clients send, e.g. "gemini"
    provider: Provider      # which backend, e.g. Provider.GOOGLE
    provider_model: str     # the provider's own model name, e.g. "gemini-2.0-flash"


def _build_registry() -> dict[str, ModelConfig]:
    """Construct the registry from configuration.

    We build it from `settings` so the actual provider model names come from
    environment variables (with sensible defaults). Public ids are deliberately
    short and provider-neutral.
    """
    entries = [
        ModelConfig("gpt", Provider.OPENAI, settings.openai_model),
        ModelConfig("gemini", Provider.GOOGLE, settings.gemini_model),
        ModelConfig("claude", Provider.ANTHROPIC, settings.anthropic_model),
        ModelConfig("groq", Provider.GROQ, settings.groq_model),
    ]
    return {entry.public_id: entry for entry in entries}


# Module-level registry, built once at import time.
MODEL_REGISTRY: dict[str, ModelConfig] = _build_registry()


def get_model_config(public_id: str) -> ModelConfig:
    """Look up a public model id, or raise UnknownModelError (-> HTTP 404).

    This is the gateway's authoritative check for "do we serve this model?".
    """
    config = MODEL_REGISTRY.get(public_id)
    if config is None:
        known = ", ".join(sorted(MODEL_REGISTRY)) or "(none configured)"
        raise UnknownModelError(
            f"Unknown model '{public_id}'. Available models: {known}."
        )
    return config


def list_models() -> list[ModelConfig]:
    """Return all registered models (used by the GET /v1/models endpoint)."""
    return list(MODEL_REGISTRY.values())
