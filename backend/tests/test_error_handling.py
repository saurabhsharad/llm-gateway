"""Tests for centralized error handling (Step 13).

Verify the consistent error envelope, status/code mapping, request-ID presence,
Step 11 logging, and that no sensitive/internal detail leaks to the client.
Offline: providers faked via override, except the sanitization test which drives
the real GroqProvider with a mocked HTTP layer.
"""

from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.chat import get_gateway_service
from app.auth.api_key import hash_api_key
from app.core.exceptions import ProviderError
from app.core.request_id import REQUEST_ID_HEADER
from app.db.database import get_db
from app.db.models import ApiKey, Request, User
from app.main import create_app

RAW_KEY = "gw_err_test_key"
CHAT_URL = "/v1/chat/completions"
BODY = {"model": "gemini", "messages": [{"role": "user", "content": "hi"}]}


class _FakeGatewayProviderError:
    async def complete(self, request, request_id):
        raise ProviderError("The upstream provider returned an error.")


class _FakeGatewayCrash:
    async def complete(self, request, request_id):
        # Message deliberately contains sensitive-looking text that must NOT leak.
        raise RuntimeError("boom at /etc/secret token=sk-LEAK-999")


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
        yield SimpleNamespace(
            client=TestClient(app, raise_server_exceptions=False),
            app=app, factory=TestSessionLocal,
        )
    finally:
        app.dependency_overrides.clear()


def _rows(factory) -> list[Request]:
    s = factory()
    try:
        return list(s.execute(select(Request)).scalars().all())
    finally:
        s.close()


def _auth() -> dict:
    return {"Authorization": f"Bearer {RAW_KEY}"}


def _assert_envelope(resp, *, status, code):
    assert resp.status_code == status
    body = resp.json()
    assert set(body.keys()) == {"error"}
    assert body["error"]["code"] == code
    assert isinstance(body["error"]["message"], str) and body["error"]["message"]
    assert resp.headers[REQUEST_ID_HEADER].startswith("req_")


# A. Authentication error
def test_missing_key_401(ctx):
    _assert_envelope(ctx.client.post(CHAT_URL, json=BODY), status=401, code="UNAUTHORIZED")
    assert _rows(ctx.factory) == []


def test_invalid_key_401(ctx):
    resp = ctx.client.post(CHAT_URL, json=BODY, headers={"Authorization": "Bearer gw_nope"})
    _assert_envelope(resp, status=401, code="UNAUTHORIZED")
    assert _rows(ctx.factory) == []


# B. Unknown model
def test_unknown_model_404_logged(ctx):
    body = {"model": "llama", "messages": [{"role": "user", "content": "hi"}]}
    resp = ctx.client.post(CHAT_URL, json=body, headers=_auth())
    _assert_envelope(resp, status=404, code="UNKNOWN_MODEL")
    rows = _rows(ctx.factory)
    assert len(rows) == 1 and rows[0].error_code == "UNKNOWN_MODEL"


# C. Provider unavailable ('gpt' -> OpenAI, no adapter registered)
def test_provider_unavailable_503_logged(ctx):
    body = {"model": "gpt", "messages": [{"role": "user", "content": "hi"}]}
    resp = ctx.client.post(CHAT_URL, json=body, headers=_auth())
    _assert_envelope(resp, status=503, code="PROVIDER_UNAVAILABLE")
    assert _rows(ctx.factory)[0].error_code == "PROVIDER_UNAVAILABLE"


# D. Provider error
def test_provider_error_502_logged(ctx):
    ctx.app.dependency_overrides[get_gateway_service] = lambda: _FakeGatewayProviderError()
    resp = ctx.client.post(CHAT_URL, json=BODY, headers=_auth())
    _assert_envelope(resp, status=502, code="PROVIDER_ERROR")
    assert _rows(ctx.factory)[0].error_code == "PROVIDER_ERROR"


# E. Unexpected exception -> generic 500, no internal detail leaked
def test_unexpected_500_is_generic_and_logged(ctx):
    ctx.app.dependency_overrides[get_gateway_service] = lambda: _FakeGatewayCrash()
    resp = ctx.client.post(CHAT_URL, json=BODY, headers=_auth())
    _assert_envelope(resp, status=500, code="INTERNAL_ERROR")
    text = resp.text
    for leaked in ("RuntimeError", "boom", "/etc/secret", "sk-LEAK-999", "Traceback"):
        assert leaked not in text
    assert _rows(ctx.factory)[0].error_code == "INTERNAL_ERROR"


# F. Validation error -> normalized envelope, input value NOT echoed, no DB row
def test_validation_422_envelope_and_no_input_echo(ctx):
    body = {"model": "gemini", "messages": [{"role": "user", "content": "hi"}],
            "secret_field": "LEAK_ME_123"}  # extra=forbid -> 422; input would echo this
    resp = ctx.client.post(CHAT_URL, json=body, headers=_auth())
    assert resp.status_code == 422
    payload = resp.json()
    assert payload["error"]["code"] == "VALIDATION_ERROR"
    assert isinstance(payload["error"]["details"], list)
    assert "LEAK_ME_123" not in resp.text          # stripped input, no echo
    assert resp.headers[REQUEST_ID_HEADER].startswith("req_")
    assert _rows(ctx.factory) == []


# G. Provider RAW error is sanitized end-to-end (real GroqProvider, mocked HTTP)
def test_provider_raw_error_is_sanitized(ctx, monkeypatch):
    class _FakeResp:
        status_code = 401
        text = '{"error":{"message":"invalid_api_key sk-PROVIDER-SECRET"}}'

        def json(self):
            return {}

    class _FakeAsyncClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            return _FakeResp()

    monkeypatch.setattr("app.providers.groq.httpx.AsyncClient", _FakeAsyncClient)
    # Use the real gateway + real registered GroqProvider (not overridden).
    resp = ctx.client.post(
        CHAT_URL, json={"model": "groq", "messages": [{"role": "user", "content": "hi"}]},
        headers=_auth(),
    )
    _assert_envelope(resp, status=502, code="PROVIDER_ERROR")
    assert "sk-PROVIDER-SECRET" not in resp.text
    assert "invalid_api_key" not in resp.text


# Public endpoints keep working (regression sanity).
def test_public_endpoints_ok(ctx):
    assert ctx.client.get("/health").status_code == 200
    assert ctx.client.get("/v1/models").status_code == 200


# httpx import kept meaningful (used indirectly via monkeypatch target)
assert httpx is not None
