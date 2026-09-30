#!/bin/sh
set -e

uv run --frozen --no-dev alembic upgrade head
exec uv run --frozen --no-dev python -m upwork_bot.app
