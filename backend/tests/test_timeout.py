"""Tests for provider timeouts (Step 14).

Deterministic and offline: httpx is mocked to raise timeout exceptions — no real
network calls, no 30-second waits. Verifies configuration validation, that both
providers translate timeouts into ProviderError, the end-to-end 502 + logging +
X-Request-ID behavior, no secret leakage, and no retries.
"""

from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select

from app.auth.api_key import hash_api_key
from app.core.config import Settings
from app.core.exceptions import ProviderError
from app.core.request_id import REQUEST_ID_HEADER
from app.db.database import get_db
from app.db.models import ApiKey, Request, User
from app.main import create_app
from app.providers.base import LLMRequest
from app.providers.gemini import GeminiProvider
from app.providers.groq import GroqProvider
from app.schemas.chat import ChatMessage
from app.schemas.common import Role

RAW_KEY = "gw_timeout_test_key"
CHAT_URL = "/v1/chat/completions"


# --- A. Configuration ------------------------------------------------------

def test_default_timeout_is_positive():
    assert Settings(_env_file=None).llm_timeout_seconds == 30.0


def test_env_override_works(monkeypatch):
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "45")
    assert Settings(_env_file=None).llm_timeout_seconds == 45.0


def test_zero_timeout_rejected():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, llm_timeout_seconds=0)


def test_negative_timeout_rejected():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, llm_timeout_seconds=-3)


# --- Fake httpx that times out (and counts calls, to prove no retries) -----

def _install_timeout_client(monkeypatch, module_path: str) -> dict:
    counter = {"calls": 0}

    class _FakeAsyncClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            counter["calls"] += 1
            raise httpx.ReadTimeout("timed out")  # subclass of TimeoutException

    monkeypatch.setattr(f"{module_path}.httpx.AsyncClient", _FakeAsyncClient)
    return counter


def _llm_request(model: str) -> LLMRequest:
    return LLMRequest(model=model, messages=[ChatMessage(role=Role.USER, content="hi")])


# --- B. Gemini timeout -> ProviderError ------------------------------------

async def test_gemini_timeout_raises_provider_error(monkeypatch):
    counter = _install_timeout_client(monkeypatch, "app.providers.gemini")
    provider = GeminiProvider(api_key="dummy", timeout_seconds=1.0)
    with pytest.raises(ProviderError) as exc:
        await provider.generate(_llm_request("gemini-3.6-flash"))
    assert "timed out" in str(exc.value).lower()
    assert counter["calls"] == 1  # exactly one attempt, no retries


# --- C. Groq timeout -> ProviderError --------------------------------------

async def test_groq_timeout_raises_provider_error(monkeypatch):
    counter = _install_timeout_client(monkeypatch, "app.providers.groq")
    provider = GroqProvider(api_key="dummy", timeout_seconds=1.0)
    with pytest.raises(ProviderError) as exc:
        await provider.generate(_llm_request("openai/gpt-oss-20b"))
    assert "timed out" in str(exc.value).lower()
    assert counter["calls"] == 1


# --- D/E/F/G. End-to-end API timeout via real GroqProvider -----------------

@pytest.fixture
def ctx(db_engine, TestSessionLocal):
    s = TestSessionLocal()
    user = User(name="dev")
    s.add(user)
    s.flush()
    s.add(ApiKey(user_id=user.id, key_hash=hash_api_key(RAW_KEY), label="k", is_active=True))
    s.commit()
    s.close()

    app = create_app()

    def override_get_db():
        db = TestSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield SimpleNamespace(client=TestClient(app), factory=TestSessionLocal)
    finally:
        app.dependency_overrides.clear()


def test_api_timeout_returns_502_logs_and_preserves_request_id(ctx, monkeypatch):
    counter = _install_timeout_client(monkeypatch, "app.providers.groq")

    resp = ctx.client.post(
        CHAT_URL,
        json={"model": "groq", "messages": [{"role": "user", "content": "hi"}]},
        headers={"Authorization": f"Bearer {RAW_KEY}"},
    )

    # D: 502 PROVIDER_ERROR with safe message + X-Request-ID.
    assert resp.status_code == 502
    body = resp.json()
    assert body["error"]["code"] == "PROVIDER_ERROR"
    rid = resp.headers[REQUEST_ID_HEADER]
    assert rid.startswith("req_")

    # F: no leakage of internals/secrets.
    text = resp.text
    for leaked in ("ReadTimeout", "httpx", "Traceback", "Authorization", "Bearer",
                   "api.groq.com", "dummy"):
        assert leaked not in text

    # G: exactly one provider attempt (no retries).
    assert counter["calls"] == 1

    # E: Step 11 logged an error row with the same request_id + latency populated.
    s = ctx.factory()
    try:
        rows = list(s.execute(select(Request)).scalars().all())
    finally:
        s.close()
    assert len(rows) == 1
    assert rows[0].status == "error"
    assert rows[0].error_code == "PROVIDER_ERROR"
    assert rows[0].request_id == rid
    assert rows[0].latency_ms is not None and rows[0].latency_ms >= 0
