"""Tests for standardized response normalization (Step 8).

These verify the single normalization entry point, ChatCompletionResponse
.from_llm_response(...), plus the cross-provider contract: no matter which
adapter produced the internal LLMResponse, the public response has the same
shape, types, and invariants.
"""

from app.providers.base import LLMResponse
from app.providers.gemini import _normalize_finish_reason as gemini_finish
from app.providers.groq import _normalize_finish_reason as groq_finish
from app.schemas.chat import ChatCompletionResponse, Usage


def _normalize(llm: LLMResponse, model="gemini", provider="google", pm="gemini-3.6-flash"):
    return ChatCompletionResponse.from_llm_response(
        request_id="req_norm_test",
        model=model,
        provider=provider,
        provider_model=pm,
        llm_response=llm,
    )


def test_from_llm_response_maps_all_fields():
    llm = LLMResponse(
        content="hello", input_tokens=10, output_tokens=5, finish_reason="stop"
    )
    resp = _normalize(llm)

    assert resp.id == "req_norm_test"
    assert resp.model == "gemini"          # public id
    assert resp.provider == "google"
    assert resp.provider_model == "gemini-3.6-flash"  # concrete model that ran
    assert resp.content == "hello"
    assert resp.finish_reason == "stop"
    assert isinstance(resp.created, int) and resp.created > 0
    assert isinstance(resp.usage, Usage)


def test_usage_total_invariant_always_holds():
    llm = LLMResponse(content="x", input_tokens=120, output_tokens=250)
    resp = _normalize(llm)
    assert resp.usage.input_tokens == 120
    assert resp.usage.output_tokens == 250
    assert resp.usage.total_tokens == 370
    assert resp.usage.total_tokens == resp.usage.input_tokens + resp.usage.output_tokens


def test_cross_provider_shape_is_identical():
    """A Gemini-derived and a Groq-derived response must have the same keys/types."""
    gemini_like = LLMResponse(content="a", input_tokens=3, output_tokens=4, finish_reason="stop")
    groq_like = LLMResponse(content="b", input_tokens=7, output_tokens=8, finish_reason="length")

    r1 = _normalize(gemini_like, model="gemini", provider="google", pm="gemini-3.6-flash")
    r2 = _normalize(groq_like, model="groq", provider="groq", pm="openai/gpt-oss-20b")

    d1, d2 = r1.model_dump(), r2.model_dump()
    # Same set of top-level keys.
    assert d1.keys() == d2.keys()
    # Same nested usage keys.
    assert d1["usage"].keys() == d2["usage"].keys()
    # Same types for every top-level field.
    for key in d1:
        assert type(d1[key]) is type(d2[key]), f"type mismatch on {key}"


def test_finish_reason_defaults_to_none_when_absent():
    llm = LLMResponse(content="x", input_tokens=1, output_tokens=1)  # no finish_reason
    resp = _normalize(llm)
    assert resp.finish_reason is None


def test_backward_compatible_direct_construction_still_works():
    """Older-style construction without the new fields must still validate."""
    resp = ChatCompletionResponse(
        id="req_x", model="gemini", provider="google", content="hi", usage=Usage()
    )
    assert resp.provider_model is None
    assert resp.finish_reason is None
    assert isinstance(resp.created, int)


def test_gemini_finish_reason_mapping():
    assert gemini_finish("STOP") == "stop"
    assert gemini_finish("MAX_TOKENS") == "length"
    assert gemini_finish("SAFETY") == "content_filter"
    assert gemini_finish("RECITATION") == "content_filter"
    assert gemini_finish("SOMETHING_NEW") == "stop"   # unknown -> stop
    assert gemini_finish(None) is None


def test_groq_finish_reason_mapping():
    assert groq_finish("stop") == "stop"
    assert groq_finish("length") == "length"
    assert groq_finish("content_filter") == "content_filter"
    assert groq_finish("tool_calls") == "stop"        # unknown -> stop
    assert groq_finish(None) is None
