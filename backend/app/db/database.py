"""Database core: engine, session factory, declarative Base, and get_db().

Synchronous SQLAlchemy 2.0 + psycopg v3.

Design notes:
  - The engine and session factory are created LAZILY (on first use), so importing
    this module never requires a live database. That keeps the app importable in
    tests and in environments where DATABASE_URL isn't set.
  - We do NOT call create_all() here. The schema is owned by Alembic migrations.
  - get_db() is the FastAPI dependency that yields a session and always closes it,
    managing the per-request connection lifecycle.
"""

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    """Declarative base all ORM models inherit from.

    Its `.metadata` is the collection of tables Alembic compares against to
    generate/verify migrations.
    """


# Created on first use by _get_engine() / get_sessionmaker().
_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def _get_engine() -> Engine:
    """Return the process-wide Engine, creating it on first use.

    Raises a clear error if DATABASE_URL is not configured, rather than failing
    obscurely deep in a query.
    """
    global _engine
    if _engine is None:
        if not settings.database_url:
            raise RuntimeError(
                "DATABASE_URL is not configured. Set it in the environment/.env "
                "before using the database."
            )
        # pool_pre_ping avoids handing out dead connections after Postgres restarts.
        _engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)
    return _engine


def get_sessionmaker() -> sessionmaker[Session]:
    """Return the session factory, creating it (and the engine) on first use."""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            bind=_get_engine(), autoflush=False, autocommit=False, future=True
        )
    return _SessionLocal


def get_db() -> Iterator[Session]:
    """FastAPI dependency: yield a Session, guaranteeing it is closed.

    Usage: `db: Session = Depends(get_db)`. The session lives for one request.
    """
    session = get_sessionmaker()()
    try:
        yield session
    finally:
        session.close()
