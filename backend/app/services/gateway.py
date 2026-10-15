"""GatewayService: orchestrates a chat completion end to end.

This is the "business logic" layer that sits between the HTTP route and the
providers. Its job:

  1. Resolve the public model id via the registry     (-> provider + real model)
  2. Get the right provider adapter from the factory   (polymorphism)
  3. Build our internal LLMRequest
  4. Call provider.generate(...)                        (the ONLY provider call)
  5. Map the internal LLMResponse into the public ChatCompletionResponse

Notice there is NO `if provider == "openai"` anywhere. The service depends only
on the abstract LLMProvider (dependency inversion); which concrete adapter runs
is decided by the factory and used polymorphically.
"""

from collections.abc import Callable

from app.providers.base import LLMProvider, LLMRequest
from app.providers.factory import get_provider
from app.schemas.chat import ChatCompletionRequest, ChatCompletionResponse
from app.schemas.common import Provider
from app.services.model_registry import get_model_config


class GatewayService:
    """Coordinates model resolution, provider selection, and response mapping."""

    def __init__(
        self,
        provider_resolver: Callable[[Provider], LLMProvider] = get_provider,
    ) -> None:
        """`provider_resolver` is injected (defaults to the real factory).

        This is dependency injection: in production it's the real factory; in
        tests we pass a resolver that returns a fake provider, so we can exercise
        the whole flow without any network calls or API keys.
        """
        self._resolve_provider = provider_resolver

    async def complete(
        self, request: ChatCompletionRequest, request_id: str
    ) -> ChatCompletionResponse:
        """Run one chat completion and return the standardized response."""
        # 1. Public id -> provider + provider-specific model (404 if unknown).
        model_config = get_model_config(request.model)

        # 2. Get the adapter for that provider (503 if not available).
        provider = self._resolve_provider(model_config.provider)

        # 3. Build our internal, provider-neutral request.
        llm_request = LLMRequest(
            model=model_config.provider_model,
            messages=request.messages,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )

        # 4. The single, polymorphic provider call. We don't know or care which
        #    concrete class this is.
        llm_response = await provider.generate(llm_request)

        # 5. Normalize the internal response into the public, standardized shape.
        #    A single entry point (from_llm_response) guarantees every provider
        #    yields an identical contract.
        return ChatCompletionResponse.from_llm_response(
            request_id=request_id,
            model=request.model,
            provider=model_config.provider.value,
            provider_model=model_config.provider_model,
            llm_response=llm_response,
        )
