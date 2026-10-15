"""Groq provider adapter.

The second concrete implementation of the LLMProvider interface. It adapts our
standardized LLMRequest to Groq's Chat Completions REST API and adapts the raw
response back into our standardized LLMResponse.

Groq exposes an OpenAI-COMPATIBLE API, which makes the translation simpler than
Gemini's:
  - roles: our system/user/assistant map DIRECTLY (no renaming needed)
  - params: our max_tokens -> "max_tokens", temperature -> "temperature"
  - endpoint & auth: POST {base}/chat/completions, Bearer token in the header
  - response shape: text lives in choices[0].message.content; token counts live
    in usage.{prompt_tokens, completion_tokens, total_tokens}

Everything Groq-specific is contained here. The gateway just calls generate().
"""

import logging

import httpx

from app.core.exceptions import ProviderError
from app.providers.base import LLMProvider, LLMRequest, LLMResponse

logger = logging.getLogger("llm_gateway")

# Groq's OpenAI-compatible base URL. The chat completions path is appended.
_GROQ_BASE_URL = "https://api.groq.com/openai/v1"

# Map Groq's (OpenAI-style) finish_reason vocabulary to our normalized set.
_FINISH_REASON_MAP = {
    "stop": "stop",
    "length": "length",
    "content_filter": "content_filter",
}


def _normalize_finish_reason(raw: str | None) -> str | None:
    if raw is None:
        return None
    # tool_calls/function_call and any others normalize to "stop".
    return _FINISH_REASON_MAP.get(raw, "stop")


class GroqProvider(LLMProvider):
    """Adapter for Groq via its OpenAI-compatible REST API."""

    name = "groq"

    def __init__(self, api_key: str, timeout_seconds: float = 30.0) -> None:
        # The key is stored privately and only ever sent in the Authorization
        # header — never logged, never placed in a URL, never returned to clients.
        self._api_key = api_key
        self._timeout = timeout_seconds

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """Translate -> call -> translate back."""
        payload = self._build_payload(request)
        url = f"{_GROQ_BASE_URL}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",  # key in header only
        }

        # --- Call the provider (async, with a timeout) ---
        # The float timeout applies to all httpx phases (connect/read/write/pool),
        # so the gateway never waits indefinitely for the provider.
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                http_response = await client.post(url, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            # Timed out. Log the cause (no headers/keys); return a safe message.
            logger.warning("Groq request timed out after %ss: %s", self._timeout, exc)
            raise ProviderError("The upstream provider request timed out.") from exc
        except httpx.HTTPError as exc:
            # Other network failure. Log the cause (no headers/keys); return a
            # safe, generic error to the client.
            logger.warning("Groq request failed: %s", exc)
            raise ProviderError("The upstream provider could not be reached.") from exc

        if http_response.status_code != 200:
            # Log status + response body (never request headers) for debugging.
            logger.warning(
                "Groq returned HTTP %s: %s",
                http_response.status_code,
                http_response.text[:500],
            )
            raise ProviderError("The upstream provider returned an error.")

        return self._parse_response(http_response.json())

    def _build_payload(self, request: LLMRequest) -> dict:
        """Convert our LLMRequest into Groq's Chat Completions request body.

        Roles are OpenAI-compatible, so our Role values ("system"/"user"/
        "assistant") pass straight through as strings.
        """
        messages = [
            {"role": message.role.value, "content": message.content}
            for message in request.messages
        ]

        payload: dict = {
            "model": request.model,  # provider-specific model name from registry
            "messages": messages,
        }

        # Only include optional generation params when the client provided them,
        # so we never override provider defaults with nulls.
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens

        return payload

    def _parse_response(self, data: dict) -> LLMResponse:
        """Convert Groq's raw JSON into our standardized LLMResponse."""
        choices = data.get("choices", [])
        if not choices:
            logger.warning("Groq returned no choices: %s", data)
            raise ProviderError("The upstream provider returned no content.")

        message = choices[0].get("message", {})
        text = message.get("content") or ""
        raw_finish = choices[0].get("finish_reason")

        if not text:
            # No visible content: keep erroring (e.g. truncated before any output).
            logger.warning("Groq returned empty content (finish_reason=%s)", raw_finish)
            raise ProviderError(
                "The provider returned an empty response "
                "(it may have hit the token limit before answering)."
            )

        # Groq usage is OpenAI-style. Map it into our neutral token fields, and
        # carry the normalized stop reason ("length" if truncated with content).
        usage = data.get("usage", {})
        return LLMResponse(
            content=text,
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            finish_reason=_normalize_finish_reason(raw_finish),
        )
