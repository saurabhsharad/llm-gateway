#!/usr/bin/env bash
# Backend container startup: migrate, THEN serve.
#
# `set -e` ensures that if `alembic upgrade head` fails, the script exits non-zero
# and the container stops — we never serve against an un-migrated / broken schema.
set -e

echo "[entrypoint] Running database migrations (alembic upgrade head)…"
alembic upgrade head

echo "[entrypoint] Starting uvicorn on 0.0.0.0:8000…"
# exec replaces the shell so uvicorn is PID 1 and receives signals (clean shutdown).
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
