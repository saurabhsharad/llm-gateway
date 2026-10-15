"""The provider abstraction: the common interface every LLM provider implements.

This is the architectural heart of the gateway. We define:

  - LLMRequest / LLMResponse: our OWN internal, provider-neutral request and
    response types. Providers translate to/from these. The rest of the app never
    sees a provider's native format.

  - LLMProvider: an Abstract Base Class (ABC) declaring the single method every
    provider must implement, `generate()`. Concrete adapters (Gemini, OpenAI,
    Anthropic) subclass this and fill in the provider-specific details.

Because the gateway depends only on LLMProvider (the abstraction) and calls
`generate()` polymorphically, it never contains `if provider == "openai": ...`.
Adding a provider means adding a subclass — no changes to the gateway.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.schemas.chat import ChatMessage


@dataclass
class LLMRequest:
    """Standardized, internal request handed to a provider adapter.

    Note `model` here is the PROVIDER-SPECIFIC model name (e.g. "gemini-2.0-flash"),
    already resolved by the model registry — not the public id ("gemini"). The
    adapter just uses it directly. Messages reuse our neutral ChatMessage type;
    generation params use neutral names the adapter maps to provider dialects.
    """

    model: str
    messages: list[ChatMessage]
    temperature: float | None = None
    max_tokens: int | None = None


@dataclass
class LLMResponse:
    """Standardized, internal response returned by every provider adapter.

    Whatever shape the provider's raw response has, the adapter converts it into
    exactly this. Token counts default to 0 for providers that don't report them.
    """

    content: str
    input_tokens: int = 0
    output_tokens: int = 0
    # Normalized reason generation stopped, set by each adapter from the provider's
    # own vocabulary: "stop" (natural end), "length" (hit token limit),
    # "content_filter" (blocked), or None if the provider didn't report one.
    # Additive/optional so existing construction stays valid.
    finish_reason: str | None = None

    @property
    def total_tokens(self) -> int:
        """Convenience: total = input + output, computed rather than stored."""
        return self.input_tokens + self.output_tokens


class LLMProvider(ABC):
    """Abstract interface all providers implement.

    Subclassing ABC + marking `generate` as @abstractmethod means Python will
    REFUSE to instantiate any subclass that doesn't implement generate(). The
    contract is enforced by the language, not just by convention.
    """

    #: Human-readable provider name, set by each subclass (e.g. "google").
    name: str = "base"

    @abstractmethod
    async def generate(self, request: LLMRequest) -> LLMResponse:
        """Take a standardized request, call the provider, return a standardized
        response.

        Every adapter's implementation follows the same three-step shape:
          1. translate LLMRequest -> the provider's native request format
          2. call the provider's API (async, over the network)
          3. translate the provider's native response -> LLMResponse
        """
        raise NotImplementedError
