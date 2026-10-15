"""Development seed: create the initial user + API key from GATEWAY_API_KEYS.

Run explicitly (never at app startup):

    python -m app.db.seed

It reads GATEWAY_API_KEYS from the environment, and for each key:
  - computes its SHA-256 hash,
  - ensures a development user exists,
  - creates an api_keys row storing ONLY the hash (never the raw key),
  - is idempotent (skips keys whose hash already exists).

It prints only safe confirmations — never the raw key or any secret.
"""

import logging

from app.auth.api_key import hash_api_key
from app.core.config import settings
from app.db.database import get_sessionmaker
from app.db.models import ApiKey, User
from app.db.repositories import get_active_api_key_by_hash, get_user_by_name

logger = logging.getLogger("llm_gateway")

_DEV_USER_NAME = "dev"


def seed() -> None:
    raw_keys = [k.strip() for k in (settings.gateway_api_keys or "").split(",") if k.strip()]
    if not raw_keys:
        print("No GATEWAY_API_KEYS configured; nothing to seed.")
        return

    session = get_sessionmaker()()
    try:
        # Ensure the development user exists.
        user = get_user_by_name(session, _DEV_USER_NAME)
        if user is None:
            user = User(name=_DEV_USER_NAME)
            session.add(user)
            session.flush()  # assign user.id
            print(f"Created user '{_DEV_USER_NAME}'.")
        else:
            print(f"User '{_DEV_USER_NAME}' already exists.")

        created, skipped = 0, 0
        for index, raw_key in enumerate(raw_keys, start=1):
            key_hash = hash_api_key(raw_key)
            if get_active_api_key_by_hash(session, key_hash) is not None:
                skipped += 1
                continue
            session.add(
                ApiKey(user_id=user.id, key_hash=key_hash, label=f"dev-key-{index}")
            )
            created += 1

        session.commit()
        # Safe confirmation only — no raw keys, no hashes printed.
        print(f"Seed complete: {created} key(s) created, {skipped} already present.")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    seed()
