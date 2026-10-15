"""Shared pytest fixtures for database-backed tests (Step 10).

Logic/auth/ORM tests run against an isolated in-memory SQLite database — fast, no
external service, safe to create/drop per test. We use StaticPool so every
connection shares the same in-memory database (so data seeded in a test is
visible to the app's get_db during a request).

The real PostgreSQL migration is verified separately in test_db.py (auto-skipped
when Postgres isn't configured).
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.db.models  # noqa: F401  (registers models on Base.metadata)
from app.db.database import Base


@pytest.fixture
def db_engine():
    """A fresh in-memory SQLite engine with all tables created via metadata.

    Note: tables here are created with create_all() as a TEST convenience. The
    application never does this — its schema is owned by Alembic migrations.
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def TestSessionLocal(db_engine):
    """Session factory bound to the test engine."""
    return sessionmaker(bind=db_engine, autoflush=False, autocommit=False, future=True)


@pytest.fixture
def db_session(TestSessionLocal):
    """A single Session for direct database tests."""
    session = TestSessionLocal()
    try:
        yield session
    finally:
        session.close()
