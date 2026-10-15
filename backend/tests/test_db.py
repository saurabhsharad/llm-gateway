"""Database + persistence tests (Step 10).

ORM/repository/auth-resolution tests run on the isolated SQLite DB. A final test
verifies the real PostgreSQL schema matches the models, and auto-skips when
Postgres isn't configured.
"""

import pytest
from sqlalchemy import create_engine, inspect

from app.auth.api_key import ClientIdentity, hash_api_key, verify_api_key
from app.core.config import settings
from app.db.models import ApiKey, User
from app.db.repositories import get_active_api_key_by_hash

RAW_KEY = "gw_unit_test_key"


def _make_user_with_key(session, *, active=True):
    user = User(name="alice")
    session.add(user)
    session.flush()
    key = ApiKey(user_id=user.id, key_hash=hash_api_key(RAW_KEY),
                 label="k", is_active=active)
    session.add(key)
    session.commit()
    return user, key


def test_hash_is_sha256_hex_and_not_plaintext():
    h = hash_api_key(RAW_KEY)
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)
    assert RAW_KEY not in h


def test_api_key_persists_and_relationship_loads(db_session):
    user, key = _make_user_with_key(db_session)
    assert key.id is not None
    assert key.user.name == "alice"          # relationship works
    assert user.api_keys[0].key_hash == hash_api_key(RAW_KEY)


def test_repository_lookup_by_hash(db_session):
    _make_user_with_key(db_session)
    found = get_active_api_key_by_hash(db_session, hash_api_key(RAW_KEY))
    assert found is not None
    assert found.user.name == "alice"


def test_repository_excludes_inactive_keys(db_session):
    _make_user_with_key(db_session, active=False)
    assert get_active_api_key_by_hash(db_session, hash_api_key(RAW_KEY)) is None


def test_repository_returns_none_for_unknown_hash(db_session):
    assert get_active_api_key_by_hash(db_session, hash_api_key("nope")) is None


def test_verify_api_key_resolves_client_identity(db_session):
    user, _ = _make_user_with_key(db_session)
    identity = verify_api_key(db_session, RAW_KEY)
    assert isinstance(identity, ClientIdentity)
    assert identity.id == str(user.id)
    assert identity.name == "alice"


def test_verify_api_key_returns_none_for_bad_key(db_session):
    _make_user_with_key(db_session)
    assert verify_api_key(db_session, "wrong-key") is None


# --- PostgreSQL migration fidelity (auto-skips without Postgres) ----------

_is_postgres = bool(settings.database_url and settings.database_url.startswith(
    "postgresql"
))


@pytest.mark.skipif(not _is_postgres, reason="No PostgreSQL DATABASE_URL configured")
def test_postgres_migrated_schema_matches_models():
    """The migrated Postgres DB must contain the tables/columns our models define."""
    engine = create_engine(settings.database_url, future=True)
    try:
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        assert {"users", "api_keys", "requests", "alembic_version"} <= tables

        api_key_cols = {c["name"] for c in inspector.get_columns("api_keys")}
        assert {"id", "user_id", "key_hash", "label", "is_active", "created_at"} <= api_key_cols

        request_cols = {c["name"] for c in inspector.get_columns("requests")}
        assert {
            "id", "request_id", "user_id", "api_key_id", "model", "provider",
            "provider_model", "input_tokens", "output_tokens", "total_tokens",
            "latency_ms", "status", "error_code", "created_at",
        } <= request_cols
    finally:
        engine.dispose()
