#!/bin/sh
# Apply any pending DB migrations, then launch the bot. Running this on every
# container start makes `docker compose up` a one-step deploy — a fresh DB is
# built up from 0001, an existing DB advances to head, and an up-to-date DB is
# a no-op. Alembic reads DATABASE_URL (compose points it at the db service).
set -e

uv run alembic upgrade head

exec uv run python -m upwork_bot.app
