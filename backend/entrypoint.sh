#!/bin/sh
# Arranque del backend: migraciones + datos iniciales + comando recibido.
# Lo usan tanto docker compose (desarrollo, con --reload) como un PaaS (Railway).
set -e

echo "[entrypoint] alembic upgrade head"
alembic upgrade head

# Zona horaria de la sesión de psql (coherente con el timezone del engine de
# la app; ver app/core/database.py y migrations/env.py).
export PGTZ="${TIMEZONE:-America/Argentina/Buenos_Aires}"

echo "[entrypoint] seed (idempotente)"
if [ -n "${DATABASE_URL:-}" ]; then
    # DATABASE_URL (ej. Railway): se normaliza el driver para psql.
    URL_PSQL=$(echo "$DATABASE_URL" | sed -e 's#^postgresql+psycopg2://#postgresql://#' -e 's#^postgres://#postgresql://#')
    psql "$URL_PSQL" -v ON_ERROR_STOP=1 -q -f migrations/seed.sql
else
    # Sin DATABASE_URL: variables PG* en vez de armar una URL a mano (una
    # contraseña con caracteres especiales sin URL-encoding rompería el parseo).
    PGHOST="${POSTGRES_HOST:-localhost}" PGPORT="${POSTGRES_PORT:-5432}" \
    PGUSER="$POSTGRES_USER" PGPASSWORD="$POSTGRES_PASSWORD" PGDATABASE="$POSTGRES_DB" \
        psql -v ON_ERROR_STOP=1 -q -f migrations/seed.sql
fi

exec "$@"
