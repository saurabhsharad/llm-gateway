"""Tests for PostgreSQL-backed gateway API-key authentication (Step 10).

These use FastAPI's TestClient with the app's get_db dependency overridden to an
isolated SQLite test database (see conftest.py). A known key is seeded as its
hash; the "valid key proceeds" test also overrides the gateway with a fake so no
real LLM call happens.
"""

import pytest
from fastapi.testclient import TestClient

from app.api.chat import get_gateway_service
from app.auth.api_key import hash_api_key
from app.db.database import get_db
from app.db.models import ApiKey, User
from app.main import create_app
from app.schemas.chat import ChatCompletionResponse, Usage

TEST_KEY = "gw_test_valid_key_123"
CHAT_URL = "/v1/chat/completions"
VALID_BODY = {"model": "gemini", "messages": [{"role": "user", "content": "hi"}]}


class _FakeGateway:
    """Stands in for GatewayService so a valid key can 'proceed' without network."""

    async def complete(self, request, request_id):
        return ChatCompletionResponse(
            id=request_id, model=request.model, provider="google",
            content="ok", usage=Usage(),
        )


def _seed_key(session_factory, *, raw_key=TEST_KEY, active=True, user_name="test"):
    """Insert a user + api_key (hash only) into the test DB."""
    s = session_factory()
    try:
        user = User(name=user_name)
        s.add(user)
        s.flush()
        s.add(ApiKey(user_id=user.id, key_hash=hash_api_key(raw_key),
                     label="test", is_active=active))
        s.commit()
        return user.id
    finally:
        s.close()


@pytest.fixture
def client(db_engine, TestSessionLocal):
    app = create_app()

    def override_get_db():
        db = TestSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app), TestSessionLocal
    finally:
        app.dependency_overrides.clear()


def _auth(key: str) -> dict:
    return {"Authorization": f"Bearer {key}"}


# --- The auth gate --------------------------------------------------------

def test_no_auth_header_returns_401(client):
    tc, _ = client
    resp = tc.post(CHAT_URL, json=VALID_BODY)
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHORIZED"


def test_malformed_header_returns_401(client):
    tc, _ = client
    resp = tc.post(CHAT_URL, json=VALID_BODY, headers={"Authorization": "Basic abc"})
    assert resp.status_code == 401


def test_invalid_key_returns_401(client):
    tc, factory = client
    _seed_key(factory)  # a valid key exists, but we present a different one
    resp = tc.post(CHAT_URL, json=VALID_BODY, headers=_auth("gw_invalid"))
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHORIZED"


def test_revoked_key_returns_401(client):
    tc, factory = client
    _seed_key(factory, active=False)  # key exists but is_active=False
    resp = tc.post(CHAT_URL, json=VALID_BODY, headers=_auth(TEST_KEY))
    assert resp.status_code == 401


def test_valid_db_key_proceeds(client):
    tc, factory = client
    _seed_key(factory)
    tc.app.dependency_overrides[get_gateway_service] = lambda: _FakeGateway()
    resp = tc.post(CHAT_URL, json=VALID_BODY, headers=_auth(TEST_KEY))
    assert resp.status_code == 200
    assert resp.json()["content"] == "ok"


# --- Auth runs BEFORE business logic; existing behavior intact ------------

def test_valid_key_unknown_model_still_404(client):
    tc, factory = client
    _seed_key(factory)
    body = {"model": "llama", "messages": [{"role": "user", "content": "hi"}]}
    resp = tc.post(CHAT_URL, json=body, headers=_auth(TEST_KEY))
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "UNKNOWN_MODEL"


def test_valid_key_invalid_body_still_422(client):
    tc, factory = client
    _seed_key(factory)
    body = {"model": "gemini", "messages": []}
    resp = tc.post(CHAT_URL, json=body, headers=_auth(TEST_KEY))
    assert resp.status_code == 422


# --- Public endpoints require no key --------------------------------------

def test_health_is_public(client):
    tc, _ = client
    assert tc.get("/health").status_code == 200


def test_models_is_public(client):
    tc, _ = client
    assert tc.get("/v1/models").status_code == 200
