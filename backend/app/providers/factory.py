"""Provider factory: the one place that maps a Provider enum to a live adapter.

This is the ONLY module allowed to know about concrete providers. Everything else
(the gateway, the endpoint) works with the abstract LLMProvider, so no business
logic ever branches on which provider is in use.

Providers register themselves here at startup (Step 6), typically only if their
API key is configured. If a model's provider was never registered, get_provider
raises ProviderUnavailableError (-> HTTP 503). That's how "the app starts even if
a provider key is missing, as long as that provider isn't requested" works.
"""

from app.core.exceptions import ProviderUnavailableError
from app.providers.base import LLMProvider
from app.schemas.common import Provider

# Maps each configured provider to its single, ready-to-use adapter instance.
_registry: dict[Provider, LLMProvider] = {}


def register_provider(provider: Provider, adapter: LLMProvider) -> None:
    """Register a concrete adapter for a provider. Called at startup."""
    _registry[provider] = adapter


def get_provider(provider: Provider) -> LLMProvider:
    """Return the adapter for a provider, or raise if it isn't available."""
    adapter = _registry.get(provider)
    if adapter is None:
        raise ProviderUnavailableError(
            f"Provider '{provider.value}' is not available. "
            "It may not be configured (missing API key)."
        )
    return adapter


def available_providers() -> list[Provider]:
    """List which providers are currently registered/available."""
    return list(_registry)


def reset_providers() -> None:
    """Clear the registry. Used by tests to isolate state."""
    _registry.clear()
