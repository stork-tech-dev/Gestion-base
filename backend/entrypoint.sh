#!/bin/sh
# Arranque del backend: migraciones + datos iniciales + comando recibido.
# Lo usan tanto docker compose (desarrollo, con --reload) como un PaaS (Railway).
set -e

echo "[entrypoint] alembic upgrade head"
alembic upgrade head

# URL para psql: DATABASE_URL si existe; si no, se arma con POSTGRES_*.
URL_PSQL="${DATABASE_URL:-postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_HOST:-localhost}:${POSTGRES_PORT:-5432}/${POSTGRES_DB}}"
URL_PSQL=$(echo "$URL_PSQL" | sed -e 's#^postgresql+psycopg2://#postgresql://#' -e 's#^postgres://#postgresql://#')

echo "[entrypoint] seed (idempotente)"
psql "$URL_PSQL" -v ON_ERROR_STOP=1 -q -f migrations/seed.sql

exec "$@"
