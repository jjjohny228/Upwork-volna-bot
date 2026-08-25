FROM python:3.12-slim

RUN pip install --no-cache-dir uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .

RUN chmod +x docker-entrypoint.sh

# Entrypoint applies pending Alembic migrations before starting the bot, so
# `docker compose up` is a one-step deploy (no manual `alembic upgrade head`).
ENTRYPOINT ["./docker-entrypoint.sh"]
