"""Pydantic schemas for the chat completion endpoint.

These classes define the *contract* between the application and the gateway:
  - What a valid request looks like  (ChatCompletionRequest)
  - What we always send back         (ChatCompletionResponse)

FastAPI uses these to validate incoming JSON, to serialize outgoing JSON, and to
generate the interactive docs. Provider-specific field names never appear here —
this is our own neutral interface, independent of OpenAI/Gemini/Anthropic.
"""

import time
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from app.schemas.common import Role

if TYPE_CHECKING:
    # Imported only for type hints to avoid a circular import at runtime:
    # providers/base.py imports ChatMessage from this module.
    from app.providers.base import LLMResponse


class ChatMessage(BaseModel):
    """A single message in the conversation."""

    role: Role
    # `...` marks the field as REQUIRED. min_length=1 rejects empty strings, so
    # a message must actually contain text.
    content: str = Field(..., min_length=1, description="The message text.")


class ChatCompletionRequest(BaseModel):
    """What a client sends to POST /v1/chat/completions.

    Note how generation parameters (temperature, max_tokens) are OPTIONAL and use
    neutral names. Each provider adapter will later translate these into whatever
    that provider actually calls them. The application never sees those details.
    """

    # Public model identifier (e.g. "gemini", "gpt", "claude"). We validate that
    # it's a non-empty string here; whether it's a KNOWN model is checked later
    # by the model registry (Step 4), which can return a proper 404.
    model: str = Field(..., min_length=1, description="Public model identifier.")

    # A conversation must have at least one message.
    messages: list[ChatMessage] = Field(..., min_length=1)

    # --- Optional generation parameters (neutral names) ---
    # temperature controls randomness: 0 = focused/deterministic, higher = more
    # creative/varied. We clamp to a sane 0–2 range.
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)

    # max_tokens caps how long the model's reply can be. A "token" is roughly a
    # word-piece; ~4 characters of English. Must be positive if provided.
    max_tokens: int | None = Field(default=None, gt=0)

    # Reject unknown fields instead of silently ignoring them. This catches typos
    # like "temprature" early and keeps the contract strict.
    model_config = {"extra": "forbid"}


class Usage(BaseModel):
    """Token accounting for a request, normalized across providers.

    input_tokens  = tokens in the prompt we sent
    output_tokens = tokens in the model's reply
    total_tokens  = input + output
    These drive usage logging and (in real systems) billing.
    """

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


class ChatCompletionResponse(BaseModel):
    """The single, standardized response shape the gateway always returns.

    Regardless of which provider handled the request, the client sees this exact
    structure. That's the whole point of a gateway: one interface to many
    providers. Response normalization (internal LLMResponse -> this shape) is
    centralized in `from_llm_response` below.

    Step 8 added `provider_model`, `finish_reason`, and `created` additively —
    older clients that ignore them keep working.
    """

    id: str = Field(..., description="Unique request ID, e.g. 'req_...'.")
    model: str = Field(..., description="Public model identifier that was used.")
    provider: str = Field(..., description="Backing provider, e.g. 'google'.")
    provider_model: str | None = Field(
        default=None,
        description="The concrete provider model that actually ran, e.g. 'gemini-3.6-flash'.",
    )
    content: str = Field(..., description="The assistant's reply text.")
    finish_reason: str | None = Field(
        default=None,
        description="Normalized stop reason: 'stop', 'length', 'content_filter', or null.",
    )
    created: int = Field(
        default_factory=lambda: int(time.time()),
        description="Unix timestamp (seconds) when the gateway produced this response.",
    )
    usage: Usage

    @classmethod
    def from_llm_response(
        cls,
        *,
        request_id: str,
        model: str,
        provider: str,
        provider_model: str,
        llm_response: "LLMResponse",
    ) -> "ChatCompletionResponse":
        """Normalize an internal LLMResponse into the public response shape.

        This is the single, authoritative place where the provider-neutral
        internal result becomes the client-facing DTO. Every provider's output
        flows through here, which is what guarantees a consistent contract no
        matter which adapter produced it.
        """
        return cls(
            id=request_id,
            model=model,
            provider=provider,
            provider_model=provider_model,
            content=llm_response.content,
            finish_reason=llm_response.finish_reason,
            created=int(time.time()),
            usage=Usage(
                input_tokens=llm_response.input_tokens,
                output_tokens=llm_response.output_tokens,
                total_tokens=llm_response.total_tokens,
            ),
        )
