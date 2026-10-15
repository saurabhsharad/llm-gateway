"""Google Gemini provider adapter.

This is the first CONCRETE implementation of the LLMProvider interface. It adapts
our standardized LLMRequest to Google's Generative Language REST API and adapts
the raw response back into our standardized LLMResponse.

Everything Gemini-specific is contained here:
  - roles: our "assistant" -> Gemini's "model"; "system" -> `systemInstruction`
  - params: our max_tokens -> Gemini's `generationConfig.maxOutputTokens`
  - endpoint & auth: POST .../models/{model}:generateContent, key in a header
  - response shape: text lives in candidates[].content.parts[].text; token
    counts live in usageMetadata

The gateway knows none of this — it just calls `generate()`.
"""

import logging

import httpx

from app.core.exceptions import ProviderError
from app.providers.base import LLMProvider, LLMRequest, LLMResponse
from app.schemas.common import Role

logger = logging.getLogger("llm_gateway")

# Base URL for Gemini's REST API. The model name and ":generateContent" action
# are appended per request.
_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

# Map Gemini's finishReason vocabulary to our normalized set. Unknown values
# fall back to "stop" so the field is always one of our known tokens.
_FINISH_REASON_MAP = {
    "STOP": "stop",
    "MAX_TOKENS": "length",
    "SAFETY": "content_filter",
    "RECITATION": "content_filter",
    "PROHIBITED_CONTENT": "content_filter",
}


def _normalize_finish_reason(raw: str | None) -> str | None:
    if raw is None:
        return None
    return _FINISH_REASON_MAP.get(raw, "stop")


class GeminiProvider(LLMProvider):
    """Adapter for Google Gemini via its REST API."""

    name = "google"

    def __init__(self, api_key: str, timeout_seconds: float = 30.0) -> None:
        # The key is stored privately and only ever sent in a request header,
        # never logged and never placed in a URL.
        self._api_key = api_key
        self._timeout = timeout_seconds

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """Translate -> call -> translate back."""
        payload = self._build_payload(request)
        url = f"{_GEMINI_BASE_URL}/{request.model}:generateContent"
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self._api_key,  # key in header, not URL
        }

        # --- Call the provider (async, with a timeout) ---
        # The float timeout applies to all httpx phases (connect/read/write/pool),
        # so the gateway never waits indefinitely for the provider.
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                http_response = await client.post(url, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            # Timed out. Log the real cause server-side; return a safe message.
            logger.warning("Gemini request timed out after %ss: %s", self._timeout, exc)
            raise ProviderError("The upstream provider request timed out.") from exc
        except httpx.HTTPError as exc:
            # Other network failure. Log the real cause; return a safe error.
            logger.warning("Gemini request failed: %s", exc)
            raise ProviderError("The upstream provider could not be reached.") from exc

        if http_response.status_code != 200:
            # Log status + body server-side for debugging; never expose to client.
            logger.warning(
                "Gemini returned HTTP %s: %s",
                http_response.status_code,
                http_response.text[:500],
            )
            raise ProviderError("The upstream provider returned an error.")

        return self._parse_response(http_response.json())

    def _build_payload(self, request: LLMRequest) -> dict:
        """Convert our LLMRequest into Gemini's request body."""
        contents: list[dict] = []
        system_texts: list[str] = []

        for message in request.messages:
            if message.role == Role.SYSTEM:
                # Gemini takes system prompts separately, not in the turn list.
                system_texts.append(message.content)
                continue
            # Gemini uses "model" where we use "assistant".
            gemini_role = "model" if message.role == Role.ASSISTANT else "user"
            contents.append({"role": gemini_role, "parts": [{"text": message.content}]})

        payload: dict = {"contents": contents}

        if system_texts:
            payload["systemInstruction"] = {
                "parts": [{"text": "\n".join(system_texts)}]
            }

        # Map our neutral generation params to Gemini's names, only if provided.
        generation_config: dict = {}
        if request.temperature is not None:
            generation_config["temperature"] = request.temperature
        if request.max_tokens is not None:
            generation_config["maxOutputTokens"] = request.max_tokens
        if generation_config:
            payload["generationConfig"] = generation_config

        return payload

    def _parse_response(self, data: dict) -> LLMResponse:
        """Convert Gemini's raw JSON into our standardized LLMResponse."""
        candidates = data.get("candidates", [])
        if not candidates:
            # e.g. the prompt was blocked by safety filters -> no candidates.
            logger.warning("Gemini returned no candidates: %s", data)
            raise ProviderError("The upstream provider returned no content.")

        candidate = candidates[0]
        # Concatenate all text parts of the first candidate.
        parts = candidate.get("content", {}).get("parts", [])
        text = "".join(part.get("text", "") for part in parts)

        # Token usage lives in usageMetadata. This is a "thinking" model, so it may
        # spend tokens reasoning before answering. We derive output tokens from the
        # TOTAL (which includes those thinking tokens) so usage reflects real cost:
        #   output = total - prompt   (falls back to visible-answer tokens).
        usage = data.get("usageMetadata", {})
        prompt_tokens = usage.get("promptTokenCount", 0)
        total_tokens = usage.get("totalTokenCount")
        if total_tokens is not None:
            output_tokens = max(total_tokens - prompt_tokens, 0)
        else:
            output_tokens = usage.get("candidatesTokenCount", 0)

        raw_finish = candidate.get("finishReason")

        if not text:
            # No visible content at all: keep erroring (e.g. a thinking model burned
            # the whole budget reasoning and hit MAX_TOKENS before writing anything).
            logger.warning("Gemini returned empty text (finishReason=%s)", raw_finish)
            raise ProviderError(
                "The provider returned an empty response "
                "(it may have hit the token limit before answering)."
            )

        # There IS content: return it, carrying the normalized stop reason. If it
        # was truncated by the token limit, finish_reason will be "length".
        return LLMResponse(
            content=text,
            input_tokens=prompt_tokens,
            output_tokens=output_tokens,
            finish_reason=_normalize_finish_reason(raw_finish),
        )
