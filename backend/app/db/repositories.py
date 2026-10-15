"""Thin data-access layer (repository functions).

These functions are the only place that writes SQLAlchemy queries for a given
concern. Keeping them here means the auth layer (and later, usage logging) depend
on small, testable functions rather than embedding queries throughout the app.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ApiKey, Request, User


def get_active_api_key_by_hash(db: Session, key_hash: str) -> ApiKey | None:
    """Return the active ApiKey matching this SHA-256 hash, or None.

    Inactive (revoked) keys are excluded, so a revoked key behaves exactly like
    an unknown one.
    """
    stmt = select(ApiKey).where(
        ApiKey.key_hash == key_hash, ApiKey.is_active.is_(True)
    )
    return db.execute(stmt).scalar_one_or_none()


def get_user_by_id(db: Session, user_id: int) -> User | None:
    """Return a user by primary key, or None."""
    return db.get(User, user_id)


def get_user_by_name(db: Session, name: str) -> User | None:
    """Return the first user with this name, or None (used by seeding)."""
    stmt = select(User).where(User.name == name)
    return db.execute(stmt).scalars().first()


def create_request_log(
    db: Session,
    *,
    request_id: str,
    user_id: int | None,
    api_key_id: int | None,
    model: str,
    provider: str | None,
    provider_model: str | None,
    input_tokens: int | None,
    output_tokens: int | None,
    total_tokens: int | None,
    latency_ms: int | None,
    status: str,
    error_code: str | None,
) -> Request:
    """Insert one usage/request-log row and commit it.

    Only metadata is stored — never prompts, responses, or raw keys. The caller
    (usage service) is responsible for making this call failure-safe.
    """
    record = Request(
        request_id=request_id,
        user_id=user_id,
        api_key_id=api_key_id,
        model=model,
        provider=provider,
        provider_model=provider_model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        latency_ms=latency_ms,
        status=status,
        error_code=error_code,
    )
    db.add(record)
    db.commit()
    return record
