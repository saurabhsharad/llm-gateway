"""Tests for request-ID formalization (Step 12).

Offline: providers faked via dependency override; DB is the isolated SQLite test
database from conftest. Asserts on the X-Request-ID header, the response body id,
and the stored requests.request_id — all of which must be the SAME value.
"""

from types import SimpleNamespace

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
from app.schemas.chat import ChatCompletionResponse, Usage

RAW_KEY = "gw_reqid_test_key"
CHAT_URL = "/v1/chat/completions"
BODY = {"model": "gemini", "messages": [{"role": "user", "content": "hi"}]}


class _FakeGatewaySuccess:
    async def complete(self, request, request_id):
        # Echo the SAME request_id into the response body `id`.
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


# A. Server generates a request ID and returns it in the header.
def test_server_generates_request_id_header(ctx):
    ctx.app.dependency_overrides[get_gateway_service] = lambda: _FakeGatewaySuccess()
    resp = ctx.client.post(CHAT_URL, json=BODY, headers=_auth())
    assert resp.status_code == 200
    rid = resp.headers[REQUEST_ID_HEADER]
    assert rid.startswith("req_")


# B & C. The SAME ID appears in header, response body id, and the DB row.
def test_same_request_id_everywhere(ctx):
    ctx.app.dependency_overrides[get_gateway_service] = lambda: _FakeGatewaySuccess()
    resp = ctx.client.post(CHAT_URL, json=BODY, headers=_auth())
    rid = resp.headers[REQUEST_ID_HEADER]

    assert resp.json()["id"] == rid                 # response body id
    rows = _rows(ctx.factory)
    assert len(rows) == 1
    assert rows[0].request_id == rid                # DB row


# D. Unknown model -> 404 with header, and stored in the error row.
def test_unknown_model_has_request_id(ctx):
    body = {"model": "llama", "messages": [{"role": "user", "content": "hi"}]}
    resp = ctx.client.post(CHAT_URL, json=body, headers=_auth())
    assert resp.status_code == 404
    rid = resp.headers[REQUEST_ID_HEADER]
    assert rid.startswith("req_")
    rows = _rows(ctx.factory)
    assert len(rows) == 1
    assert rows[0].request_id == rid
    assert rows[0].error_code == "UNKNOWN_MODEL"


# E. Provider error -> 502 with header, same id logged.
def test_provider_error_has_request_id(ctx):
    ctx.app.dependency_overrides[get_gateway_service] = lambda: _FakeGatewayProviderError()
    resp = ctx.client.post(CHAT_URL, json=BODY, headers=_auth())
    assert resp.status_code == 502
    rid = resp.headers[REQUEST_ID_HEADER]
    rows = _rows(ctx.factory)
    assert rows[0].request_id == rid


# F. Unexpected 500 -> header present.
def test_unexpected_500_has_request_id(ctx):
    ctx.app.dependency_overrides[get_gateway_service] = lambda: _FakeGatewayCrash()
    resp = ctx.client.post(CHAT_URL, json=BODY, headers=_auth())
    assert resp.status_code == 500
    assert resp.headers[REQUEST_ID_HEADER].startswith("req_")


# G. Missing API key -> 401, header present, NO db row.
def test_missing_key_401_has_header_but_no_log(ctx):
    resp = ctx.client.post(CHAT_URL, json=BODY)
    assert resp.status_code == 401
    assert resp.headers[REQUEST_ID_HEADER].startswith("req_")
    assert _rows(ctx.factory) == []


# H. Invalid body -> 422, header present, NO db row.
def test_invalid_body_422_has_header_but_no_log(ctx):
    resp = ctx.client.post(CHAT_URL, json={"model": "gemini", "messages": []}, headers=_auth())
    assert resp.status_code == 422
    assert resp.headers[REQUEST_ID_HEADER].startswith("req_")
    assert _rows(ctx.factory) == []


# I. Client-provided X-Request-ID is honored when valid, and stored.
def test_client_provided_request_id_is_used(ctx):
    ctx.app.dependency_overrides[get_gateway_service] = lambda: _FakeGatewaySuccess()
    headers = {**_auth(), REQUEST_ID_HEADER: "req_client_test_123"}
    resp = ctx.client.post(CHAT_URL, json=BODY, headers=headers)
    assert resp.headers[REQUEST_ID_HEADER] == "req_client_test_123"
    assert _rows(ctx.factory)[0].request_id == "req_client_test_123"


# I (cont). Malformed/oversized client ID is rejected -> server generates one.
def test_malformed_client_request_id_is_replaced(ctx):
    ctx.app.dependency_overrides[get_gateway_service] = lambda: _FakeGatewaySuccess()
    bad = "not valid! contains spaces & symbols " + "x" * 300
    headers = {**_auth(), REQUEST_ID_HEADER: bad}
    resp = ctx.client.post(CHAT_URL, json=BODY, headers=headers)
    rid = resp.headers[REQUEST_ID_HEADER]
    assert rid != bad
    assert rid.startswith("req_")


# J. IDs are unique across requests.
def test_request_ids_are_unique(ctx):
    ctx.app.dependency_overrides[get_gateway_service] = lambda: _FakeGatewaySuccess()
    r1 = ctx.client.post(CHAT_URL, json=BODY, headers=_auth())
    r2 = ctx.client.post(CHAT_URL, json=BODY, headers=_auth())
    assert r1.headers[REQUEST_ID_HEADER] != r2.headers[REQUEST_ID_HEADER]


# Public endpoints also carry the header.
def test_public_endpoints_have_request_id(ctx):
    assert ctx.client.get("/health").headers[REQUEST_ID_HEADER].startswith("req_")
    assert ctx.client.get("/v1/models").headers[REQUEST_ID_HEADER].startswith("req_")
