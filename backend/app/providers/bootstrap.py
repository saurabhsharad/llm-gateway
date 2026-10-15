"""Provider bootstrap: build and register the adapters that are configured.

Called once at application startup. For each provider, we register an adapter
ONLY if its API key is present. This is what lets the gateway start even when
some provider keys are missing — requests for an unconfigured provider simply get
a 503 (PROVIDER_UNAVAILABLE) instead of crashing the app.

This is the only place, besides the factory, that references concrete providers.
"""

import logging

from app.core.config import settings
from app.providers.factory import register_provider
from app.providers.gemini import GeminiProvider
from app.providers.groq import GroqProvider
from app.schemas.common import Provider

logger = logging.getLogger("llm_gateway")


def configure_providers() -> None:
    """Register an adapter for every provider that has an API key configured."""
    if settings.gemini_api_key:
        register_provider(
            Provider.GOOGLE,
            GeminiProvider(
                api_key=settings.gemini_api_key,
                timeout_seconds=settings.llm_timeout_seconds,
            ),
        )
        logger.info("Registered provider: google (Gemini)")

    if settings.groq_api_key:
        register_provider(
            Provider.GROQ,
            GroqProvider(
                api_key=settings.groq_api_key,
                timeout_seconds=settings.llm_timeout_seconds,
            ),
        )
        logger.info("Registered provider: groq")

    # OpenAI and Anthropic adapters can be added later in the same pattern. Their
    # keys are already read in config; once their adapters exist, register here.

    if not (settings.gemini_api_key or settings.groq_api_key):
        logger.warning("No provider API keys configured; chat requests will 503.")
