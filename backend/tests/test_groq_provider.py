"""Unit tests for GroqProvider (Step 7).

These tests use a MOCKED httpx client — no real Groq API calls, no real API key.
We assert on request translation (endpoint, auth header, body), response parsing,
token normalization, and error handling. The key used here is a dummy string.
"""

import httpx
import pytest

from app.core.exceptions import ProviderError
from app.providers.base import LLMRequest, LLMResponse
from app.providers.groq import GroqProvider
from app.schemas.chat import ChatMessage
from app.schemas.common import Provider, Role
from app.services.gateway import GatewayService

DUMMY_KEY = "test-groq-key-not-real"


class _FakeResponse:
    """Minimal stand-in for httpx.Response."""

    def __init__(self, status_code: int, json_data: dict | None = None, text: str = ""):
        self.status_code = status_code
        self._json = json_data or {}
        self.text = text

    def json(self) -> dict:
        return self._json


def _install_fake_httpx(monkeypatch, *, response=None, exc=None) -> dict:
    """Patch httpx.AsyncClient inside the groq module.

    Returns a `captured` dict that records the url/json/headers the adapter sent,
    so tests can assert on exactly what would go over the wire.
    """
    captured: dict = {}

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            captured["client_kwargs"] = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, json=None, headers=None):
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers
            if exc is not None:
                raise exc
            return response

    monkeypatch.setattr("app.providers.groq.httpx.AsyncClient", _FakeAsyncClient)
    return captured


def _ok_response() -> _FakeResponse:
    """A realistic Groq (OpenAI-compatible) success payload."""
    return _FakeResponse(
        200,
        {
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "Binary search halves the range."},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20},
        },
    )


def _sample_llm_request(model: str = "openai/gpt-oss-20b") -> LLMRequest:
    return LLMRequest(
        model=model,
        messages=[
            ChatMessage(role=Role.SYSTEM, content="Be concise."),
            ChatMessage(role=Role.USER, content="What is binary search?"),
        ],
        temperature=0.4,
        max_tokens=200,
    )


async def test_request_translation_endpoint_auth_and_body(monkeypatch):
    """Verifies endpoint URL, Authorization header, and translated request body."""
    captured = _install_fake_httpx(monkeypatch, response=_ok_response())
    provider = GroqProvider(api_key=DUMMY_KEY, timeout_seconds=15.0)

    await provider.generate(_sample_llm_request("openai/gpt-oss-20b"))

    # Correct Groq endpoint.
    assert captured["url"] == "https://api.groq.com/openai/v1/chat/completions"

    # Correct Authorization header (Bearer + the key we passed in — a dummy).
    assert captured["headers"]["Authorization"] == f"Bearer {DUMMY_KEY}"
    assert captured["headers"]["Content-Type"] == "application/json"

    # Correct request body: model, mapped messages, and generation params.
    body = captured["json"]
    assert body["model"] == "openai/gpt-oss-20b"
    assert body["messages"] == [
        {"role": "system", "content": "Be concise."},
        {"role": "user", "content": "What is binary search?"},
    ]
    assert body["temperature"] == 0.4
    assert body["max_tokens"] == 200

    # The timeout was passed to the client.
    assert captured["client_kwargs"].get("timeout") == 15.0


async def test_optional_params_omitted_when_not_provided(monkeypatch):
    """temperature/max_tokens must not appear in the body when the client omits them."""
    captured = _install_fake_httpx(monkeypatch, response=_ok_response())
    provider = GroqProvider(api_key=DUMMY_KEY)

    request = LLMRequest(
        model="openai/gpt-oss-20b",
        messages=[ChatMessage(role=Role.USER, content="hi")],
    )
    await provider.generate(request)

    body = captured["json"]
    assert "temperature" not in body
    assert "max_tokens" not in body


async def test_response_parsing_and_token_normalization(monkeypatch):
    """Content extraction + input/output/total token normalization."""
    _install_fake_httpx(monkeypatch, response=_ok_response())
    provider = GroqProvider(api_key=DUMMY_KEY)

    result = await provider.generate(_sample_llm_request())

    assert isinstance(result, LLMResponse)
    assert result.content == "Binary search halves the range."
    assert result.input_tokens == 12
    assert result.output_tokens == 8
    assert result.total_tokens == 20  # computed property == prompt + completion


async def test_non_200_raises_provider_error_without_leaking(monkeypatch):
    """An upstream error becomes a generic ProviderError; body isn't leaked."""
    err_body = '{"error":{"message":"invalid_api_key secret-should-not-leak"}}'
    _install_fake_httpx(monkeypatch, response=_FakeResponse(401, text=err_body))
    provider = GroqProvider(api_key=DUMMY_KEY)

    with pytest.raises(ProviderError) as exc_info:
        await provider.generate(_sample_llm_request())

    # The client-facing message is generic and contains no provider internals.
    assert "secret-should-not-leak" not in str(exc_info.value)


async def test_network_error_raises_provider_error(monkeypatch):
    """A network/timeout failure maps to ProviderError."""
    _install_fake_httpx(monkeypatch, exc=httpx.ConnectTimeout("timed out"))
    provider = GroqProvider(api_key=DUMMY_KEY)

    with pytest.raises(ProviderError):
        await provider.generate(_sample_llm_request())


async def test_empty_content_raises_provider_error(monkeypatch):
    """Empty assistant content (e.g. truncated) is treated as a provider error."""
    empty = _FakeResponse(
        200,
        {
            "choices": [{"message": {"content": ""}, "finish_reason": "length"}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 0, "total_tokens": 5},
        },
    )
    _install_fake_httpx(monkeypatch, response=empty)
    provider = GroqProvider(api_key=DUMMY_KEY)

    with pytest.raises(ProviderError):
        await provider.generate(_sample_llm_request())


async def test_partial_content_with_length_returns_not_errors(monkeypatch):
    """When there IS visible content but generation stopped at the token limit,
    the adapter returns the content with finish_reason='length' (no error)."""
    truncated = _FakeResponse(
        200,
        {
            "choices": [
                {"message": {"content": "Binary search hal"}, "finish_reason": "length"}
            ],
            "usage": {"prompt_tokens": 6, "completion_tokens": 4, "total_tokens": 10},
        },
    )
    _install_fake_httpx(monkeypatch, response=truncated)
    provider = GroqProvider(api_key=DUMMY_KEY)

    result = await provider.generate(_sample_llm_request())
    assert result.content == "Binary search hal"
    assert result.finish_reason == "length"


async def test_gateway_routes_groq_through_abstraction(monkeypatch):
    """Gateway integration: 'groq' resolves to Provider.GROQ and the gateway drives
    a (fake) Groq adapter polymorphically — no provider branching involved."""
    from app.core.config import settings

    class _FakeGroq(GroqProvider):
        def __init__(self):
            super().__init__(api_key=DUMMY_KEY)
            self.received = None

        async def generate(self, request):
            self.received = request
            return LLMResponse(content="ok", input_tokens=3, output_tokens=2)

    fake = _FakeGroq()
    gateway = GatewayService(provider_resolver=lambda provider: fake)

    from app.schemas.chat import ChatCompletionRequest

    response = await gateway.complete(
        ChatCompletionRequest(
            model="groq",
            messages=[ChatMessage(role=Role.USER, content="hi")],
        ),
        request_id="req_groq_test",
    )

    assert response.provider == Provider.GROQ.value  # "groq"
    assert response.model == "groq"
    assert response.content == "ok"
    assert response.usage.total_tokens == 5
    # The gateway passed the provider-specific model (from the registry/config).
    assert fake.received.model == settings.groq_model
