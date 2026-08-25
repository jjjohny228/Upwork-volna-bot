#!/bin/sh
# Apply any pending DB migrations, then launch the bot. Running this on every
set -e

uv run alembic upgrade head

exec uv run python -m upwork_bot.app
