"""Tests for usage/request logging (Step 11).

Offline: providers are faked via dependency override; the DB is the isolated
SQLite test database from conftest. We assert on rows written to `requests`.
"""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.chat import get_gateway_service
from app.auth.api_key import hash_api_key
from app.core.exceptions import ProviderError
from app.db.database import get_db
from app.db.models import ApiKey, Request, User
from app.main import create_app
from app.schemas.chat import ChatCompletionResponse, Usage
from app.services import usage as usage_service

RAW_KEY = "gw_usage_test_key"
CHAT_URL = "/v1/chat/completions"
BODY = {"model": "gemini", "messages": [{"role": "user", "content": "hi"}]}


class _FakeGatewaySuccess:
    async def complete(self, request, request_id):
        return ChatCompletionResponse(
            id=request_id, model=request.model, provider="google",
            provider_model="gemini-3.6-flash", content="ok", finish_reason="stop",
            usage=Usage(input_tokens=10, output_tokens=5, total_tokens=15),
        )


class _FakeGatewayProviderError:
    async def complete(self, request, request_id):
        raise ProviderError("boom")


class _FakeGatewayCrash:
    async def complete(self, request, request_id):
        raise RuntimeError("unexpected")


@pytest.fixture
def ctx(db_engine, TestSessionLocal):
    # Seed a user + active key.
    s = TestSessionLocal()
    user = User(name="dev")
    s.add(user)
    s.flush()
    key = ApiKey(user_id=user.id, key_hash=hash_api_key(RAW_KEY), label="k", is_active=True)
    s.add(key)
    s.commit()
    uid, kid = user.id, key.id
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
        # raise_server_exceptions=False so the global 500 handler's response comes
        # through (instead of TestClient re-raising) for the unexpected-error test.
        yield SimpleNamespace(
            client=TestClient(app, raise_server_exceptions=False), app=app,
            factory=TestSessionLocal, user_id=uid, api_key_id=kid,
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


# --- Success ---------------------------------------------------------------

def test_success_creates_exactly_one_row_with_correct_metadata(ctx):
    ctx.app.dependency_overrides[get_gateway_service] = lambda: _FakeGatewaySuccess()
    resp = ctx.client.post(CHAT_URL, json=BODY, headers=_auth())
    assert resp.status_code == 200

    rows = _rows(ctx.factory)
    assert len(rows) == 1
    r = rows[0]
    assert r.user_id == ctx.user_id
    assert r.api_key_id == ctx.api_key_id
    assert r.model == "gemini"
    assert r.provider == "google"
    assert r.provider_model == "gemini-3.6-flash"
    assert r.input_tokens == 10
    assert r.output_tokens == 5
    assert r.total_tokens == 15
    assert r.latency_ms is not None and r.latency_ms >= 0
    assert r.status == "success"
    assert r.error_code is None
    assert r.request_id and r.request_id.startswith("req_")
    assert r.created_at is not None


# --- Errors (post-authentication) -----------------------------------------

def test_provider_error_returns_502_and_logs_error_row(ctx):
    ctx.app.dependency_overrides[get_gateway_service] = lambda: _FakeGatewayProviderError()
    resp = ctx.client.post(CHAT_URL, json=BODY, headers=_auth())
    assert resp.status_code == 502  # original behavior unchanged

    rows = _rows(ctx.factory)
    assert len(rows) == 1
    assert rows[0].status == "error"
    assert rows[0].error_code == "PROVIDER_ERROR"
    assert rows[0].input_tokens is None


def test_unknown_model_returns_404_and_logs_error_with_null_provider(ctx):
    # Real gateway (not overridden): unknown model -> UnknownModelError before provider.
    body = {"model": "llama", "messages": [{"role": "user", "content": "hi"}]}
    resp = ctx.client.post(CHAT_URL, json=body, headers=_auth())
    assert resp.status_code == 404

    rows = _rows(ctx.factory)
    assert len(rows) == 1
    assert rows[0].status == "error"
    assert rows[0].error_code == "UNKNOWN_MODEL"
    assert rows[0].model == "llama"
    assert rows[0].provider is None
    assert rows[0].provider_model is None


def test_provider_unavailable_returns_503_and_logs(ctx):
    # 'gpt' maps to OpenAI, which has no adapter registered -> 503.
    body = {"model": "gpt", "messages": [{"role": "user", "content": "hi"}]}
    resp = ctx.client.post(CHAT_URL, json=body, headers=_auth())
    assert resp.status_code == 503

    rows = _rows(ctx.factory)
    assert len(rows) == 1
    assert rows[0].status == "error"
    assert rows[0].error_code == "PROVIDER_UNAVAILABLE"


def test_unexpected_error_returns_500_and_logs_internal_error(ctx):
    ctx.app.dependency_overrides[get_gateway_service] = lambda: _FakeGatewayCrash()
    resp = ctx.client.post(CHAT_URL, json=BODY, headers=_auth())
    assert resp.status_code == 500

    rows = _rows(ctx.factory)
    assert len(rows) == 1
    assert rows[0].status == "error"
    assert rows[0].error_code == "INTERNAL_ERROR"


# --- Failure-safe logging --------------------------------------------------

def test_logging_failure_does_not_change_success_response(ctx, monkeypatch):
    ctx.app.dependency_overrides[get_gateway_service] = lambda: _FakeGatewaySuccess()

    def _boom(*args, **kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(usage_service, "create_request_log", _boom)
    resp = ctx.client.post(CHAT_URL, json=BODY, headers=_auth())
    # Response is unchanged despite logging failure.
    assert resp.status_code == 200
    assert resp.json()["content"] == "ok"
    # And no row was persisted.
    assert _rows(ctx.factory) == []


def test_logging_failure_does_not_change_error_response(ctx, monkeypatch):
    ctx.app.dependency_overrides[get_gateway_service] = lambda: _FakeGatewayProviderError()
    monkeypatch.setattr(usage_service, "create_request_log",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("db down")))
    resp = ctx.client.post(CHAT_URL, json=BODY, headers=_auth())
    assert resp.status_code == 502  # original provider error preserved


# --- Not logged (pre-handler failures) ------------------------------------

def test_missing_key_401_not_logged(ctx):
    resp = ctx.client.post(CHAT_URL, json=BODY)
    assert resp.status_code == 401
    assert _rows(ctx.factory) == []


def test_invalid_key_401_not_logged(ctx):
    resp = ctx.client.post(CHAT_URL, json=BODY, headers={"Authorization": "Bearer gw_invalid"})
    assert resp.status_code == 401
    assert _rows(ctx.factory) == []


def test_invalid_body_422_not_logged(ctx):
    resp = ctx.client.post(CHAT_URL, json={"model": "gemini", "messages": []}, headers=_auth())
    assert resp.status_code == 422
    assert _rows(ctx.factory) == []
