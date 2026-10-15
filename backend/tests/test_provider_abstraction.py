"""Tests for the provider abstraction (Step 5).

These are UNIT tests: they exercise our own code in isolation, with NO network
calls and NO real API keys. We do that by injecting a FAKE provider — a subclass
of LLMProvider — into the GatewayService. This proves two things:

  1. Polymorphism: the gateway calls `provider.generate()` without knowing the
     concrete type. Any LLMProvider subclass works.
  2. Dependency inversion / injection: the gateway depends on the abstraction and
     accepts its provider resolver from outside, so it's testable without I/O.
"""

import pytest

from app.core.config import settings
from app.core.exceptions import ProviderUnavailableError, UnknownModelError
from app.providers.base import LLMProvider, LLMRequest, LLMResponse
from app.providers.factory import get_provider, register_provider, reset_providers
from app.schemas.chat import ChatCompletionRequest, ChatMessage
from app.schemas.common import Provider, Role
from app.services.gateway import GatewayService


class FakeProvider(LLMProvider):
    """A stand-in provider that records what it received and returns canned data.

    This is exactly what real adapters (Gemini, etc.) will be — just without the
    network. Because it subclasses LLMProvider and implements generate(), the
    gateway treats it identically to a real provider.
    """

    name = "fake"

    def __init__(self) -> None:
        self.received: LLMRequest | None = None

    async def generate(self, request: LLMRequest) -> LLMResponse:
        self.received = request
        return LLMResponse(
            content=f"echo: {request.messages[-1].content}",
            input_tokens=11,
            output_tokens=7,
        )


def _sample_request(model: str = "gemini") -> ChatCompletionRequest:
    return ChatCompletionRequest(
        model=model,
        messages=[ChatMessage(role=Role.USER, content="Explain binary search")],
        temperature=0.5,
        max_tokens=100,
    )


async def test_gateway_drives_provider_polymorphically():
    """The gateway resolves the model, calls the (fake) provider, and normalizes
    the response — all without knowing the concrete provider type."""
    fake = FakeProvider()
    # Inject a resolver that always returns our fake, regardless of provider.
    gateway = GatewayService(provider_resolver=lambda provider: fake)

    response = await gateway.complete(_sample_request("gemini"), request_id="req_test")

    # Response is normalized into our standardized shape.
    assert response.id == "req_test"
    assert response.model == "gemini"
    assert response.provider == "google"  # from the model registry
    assert response.content == "echo: Explain binary search"
    # Usage is mapped and total is computed.
    assert response.usage.input_tokens == 11
    assert response.usage.output_tokens == 7
    assert response.usage.total_tokens == 18

    # The gateway passed the PROVIDER-SPECIFIC model name (from the registry),
    # not the public id, down to the adapter. We compare against config rather
    # than a hardcoded string so the test survives model-name changes.
    assert fake.received is not None
    assert fake.received.model == settings.gemini_model
    assert fake.received.model != "gemini"  # not the public id
    assert fake.received.temperature == 0.5
    assert fake.received.max_tokens == 100


async def test_unknown_model_raises_before_touching_a_provider():
    """An unknown public id fails at the registry (404), never reaching a provider."""
    gateway = GatewayService(provider_resolver=lambda provider: FakeProvider())
    with pytest.raises(UnknownModelError):
        await gateway.complete(_sample_request("does-not-exist"), request_id="req_x")


def test_factory_raises_when_provider_not_registered():
    """With nothing registered, the real factory reports the provider unavailable
    (this is the 503 path used until a real provider is added in Step 6)."""
    reset_providers()
    with pytest.raises(ProviderUnavailableError):
        get_provider(Provider.GOOGLE)


def test_factory_returns_registered_provider():
    """Once registered, the factory returns that adapter for the provider."""
    reset_providers()
    fake = FakeProvider()
    register_provider(Provider.GOOGLE, fake)
    assert get_provider(Provider.GOOGLE) is fake
    reset_providers()


def test_abstract_provider_cannot_be_instantiated():
    """LLMProvider is abstract: Python refuses to instantiate it directly,
    enforcing the interface contract."""
    with pytest.raises(TypeError):
        LLMProvider()  # type: ignore[abstract]
