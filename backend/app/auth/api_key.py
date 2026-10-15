"""Gateway (client) API-key authentication — PostgreSQL-backed (Step 10).

This module is the entire authentication concern, isolated from business logic.
It answers one question: "is the caller a known, active client?" — nothing else
(no authorization/permissions, no rate limiting).

Persistence (Step 10): keys live in the `api_keys` table, stored ONLY as their
SHA-256 hash. `verify_api_key(db, raw_key)` hashes the presented key and looks it
up via the repository layer. This replaced the Step 9 in-memory store; the seam
(`verify_api_key` / `require_api_key`) is unchanged in spirit — only its backing
store moved from a dict to the database.

Why SHA-256 (not bcrypt/argon2)? API keys are long, random, high-entropy secrets,
so a fast one-way hash is sufficient and cheap to run on every request. Slow,
salted hashing is for low-entropy passwords.
"""

import hashlib
import logging
from dataclasses import dataclass

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.exceptions import AuthenticationError
from app.db.database import get_db
from app.db.repositories import get_active_api_key_by_hash

logger = logging.getLogger("llm_gateway")


@dataclass(frozen=True)
class ClientIdentity:
    """The client behind a valid API key.

    `id` and `name` come from the owning user; `api_key_id` is the specific key
    used (added additively in Step 11 so usage logging can attribute a request to
    both the user and the exact key, without exposing the key itself).
    """

    id: str
    name: str
    api_key_id: int


def hash_api_key(raw_key: str) -> str:
    """Return the SHA-256 hex digest of a raw API key.

    One-way: given the hash you cannot recover the key. We store and compare only
    these digests, so a leak of the store never exposes usable keys.
    """
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def verify_api_key(db: Session, raw_key: str) -> ClientIdentity | None:
    """Return the client for a raw key, or None if it isn't recognized/active.

    This is the persistence seam: hash the key, look up the active ApiKey, and
    resolve the owning user into a ClientIdentity.
    """
    api_key = get_active_api_key_by_hash(db, hash_api_key(raw_key))
    if api_key is None:
        return None
    user = api_key.user
    return ClientIdentity(id=str(user.id), name=user.name, api_key_id=api_key.id)


# HTTPBearer parses "Authorization: Bearer <token>". auto_error=False makes it
# return None (instead of raising its own 403) so WE control the 401 and its
# JSON shape via the centralized error handler.
_bearer_scheme = HTTPBearer(auto_error=False)


def require_api_key(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> ClientIdentity:
    """FastAPI dependency that gates protected endpoints.

    Raises AuthenticationError (-> HTTP 401 via the existing GatewayError handler)
    when the credential is missing, not a Bearer token, or unknown/revoked. On
    success returns the ClientIdentity, so later steps can attribute the request.
    """
    if credentials is None or not credentials.credentials:
        raise AuthenticationError("Missing or malformed Authorization header.")

    identity = verify_api_key(db, credentials.credentials)
    if identity is None:
        raise AuthenticationError("Invalid API key.")

    return identity
