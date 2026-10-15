"""SQLAlchemy ORM models: users, api_keys, requests.

These map Python objects to database tables. Alembic reads Base.metadata (which
these classes populate) to generate and verify migrations.

Portability: only portable column types are used (Integer, String, Boolean,
DateTime(timezone=True), Text) so the same models work on PostgreSQL (production)
and SQLite (fast isolated tests).

Privacy: we never store raw API keys (only their SHA-256 hash) and never store
prompt content.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class User(Base):
    """A client of the gateway. A minimal placeholder — no auth/RBAC here."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    api_keys: Mapped[list["ApiKey"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    requests: Mapped[list["Request"]] = relationship(back_populates="user")


class ApiKey(Base):
    """A gateway (client) API key, stored only as a SHA-256 hash."""

    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # SHA-256 hex digest (64 chars). Unique + indexed for fast lookup by hash.
    key_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Revocation = set is_active False; lookups filter on this.
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="api_keys")
    requests: Mapped[list["Request"]] = relationship(back_populates="api_key")


class Request(Base):
    """Usage record for one gateway request.

    Created now as the schema foundation for Step 11 (usage logging). NOTHING
    writes to this table yet. No prompt content is ever stored here.
    """

    __tablename__ = "requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    api_key_id: Mapped[int | None] = mapped_column(
        ForeignKey("api_keys.id", ondelete="SET NULL"), nullable=True, index=True
    )

    model: Mapped[str] = mapped_column(String(100), nullable=False)
    # provider / provider_model are nullable: an error can occur BEFORE the model
    # is resolved (e.g. UnknownModelError), so those requests are logged with no
    # provider context rather than being dropped (Step 11, option 16-A).
    provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    provider_model: Mapped[str | None] = mapped_column(String(150), nullable=True)

    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    status: Mapped[str] = mapped_column(String(20), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(50), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    user: Mapped["User | None"] = relationship(back_populates="requests")
    api_key: Mapped["ApiKey | None"] = relationship(back_populates="requests")
