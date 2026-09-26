# Módulo 01 — Infraestructura Base: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dejar un entorno que levanta con `docker compose up` (db + backend + backup), con FastAPI, Alembic, auditoría inmutable, configuración del sistema, seed idempotente, layout HTML base (sidebar, header, modo oscuro) y los macros Jinja2 reutilizables, todo testeado.

**Architecture:** Un solo backend FastAPI que sirve API (`/api/v1`) y HTML (Jinja2 + HTMX + Alpine + Tailwind CDN). PostgreSQL 15 en Docker; migraciones Alembic escritas a mano en SQL; tests pytest contra una base Postgres real (`gestion_test`) con transacción revertida por test. Los archivos subidos viven en un volumen `/uploads`; un servicio `backup` hace `pg_dump` diario.

**Tech Stack:** Python 3.12, FastAPI 0.115, SQLAlchemy 2.0, Alembic 1.14, psycopg2, pydantic-settings, Jinja2, pytest + httpx (TestClient), Docker Compose v2, Tailwind (CDN), Alpine.js 3.14.8, htmx 2.0.4.

**Spec:** `modulos/01_infraestructura.md` (+ `CLAUDE.md`).

## Global Constraints

- Código y comentarios en español. Sin dependencias de servicios pagos.
- **Git:** se trabaja en la rama local `modulo-01-infraestructura` (autorizada por el usuario). Cada tarea termina con UN commit en esa rama (mensaje `feat(infra): …`, con la línea `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`). NUNCA `git push`, ni merge a `main`, ni reescribir historia. Nunca commitear `.env`, `uploads/` ni `backups/`.
- Todo corre dentro de Docker: los tests se ejecutan con `docker compose exec backend pytest …` (Python 3.12 del contenedor, Postgres del servicio `db`).
- En esta máquina el puerto 5432 está ocupado por un Postgres local: el `.env` local usa `POSTGRES_PORT_HOST=5433` y `BACKEND_PORT_PROD=8080`.
- Todas las columnas de fecha son `TIMESTAMP` sin zona con hora del negocio (`America/Argentina/Buenos_Aires`); la conexión fija `timezone` a esa zona.
- Ningún módulo lee `os.environ`: todo por `config.settings`.
- Breakpoints Tailwind: solo `sm` 640, `lg` 1024, `xl` 1280. Sin scroll horizontal. Toque mínimo 44px en punteros táctiles.
- Colores, tipografía y geometría SOLO en `static/css/custom.css` (variables) y `components/_tailwind_config.html`.
- Versiones exactas de `requirements.txt` según el spec.

## Desvíos deliberados respecto del spec (mejoras, documentadas)

1. `entrypoint.sh` corre migraciones + seed **siempre** y después `exec "$@"`; el Dockerfile usa `ENTRYPOINT` + `CMD`. Así `docker compose` (que pisa el `CMD` con `--reload`) también migra y siembra en desarrollo. El seed arma la URL de psql desde `DATABASE_URL` o desde `POSTGRES_*`.
2. `modal_confirmacion` es un **diálogo global** (renderizado una vez en `base.html`) que se usa desde JS con `await confirmar({...})` → `true/false`. Una sola definición para todo el sistema (Principio 2). `modal.html` solo tiene `modal(...)`.
3. El tema oscuro se aplica con `x-effect` desde `<body>` (no `x-data` en `<html>`): mismo comportamiento, sin depender de que Alpine inicialice el elemento raíz.
4. `configuracion_sistema` tiene índice único `((true))` para garantizar la fila única en la base.
5. `paginacion` vive solo en `paginacion.html` (no se re-exporta desde `table.html`).

---

## File Structure

```
/docker-compose.yml, /.env.example, /.env (local, no versionado), /README.md
/backup/backup.sh                       → loop diario de pg_dump con rotación
/backend
  Dockerfile, entrypoint.sh, requirements.txt, alembic.ini, pytest.ini
  main.py                               → app FastAPI (middlewares, mounts, routers)
  config.py                             → Settings (pydantic-settings), instancia única
  /migrations/env.py, script.py.mako, seed.sql
  /migrations/versions/0001_infraestructura_base.py
  /app/__init__.py
  /app/api/__init__.py, pages.py        → rutas HTML, menú, contexto_base
  /app/api/v1/__init__.py               → api_router agregador
  /app/api/v1/health.py                 → /health y /health/db
  /app/core/__init__.py, database.py, utils.py, auditoria.py, templates.py
  /app/middleware/__init__.py           → (AuthRefreshMiddleware llega en sesión 02)
  /app/models/__init__.py, auditoria.py, configuracion.py, motivo_baja.py
  /app/schemas/__init__.py, comunes.py, auditoria.py
  /app/services/__init__.py, auditoria.py, configuracion.py
  /app/repositories/__init__.py, /app/reports/__init__.py
  /app/templates/base.html
  /app/templates/pages/index.html, pendiente.html
  /app/templates/components/_tailwind_config.html, _favicon.html, _sidebar_item.html,
      badge.html, botones.html, combobox.html, encabezado.html, form_field.html, hub.html,
      icons.html, marca.html, miniatura.html, modal.html, modal_confirmacion.html,
      paginacion.html, switch_activos.html, switch_estado.html, table.html, toast.html
  /app/templates/auth/.gitkeep, /app/templates/reports/.gitkeep
  /app/static/css/custom.css, /app/static/js/app.js
  /app/static/img/favicon.svg, favicon-32.png, apple-touch-icon.png
  /tests/__init__.py, conftest.py, test_health.py, test_utils.py, test_auditoria.py,
      test_configuracion.py, test_seed.py, test_uploads.py, test_tokens.py,
      test_componentes.py, test_marca.py, test_pages.py
```

---

### Task 1: Esqueleto Docker + FastAPI + base de datos + healthcheck

**Files:**
- Create: `docker-compose.yml`, `.env.example`, `.env`, `backend/Dockerfile`, `backend/entrypoint.sh`, `backend/requirements.txt`, `backend/alembic.ini`, `backend/pytest.ini`, `backend/config.py`, `backend/main.py`, `backend/migrations/env.py`, `backend/migrations/script.py.mako`, `backend/migrations/seed.sql` (vacío con comentario), `backend/migrations/versions/.gitkeep`, `backend/app/core/database.py`, `backend/app/api/v1/__init__.py`, `backend/app/api/v1/health.py`, `backend/app/api/pages.py` (router vacío), `backend/app/models/__init__.py` (vacío), todos los `__init__.py`, `backend/tests/conftest.py`
- Test: `backend/tests/test_health.py`

**Interfaces:**
- Produces: `config.settings` (atributos del spec + `DATABASE_URL`, `TZ`, `CORS_ORIGINS_LIST`, `UPLOADS_DIR`); `app.core.database.{engine, SessionLocal, Base, get_db}`; `app.api.v1.api_router`; `app.api.pages.router`; fixtures `db` (Session en transacción revertida) y `client` (TestClient con `get_db` sobreescrito); helper `tests.conftest.ejecutar_sql(conexion, ruta)`.

- [ ] **Step 1: Archivos de Docker y entorno**

`docker-compose.yml`:
```yaml
# Stack de desarrollo/producción de una instancia (un cliente = una instancia).
name: gestion

services:
  db:
    image: postgres:15
    container_name: gestion_db
    restart: unless-stopped
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-gestion}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-gestion}
      POSTGRES_DB: ${POSTGRES_DB:-gestion}
      TZ: America/Argentina/Buenos_Aires
      PGTZ: America/Argentina/Buenos_Aires
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "${POSTGRES_PORT_HOST:-5432}:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $${POSTGRES_USER} -d $${POSTGRES_DB}"]
      interval: 5s
      timeout: 5s
      retries: 10

  backend:
    build: ./backend
    container_name: gestion_backend
    restart: unless-stopped
    env_file: .env
    environment:
      POSTGRES_HOST: db
      POSTGRES_PORT: "5432"
      UPLOADS_DIR: /uploads
      TZ: America/Argentina/Buenos_Aires
    depends_on:
      db:
        condition: service_healthy
    volumes:
      - ./backend:/app
      - ./uploads:/uploads
    ports:
      - "${BACKEND_PORT_HOST:-8000}:8000"
      - "${BACKEND_PORT_PROD:-80}:8000"
    command: ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
    healthcheck:
      test: ["CMD", "curl", "-fsS", "http://localhost:8000/api/v1/health"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 20s

volumes:
  postgres_data:
```
(El servicio `backup` se agrega en la Task 5.)

`.env.example`:
```dotenv
# ---- Aplicación ----
APP_NAME=Sistema de Gestión
APP_ENV=development
DEBUG=false
APP_URL=http://localhost:8000
TIMEZONE=America/Argentina/Buenos_Aires

# ---- Base de datos ----
POSTGRES_USER=gestion
POSTGRES_PASSWORD=gestion
POSTGRES_DB=gestion
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
# DATABASE_URL=postgresql://usuario:clave@host:5432/base   (opcional, pisa lo anterior; ej. Railway)

# ---- Puertos del host (docker compose) ----
POSTGRES_PORT_HOST=5432
BACKEND_PORT_HOST=8000
BACKEND_PORT_PROD=80

# ---- JWT y sesión ----
JWT_SECRET=cambiar-por-un-secreto-largo-y-aleatorio
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_MINUTES=30
JWT_REFRESH_TOKEN_DAYS=7
SESION_INACTIVIDAD_MINUTOS=30
JWT_COOKIE_NAME=access_token
JWT_REFRESH_COOKIE_NAME=refresh_token
COOKIE_SECURE=false

# ---- CORS (separado por comas) ----
CORS_ORIGINS=http://localhost:8000

# ---- Email (opcional: sin SMTP_HOST no se envían mails) ----
SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM=no-reply@example.com
SMTP_TLS=true

# ---- Archivos subidos ----
UPLOADS_DIR=/uploads

# ---- Backups (servicio backup) ----
BACKUP_HORA=03:00
BACKUP_RETENCION_DIAS=14
BACKUP_AHORA=0
```

`.env` (local, ignorado por git): copia de `.env.example` con `POSTGRES_PORT_HOST=5433` y `BACKEND_PORT_PROD=8080`:
```bash
cd /Users/agustin/Documents/Stork-Gestion && sed -e 's/^POSTGRES_PORT_HOST=.*/POSTGRES_PORT_HOST=5433/' -e 's/^BACKEND_PORT_PROD=.*/BACKEND_PORT_PROD=8080/' .env.example > .env
```

`backend/Dockerfile`:
```dockerfile
FROM python:3.12-slim

ENV TZ=America/Argentina/Buenos_Aires \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Sistema: compilación de psycopg2, psql (seed), zona horaria, curl (healthcheck)
# y librerías de WeasyPrint.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libpq-dev postgresql-client tzdata curl \
        libpango-1.0-0 libpangoft2-1.0-0 libcairo2 libgdk-pixbuf-2.0-0 \
        libffi-dev shared-mime-info fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# requirements antes que el código: cache de capas
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chmod +x entrypoint.sh

ENTRYPOINT ["./entrypoint.sh"]
CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
```

`backend/entrypoint.sh`:
```sh
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
```
Luego: `chmod +x backend/entrypoint.sh`.

`backend/requirements.txt`: exactamente el bloque del spec (sección 4), una dependencia por línea, conservando el comentario de `python-barcode`.

- [ ] **Step 2: Config, base de datos y app**

`backend/config.py`:
```python
"""Configuración única del sistema, leída del entorno / .env.

Ningún módulo lee os.environ directamente: todos importan `settings`.
"""
from zoneinfo import ZoneInfo

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    # Aplicación
    APP_NAME: str = "Sistema de Gestión"
    APP_ENV: str = "development"  # development | production (| test)
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"
    APP_URL: str = "http://localhost:8000"
    TIMEZONE: str = "America/Argentina/Buenos_Aires"

    # Base de datos
    POSTGRES_USER: str = "gestion"
    POSTGRES_PASSWORD: str = "gestion"
    POSTGRES_DB: str = "gestion"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    DATABASE_URL_OVERRIDE: str | None = Field(default=None, alias="DATABASE_URL")

    # JWT y sesión
    JWT_SECRET: str = "cambiar-en-produccion"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_MINUTES: int = 30
    JWT_REFRESH_TOKEN_DAYS: int = 7
    SESION_INACTIVIDAD_MINUTOS: int = 30  # debe ser >= JWT_ACCESS_TOKEN_MINUTES
    JWT_COOKIE_NAME: str = "access_token"
    JWT_REFRESH_COOKIE_NAME: str = "refresh_token"
    COOKIE_SECURE: bool = False

    # CORS
    CORS_ORIGINS: str = "http://localhost:8000"

    # SMTP
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_FROM: str = "no-reply@example.com"
    SMTP_TLS: bool = True

    # Archivos subidos (volumen persistente)
    UPLOADS_DIR: str = "/uploads"

    # Backups (los usa el servicio backup; se documentan acá)
    BACKUP_HORA: str = "03:00"
    BACKUP_RETENCION_DIAS: int = 14

    @property
    def TZ(self) -> ZoneInfo:
        return ZoneInfo(self.TIMEZONE)

    @property
    def DATABASE_URL(self) -> str:
        """URL SQLAlchemy. DATABASE_URL (si viene) pisa las variables POSTGRES_*."""
        if self.DATABASE_URL_OVERRIDE:
            url = self.DATABASE_URL_OVERRIDE
            for prefijo in ("postgres://", "postgresql://"):
                if url.startswith(prefijo):
                    return "postgresql+psycopg2://" + url[len(prefijo):]
            return url
        return (
            f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def CORS_ORIGINS_LIST(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


settings = Settings()
```

`backend/app/core/database.py`:
```python
"""Motor, sesión y base declarativa de SQLAlchemy."""
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from config import settings

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    echo=settings.DEBUG and settings.APP_ENV == "development",
    # Todas las columnas son TIMESTAMP sin zona en hora del negocio:
    # la conexión fija la zona para que now() sea coherente en cualquier servidor.
    connect_args={"options": f"-c timezone={settings.TIMEZONE}"},
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    """Dependency de FastAPI: una sesión por request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

`backend/app/api/v1/health.py`:
```python
"""Healthchecks: /health no toca la base; /health/db sí."""
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.database import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/health/db")
def health_db(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "database": "error", "detalle": str(exc.__cause__ or exc)},
        )
    return {"status": "ok", "database": "ok"}
```

`backend/app/api/v1/__init__.py`:
```python
"""Router único de la API v1: agrega los routers de cada módulo."""
from fastapi import APIRouter

from app.api.v1 import health

api_router = APIRouter()
api_router.include_router(health.router)
```

`backend/app/api/pages.py` (se completa en la Task 7):
```python
"""Rutas HTML (Jinja2). Fuera del esquema OpenAPI."""
from fastapi import APIRouter

router = APIRouter(include_in_schema=False)
```

`backend/main.py`:
```python
"""Punto de entrada de la aplicación FastAPI."""
import importlib
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.pages import router as pages_router
from app.api.v1 import api_router
from config import settings

BASE_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Registra todos los modelos en el metadata de SQLAlchemy.
    importlib.import_module("app.models")
    yield


docs_habilitadas = settings.APP_ENV != "production"

app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if docs_habilitadas else None,
    redoc_url="/redoc" if docs_habilitadas else None,
    openapi_url="/openapi.json" if docs_habilitadas else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS_LIST,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Punto de montaje del AuthRefreshMiddleware (sesión 02):
# app.add_middleware(AuthRefreshMiddleware)

app.mount("/static", StaticFiles(directory=BASE_DIR / "app" / "static"), name="static")

# La API tiene prioridad: las páginas HTML se montan al final.
app.include_router(api_router, prefix=settings.API_V1_PREFIX)
app.include_router(pages_router)
```
Crear `backend/app/static/css/`, `js/`, `img/` con un `.gitkeep` cada uno para que `StaticFiles` encuentre el directorio.

- [ ] **Step 3: Alembic y pytest**

`backend/alembic.ini`:
```ini
[alembic]
script_location = migrations
prepend_sys_path = .
file_template = %%(rev)s_%%(slug)s
```

`backend/migrations/env.py`:
```python
"""Entorno de Alembic: toma la URL de config.settings (nunca del .ini)."""
from alembic import context
from sqlalchemy import create_engine, pool

import app.models  # noqa: F401  (registra los modelos)
from app.core.database import Base
from config import settings

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(url=settings.DATABASE_URL, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(settings.DATABASE_URL, poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

`backend/migrations/script.py.mako`:
```mako
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""
from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

`backend/migrations/seed.sql`:
```sql
-- Datos iniciales del sistema. IDEMPOTENTE: se puede ejecutar N veces.
-- No usar el carácter de porcentaje en este archivo (lo ejecuta también psycopg2 en los tests).
```

`backend/pytest.ini`:
```ini
[pytest]
pythonpath = .
testpaths = tests
addopts = -q
```

`backend/tests/conftest.py`:
```python
"""Fixtures comunes. Los tests corren contra PostgreSQL real, en la base
`gestion_test`, que se recrea en cada corrida; cada test corre en una
transacción que se revierte al final (así se prueban triggers y UNIQUE)."""
import os
import tempfile

# Antes de importar la app: base y carpeta de uploads de test.
os.environ["POSTGRES_DB"] = os.environ.get("POSTGRES_DB_TEST", "gestion_test")
os.environ.pop("DATABASE_URL", None)
os.environ["UPLOADS_DIR"] = tempfile.mkdtemp(prefix="uploads_test_")
os.environ["APP_ENV"] = "test"

from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from config import settings  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parents[1]


def ejecutar_sql(conexion, ruta: Path) -> None:
    """Ejecuta un archivo .sql completo (varias sentencias, bloques DO)."""
    conexion.exec_driver_sql(ruta.read_text(encoding="utf-8"))


def _recrear_base() -> None:
    url_admin = settings.DATABASE_URL.rsplit("/", 1)[0] + "/postgres"
    admin = create_engine(url_admin, isolation_level="AUTOCOMMIT")
    with admin.connect() as conexion:
        conexion.execute(text(f'DROP DATABASE IF EXISTS "{settings.POSTGRES_DB}" WITH (FORCE)'))
        conexion.execute(text(f'CREATE DATABASE "{settings.POSTGRES_DB}"'))
    admin.dispose()


@pytest.fixture(scope="session", autouse=True)
def base_de_test():
    _recrear_base()
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    command.upgrade(cfg, "head")

    from app.core.database import engine

    with engine.begin() as conexion:
        ejecutar_sql(conexion, BACKEND_DIR / "migrations" / "seed.sql")
    yield
    engine.dispose()


@pytest.fixture
def db():
    from app.core.database import engine

    conexion = engine.connect()
    transaccion = conexion.begin()
    sesion = Session(
        bind=conexion,
        join_transaction_mode="create_savepoint",
        autoflush=False,
        expire_on_commit=False,
    )
    try:
        yield sesion
    finally:
        sesion.close()
        transaccion.rollback()
        conexion.close()


@pytest.fixture
def client(db):
    from app.core.database import get_db
    from main import app

    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as cliente:
        yield cliente
    app.dependency_overrides.clear()
```
El seed vacío (solo comentarios) se ejecuta sin error.

- [ ] **Step 4: Escribir el test**

`backend/tests/test_health.py`:
```python
from sqlalchemy.exc import OperationalError

from app.core.database import get_db


def test_health_no_toca_la_base(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_health_db_ok(client):
    r = client.get("/api/v1/health/db")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "database": "ok"}


def test_health_db_caida(client):
    from main import app

    class SesionCaida:
        def execute(self, *args, **kwargs):
            raise OperationalError("SELECT 1", {}, Exception("sin conexión"))

    app.dependency_overrides[get_db] = lambda: SesionCaida()
    r = client.get("/api/v1/health/db")
    assert r.status_code == 503
    cuerpo = r.json()
    assert cuerpo["status"] == "degraded" and cuerpo["database"] == "error"
    assert "sin conexión" in cuerpo["detalle"]


def test_swagger_disponible_fuera_de_produccion(client):
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200
```

- [ ] **Step 5: Levantar y correr los tests**

Requiere Docker Desktop corriendo (`open -a Docker` y esperar a que `docker info` responda).
```bash
cd /Users/agustin/Documents/Stork-Gestion && docker compose up -d --build && docker compose ps
docker compose exec backend pytest tests/test_health.py -v
curl -fsS http://localhost:8000/api/v1/health && curl -fsS http://localhost:8000/api/v1/health/db
```
Expected: `db` y `backend` healthy; 4 tests PASS; ambos curl con `"status":"ok"`.

- [ ] **Step 6: Commit** — `git add` de los archivos de la tarea y `git commit` en la rama (ver Global Constraints). Verificar que `.env` NO aparece (está en `.gitignore`).

---

### Task 2: Utilidades transversales (`core/utils.py`)

**Files:**
- Create: `backend/app/core/utils.py`
- Test: `backend/tests/test_utils.py`

**Interfaces:**
- Produces: `ahora() -> datetime` (aware), `ahora_db() -> datetime` (naive, hora del negocio), `ip_de_request(request) -> str | None`, `redondear(valor, decimales=2) -> Decimal`, `redondear_hacia_arriba(valor, multiplo) -> Decimal`, `redondear_hacia_abajo(valor, multiplo) -> Decimal`, `normalizar_texto(texto) -> str | None`, `capitalizar_inicial(texto) -> str | None`, `sin_tildes(texto) -> str | None`, `sin_tildes_sql(columna)` (expresión SQL), `TILDES`, `SIN_TILDES`.

- [ ] **Step 1: Test que falla**

`backend/tests/test_utils.py`:
```python
from datetime import timezone
from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy import literal, select

from app.core.utils import (
    ahora,
    ahora_db,
    capitalizar_inicial,
    ip_de_request,
    normalizar_texto,
    redondear,
    redondear_hacia_abajo,
    redondear_hacia_arriba,
    sin_tildes,
    sin_tildes_sql,
)


def test_ahora_con_zona_y_ahora_db_sin_zona():
    assert ahora().tzinfo is not None
    assert ahora().utcoffset() is not None
    assert ahora_db().tzinfo is None
    # ahora_db es la misma hora local, sin zona
    assert abs((ahora().replace(tzinfo=None) - ahora_db()).total_seconds()) < 2


def test_redondear_half_up():
    assert redondear(Decimal("2.345")) == Decimal("2.35")
    assert redondear(Decimal("2.344")) == Decimal("2.34")
    assert redondear(2.5, 0) == Decimal("3")
    assert redondear("10") == Decimal("10.00")


def test_redondear_hacia_arriba_al_multiplo():
    assert redondear_hacia_arriba(Decimal("12001"), Decimal("1000")) == Decimal("13000.00")
    assert redondear_hacia_arriba(Decimal("12000"), 1000) == Decimal("12000.00")
    assert redondear_hacia_arriba(Decimal("0.01"), 100) == Decimal("100.00")


def test_redondear_hacia_arriba_multiplo_no_positivo_no_redondea():
    assert redondear_hacia_arriba(Decimal("12001.555"), 0) == Decimal("12001.56")
    assert redondear_hacia_arriba(Decimal("12001.5"), -5) == Decimal("12001.50")


def test_redondear_hacia_abajo_al_multiplo():
    assert redondear_hacia_abajo(Decimal("12999"), 1000) == Decimal("12000.00")
    assert redondear_hacia_abajo(Decimal("12000"), 1000) == Decimal("12000.00")
    assert redondear_hacia_abajo(Decimal("99.99"), 0) == Decimal("99.99")


def test_normalizar_texto():
    assert normalizar_texto("  hola    mundo ") == "hola mundo"
    assert normalizar_texto("   ") is None
    assert normalizar_texto("") is None
    assert normalizar_texto(None) is None


def test_capitalizar_inicial_no_toca_el_resto():
    assert capitalizar_inicial("remera AZUL talle M") == "Remera AZUL talle M"
    assert capitalizar_inicial("  ñandú  ") == "Ñandú"
    assert capitalizar_inicial(None) is None


def test_sin_tildes():
    assert sin_tildes("Córdoba Ñandú pingüino ÁÉÍÓÚÜ") == "Cordoba Nandu pinguino AEIOUU"
    assert sin_tildes(None) is None


def test_sin_tildes_sql_usa_la_misma_tabla(db):
    assert db.scalar(select(sin_tildes_sql(literal("Córdoba Ñandú")))) == "Cordoba Nandu"


def test_ip_de_request_respeta_x_forwarded_for():
    con_proxy = SimpleNamespace(
        headers={"x-forwarded-for": "200.1.1.1, 10.0.0.1"}, client=SimpleNamespace(host="10.0.0.2")
    )
    directo = SimpleNamespace(headers={}, client=SimpleNamespace(host="10.0.0.2"))
    sin_cliente = SimpleNamespace(headers={}, client=None)
    assert ip_de_request(con_proxy) == "200.1.1.1"
    assert ip_de_request(directo) == "10.0.0.2"
    assert ip_de_request(sin_cliente) is None
```

- [ ] **Step 2: Correr y ver que falla**

Run: `docker compose exec backend pytest tests/test_utils.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.utils'`.

- [ ] **Step 3: Implementación**

`backend/app/core/utils.py`:
```python
"""Utilidades transversales (Principio 2: una sola definición)."""
from datetime import datetime
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, Decimal

from sqlalchemy import func

from config import settings

# Misma tabla de reemplazo en Python y en SQL (translate de Postgres; no se
# usa la extensión unaccent porque exige superusuario).
TILDES = "áéíóúüñÁÉÍÓÚÜÑ"
SIN_TILDES = "aeiouunAEIOUUN"
_TABLA_TILDES = str.maketrans(TILDES, SIN_TILDES)

_CENTAVOS = Decimal("0.01")


def ahora() -> datetime:
    """Fecha y hora actual con la zona del negocio (cálculos, JWT)."""
    return datetime.now(settings.TZ)


def ahora_db() -> datetime:
    """Fecha y hora del negocio SIN tzinfo: las columnas son TIMESTAMP sin zona."""
    return ahora().replace(tzinfo=None)


def ip_de_request(request) -> str | None:
    """IP del cliente, respetando X-Forwarded-For (primer salto) detrás de un proxy."""
    reenviada = request.headers.get("x-forwarded-for")
    if reenviada:
        return reenviada.split(",")[0].strip() or None
    return request.client.host if request.client else None


def _decimal(valor) -> Decimal:
    return valor if isinstance(valor, Decimal) else Decimal(str(valor))


def redondear(valor, decimales: int = 2) -> Decimal:
    """Redondeo comercial (half-up)."""
    return _decimal(valor).quantize(Decimal(1).scaleb(-decimales), rounding=ROUND_HALF_UP)


def _redondear_al_multiplo(valor, multiplo, modo) -> Decimal:
    valor, multiplo = _decimal(valor), _decimal(multiplo)
    if multiplo <= 0:
        return redondear(valor)
    return ((valor / multiplo).to_integral_value(rounding=modo) * multiplo).quantize(_CENTAVOS)


def redondear_hacia_arriba(valor, multiplo) -> Decimal:
    """CEIL al múltiplo (precio de venta). Múltiplo <= 0: no redondea (solo a centavos)."""
    return _redondear_al_multiplo(valor, multiplo, ROUND_CEILING)


def redondear_hacia_abajo(valor, multiplo) -> Decimal:
    """FLOOR al múltiplo (precios con descuento). Múltiplo <= 0: no redondea."""
    return _redondear_al_multiplo(valor, multiplo, ROUND_FLOOR)


def normalizar_texto(texto: str | None) -> str | None:
    """Colapsa espacios; un texto vacío pasa a None."""
    if texto is None:
        return None
    limpio = " ".join(texto.split())
    return limpio or None


def capitalizar_inicial(texto: str | None) -> str | None:
    """Solo la primera letra en mayúscula; el resto queda como vino."""
    limpio = normalizar_texto(texto)
    if limpio is None:
        return None
    return limpio[0].upper() + limpio[1:]


def sin_tildes(texto: str | None) -> str | None:
    return texto.translate(_TABLA_TILDES) if texto is not None else None


def sin_tildes_sql(columna):
    """Expresión SQL equivalente a sin_tildes() (para ILIKE insensible a tildes)."""
    return func.translate(columna, TILDES, SIN_TILDES)
```

- [ ] **Step 4: Correr y ver que pasa**

Run: `docker compose exec backend pytest tests/test_utils.py -v`
Expected: 10 PASS.

- [ ] **Step 5: Commit** — `git add` de los archivos de la tarea y `git commit` en la rama (ver Global Constraints).

---

### Task 3: Migración 0001, modelos, auditoría y configuración

**Files:**
- Create: `backend/migrations/versions/0001_infraestructura_base.py`, `backend/app/models/auditoria.py`, `backend/app/models/configuracion.py`, `backend/app/models/motivo_baja.py`, `backend/app/core/auditoria.py`, `backend/app/services/auditoria.py`, `backend/app/services/configuracion.py`, `backend/app/schemas/comunes.py`, `backend/app/schemas/auditoria.py`
- Modify: `backend/app/models/__init__.py`
- Test: `backend/tests/test_auditoria.py`, `backend/tests/test_configuracion.py`

**Interfaces:**
- Consumes: `Base`, `ahora_db`, `ip_de_request`.
- Produces: modelos `Auditoria`, `ConfiguracionSistema`, `MotivoBaja`; `registrar_auditoria(db, *, accion, entidad, usuario_id=None, entidad_id=None, estado_anterior=None, estado_nuevo=None, ip_origen=None, request=None) -> Auditoria`; `snapshot(obj, campos=None) -> dict | None`; `CAMPOS_SENSIBLES`; `listar_auditoria(db, *, usuario_id=None, accion=None, entidad=None, entidad_id=None, desde=None, hasta=None, pagina=1, tamano=50) -> tuple[list[Auditoria], int]`; `TAMANO_MAXIMO_AUDITORIA = 200`; `obtener_configuracion(db) -> ConfiguracionSistema`; schemas `RespuestaPaginada[T]` (`total, pagina, tamano, resultados`), `MensajeResponse` (`mensaje`), `AuditoriaResponse`.

- [ ] **Step 1: Tests que fallan**

`backend/tests/test_auditoria.py`:
```python
from datetime import date, timedelta
from decimal import Decimal
from enum import Enum

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.auditoria import registrar_auditoria, snapshot
from app.core.utils import ahora_db
from app.models import MotivoBaja
from app.services.auditoria import listar_auditoria


class Color(Enum):
    ROJO = "rojo"


def test_registrar_auditoria_guarda_json_seguro_sin_sensibles(db):
    registro = registrar_auditoria(
        db,
        accion="prueba.crear",
        entidad="prueba",
        entidad_id=7,
        usuario_id=3,
        ip_origen="200.1.1.1",
        estado_nuevo={
            "precio": Decimal("10.50"),
            "cuando": date(2026, 1, 2),
            "color": Color.ROJO,
            "password_hash": "secreto",
            "clave_especial": "1234",
        },
    )
    assert registro.id is not None
    assert registro.estado_nuevo == {"precio": "10.50", "cuando": "2026-01-02", "color": "rojo"}
    assert registro.estado_anterior is None
    assert registro.timestamp.tzinfo is None
    assert abs((ahora_db() - registro.timestamp).total_seconds()) < 5


def test_snapshot_de_modelo_y_campos(db):
    motivo = MotivoBaja(nombre="Prueba snapshot", activo=True)
    db.add(motivo)
    db.flush()
    assert snapshot(motivo) == {"id": motivo.id, "nombre": "Prueba snapshot", "activo": True}
    assert snapshot(motivo, campos=["nombre"]) == {"nombre": "Prueba snapshot"}
    assert snapshot(None) is None


@pytest.mark.parametrize(
    "sentencia",
    ["UPDATE auditoria SET accion = 'x'", "DELETE FROM auditoria", "TRUNCATE auditoria"],
)
def test_auditoria_es_inmutable_en_la_base(db, sentencia):
    registrar_auditoria(db, accion="prueba.inmutable", entidad="prueba")
    with pytest.raises(DBAPIError) as error:
        db.execute(text(sentencia))
    assert "solo inserción" in str(error.value)


def test_listar_auditoria_filtra_y_ordena(db):
    for accion, usuario in [("zzventa.crear", 1), ("zzventa.anular", 2), ("zzproducto.editar", 1)]:
        registrar_auditoria(db, accion=accion, entidad=accion.split(".")[0], usuario_id=usuario, entidad_id=5)

    registros, total = listar_auditoria(db, accion="zzventa.")
    assert total == 2
    assert [r.accion for r in registros] == ["zzventa.anular", "zzventa.crear"]  # timestamp desc, id desc

    _, total = listar_auditoria(db, accion="zz", usuario_id=1)
    assert total == 2
    _, total = listar_auditoria(db, entidad="ZZPRODUCTO", entidad_id=5)
    assert total == 1

    hoy = ahora_db().date()
    _, total = listar_auditoria(db, accion="zz", desde=hoy, hasta=hoy)
    assert total == 3
    _, total = listar_auditoria(db, accion="zz", desde=hoy + timedelta(days=1))
    assert total == 0


def test_listar_auditoria_pagina_y_limita_tamano(db):
    for i in range(3):
        registrar_auditoria(db, accion=f"zzpag.{i}", entidad="zzpag")
    registros, total = listar_auditoria(db, accion="zzpag.", pagina=2, tamano=2)
    assert total == 3 and len(registros) == 1
    registros, _ = listar_auditoria(db, accion="zzpag.", tamano=10_000)
    assert len(registros) == 3  # el tope (200) no rompe
```

`backend/tests/test_configuracion.py`:
```python
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.services.configuracion import obtener_configuracion


def test_obtener_configuracion_devuelve_los_valores_del_seed(db):
    config = obtener_configuracion(db)
    assert config.redondeo == Decimal("1000.00")
    assert config.margen_default == Decimal("100.00")
    assert config.descuento_maximo == Decimal("30.00")
    assert config.tope_descuento_venta == Decimal("50.00")


def test_configuracion_es_fila_unica(db):
    with pytest.raises(IntegrityError):
        db.execute(
            text(
                "INSERT INTO configuracion_sistema (redondeo, margen_default, descuento_maximo, tope_descuento_venta) "
                "VALUES (1, 1, 1, 1)"
            )
        )


@pytest.mark.parametrize(
    "columna, valor",
    [("descuento_maximo", 101), ("tope_descuento_venta", -1), ("margen_default", 1001), ("redondeo", -1)],
)
def test_configuracion_rechaza_valores_fuera_de_rango(db, columna, valor):
    with pytest.raises(IntegrityError):
        db.execute(text(f"UPDATE configuracion_sistema SET {columna} = :valor"), {"valor": valor})
```
Nota: estos tests necesitan el seed de la Task 4 para `obtener_configuracion`. En esta tarea se escribe también el INSERT de `configuracion_sistema` en el seed (ver Step 3, al final) para que pasen; la Task 4 completa y prueba la idempotencia.

- [ ] **Step 2: Correr y ver que falla**

Run: `docker compose exec backend pytest tests/test_auditoria.py tests/test_configuracion.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.auditoria'`.

- [ ] **Step 3: Implementación**

`backend/migrations/versions/0001_infraestructura_base.py`:
```python
"""Infraestructura base: auditoría inmutable, configuración del sistema y motivos de baja.

Revision ID: 0001
Revises:
"""
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE auditoria (
            id              BIGSERIAL PRIMARY KEY,
            usuario_id      BIGINT,                 -- NULL = sistema. Sin FK: el registro sobrevive al usuario
            accion          VARCHAR(100) NOT NULL,  -- "<entidad>.<verbo>"
            entidad         VARCHAR(100) NOT NULL,
            entidad_id      BIGINT,
            estado_anterior JSONB,
            estado_nuevo    JSONB,
            ip_origen       VARCHAR(45),
            timestamp       TIMESTAMP NOT NULL DEFAULT now()
        );
        CREATE INDEX ix_auditoria_usuario_id ON auditoria (usuario_id);
        CREATE INDEX ix_auditoria_accion ON auditoria (accion);
        CREATE INDEX ix_auditoria_entidad ON auditoria (entidad);
        CREATE INDEX ix_auditoria_timestamp ON auditoria (timestamp);
        CREATE INDEX ix_auditoria_entidad_entidad_id ON auditoria (entidad, entidad_id);

        -- Inmutabilidad (capa 1): triggers a nivel sentencia.
        CREATE FUNCTION auditoria_bloquear_modificacion() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'La tabla auditoria es de solo inserción (operación % bloqueada)', TG_OP
                USING ERRCODE = 'insufficient_privilege';
        END;
        $$;
        CREATE TRIGGER trg_auditoria_no_update BEFORE UPDATE ON auditoria
            FOR EACH STATEMENT EXECUTE FUNCTION auditoria_bloquear_modificacion();
        CREATE TRIGGER trg_auditoria_no_delete BEFORE DELETE ON auditoria
            FOR EACH STATEMENT EXECUTE FUNCTION auditoria_bloquear_modificacion();
        CREATE TRIGGER trg_auditoria_no_truncate BEFORE TRUNCATE ON auditoria
            FOR EACH STATEMENT EXECUTE FUNCTION auditoria_bloquear_modificacion();

        -- Inmutabilidad (capa 2): defensa en profundidad. Si el rol es
        -- superusuario, lo que cuenta es el trigger.
        REVOKE UPDATE, DELETE, TRUNCATE ON auditoria FROM CURRENT_USER;

        CREATE TABLE configuracion_sistema (
            id                   BIGSERIAL PRIMARY KEY,
            redondeo             NUMERIC(10,2) NOT NULL CHECK (redondeo >= 0),
            margen_default       NUMERIC(6,2)  NOT NULL CHECK (margen_default BETWEEN 0 AND 1000),
            descuento_maximo     NUMERIC(5,2)  NOT NULL CHECK (descuento_maximo BETWEEN 0 AND 100),
            tope_descuento_venta NUMERIC(5,2)  NOT NULL CHECK (tope_descuento_venta BETWEEN 0 AND 100),
            updated_at           TIMESTAMP NOT NULL DEFAULT now(),
            updated_by           BIGINT      -- FK a usuarios en la migración 0002
        );
        -- Fila única garantizada en la base.
        CREATE UNIQUE INDEX uq_configuracion_sistema_fila_unica ON configuracion_sistema ((true));

        CREATE TABLE motivos_baja (
            id     BIGSERIAL PRIMARY KEY,
            nombre VARCHAR(100) NOT NULL UNIQUE,
            activo BOOLEAN NOT NULL DEFAULT TRUE
        );
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE motivos_baja;
        DROP TABLE configuracion_sistema;
        DROP TABLE auditoria;
        DROP FUNCTION auditoria_bloquear_modificacion();
        """
    )
```

`backend/app/models/auditoria.py`:
```python
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Auditoria(Base):
    """Registro append-only (la base rechaza UPDATE/DELETE/TRUNCATE)."""

    __tablename__ = "auditoria"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # Sin FK a usuarios a propósito: la auditoría debe sobrevivir al usuario.
    usuario_id: Mapped[int | None] = mapped_column(BigInteger)
    accion: Mapped[str] = mapped_column(String(100))
    entidad: Mapped[str] = mapped_column(String(100))
    entidad_id: Mapped[int | None] = mapped_column(BigInteger)
    estado_anterior: Mapped[dict | None] = mapped_column(JSONB)
    estado_nuevo: Mapped[dict | None] = mapped_column(JSONB)
    ip_origen: Mapped[str | None] = mapped_column(String(45))
    timestamp: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
```

`backend/app/models/configuracion.py`:
```python
from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ConfiguracionSistema(Base):
    """Fila única con los parámetros comerciales del sistema."""

    __tablename__ = "configuracion_sistema"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    redondeo: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    margen_default: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    descuento_maximo: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    tope_descuento_venta: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_by: Mapped[int | None] = mapped_column(BigInteger)
```

`backend/app/models/motivo_baja.py`:
```python
from sqlalchemy import BigInteger, Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MotivoBaja(Base):
    """Catálogo de motivos de baja de stock (lo usa la sesión 05)."""

    __tablename__ = "motivos_baja"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(100), unique=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
```

`backend/app/models/__init__.py`:
```python
"""Registro de todos los modelos (lo importan main.lifespan y Alembic)."""
from app.models.auditoria import Auditoria
from app.models.configuracion import ConfiguracionSistema
from app.models.motivo_baja import MotivoBaja

__all__ = ["Auditoria", "ConfiguracionSistema", "MotivoBaja"]
```

`backend/app/core/auditoria.py`:
```python
"""Única vía de escritura de la auditoría (Principio 3).

registrar_auditoria hace add + flush y NUNCA commit: el registro viaja en la
misma transacción que la acción auditada.
"""
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
from uuid import UUID

from sqlalchemy import inspect

from app.core.utils import ahora_db, ip_de_request
from app.models.auditoria import Auditoria

CAMPOS_SENSIBLES = frozenset(
    {
        "password",
        "password_hash",
        "clave_especial",
        "clave_especial_hash",
        "pin",
        "pin_hash",
        "token",
        "access_token",
        "refresh_token",
    }
)


def _valor_json(valor):
    if isinstance(valor, Enum):
        return valor.value
    if isinstance(valor, Decimal):
        return str(valor)
    if isinstance(valor, (datetime, date, time)):
        return valor.isoformat()
    if isinstance(valor, UUID):
        return str(valor)
    if isinstance(valor, dict):
        return {str(k): _valor_json(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple, set)):
        return [_valor_json(v) for v in valor]
    return valor


def snapshot(obj, campos=None) -> dict | None:
    """Modelo SQLAlchemy o dict → dict JSON-safe sin campos sensibles."""
    if obj is None:
        return None
    if isinstance(obj, dict):
        datos = dict(obj)
    else:
        datos = {attr.key: getattr(obj, attr.key) for attr in inspect(obj).mapper.column_attrs}
    if campos is not None:
        datos = {k: datos[k] for k in campos if k in datos}
    return {k: _valor_json(v) for k, v in datos.items() if k not in CAMPOS_SENSIBLES}


def registrar_auditoria(
    db,
    *,
    accion: str,
    entidad: str,
    usuario_id: int | None = None,
    entidad_id: int | None = None,
    estado_anterior=None,
    estado_nuevo=None,
    ip_origen: str | None = None,
    request=None,
) -> Auditoria:
    if ip_origen is None and request is not None:
        ip_origen = ip_de_request(request)
    registro = Auditoria(
        usuario_id=usuario_id,
        accion=accion,
        entidad=entidad,
        entidad_id=entidad_id,
        estado_anterior=snapshot(estado_anterior),
        estado_nuevo=snapshot(estado_nuevo),
        ip_origen=ip_origen,
        timestamp=ahora_db(),
    )
    db.add(registro)
    db.flush()
    return registro
```

`backend/app/services/auditoria.py`:
```python
"""Consulta de la auditoría (solo lectura). El endpoint llega en la sesión 02."""
from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select

from app.models.auditoria import Auditoria

TAMANO_MAXIMO_AUDITORIA = 200


def listar_auditoria(
    db,
    *,
    usuario_id: int | None = None,
    accion: str | None = None,
    entidad: str | None = None,
    entidad_id: int | None = None,
    desde: date | None = None,
    hasta: date | None = None,
    pagina: int = 1,
    tamano: int = 50,
) -> tuple[list[Auditoria], int]:
    condiciones = []
    if usuario_id is not None:
        condiciones.append(Auditoria.usuario_id == usuario_id)
    if accion:
        condiciones.append(Auditoria.accion.ilike(f"%{accion}%"))
    if entidad:
        condiciones.append(Auditoria.entidad.ilike(f"%{entidad}%"))
    if entidad_id is not None:
        condiciones.append(Auditoria.entidad_id == entidad_id)
    if desde:
        condiciones.append(Auditoria.timestamp >= datetime.combine(desde, time.min))
    if hasta:  # inclusivo: todo el día "hasta"
        condiciones.append(Auditoria.timestamp < datetime.combine(hasta + timedelta(days=1), time.min))

    tamano = max(1, min(tamano, TAMANO_MAXIMO_AUDITORIA))
    pagina = max(1, pagina)

    total = db.scalar(select(func.count()).select_from(Auditoria).where(*condiciones))
    registros = db.scalars(
        select(Auditoria)
        .where(*condiciones)
        .order_by(Auditoria.timestamp.desc(), Auditoria.id.desc())
        .offset((pagina - 1) * tamano)
        .limit(tamano)
    ).all()
    return list(registros), total
```

`backend/app/services/configuracion.py`:
```python
"""Lectura de configuracion_sistema: única vía para todos los services."""
from sqlalchemy import select

from app.models.configuracion import ConfiguracionSistema


def obtener_configuracion(db) -> ConfiguracionSistema:
    config = db.scalar(select(ConfiguracionSistema).limit(1))
    if config is None:
        raise RuntimeError("Falta la fila de configuracion_sistema: ejecutar migrations/seed.sql")
    return config
```

`backend/app/schemas/comunes.py`:
```python
"""Esquemas compartidos por todos los módulos."""
from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class RespuestaPaginada(BaseModel, Generic[T]):
    """Envoltorio estándar de todos los listados paginados."""

    total: int
    pagina: int
    tamano: int
    resultados: list[T]


class MensajeResponse(BaseModel):
    mensaje: str
```

`backend/app/schemas/auditoria.py`:
```python
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AuditoriaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    usuario_id: int | None
    accion: str
    entidad: str
    entidad_id: int | None
    estado_anterior: dict | None
    estado_nuevo: dict | None
    ip_origen: str | None
    timestamp: datetime
```

Agregar al final de `backend/migrations/seed.sql`:
```sql
-- Configuración del sistema (fila única).
INSERT INTO configuracion_sistema (redondeo, margen_default, descuento_maximo, tope_descuento_venta)
SELECT 1000.00, 100.00, 30.00, 50.00
WHERE NOT EXISTS (SELECT 1 FROM configuracion_sistema);
```

- [ ] **Step 4: Migrar y correr los tests**

```bash
docker compose restart backend   # el entrypoint aplica la migración y el seed
docker compose exec backend alembic current     # Expected: 0001 (head)
docker compose exec backend pytest tests/test_auditoria.py tests/test_configuracion.py -v
```
Expected: todos PASS (10 tests).

- [ ] **Step 5: Commit** — `git add` de los archivos de la tarea y `git commit` en la rama (ver Global Constraints).

---

### Task 4: Seed idempotente completo

**Files:**
- Modify: `backend/migrations/seed.sql`
- Test: `backend/tests/test_seed.py`

**Interfaces:**
- Consumes: `tests.conftest.ejecutar_sql`, `BACKEND_DIR`.
- Produces: seed con configuración, motivos de baja y `sistema.seed`; convención para sesiones futuras: bloques `DO $$ … IF to_regclass('public.<tabla>') IS NULL THEN RAISE NOTICE …; RETURN; END IF; … $$;`.

- [ ] **Step 1: Test que falla**

`backend/tests/test_seed.py`:
```python
from sqlalchemy import text

from tests.conftest import BACKEND_DIR, ejecutar_sql

SEED = BACKEND_DIR / "migrations" / "seed.sql"


def _contar(db, sql):
    return db.execute(text(sql)).scalar_one()


def test_seed_es_idempotente(db):
    conexion = db.connection()
    ejecutar_sql(conexion, SEED)
    ejecutar_sql(conexion, SEED)

    assert _contar(db, "SELECT count(*) FROM configuracion_sistema") == 1
    nombres = db.execute(text("SELECT nombre FROM motivos_baja ORDER BY nombre")).scalars().all()
    assert nombres == ["Merma", "Muestra", "Robo", "Rotura"]
    assert _contar(db, "SELECT count(*) FROM auditoria WHERE accion = 'sistema.seed'") == 1


def test_seed_no_usa_el_caracter_porcentaje():
    # psycopg2 interpreta ese carácter al ejecutar el archivo desde los tests.
    assert "%" not in SEED.read_text(encoding="utf-8")
```

- [ ] **Step 2: Correr y ver que falla**

Run: `docker compose exec backend pytest tests/test_seed.py -v`
Expected: FAIL — la lista de motivos está vacía y no hay `sistema.seed`.

- [ ] **Step 3: Completar el seed**

`backend/migrations/seed.sql` completo:
```sql
-- Datos iniciales del sistema. IDEMPOTENTE: se puede ejecutar N veces.
-- Cada sesión agrega su bloque al final. Los bloques que dependen de tablas
-- de sesiones posteriores se protegen con to_regclass(...) IS NULL → RETURN.
-- No usar el carácter de porcentaje en este archivo (lo ejecuta también psycopg2 en los tests).

-- ===== Sesión 01 =====

-- Configuración del sistema (fila única).
INSERT INTO configuracion_sistema (redondeo, margen_default, descuento_maximo, tope_descuento_venta)
SELECT 1000.00, 100.00, 30.00, 50.00
WHERE NOT EXISTS (SELECT 1 FROM configuracion_sistema);

-- Motivos de baja de stock.
INSERT INTO motivos_baja (nombre) VALUES ('Rotura'), ('Robo'), ('Muestra'), ('Merma')
ON CONFLICT (nombre) DO NOTHING;

-- Marca de que el seed corrió (una sola vez).
INSERT INTO auditoria (usuario_id, accion, entidad, estado_nuevo)
SELECT NULL, 'sistema.seed', 'sistema', jsonb_build_object('sesion', '01')
WHERE NOT EXISTS (SELECT 1 FROM auditoria WHERE accion = 'sistema.seed');
```

- [ ] **Step 4: Correr los tests y el seed real dos veces**

```bash
docker compose exec backend pytest tests/test_seed.py tests/test_configuracion.py -v
docker compose restart backend && docker compose restart backend
docker compose exec db psql -U gestion -d gestion -c "SELECT count(*) FROM motivos_baja;" -c "SELECT count(*) FROM auditoria WHERE accion='sistema.seed';"
```
Expected: tests PASS; conteos `4` y `1` después de dos reinicios.

- [ ] **Step 5: Commit** — `git add` de los archivos de la tarea y `git commit` en la rama (ver Global Constraints).

---

### Task 5: Uploads persistentes y servicio de backups

**Files:**
- Create: `backup/backup.sh`
- Modify: `docker-compose.yml` (servicio `backup`), `backend/main.py` (mount `/uploads`)
- Test: `backend/tests/test_uploads.py`

**Interfaces:**
- Produces: archivos en `settings.UPLOADS_DIR` servidos en `/uploads/<ruta>`; dumps `backups/gestion-YYYY-MM-DD_HHMM.dump`.

- [ ] **Step 1: Test que falla**

`backend/tests/test_uploads.py`:
```python
from pathlib import Path

from config import settings


def test_archivos_de_uploads_se_sirven(client):
    carpeta = Path(settings.UPLOADS_DIR) / "productos"
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / "prueba.txt").write_text("hola", encoding="utf-8")

    r = client.get("/uploads/productos/prueba.txt")
    assert r.status_code == 200
    assert r.text == "hola"


def test_uploads_inexistente_da_404(client):
    assert client.get("/uploads/no-existe.jpg").status_code == 404
```

- [ ] **Step 2: Correr y ver que falla**

Run: `docker compose exec backend pytest tests/test_uploads.py -v`
Expected: FAIL — 404 en el primer test (no hay mount).

- [ ] **Step 3: Implementación**

En `backend/main.py`, después del mount de `/static`:
```python
# Archivos subidos: volumen persistente, fuera del código y del contenedor.
Path(settings.UPLOADS_DIR).mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=settings.UPLOADS_DIR), name="uploads")
```

`backup/backup.sh`:
```sh
#!/bin/sh
# Backups diarios de la base con pg_dump (formato custom) y rotación.
# Variables: POSTGRES_*, BACKUP_HORA (HH:MM, hora del negocio),
# BACKUP_RETENCION_DIAS, BACKUP_AHORA=1 (dump inmediato al arrancar).
set -u

HORA="${BACKUP_HORA:-03:00}"
RETENCION="${BACKUP_RETENCION_DIAS:-14}"
DESTINO=/backups
export PGPASSWORD="$POSTGRES_PASSWORD"

hacer_backup() {
    archivo="$DESTINO/gestion-$(date +%Y-%m-%d_%H%M).dump"
    if pg_dump -Fc -h "$POSTGRES_HOST" -p "${POSTGRES_PORT:-5432}" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f "$archivo.tmp"; then
        mv "$archivo.tmp" "$archivo"
        echo "[backup] OK $archivo"
    else
        rm -f "$archivo.tmp"
        echo "[backup] ERROR al generar $archivo"
    fi
    # Rotación: borra dumps con más de RETENCION días.
    find "$DESTINO" -name 'gestion-*.dump' -mmin +"$((RETENCION * 1440))" -print -delete
}

mkdir -p "$DESTINO"
echo "[backup] programado todos los días a las $HORA, retención $RETENCION días"
[ "${BACKUP_AHORA:-0}" = "1" ] && hacer_backup

while true; do
    ahora=$(date +%s)
    objetivo=$(date -d "$(date +%Y-%m-%d) $HORA" +%s)
    [ "$objetivo" -le "$ahora" ] && objetivo=$(date -d "tomorrow $HORA" +%s)
    sleep $((objetivo - ahora))
    hacer_backup
done
```
Luego `chmod +x backup/backup.sh`.

En `docker-compose.yml`, agregar el servicio (antes de `volumes:`):
```yaml
  backup:
    image: postgres:15
    container_name: gestion_backup
    restart: unless-stopped
    env_file: .env
    environment:
      POSTGRES_HOST: db
      POSTGRES_PORT: "5432"
      TZ: America/Argentina/Buenos_Aires
      BACKUP_AHORA: ${BACKUP_AHORA:-0}
    depends_on:
      db:
        condition: service_healthy
    volumes:
      - ./backups:/backups
      - ./backup/backup.sh:/backup/backup.sh:ro
    entrypoint: ["sh", "/backup/backup.sh"]
```

- [ ] **Step 4: Verificar**

```bash
docker compose exec backend pytest tests/test_uploads.py -v            # Expected: 2 PASS
BACKUP_AHORA=1 docker compose up -d backup && sleep 5 && docker compose logs backup | tail -5
ls -la backups/                                                         # Expected: gestion-<fecha>.dump
docker compose exec -T db createdb -U gestion restore_prueba
docker compose exec -T db pg_restore -U gestion -d restore_prueba < backups/$(ls backups | tail -1)
docker compose exec db psql -U gestion -d restore_prueba -c "SELECT count(*) FROM motivos_baja;"   # Expected: 4
docker compose exec db dropdb -U gestion restore_prueba
# Persistencia de uploads:
mkdir -p uploads && echo ok > uploads/persistencia.txt && docker compose down && docker compose up -d --build && sleep 10 && curl -fsS http://localhost:8000/uploads/persistencia.txt && rm uploads/persistencia.txt
```
(`BACKUP_AHORA` llega al contenedor por `environment:` con interpolación, así que la variable de la línea de comandos pisa la del `.env`; después volver a levantar `backup` sin ella.)
Expected: log `[backup] OK …`, dump restaurable con 4 motivos, curl imprime `ok`.

- [ ] **Step 5: Commit** — `git add` de los archivos de la tarea y `git commit` en la rama (ver Global Constraints). `uploads/` y `backups/` no deben aparecer.

---

### Task 6: Tokens de diseño (`custom.css`, config de Tailwind, favicon)

**Files:**
- Create: `backend/app/static/css/custom.css`, `backend/app/templates/components/_tailwind_config.html`, `backend/app/templates/components/_favicon.html`, `backend/app/static/img/favicon.svg`, `backend/app/static/img/favicon-32.png`, `backend/app/static/img/apple-touch-icon.png`
- Test: `backend/tests/test_tokens.py`

**Interfaces:**
- Produces: variables CSS del spec (colores, `--font-sans`, geometría, alturas); clases CSS `.contenedor-x`, `.campo`, `.campo-error`, `.campo-linea`, `.boton`, `.boton-primario`, `.boton-secundario`, `.boton-peligro`, `.boton-acento`, `.btn-accion`, `.tarjeta`, `.tarjeta-enlace`, `.tabla`, `.nav-item`, `.nav-activo`, `.acceso-check`, `.switch-contenedor`, `.switch`, `.switch-on`, `.switch-perilla`, `.toast`, `.toast-exito`, `.toast-error`, `.fondo-modal`, `.modal-panel`, `.combobox-opcion`, `[x-cloak]`, `.htmx-indicator`, `.no-print`; colores Tailwind `primary, primary-hover, accent, welcome, bg, surface, surface-alt, borde, borde-campo, texto, texto-muted, texto-disabled, texto-header, texto-invert, danger, success, sidebar-bg, sidebar-text`.

- [ ] **Step 1: Test que falla**

`backend/tests/test_tokens.py`:
```python
import re
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1] / "app"
CSS = (APP_DIR / "static" / "css" / "custom.css").read_text(encoding="utf-8")
TAILWIND = (APP_DIR / "templates" / "components" / "_tailwind_config.html").read_text(encoding="utf-8")

COLORES = [
    "--color-primary", "--color-primary-hover", "--color-accent", "--color-welcome",
    "--color-bg", "--color-surface", "--color-surface-alt", "--color-border",
    "--color-text", "--color-text-muted", "--color-text-disabled", "--color-text-header",
    "--color-text-invert", "--color-input-border", "--color-danger", "--color-success",
    "--color-sidebar-bg", "--color-sidebar-text", "--color-sidebar-active", "--color-check-borde",
]
GEOMETRIA = [
    "--font-sans", "--radius-input", "--radius-pill", "--radius-search", "--sidebar-width",
    "--header-height", "--layout-max", "--alto-control", "--alto-boton", "--toque-min",
]


def _bloque(patron: str) -> str:
    """Contenido del primer bloque de nivel superior que empieza con `patron`."""
    m = re.search(rf"^{patron}\s*\{{(.*?)^\}}", CSS, re.S | re.M)
    assert m, f"no se encontró el bloque {patron}"
    return m.group(1)


def _define(bloque: str, variable: str) -> bool:
    return re.search(rf"{re.escape(variable)}\s*:", bloque) is not None


def test_root_define_todas_las_variables():
    root = _bloque(r":root")
    faltan = [v for v in COLORES + GEOMETRIA if not _define(root, v)]
    assert not faltan, f"faltan en :root: {faltan}"


def test_modo_oscuro_redefine_todos_los_colores():
    oscuro = _bloque(r"\.dark")
    faltan = [v for v in COLORES if not _define(oscuro, v)]
    assert not faltan, f"faltan en .dark: {faltan}"


def test_puntero_tactil_sube_los_controles_a_44px():
    m = re.search(r"@media\s*\(pointer:\s*coarse\)\s*\{\s*:root\s*\{([^}]*)\}", CSS)
    assert m, "falta el bloque @media (pointer: coarse) { :root { ... } }"
    for variable in ("--alto-control", "--alto-boton", "--toque-min"):
        assert re.search(rf"{variable}\s*:\s*2\.75rem", m.group(1)), variable


def test_tailwind_solo_usa_variables_existentes():
    root = _bloque(r":root")
    usadas = set(re.findall(r"var\(--([\w-]+)\)", TAILWIND)) | {
        f"color-{c}" for c in re.findall(r"c\('([\w-]+)'\)", TAILWIND)
    }
    faltan = [v for v in usadas if v.startswith(("color-", "font-", "radius-", "sidebar-", "header-", "alto-", "toque-", "layout-")) and not _define(root, f"--{v}")]
    assert not faltan, f"el config de Tailwind usa variables inexistentes: {faltan}"


def test_tailwind_reemplaza_breakpoints():
    assert "screens:" in TAILWIND
    assert "'640px'" in TAILWIND and "'1024px'" in TAILWIND and "'1280px'" in TAILWIND
    assert "md:" not in TAILWIND and "2xl:" not in TAILWIND


def test_sin_scroll_horizontal_global():
    assert re.search(r"html,\s*body\s*\{[^}]*overflow-x:\s*hidden", CSS)
```

- [ ] **Step 2: Correr y ver que falla**

Run: `docker compose exec backend pytest tests/test_tokens.py -v`
Expected: FAIL — `FileNotFoundError` (custom.css no existe).

- [ ] **Step 3: Implementación**

`backend/app/static/css/custom.css`:
```css
/* =====================================================================
   Tokens de diseño: ÚNICA fuente de colores, tipografía y geometría.
   Los valores son PROVISORIOS (neutros) hasta cerrar el diseño final:
   cambiar el diseño = editar este archivo y _tailwind_config.html.
   Cada cliente puede tener su paleta redefiniendo estas variables.
   ===================================================================== */

:root {
  /* Colores */
  --color-primary: #2563eb;
  --color-primary-hover: #1d4ed8;
  --color-accent: #0891b2;
  --color-welcome: #2563eb;
  --color-bg: #f5f6f8;
  --color-surface: #ffffff;
  --color-surface-alt: #f0f1f3;
  --color-border: #f0f0f0;
  --color-text: #1f2937;
  --color-text-muted: #6b7280;
  --color-text-disabled: #9ca3af;
  --color-text-header: #111827;
  --color-text-invert: #ffffff;
  --color-input-border: #f0f0f0;
  --color-danger: #dc2626;
  --color-success: #16a34a;
  --color-sidebar-bg: #1f2937;
  --color-sidebar-text: #f9fafb;
  --color-sidebar-active: #374151;
  --color-check-borde: #9ca3af;

  /* Tipografía */
  --font-sans: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;

  /* Geometría */
  --radius-input: 0.3125rem;   /* 5px */
  --radius-pill: 9999px;
  --radius-search: 0.625rem;
  --radius-tarjeta: 1.25rem;   /* 20px */
  --sidebar-width: 18.125rem;  /* 290px */
  --header-height: 4.6875rem;  /* 75px */
  --layout-max: 90rem;

  /* Alturas de control */
  --alto-control: 2.5rem;      /* 40px */
  --alto-boton: 2.1875rem;     /* 35px */
  --toque-min: 2rem;
}

/* Pantallas táctiles: área de toque mínima de 44px. */
@media (pointer: coarse) {
  :root {
    --alto-control: 2.75rem;
    --alto-boton: 2.75rem;
    --toque-min: 2.75rem;
  }
}

.dark {
  color-scheme: dark;
  --color-primary: #3b82f6;
  --color-primary-hover: #60a5fa;
  --color-accent: #22d3ee;
  --color-welcome: #60a5fa;
  --color-bg: #0f1115;
  --color-surface: #181b21;
  --color-surface-alt: #20242c;
  --color-border: #2a2f38;
  --color-text: #e5e7eb;
  --color-text-muted: #9ca3af;
  --color-text-disabled: #6b7280;
  --color-text-header: #f9fafb;
  --color-text-invert: #ffffff;
  --color-input-border: #2a2f38;
  --color-danger: #f87171;
  --color-success: #4ade80;
  --color-sidebar-bg: #111318;
  --color-sidebar-text: #e5e7eb;
  --color-sidebar-active: #23262e;
  --color-check-borde: #6b7280;
}

/* ----- Base ----- */
html, body { overflow-x: hidden; }
img, svg, video, canvas { max-width: 100%; }
[x-cloak] { display: none !important; }

/* Padding horizontal del contenido: 1rem / 2.25rem (sm) / 3.75rem (lg). */
.contenedor-x { padding-inline: 1rem; }
@media (min-width: 640px) { .contenedor-x { padding-inline: 2.25rem; } }
@media (min-width: 1024px) { .contenedor-x { padding-inline: 3.75rem; } }

/* ----- Campos ----- */
.campo {
  width: 100%;
  min-height: var(--alto-control);
  padding: 0 0.75rem;
  border: 2px solid var(--color-input-border);
  border-radius: var(--radius-input);
  background: var(--color-surface);
  color: var(--color-text);
  font-size: 1rem;
}
textarea.campo { padding-block: 0.5rem; }
.campo::placeholder { color: var(--color-text-disabled); }
.campo:focus-visible { outline: 2px solid var(--color-primary); outline-offset: 0; border-color: transparent; }
.campo:disabled { opacity: 0.6; cursor: not-allowed; }
.campo-error { border-color: var(--color-danger); }
.campo-linea {
  width: 100%;
  min-height: var(--alto-control);
  border: 0;
  border-bottom: 2px solid var(--color-input-border);
  background: transparent;
  color: var(--color-text);
}
.campo-linea:focus-visible { outline: none; border-bottom-color: var(--color-primary); }
/* Fuerza de color en modo oscuro (autocompletado y selects nativos). */
.dark input, .dark select, .dark textarea { color: var(--color-text); background-color: var(--color-surface); }
.acceso-check {
  width: 1.125rem; height: 1.125rem;
  accent-color: var(--color-primary);
  border: 2px solid var(--color-check-borde);
}

/* ----- Botones ----- */
.boton {
  display: inline-flex; align-items: center; justify-content: center; gap: 0.5rem;
  min-height: var(--alto-boton);
  padding: 0 1rem;
  border-radius: var(--radius-input);
  font-weight: 600; font-size: 0.875rem;
  transition: background-color .15s, color .15s, opacity .15s;
}
.boton:disabled { opacity: 0.5; cursor: not-allowed; }
.boton-primario { background: var(--color-primary); color: var(--color-text-invert); }
.boton-primario:hover:not(:disabled) { background: var(--color-primary-hover); }
.boton-acento { background: var(--color-accent); color: var(--color-text-invert); }
.boton-secundario { background: var(--color-surface); color: var(--color-text); border: 2px solid var(--color-border); }
.boton-secundario:hover:not(:disabled) { background: var(--color-surface-alt); }
.boton-peligro { background: var(--color-danger); color: var(--color-text-invert); }
.btn-accion {
  display: inline-flex; align-items: center; justify-content: center;
  min-width: var(--toque-min); min-height: var(--toque-min);
  border-radius: var(--radius-input);
  color: var(--color-text-muted);
}
.btn-accion:hover { background: var(--color-surface-alt); }

/* ----- Tarjetas ----- */
.tarjeta {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-tarjeta);
  padding: 1.25rem;
}
.tarjeta-enlace { transition: box-shadow .15s, transform .15s; }
.tarjeta-enlace:hover { box-shadow: 0 6px 20px rgb(0 0 0 / .08); transform: translateY(-1px); }

/* ----- Tabla de listado ----- */
.tabla { width: 100%; border-collapse: collapse; font-size: 0.875rem; }
.tabla th {
  padding: 0.75rem 1rem; text-align: left; white-space: nowrap;
  font-weight: 600; color: var(--color-text-disabled);
}
.tabla td { padding: 0.75rem 1rem; border-top: 1px solid var(--color-border); color: var(--color-text); }
.tabla td + td, .tabla th + th { border-left: 1px solid var(--color-border); }
.tabla tbody tr { transition: box-shadow .15s; }
.tabla tbody tr:hover { box-shadow: 0 2px 10px rgb(0 0 0 / .07); }

/* ----- Sidebar ----- */
.nav-item {
  display: flex; align-items: center; gap: 0.75rem;
  min-height: 2.75rem; padding: 0 0.75rem;
  border-radius: var(--radius-input);
  color: var(--color-sidebar-text); opacity: .85;
}
.nav-item:hover { opacity: 1; background: var(--color-sidebar-active); }
.nav-activo { opacity: 1; background: var(--color-sidebar-active); font-weight: 600; }

/* ----- Switch ----- */
.switch-contenedor { display: inline-flex; align-items: center; gap: 0.5rem; cursor: pointer; min-height: var(--toque-min); }
.switch {
  position: relative; width: 2.5rem; height: 1.375rem; flex-shrink: 0;
  border-radius: var(--radius-pill); background: var(--color-text-disabled);
  transition: background-color .15s;
}
.switch-on { background: var(--color-primary); }
.switch-perilla {
  position: absolute; top: 0.1875rem; left: 0.1875rem;
  width: 1rem; height: 1rem; border-radius: 9999px; background: #fff;
  transition: transform .15s;
}
.switch-on .switch-perilla { transform: translateX(1.125rem); }

/* ----- Toasts ----- */
.toast {
  display: flex; align-items: center; gap: 0.75rem;
  width: 100%; max-width: 24rem; padding: 0.75rem 1rem;
  border-radius: var(--radius-input); box-shadow: 0 8px 24px rgb(0 0 0 / .15);
  color: var(--color-text-invert); font-size: 0.875rem;
}
.toast-exito { background: var(--color-success); }
.toast-error { background: var(--color-danger); }
.toast .btn-accion { color: inherit; }

/* ----- Modales (solo se cierran con la X o Cancelar) ----- */
.fondo-modal {
  position: fixed; inset: 0; z-index: 50;
  display: flex; align-items: flex-end; justify-content: center;
  background: rgb(0 0 0 / .45);
}
@media (min-width: 640px) { .fondo-modal { align-items: center; padding: 1rem; } }
.modal-panel {
  width: 100%; max-height: 92vh; overflow-y: auto;
  border-bottom-left-radius: 0; border-bottom-right-radius: 0;
}
@media (min-width: 640px) { .modal-panel { border-radius: var(--radius-tarjeta); } }

/* ----- Combobox ----- */
.combobox-opcion {
  display: block; width: 100%; text-align: left;
  min-height: var(--toque-min); padding: 0.375rem 0.75rem;
  color: var(--color-text);
}
.combobox-opcion:hover, .combobox-opcion[aria-selected="true"] { background: var(--color-surface-alt); }

/* ----- HTMX ----- */
.htmx-indicator { opacity: 0; transition: opacity .2s; }
.htmx-request .htmx-indicator, .htmx-request.htmx-indicator { opacity: 1; }

/* ----- Impresión ----- */
@media print {
  .no-print { display: none !important; }
  body { background: #fff; }
}
```

`backend/app/templates/components/_tailwind_config.html`:
```html
{# Config ÚNICA de Tailwind (va por CDN, no hay tailwind.config.js).
   Los colores salen de las variables de custom.css; color-mix permite
   modificadores de opacidad (bg-danger/15). #}
<script>
  (function () {
    const c = (nombre) => `color-mix(in srgb, var(--color-${nombre}) calc(<alpha-value> * 100%), transparent)`;
    tailwind.config = {
      darkMode: 'class',
      theme: {
        screens: { sm: '640px', lg: '1024px', xl: '1280px' },
        extend: {
          colors: {
            primary: c('primary'),
            'primary-hover': c('primary-hover'),
            accent: c('accent'),
            welcome: c('welcome'),
            bg: c('bg'),
            surface: c('surface'),
            'surface-alt': c('surface-alt'),
            borde: c('border'),
            'borde-campo': c('input-border'),
            texto: c('text'),
            'texto-muted': c('text-muted'),
            'texto-disabled': c('text-disabled'),
            'texto-header': c('text-header'),
            'texto-invert': c('text-invert'),
            danger: c('danger'),
            success: c('success'),
            'sidebar-bg': c('sidebar-bg'),
            'sidebar-text': c('sidebar-text'),
          },
          fontFamily: { sans: 'var(--font-sans)' },
          fontSize: {
            xs: ['0.75rem', { lineHeight: '1rem' }],
            sm: ['0.875rem', { lineHeight: '1.25rem' }],
            base: ['1rem', { lineHeight: '1.5rem' }],
            lg: ['1.125rem', { lineHeight: '1.75rem' }],
            xl: ['1.25rem', { lineHeight: '1.75rem' }],
            '2xl': ['1.5rem', { lineHeight: '2rem' }],
            titulo: ['1.75rem', { lineHeight: '2.25rem' }],
          },
          borderRadius: {
            input: 'var(--radius-input)',
            pill: 'var(--radius-pill)',
            search: 'var(--radius-search)',
          },
          spacing: { sidebar: 'var(--sidebar-width)', header: 'var(--header-height)' },
          maxWidth: { layout: 'var(--layout-max)' },
          height: { control: 'var(--alto-control)', boton: 'var(--alto-boton)' },
          width: { control: 'var(--alto-control)' },
          minHeight: { toque: 'var(--toque-min)' },
          minWidth: { toque: 'var(--toque-min)' },
        },
      },
    };
  })();
</script>
```
Nota: `c('input-border')` → `--color-input-border` (existe). El test extrae `c('…')` y verifica `--color-…`.

`backend/app/templates/components/_favicon.html`:
```html
<link rel="icon" href="{{ estatico('/img/favicon.svg') }}" type="image/svg+xml">
<link rel="icon" href="{{ estatico('/img/favicon-32.png') }}" sizes="32x32" type="image/png">
<link rel="apple-touch-icon" href="{{ estatico('/img/apple-touch-icon.png') }}">
```

`backend/app/static/img/favicon.svg` (provisorio):
```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" rx="7" fill="#2563eb"/><path d="M9 21.5c1.4 1.2 3.4 2 5.6 2 3.3 0 5.4-1.6 5.4-4 0-5.3-10.4-3.1-10.4-8 0-2.1 1.9-3.6 4.8-3.6 1.9 0 3.6.6 4.9 1.6" fill="none" stroke="#fff" stroke-width="2.6" stroke-linecap="round"/></svg>
```

PNGs provisorios (color primario sólido), generados sin dependencias:
```bash
docker compose exec backend python - <<'EOF'
import struct, zlib
from pathlib import Path

def png(ruta, lado, rgb=(37, 99, 235)):
    fila = b"\x00" + bytes(rgb) * lado
    def chunk(tipo, datos):
        return struct.pack(">I", len(datos)) + tipo + datos + struct.pack(">I", zlib.crc32(tipo + datos) & 0xFFFFFFFF)
    Path(ruta).write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", lado, lado, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(fila * lado))
        + chunk(b"IEND", b"")
    )

png("app/static/img/favicon-32.png", 32)
png("app/static/img/apple-touch-icon.png", 180)
EOF
```

- [ ] **Step 4: Correr y ver que pasa**

Run: `docker compose exec backend pytest tests/test_tokens.py -v`
Expected: 6 PASS.

- [ ] **Step 5: Commit** — `git add` de los archivos de la tarea y `git commit` en la rama (ver Global Constraints).

---

### Task 7: Layout base (templates.py, iconos, marca, sidebar, base.html, páginas) + `app.js`

**Files:**
- Create: `backend/app/core/templates.py`, `backend/app/templates/components/icons.html`, `marca.html`, `_sidebar_item.html`, `toast.html`, `modal_confirmacion.html`, `encabezado.html`, `botones.html`, `backend/app/templates/base.html`, `backend/app/templates/pages/index.html`, `backend/app/templates/pages/pendiente.html`, `backend/app/templates/auth/.gitkeep`, `backend/app/templates/reports/.gitkeep`, `backend/app/static/js/app.js`
- Modify: `backend/app/api/pages.py`
- Test: `backend/tests/test_marca.py`, `backend/tests/test_pages.py`

**Interfaces:**
- Consumes: `settings`, `get_db`, variables/clases CSS de la Task 6.
- Produces:
  - `app.core.templates`: `templates` (Jinja2Templates), `STATIC_DIR`, `estatico(path) -> str` (`/static/<path>?v=<mtime>`), `logo_url() -> str | None`, filtro Jinja `js` (valor → JSON escapado para atributos HTML). Globals: `APP_NAME`, `APP_ENV`, `estatico`, `logo_url`.
  - `app.api.pages`: `router`, `MENU_SIDEBAR`, `MENU_SIDEBAR_PIE`, `_visible(item, usuario, db) -> bool`, `menu_visible(items, usuario, db) -> list[dict]`, `contexto_base(request, db, actual, **extra) -> dict` (claves `request, menu, menu_pie, actual, usuario_actual, es_admin, inactividad_minutos` + extra). Ítem de menú: `{"nombre", "url", "icono", opcional "oculto", "solo_admin", "hub_configuracion", "modulo", "recurso"}`.
  - Macros: `icono(nombre, clases="w-5 h-5")`; `marca(clases="")`; `sidebar_item(item, actual)`; `contenedor_toasts()`; `modal_confirmacion()`; `encabezado(titulo, volver_url=None, volver_texto="Volver")` (call-block opcional); `accion(variante, texto=None, href=None, atributos="", icono_nombre=None, enlace=False)`, `acciones()` (call-block), `volver(url, texto="Volver")`.
  - JS globales: `temaApp()`, `pesos(v)`, `formatearDolar(v)`, `toast(mensaje, tipo='exito', duracion=4000)`, `toasts()`, `pedir(url, opciones)`, `mensajeDeError(datos, status)`, `normalizarTexto(t)`, `rutaDeIds(arbol, id)`, `rutaCategoria(arbol, id, separador=' > ')`, `combobox(config)`, `confirmar(opciones) -> Promise<boolean>`, `dialogoConfirmacion()`, `cerrarSesion()`, `webcamCapture()`, `avisoSesion(minutos)`; eventos `sesion:actividad`, `atajo-buscar` (F2), `atajo-confirmar` (F10), `atajo-cancelar` (ESC).

- [ ] **Step 1: Tests que fallan**

`backend/tests/test_marca.py`:
```python
from app.core import templates as modulo_templates


def _render_marca():
    plantilla = modulo_templates.templates.env.from_string(
        '{% from "components/marca.html" import marca %}{{ marca("w-full") }}'
    )
    return plantilla.render()


def test_marca_sin_logo_muestra_el_nombre(monkeypatch, tmp_path):
    monkeypatch.setattr(modulo_templates, "STATIC_DIR", tmp_path)
    html = _render_marca()
    assert modulo_templates.templates.env.globals["APP_NAME"] in html
    assert "<img" not in html


def test_marca_con_logo_muestra_la_imagen_versionada(monkeypatch, tmp_path):
    (tmp_path / "img").mkdir()
    (tmp_path / "img" / "logo.svg").write_text("<svg/>", encoding="utf-8")
    monkeypatch.setattr(modulo_templates, "STATIC_DIR", tmp_path)
    html = _render_marca()
    assert '<img src="/static/img/logo.svg?v=' in html
    assert 'class="w-full"' in html


def test_estatico_versiona_y_tolera_inexistentes():
    assert modulo_templates.estatico("/js/app.js").startswith("/static/js/app.js?v=")
    assert modulo_templates.estatico("no/existe.css") == "/static/no/existe.css"


def test_filtro_js_escapa_para_atributos():
    salida = modulo_templates.templates.env.from_string("{{ valor|js }}").render(valor='Dijo "hola" & <chau>')
    assert '"' not in salida and "<" not in salida
    assert "&#34;" in salida
```

`backend/tests/test_pages.py`:
```python
def test_inicio_renderiza_layout_y_saludo(client):
    r = client.get("/")
    assert r.status_code == 200
    html = r.text
    assert "Bienvenido" in html
    assert 'id="contenido"' in html
    assert 'aria-label="Menú principal"' in html           # sidebar
    assert ">Inicio<" in html and 'aria-current="page"' in html
    assert "Ajustes" in html                               # pie del sidebar
    assert "Auditoría" not in html                         # ítem oculto
    assert "cdn.tailwindcss.com" in html
    assert "/static/js/app.js?v=" in html and "/static/css/custom.css?v=" in html
    assert 'x-data="toasts()"' in html                     # contenedor de toasts
    assert "dialogoConfirmacion()" in html                 # diálogo global
    assert "buscador-global" in html                       # buscador comentado
    assert "text-welcome" in html


def test_ajustes_usa_la_pagina_pendiente(client):
    r = client.get("/ajustes")
    assert r.status_code == 200
    assert "Este módulo todavía no está disponible." in r.text


def test_la_api_tiene_prioridad_sobre_las_paginas(client):
    assert client.get("/api/v1/health").json() == {"status": "ok"}


def test_static_se_sirve(client):
    assert client.get("/static/js/app.js").status_code == 200
    assert client.get("/static/css/custom.css").status_code == 200
```

- [ ] **Step 2: Correr y ver que falla**

Run: `docker compose exec backend pytest tests/test_marca.py tests/test_pages.py -v`
Expected: FAIL — `ModuleNotFoundError: app.core.templates` / 404 en `/`.

- [ ] **Step 3: `core/templates.py`**

```python
"""Instancia única de Jinja2Templates y helpers globales de plantillas."""
import json
from pathlib import Path

from fastapi.templating import Jinja2Templates
from markupsafe import Markup, escape

from config import settings

APP_DIR = Path(__file__).resolve().parents[1]
STATIC_DIR = APP_DIR / "static"

templates = Jinja2Templates(directory=str(APP_DIR / "templates"))


def estatico(path: str) -> str:
    """URL de un archivo estático con ?v=<mtime> para romper la caché del navegador
    (StaticFiles no manda Cache-Control)."""
    relativo = path.lstrip("/")
    try:
        version = int((STATIC_DIR / relativo).stat().st_mtime)
    except OSError:
        return f"/static/{relativo}"
    return f"/static/{relativo}?v={version}"


def logo_url() -> str | None:
    """Logo del cliente si existe static/img/logo.svg; si no, se muestra APP_NAME."""
    return estatico("/img/logo.svg") if (STATIC_DIR / "img" / "logo.svg").is_file() else None


def js(valor) -> Markup:
    """Valor Python → literal JS seguro dentro de un atributo HTML (x-data, @click…)."""
    return Markup(escape(json.dumps(valor, ensure_ascii=False)))


templates.env.globals.update(
    APP_NAME=settings.APP_NAME,
    APP_ENV=settings.APP_ENV,
    estatico=estatico,
    logo_url=logo_url,
)
templates.env.filters["js"] = js
```

- [ ] **Step 4: Macros del layout**

`backend/app/templates/components/icons.html`:
```jinja
{# Set de íconos SVG inline (trazo, 24x24). icono(nombre, clases). #}
{% set ICONOS = {
  "inicio": '<path d="M3 11.5 12 4l9 7.5"/><path d="M5 10v10h5v-6h4v6h5V10"/>',
  "productos": '<path d="M3 7.5 12 3l9 4.5v9L12 21l-9-4.5z"/><path d="M3 7.5 12 12l9-4.5M12 12v9"/>',
  "stock": '<path d="m12 3 9 5-9 5-9-5z"/><path d="m3 13 9 5 9-5"/>',
  "ventas": '<circle cx="9" cy="20" r="1.5"/><circle cx="18" cy="20" r="1.5"/><path d="M2 3h3l2.5 12h12l2-8H6.2"/>',
  "clientes": '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0"/><path d="M16 4.5a3.5 3.5 0 0 1 0 7M18 14a6 6 0 0 1 3.5 6"/>',
  "caja": '<rect x="3" y="6" width="18" height="13" rx="2"/><path d="M3 10h18M16 15h2"/>',
  "reportes": '<path d="M4 20V4M4 20h16"/><path d="M8 16v-5M12 16V8M16 16v-3"/>',
  "configuracion": '<path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12"/><circle cx="16" cy="6" r="2"/><circle cx="10" cy="12" r="2"/><circle cx="18" cy="18" r="2"/>',
  "ajustes": '<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M4.2 4.2l2.1 2.1M17.7 17.7l2.1 2.1M2 12h3M19 12h3M4.2 19.8l2.1-2.1M17.7 6.3l2.1-2.1"/>',
  "auditoria": '<path d="M12 3 4 6v6c0 4.5 3.4 8 8 9 4.6-1 8-4.5 8-9V6z"/><path d="m9 12 2 2 4-4"/>',
  "menu": '<path d="M4 6h16M4 12h16M4 18h16"/>',
  "cerrar": '<path d="M6 6l12 12M18 6 6 18"/>',
  "luna": '<path d="M20 14.5A8 8 0 0 1 9.5 4 8 8 0 1 0 20 14.5z"/>',
  "sol": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
  "campana": '<path d="M6 16v-5a6 6 0 0 1 12 0v5l2 2H4z"/><path d="M10 20a2 2 0 0 0 4 0"/>',
  "usuario": '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
  "ver": '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
  "editar": '<path d="M4 20h4L19 9l-4-4L4 16z"/><path d="m13.5 6.5 4 4"/>',
  "borrar": '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/>',
  "activar": '<path d="m5 12 5 5 9-10"/>',
  "chevron-derecha": '<path d="m9 6 6 6-6 6"/>',
  "chevron-abajo": '<path d="m6 9 6 6 6-6"/>',
  "chevron-izquierda": '<path d="m15 6-6 6 6 6"/>',
  "flecha-izquierda": '<path d="M19 12H5M11 6l-6 6 6 6"/>',
  "buscar": '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
  "mas": '<path d="M12 5v14M5 12h14"/>',
  "foto": '<rect x="3" y="5" width="18" height="14" rx="2"/><circle cx="9" cy="10" r="2"/><path d="m21 16-5-5-8 8"/>',
  "descargar": '<path d="M12 4v11M7 10l5 5 5-5M5 20h14"/>',
  "salir": '<path d="M15 4h4v16h-4M10 8l-4 4 4 4M6 12h10"/>',
  "candado": '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
  "punto": '<circle cx="12" cy="12" r="2"/>',
} %}

{% macro icono(nombre, clases="w-5 h-5") -%}
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" class="{{ clases }}" aria-hidden="true">{{ ICONOS.get(nombre, ICONOS["punto"])|safe }}</svg>
{%- endmacro %}
```

`backend/app/templates/components/marca.html`:
```jinja
{# Logo del cliente (static/img/logo.svg) o, si no existe, APP_NAME en texto. #}
{% macro marca(clases="") -%}
{%- set logo = logo_url() -%}
{%- if logo -%}
<img src="{{ logo }}" alt="{{ APP_NAME }}" class="{{ clases }}">
{%- else -%}
<span class="block text-2xl font-black leading-tight tracking-tight {{ clases }}">{{ APP_NAME }}</span>
{%- endif -%}
{%- endmacro %}
```

`backend/app/templates/components/_sidebar_item.html`:
```jinja
{% from "components/icons.html" import icono %}
{% macro sidebar_item(item, actual) -%}
{%- set activo = actual == item.url or (item.url != "/" and actual and actual.startswith(item.url)) -%}
<li>
  <a href="{{ item.url }}" class="nav-item{% if activo %} nav-activo{% endif %}"{% if activo %} aria-current="page"{% endif %}>
    {{ icono(item.icono, "w-5 h-5 shrink-0") }}<span>{{ item.nombre }}</span>
  </a>
</li>
{%- endmacro %}
```

`backend/app/templates/components/toast.html`:
```jinja
{% from "components/icons.html" import icono %}
{# Contenedor global de toasts. Se disparan con window.toast(...) o con
   HX-Trigger: {"toast": {"mensaje": "...", "tipo": "exito|error"}}. #}
{% macro contenedor_toasts() -%}
<div x-data="toasts()" @toast.window="agregar($event.detail)"
     class="pointer-events-none fixed inset-x-0 bottom-0 z-[60] flex flex-col items-center gap-2 p-4 sm:items-end"
     aria-live="polite">
  <template x-for="t in lista" :key="t.id">
    <div x-transition.opacity class="toast pointer-events-auto" :class="t.tipo === 'error' ? 'toast-error' : 'toast-exito'" role="status">
      <span class="flex-1" x-text="t.mensaje"></span>
      <button type="button" class="btn-accion" @click="quitar(t.id)" aria-label="Cerrar aviso">{{ icono("cerrar", "w-4 h-4") }}</button>
    </div>
  </template>
</div>
{%- endmacro %}
```

`backend/app/templates/components/modal_confirmacion.html`:
```jinja
{# Diálogo de confirmación GLOBAL (una sola instancia en base.html).
   Uso desde JS:  if (!(await confirmar({ titulo, mensaje, advertencia,
   textoConfirmar, peligro: true }))) return;
   Nunca usar confirm() del navegador. #}
{% macro modal_confirmacion() -%}
<div x-data="dialogoConfirmacion()" @confirmar.window="abrir($event.detail)">
  <div x-show="abierto" x-cloak class="fondo-modal" role="alertdialog" aria-modal="true" aria-labelledby="confirmacion-titulo">
    <div class="tarjeta modal-panel max-w-md">
      <h2 id="confirmacion-titulo" class="text-xl font-bold text-texto-header" x-text="titulo"></h2>
      <p class="mt-3 text-texto" x-show="mensaje" x-text="mensaje"></p>
      <p class="mt-3 rounded-input bg-danger/10 p-3 text-sm text-danger" x-show="advertencia" x-text="advertencia"></p>
      <div class="mt-6 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        <button type="button" class="boton boton-secundario" @click="responder(false)">Cancelar</button>
        <button type="button" x-ref="confirmar" class="boton" :class="peligro ? 'boton-peligro' : 'boton-primario'"
                @click="responder(true)" x-text="textoConfirmar"></button>
      </div>
    </div>
  </div>
</div>
{%- endmacro %}
```

`backend/app/templates/components/botones.html`:
```jinja
{% from "components/icons.html" import icono %}
{# Acciones de fila y botón "volver". variante: ver | editar | borrar | activar
   (o cualquier otra con icono_nombre y texto propios). #}
{% set VARIANTES_ACCION = {
  "ver": ("Ver", "ver", "hover:text-primary"),
  "editar": ("Editar", "editar", "hover:text-primary"),
  "borrar": ("Borrar", "borrar", "hover:text-danger"),
  "activar": ("Activar", "activar", "hover:text-success"),
} %}

{% macro accion(variante, texto=None, href=None, atributos="", icono_nombre=None, enlace=False) -%}
{%- set conf = VARIANTES_ACCION.get(variante, (texto or variante, icono_nombre or "punto", "hover:text-primary")) -%}
{%- set etiqueta = texto or conf[0] -%}
{%- if href or enlace -%}
<a {% if href %}href="{{ href }}"{% endif %} class="btn-accion {{ conf[2] }}" title="{{ etiqueta }}" aria-label="{{ etiqueta }}" {{ atributos|safe }}>{{ icono(icono_nombre or conf[1]) }}</a>
{%- else -%}
<button type="button" class="btn-accion {{ conf[2] }}" title="{{ etiqueta }}" aria-label="{{ etiqueta }}" {{ atributos|safe }}>{{ icono(icono_nombre or conf[1]) }}</button>
{%- endif -%}
{%- endmacro %}

{% macro acciones() -%}
<div class="flex items-center justify-end gap-1">{{ caller() }}</div>
{%- endmacro %}

{% macro volver(url, texto="Volver") -%}
<a href="{{ url }}" class="inline-flex min-h-toque items-center gap-1 text-sm text-texto-muted hover:text-primary">{{ icono("flecha-izquierda", "w-4 h-4") }}<span>{{ texto }}</span></a>
{%- endmacro %}
```

`backend/app/templates/components/encabezado.html`:
```jinja
{% from "components/botones.html" import volver %}
{# Título de página + "volver" opcional + acciones a la derecha (call-block). #}
{% macro encabezado(titulo, volver_url=None, volver_texto="Volver") -%}
<header class="mb-6 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
  <div class="min-w-0">
    {% if volver_url %}{{ volver(volver_url, volver_texto) }}{% endif %}
    <h1 class="text-titulo font-bold text-texto-header">{{ titulo }}</h1>
  </div>
  {% if caller is defined %}<div class="flex flex-wrap items-center gap-2">{{ caller() }}</div>{% endif %}
</header>
{%- endmacro %}
```

- [ ] **Step 5: `base.html` y páginas**

`backend/app/templates/base.html`:
```jinja
{% from "components/icons.html" import icono %}
{% from "components/marca.html" import marca %}
{% from "components/_sidebar_item.html" import sidebar_item %}
{% from "components/toast.html" import contenedor_toasts %}
{% from "components/modal_confirmacion.html" import modal_confirmacion %}
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block titulo %}{{ APP_NAME }}{% endblock %}</title>
  {# Tema antes de pintar: evita el parpadeo claro→oscuro. #}
  <script>
    try {
      if (localStorage.theme === 'dark' || (!('theme' in localStorage) && matchMedia('(prefers-color-scheme: dark)').matches)) {
        document.documentElement.classList.add('dark');
      }
    } catch (e) {}
  </script>
  {% include "components/_favicon.html" %}
  <script src="https://cdn.tailwindcss.com"></script>
  {% include "components/_tailwind_config.html" %}
  <link rel="stylesheet" href="{{ estatico('/css/custom.css') }}">
  <script src="https://unpkg.com/htmx.org@2.0.4/dist/htmx.min.js"></script>
  <script src="{{ estatico('/js/app.js') }}" defer></script>
  <script src="https://unpkg.com/alpinejs@3.14.8/dist/cdn.min.js" defer></script>
  {% block head_extra %}{% endblock %}
</head>
<body class="min-h-screen bg-bg font-sans text-texto antialiased"
      x-data="{ nav: false, ...temaApp() }"
      x-effect="document.documentElement.classList.toggle('dark', oscuro)"
      @keydown.escape.window="nav = false">

  <a href="#contenido" class="sr-only focus:not-sr-only focus:fixed focus:left-2 focus:top-2 focus:z-[70] focus:rounded-input focus:bg-surface focus:p-2">Saltar al contenido</a>

  {# Overlay del cajón (mobile/tablet) #}
  <div x-show="nav" x-cloak x-transition.opacity class="fixed inset-0 z-30 bg-black/40 lg:hidden" @click="nav = false"></div>

  {# Sidebar: fijo desde lg, cajón deslizable por debajo #}
  <aside class="fixed inset-y-0 left-0 z-40 flex w-sidebar max-w-[85vw] -translate-x-full flex-col bg-sidebar-bg text-sidebar-text transition-transform duration-200 lg:translate-x-0"
         :class="{ 'translate-x-0': nav, '-translate-x-full': !nav }"
         aria-label="Menú principal">
    <div class="flex items-start justify-between gap-2 px-6 pb-2 pt-6">
      <a href="/" class="block w-[78%]">{{ marca("w-full") }}</a>
      <button type="button" class="btn-accion text-sidebar-text lg:hidden" @click="nav = false" aria-label="Cerrar menú">{{ icono("cerrar") }}</button>
    </div>
    {% if usuario_actual %}<p class="px-6 text-right text-sm opacity-80">{{ usuario_actual.nombre }}</p>{% endif %}
    <nav class="mt-4 flex-1 overflow-y-auto px-3">
      <ul class="flex flex-col gap-1">
        {% for item in menu %}{{ sidebar_item(item, actual) }}{% endfor %}
      </ul>
    </nav>
    <ul class="flex flex-col gap-1 px-3 pb-6 pt-2">
      {% for item in menu_pie %}{{ sidebar_item(item, actual) }}{% endfor %}
    </ul>
  </aside>

  <div class="flex min-h-screen flex-col lg:pl-sidebar">
    <header class="contenedor-x sticky top-0 z-20 flex h-header items-center gap-2 border-b border-borde bg-surface">
      <button type="button" class="btn-accion lg:hidden" @click="nav = true" aria-label="Abrir menú">{{ icono("menu") }}</button>
      <div class="flex-1"></div>
      <!-- Buscador global: se habilita cuando exista su módulo.
      <input id="buscador-global" type="search" class="campo max-w-sm rounded-search" placeholder="Buscar…">
      -->
      <button type="button" class="btn-accion" @click="alternarTema()" :aria-label="oscuro ? 'Usar tema claro' : 'Usar tema oscuro'" title="Cambiar tema">
        <span x-show="!oscuro">{{ icono("luna") }}</span>
        <span x-show="oscuro" x-cloak>{{ icono("sol") }}</span>
      </button>
      <button type="button" class="btn-accion" disabled aria-label="Notificaciones (próximamente)" title="Notificaciones (próximamente)">{{ icono("campana") }}</button>
      {% if usuario_actual %}
      <div class="relative" x-data="{ abierto: false }" @click.outside="abierto = false">
        <button type="button" class="inline-flex min-h-toque items-center gap-2 rounded-pill bg-accent px-3 text-sm font-semibold text-texto-invert"
                @click="abierto = !abierto" :aria-expanded="abierto">
          {{ icono("usuario", "w-4 h-4") }}<span class="max-w-[8rem] truncate">{{ usuario_actual.nombre.split()[0] }}</span>
        </button>
        <div x-show="abierto" x-cloak x-transition.opacity class="absolute right-0 mt-2 w-56 rounded-input border border-borde bg-surface py-2 shadow-lg">
          <p class="px-4 pb-2 text-xs text-texto-muted">{{ usuario_actual.rol_nombre|default('') }}</p>
          <a href="/cambiar-password" class="combobox-opcion">Cambiar contraseña</a>
          <button type="button" class="combobox-opcion" @click="cerrarSesion()">Cerrar sesión</button>
        </div>
      </div>
      {% endif %}
    </header>

    <main id="contenido" class="contenedor-x mx-auto w-full max-w-layout flex-1 py-6">
      {% block contenido %}{% endblock %}
    </main>
  </div>

  {{ contenedor_toasts() }}
  {{ modal_confirmacion() }}

  {% if usuario_actual %}
  <div x-data="avisoSesion({{ inactividad_minutos }})">
    <div x-show="visible" x-cloak class="fondo-modal" role="alertdialog" aria-modal="true" aria-labelledby="aviso-sesion-titulo">
      <div class="tarjeta modal-panel max-w-md">
        <h2 id="aviso-sesion-titulo" class="text-xl font-bold text-texto-header">Tu sesión está por vencer</h2>
        <p class="mt-3 text-texto">Por inactividad, la sesión se cierra en menos de 2 minutos.</p>
        <div class="mt-6 flex justify-end">
          <button type="button" class="boton boton-primario" @click="seguir()">Seguir trabajando</button>
        </div>
      </div>
    </div>
  </div>
  {% endif %}

  {% block scripts %}{% endblock %}
</body>
</html>
```

`backend/app/templates/pages/index.html`:
```jinja
{% extends "base.html" %}
{% block contenido %}
<h1 class="text-2xl font-black text-welcome">Bienvenido{% if usuario_actual %}, {{ usuario_actual.nombre.split()[0] }}{% endif %}</h1>
{% endblock %}
```

`backend/app/templates/pages/pendiente.html`:
```jinja
{% extends "base.html" %}
{% from "components/encabezado.html" import encabezado %}
{% block titulo %}{{ titulo }} · {{ APP_NAME }}{% endblock %}
{% block contenido %}
{{ encabezado(titulo) }}
<div class="tarjeta">
  <p class="text-texto-muted">Este módulo todavía no está disponible.</p>
</div>
{% endblock %}
```

`backend/app/api/pages.py`:
```python
"""Rutas HTML (Jinja2). Fuera del esquema OpenAPI.

El sidebar se define acá y se filtra con _visible(); la sesión 02 agrega la
sesión obligatoria y los permisos, y cada módulo suma su ítem.
"""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.templates import templates
from config import settings

router = APIRouter(include_in_schema=False)

# Ítems: nombre, url, icono y, opcionalmente, oculto / solo_admin /
# hub_configuracion / modulo / recurso (se evalúan en _visible).
MENU_SIDEBAR: list[dict] = [
    {"nombre": "Inicio", "url": "/", "icono": "inicio"},
    # Sin pantalla HTML de auditoría: el ítem existe pero está oculto.
    {"nombre": "Auditoría", "url": "/auditoria", "icono": "auditoria", "oculto": True},
]
MENU_SIDEBAR_PIE: list[dict] = [
    {"nombre": "Ajustes", "url": "/ajustes", "icono": "ajustes"},
]


def _visible(item: dict, usuario, db: Session) -> bool:
    """Regla única de visibilidad para ítems del sidebar y tarjetas de hubs."""
    return not item.get("oculto", False)


def menu_visible(items: list[dict], usuario, db: Session) -> list[dict]:
    return [item for item in items if _visible(item, usuario, db)]


def contexto_base(request: Request, db: Session, actual: str, **extra) -> dict:
    """Contexto común de todas las páginas."""
    usuario = None  # sesión 02: usuario autenticado
    return {
        "request": request,
        "menu": menu_visible(MENU_SIDEBAR, usuario, db),
        "menu_pie": menu_visible(MENU_SIDEBAR_PIE, usuario, db),
        "actual": actual,
        "usuario_actual": usuario,
        "es_admin": False,
        "inactividad_minutos": settings.SESION_INACTIVIDAD_MINUTOS,
        **extra,
    }


@router.get("/")
def inicio(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(request, "pages/index.html", contexto_base(request, db, "/"))


@router.get("/ajustes")
def ajustes(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        request, "pages/pendiente.html", contexto_base(request, db, "/ajustes", titulo="Ajustes")
    )
```

- [ ] **Step 6: `static/js/app.js`**

```js
/* Funciones JavaScript globales (sin build). Se carga ANTES que Alpine. */
(function () {
  'use strict';

  // ---------- Tema claro / oscuro (persistido en localStorage.theme) ----------
  window.temaApp = function () {
    return {
      oscuro: document.documentElement.classList.contains('dark'),
      alternarTema() {
        this.oscuro = !this.oscuro;
        try { localStorage.theme = this.oscuro ? 'dark' : 'light'; } catch (e) { /* sin storage */ }
      },
    };
  };

  // ---------- Formato de números (es-AR). Decimales solo si existen. ----------
  function formatearNumero(valor) {
    if (valor === null || valor === undefined || valor === '') return '';
    const n = Number(valor);
    if (Number.isNaN(n)) return '';
    const decimales = Number.isInteger(n) ? 0 : 2;
    return n.toLocaleString('es-AR', { minimumFractionDigits: decimales, maximumFractionDigits: 2 });
  }
  window.pesos = formatearNumero;
  window.formatearDolar = formatearNumero;

  // ---------- Toasts ----------
  window.toast = function (mensaje, tipo = 'exito', duracion = 4000) {
    window.dispatchEvent(new CustomEvent('toast', { detail: { mensaje, tipo, duracion } }));
  };
  window.toasts = function () {
    return {
      lista: [],
      siguiente: 1,
      agregar({ mensaje, tipo = 'exito', duracion = 4000 } = {}) {
        if (!mensaje) return;
        const id = this.siguiente++;
        this.lista.push({ id, mensaje, tipo });
        if (duracion > 0) setTimeout(() => this.quitar(id), duracion);
      },
      quitar(id) { this.lista = this.lista.filter((t) => t.id !== id); },
    };
  };

  // ---------- Pedidos JSON a la API ----------
  function mensajeDeError(datos, status) {
    const detalle = datos && datos.detail;
    if (typeof detalle === 'string') return detalle;
    if (Array.isArray(detalle) && detalle.length) return detalle[0].msg || 'Datos inválidos.';
    return `Error ${status}`;
  }
  window.mensajeDeError = mensajeDeError;

  window.pedir = async function (url, opciones = {}) {
    const op = { credentials: 'same-origin', ...opciones, headers: { Accept: 'application/json', ...(opciones.headers || {}) } };
    if (op.body !== undefined && !(op.body instanceof FormData) && typeof op.body !== 'string') {
      op.body = JSON.stringify(op.body);
      op.headers['Content-Type'] = 'application/json';
    }
    const respuesta = await fetch(url, op);
    if (respuesta.status === 204) return null;
    const esJson = (respuesta.headers.get('content-type') || '').includes('application/json');
    const datos = esJson ? await respuesta.json() : await respuesta.text();
    if (!respuesta.ok) {
      const error = new Error(mensajeDeError(esJson ? datos : null, respuesta.status));
      error.status = respuesta.status;
      error.datos = datos;  // para marcar campos en errores 422
      throw error;
    }
    return datos;
  };

  // ---------- Texto y categorías ----------
  window.normalizarTexto = (texto) =>
    String(texto ?? '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim();

  /** Ids desde la raíz hasta `id` en un árbol [{id, nombre, hijos: [...]}]. */
  window.rutaDeIds = function (arbol, id, camino = []) {
    for (const nodo of arbol || []) {
      const actual = [...camino, nodo.id];
      if (nodo.id == id) return actual;
      const encontrado = window.rutaDeIds(nodo.hijos, id, actual);
      if (encontrado.length) return encontrado;
    }
    return [];
  };

  /** Camino legible de una categoría: "Ropa > Remeras > Lisas". */
  window.rutaCategoria = function (arbol, id, separador = ' > ') {
    const nombres = [];
    let nivel = arbol;
    for (const idNodo of window.rutaDeIds(arbol, id)) {
      const nodo = (nivel || []).find((n) => n.id == idNodo);
      nombres.push(nodo.nombre);
      nivel = nodo.hijos;
    }
    return nombres.join(separador);
  };

  // ---------- Combobox (select con búsqueda) ----------
  window.combobox = function ({ fuente, texto = 'texto', valor = 'id' }) {
    return {
      seleccion: null,
      busqueda: '',
      abierto: false,
      activo: 0,
      campoTexto: texto,
      campoValor: valor,
      get opciones() { return fuente() || []; },
      get filtradas() {
        const q = window.normalizarTexto(this.busqueda);
        return this.opciones.filter((o) => window.normalizarTexto(o[this.campoTexto]).includes(q)).slice(0, 50);
      },
      get etiqueta() {
        const elegida = this.opciones.find((o) => o[this.campoValor] == this.seleccion);
        return elegida ? elegida[this.campoTexto] : '';
      },
      abrir() {
        this.abierto = true;
        this.busqueda = '';
        this.activo = 0;
        this.$nextTick(() => this.$refs.buscador && this.$refs.buscador.focus());
      },
      cerrar() { this.abierto = false; },
      alternar() { this.abierto ? this.cerrar() : this.abrir(); },
      elegir(opcion) {
        this.seleccion = opcion ? opcion[this.campoValor] : null;
        this.cerrar();
        this.$dispatch('cambio', this.seleccion);
      },
      mover(delta) {
        const total = this.filtradas.length;
        if (total) this.activo = (this.activo + delta + total) % total;
      },
      confirmar() {
        const opcion = this.filtradas[this.activo];
        if (opcion) this.elegir(opcion);
      },
    };
  };

  // ---------- Confirmación global (reemplaza a confirm()) ----------
  window.confirmar = function (opciones = {}) {
    return new Promise((resolver) => {
      window.dispatchEvent(new CustomEvent('confirmar', { detail: { ...opciones, resolver } }));
    });
  };
  window.dialogoConfirmacion = function () {
    return {
      abierto: false,
      titulo: '',
      mensaje: '',
      advertencia: '',
      textoConfirmar: 'Confirmar',
      peligro: false,
      resolver: null,
      abrir(d) {
        this.titulo = d.titulo || '¿Confirmás la acción?';
        this.mensaje = d.mensaje || '';
        this.advertencia = d.advertencia || '';
        this.textoConfirmar = d.textoConfirmar || 'Confirmar';
        this.peligro = !!d.peligro;
        this.resolver = d.resolver;
        this.abierto = true;
        this.$nextTick(() => this.$refs.confirmar && this.$refs.confirmar.focus());
      },
      responder(valor) {
        this.abierto = false;
        if (this.resolver) this.resolver(valor);
        this.resolver = null;
      },
    };
  };

  // ---------- Cámara (fotos de productos) ----------
  window.webcamCapture = function () {
    return {
      stream: null,
      activa: false,
      error: '',
      async iniciar() {
        this.error = '';
        try {
          this.stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' }, audio: false });
          this.$refs.video.srcObject = this.stream;
          this.activa = true;
        } catch (e) {
          this.error = 'No se pudo acceder a la cámara.';
        }
      },
      capturar(tipo = 'image/jpeg', calidad = 0.9) {
        const video = this.$refs.video;
        const lienzo = document.createElement('canvas');
        lienzo.width = video.videoWidth;
        lienzo.height = video.videoHeight;
        lienzo.getContext('2d').drawImage(video, 0, 0);
        return new Promise((resolver) => lienzo.toBlob(resolver, tipo, calidad));
      },
      detener() {
        if (this.stream) this.stream.getTracks().forEach((t) => t.stop());
        this.stream = null;
        this.activa = false;
      },
    };
  };

  // ---------- Sesión ----------
  window.cerrarSesion = async function () {
    try {
      await fetch('/api/v1/auth/logout', { method: 'POST', credentials: 'same-origin' });
    } finally {
      window.location.href = '/login';
    }
  };

  let sesionVencidaAvisada = false;
  function avisarSesionVencida() {
    if (sesionVencidaAvisada) return;
    sesionVencidaAvisada = true;
    window.toast('Tu sesión venció. Volvé a ingresar.', 'error');
    setTimeout(() => { window.location.href = '/login'; }, 1500);
  }

  // Wrapper de fetch: cuenta como actividad y detecta la sesión vencida.
  const fetchOriginal = window.fetch.bind(window);
  window.fetch = async function (recurso, opciones) {
    const respuesta = await fetchOriginal(recurso, opciones);
    const url = String((recurso && recurso.url) || recurso);
    window.dispatchEvent(new Event('sesion:actividad'));
    if (respuesta.status === 401 && !url.includes('/api/v1/auth/')) avisarSesionVencida();
    return respuesta;
  };

  document.addEventListener('htmx:afterRequest', () => window.dispatchEvent(new Event('sesion:actividad')));
  document.addEventListener('htmx:responseError', (evento) => {
    const xhr = evento.detail.xhr;
    if (xhr.status === 401) return avisarSesionVencida();
    let datos = null;
    try { datos = JSON.parse(xhr.responseText); } catch (e) { /* no es JSON */ }
    window.toast(mensajeDeError(datos, xhr.status), 'error');
  });
  document.addEventListener('htmx:sendError', () => window.toast('Sin conexión con el servidor.', 'error'));

  /** Aviso 2 minutos antes del vencimiento por inactividad. */
  window.avisoSesion = function (minutos) {
    const total = minutos * 60 * 1000;
    const anticipo = 2 * 60 * 1000;
    return {
      visible: false,
      ultima: Date.now(),
      intervalo: null,
      init() {
        window.addEventListener('sesion:actividad', () => { if (!this.visible) this.ultima = Date.now(); });
        this.intervalo = setInterval(() => this.revisar(), 15000);
      },
      revisar() {
        const inactivo = Date.now() - this.ultima;
        if (inactivo >= total) {
          clearInterval(this.intervalo);
          avisarSesionVencida();
        } else if (inactivo >= total - anticipo) {
          this.visible = true;
        }
      },
      async seguir() {
        try {
          await window.pedir('/api/v1/auth/refresh', { method: 'POST' });
          this.ultima = Date.now();
          this.visible = false;
        } catch (e) {
          avisarSesionVencida();
        }
      },
    };
  };

  // ---------- Atajos globales ----------
  const ATAJOS = { F2: 'atajo-buscar', F10: 'atajo-confirmar', Escape: 'atajo-cancelar' };
  document.addEventListener('keydown', (evento) => {
    const nombre = ATAJOS[evento.key];
    if (!nombre) return;
    if (evento.key !== 'Escape') evento.preventDefault();
    window.dispatchEvent(new CustomEvent(nombre));
  });
})();
```

- [ ] **Step 7: Correr y ver que pasa**

Run: `docker compose exec backend pytest tests/test_marca.py tests/test_pages.py -v`
Expected: 8 PASS.
Verificación manual: abrir `http://localhost:8000/` → sidebar, header, saludo; el toggle ☾/☀ cambia el tema sin recargar y persiste al recargar; en la consola del navegador no hay errores de JS; con el ancho < 1024px el sidebar se oculta, el botón ☰ lo abre con overlay, ESC y el overlay lo cierran; sin scroll horizontal a 320px.

- [ ] **Step 8: Commit** — `git add` de los archivos de la tarea y `git commit` en la rama (ver Global Constraints).

---

### Task 8: Macros reutilizables restantes

**Files:**
- Create: `backend/app/templates/components/badge.html`, `combobox.html`, `form_field.html`, `hub.html`, `miniatura.html`, `modal.html`, `paginacion.html`, `switch_activos.html`, `switch_estado.html`, `table.html`
- Test: `backend/tests/test_componentes.py`

**Interfaces:**
- Consumes: `icono`, filtro `js`, JS `combobox(...)`, clases CSS de la Task 6.
- Produces (firmas exactas):
  - `badge(texto, variante="neutro")`, `estado_texto(texto, variante="neutro")` — variantes `exito | peligro | neutro | primario`.
  - `combobox(id, opciones, modelo, texto="texto", valor="id", etiqueta=None, placeholder="Buscar…", vacio="Todos", al_cambiar="")` — `opciones` y `modelo` son expresiones Alpine; emite el evento `cambio`.
  - `campo(nombre, etiqueta, tipo="text", modelo=None, requerido=False, placeholder="", ayuda=None, error=None, atributos="")`, `campo_select(nombre, etiqueta, opciones, modelo=None, requerido=False, vacio="Elegí una opción", error=None, atributos="")` (opciones: lista de `(valor, texto)`), `campo_booleano(nombre, etiqueta, modelo, atributos="")`, `campo_rango(nombre, etiqueta, modelo_desde, modelo_hasta, tipo="number")`, `boton(texto, variante="primario", tipo="button", atributos="", icono_nombre=None)`.
  - `hub(secciones, vacio="No tenés secciones disponibles.")` — secciones: `[{nombre, descripcion, url, title?}]`.
  - `miniatura(src, tamano="md", alt="Foto del producto")` — `src` expresión Alpine; tamaños `sm | md | lg`.
  - `modal(titulo, id, abierto="modal", ancho="max-w-2xl", titulo_expr=None)` — call-block; se cierra solo con la X.
  - `paginacion(pagina="pagina", total="total", tamano="tamano", al_cambiar="cargar()")`.
  - `switch_activos(modelo="soloActivos", al_cambiar="", id="switch-activos", etiqueta="Solo activos")`, `switch_estado(modelo="activos", al_cambiar="", id="switch-estado", etiquetas=("Activos", "Inactivos"))`.
  - `barra_filtros(total="total", limpiar="limpiarFiltros()", buscar=None, etiqueta="registros encontrados", extras="")` — call-block con los inputs; `extras` = HTML ya renderizado (ej. un switch) en la fila del contador.
  - `tabla(columnas, filas="filas", clave="id", vacio="No se encontraron registros.", cargando=None)` — columnas: `[{titulo, expr, clase?, html?}]`, `expr` usa `fila`; call-block opcional con las acciones de la fila.

- [ ] **Step 1: Test que falla**

`backend/tests/test_componentes.py`:
```python
import pytest

from app.core.templates import templates


def render(fuente: str, **contexto) -> str:
    return templates.env.from_string(fuente).render(**contexto)


def test_badge_y_estado_texto():
    html = render('{% from "components/badge.html" import badge, estado_texto %}{{ badge("Activo", "exito") }}{{ estado_texto("Pendiente", "peligro") }}{{ badge("X", "inventada") }}')
    assert "bg-success/15" in html and "Activo" in html
    assert "text-danger" in html and "Pendiente" in html
    assert "bg-surface-alt" in html  # variante desconocida → neutro


def test_botones_accion_volver_y_acciones():
    html = render(
        '{% from "components/botones.html" import accion, acciones, volver %}'
        '{% call acciones() %}{{ accion("ver", atributos=\'@click="ver(fila)"\') }}{{ accion("borrar") }}{% endcall %}'
        '{{ accion("editar", href="/x/1") }}{{ volver("/configuracion", "Configuraciones") }}'
    )
    assert 'aria-label="Ver"' in html and '@click="ver(fila)"' in html
    assert 'aria-label="Borrar"' in html and "hover:text-danger" in html
    assert '<a href="/x/1"' in html and 'aria-label="Editar"' in html
    assert 'href="/configuracion"' in html and "Configuraciones" in html
    assert "justify-end" in html


def test_encabezado_con_y_sin_acciones():
    sin = render('{% from "components/encabezado.html" import encabezado %}{{ encabezado("Usuarios") }}')
    con = render('{% from "components/encabezado.html" import encabezado %}{% call encabezado("Usuarios", "/configuracion", "Configuraciones") %}<button>+ Crear nuevo</button>{% endcall %}')
    assert "<h1" in sin and "Usuarios" in sin and "flex-wrap" not in sin
    assert "+ Crear nuevo" in con and 'href="/configuracion"' in con


def test_form_field_macros():
    html = render(
        '{% from "components/form_field.html" import campo, campo_select, campo_booleano, campo_rango, boton %}'
        '{{ campo("nombre", "Nombre", modelo="form.nombre", requerido=True, error="errores.nombre") }}'
        '{{ campo_select("rol", "Rol", [(1, "Admin"), (2, "Vendedor")], modelo="form.rol_id") }}'
        '{{ campo_booleano("activo", "Activo", "form.activo") }}'
        '{{ campo_rango("precio", "Precio", "filtros.desde", "filtros.hasta") }}'
        '{{ boton("Guardar", tipo="submit") }}'
    )
    assert 'for="nombre"' in html and 'x-model="form.nombre"' in html and "required" in html
    assert 'text-danger">*' in html and 'x-text="errores.nombre"' in html
    assert '<option value="1">Admin</option>' in html and "Elegí una opción" in html
    assert 'type="checkbox"' in html and 'x-model="form.activo"' in html
    assert 'x-model="filtros.desde"' in html and 'x-model="filtros.hasta"' in html
    assert 'type="submit"' in html and "boton-primario" in html


def test_combobox_escapa_la_configuracion():
    html = render('{% from "components/combobox.html" import combobox %}{{ combobox("f-proveedor", "proveedores", "filtros.proveedor_id", texto="nombre", vacio="Proveedor (todos)", etiqueta="Proveedor") }}')
    assert 'x-data="combobox({ fuente: () => (proveedores), texto: &#34;nombre&#34;' in html
    assert 'x-model="filtros.proveedor_id"' in html and 'x-modelable="seleccion"' in html
    assert "Proveedor (todos)" in html and 'for="f-proveedor"' in html


def test_hub_con_y_sin_secciones():
    con = render('{% from "components/hub.html" import hub %}{{ hub(s) }}', s=[{"nombre": "Usuarios", "descripcion": "Altas", "url": "/usuarios", "title": "Ayuda"}])
    sin = render('{% from "components/hub.html" import hub %}{{ hub([]) }}')
    assert 'href="/usuarios"' in con and 'title="Ayuda"' in con and "tarjeta-enlace" in con
    assert "No tenés secciones disponibles." in sin


def test_miniatura_modal_paginacion():
    html = render(
        '{% from "components/miniatura.html" import miniatura %}{% from "components/modal.html" import modal %}'
        '{% from "components/paginacion.html" import paginacion %}'
        '{{ miniatura("fila.foto_url", "sm") }}'
        '{% call modal("Nuevo usuario", "modal-usuario", abierto="formAbierto") %}<p>cuerpo</p>{% endcall %}'
        '{{ paginacion() }}'
    )
    assert ':src="fila.foto_url"' in html and "w-10 h-10" in html
    assert 'x-show="formAbierto"' in html and '@click="formAbierto = false"' in html and "cuerpo" in html
    assert "@keydown.escape" not in html  # el modal NO se cierra con ESC
    assert "Anterior" in html and "Siguiente" in html and "pagina--; cargar()" in html


def test_switches():
    html = render(
        '{% from "components/switch_activos.html" import switch_activos %}{% from "components/switch_estado.html" import switch_estado %}'
        '{{ switch_activos("soloActivos", "cargar()") }}{{ switch_estado("activos", "", "sw-estado") }}'
    )
    assert 'role="switch"' in html and '@click="soloActivos = !soloActivos; cargar()"' in html
    assert "Solo activos" in html
    assert "activos ? " in html and "Inactivos" in html and 'id="sw-estado"' in html


def test_barra_filtros_y_tabla():
    html = render(
        '{% from "components/table.html" import barra_filtros, tabla %}{% from "components/botones.html" import accion %}'
        '{% call barra_filtros(buscar="buscar()", extras="<span>EXTRA</span>"|safe) %}<input id="f">{% endcall %}'
        '{% call tabla(cols, cargando="cargando") %}{{ accion("ver") }}{% endcall %}'
        '{{ tabla(cols) }}',
        cols=[{"titulo": "Nombre", "expr": "fila.nombre"}, {"titulo": "Estado", "expr": "fila.estado_html", "html": True, "clase": "text-right"}],
    )
    assert "registros encontrados" in html and 'x-text="total"' in html
    assert '@click="buscar()"' in html and "Limpiar filtros" in html and "EXTRA" in html
    assert 'x-for="fila in filas"' in html and ':key="fila.id"' in html
    assert 'x-text="fila.nombre"' in html and 'x-html="fila.estado_html"' in html
    assert 'colspan="3"' in html and 'colspan="2"' in html  # con y sin columna de acciones
    assert "Cargando…" in html and "No se encontraron registros." in html


@pytest.mark.parametrize(
    "archivo",
    ["badge", "botones", "combobox", "encabezado", "form_field", "hub", "icons", "marca", "miniatura",
     "modal", "modal_confirmacion", "paginacion", "switch_activos", "switch_estado", "table", "toast", "_sidebar_item"],
)
def test_todos_los_componentes_compilan(archivo):
    templates.env.get_template(f"components/{archivo}.html")
```

- [ ] **Step 2: Correr y ver que falla**

Run: `docker compose exec backend pytest tests/test_componentes.py -v`
Expected: FAIL — `TemplateNotFound: components/badge.html` (y otros).

- [ ] **Step 3: Implementación**

`badge.html`:
```jinja
{# Etiquetas de estado. badge = con fondo; estado_texto = texto coloreado inline (tablas). #}
{% set FONDOS_BADGE = {
  "exito": "bg-success/15 text-success",
  "peligro": "bg-danger/15 text-danger",
  "primario": "bg-primary/15 text-primary",
  "neutro": "bg-surface-alt text-texto-muted",
} %}
{% set TEXTOS_ESTADO = {
  "exito": "text-success",
  "peligro": "text-danger",
  "primario": "text-primary",
  "neutro": "text-texto-muted",
} %}

{% macro badge(texto, variante="neutro") -%}
<span class="inline-flex items-center rounded-pill px-2.5 py-0.5 text-xs font-semibold {{ FONDOS_BADGE.get(variante, FONDOS_BADGE['neutro']) }}">{{ texto }}</span>
{%- endmacro %}

{% macro estado_texto(texto, variante="neutro") -%}
<span class="text-sm font-semibold {{ TEXTOS_ESTADO.get(variante, TEXTOS_ESTADO['neutro']) }}">{{ texto }}</span>
{%- endmacro %}
```

`combobox.html`:
```jinja
{% from "components/icons.html" import icono %}
{# Select con búsqueda (catálogos largos). `opciones` y `modelo` son expresiones
   Alpine del componente de la página. Emite el evento `cambio` al elegir. #}
{% macro combobox(id, opciones, modelo, texto="texto", valor="id", etiqueta=None, placeholder="Buscar…", vacio="Todos", al_cambiar="") -%}
<div class="relative flex flex-col gap-1"
     x-data="combobox({ fuente: () => ({{ opciones }}), texto: {{ texto|js }}, valor: {{ valor|js }} })"
     x-modelable="seleccion" x-model="{{ modelo }}"
     @click.outside="cerrar()"{% if al_cambiar %} @cambio="{{ al_cambiar }}"{% endif %}>
  {% if etiqueta %}<label for="{{ id }}" class="text-lg font-medium text-texto">{{ etiqueta }}</label>{% endif %}
  <button type="button" id="{{ id }}" class="campo flex items-center justify-between gap-2 text-left"
          @click="alternar()" @keydown.arrow-down.prevent="abrir()" :aria-expanded="abierto" aria-haspopup="listbox">
    <span class="truncate" :class="etiqueta ? '' : 'text-texto-disabled'" x-text="etiqueta || {{ vacio|js }}"></span>
    {{ icono("chevron-abajo", "w-4 h-4 shrink-0 text-texto-muted") }}
  </button>
  <div x-show="abierto" x-cloak x-transition.opacity class="absolute top-full z-30 mt-1 w-full overflow-hidden rounded-input border border-borde bg-surface shadow-lg">
    <input x-ref="buscador" type="text" x-model="busqueda" placeholder="{{ placeholder }}" autocomplete="off"
           class="campo rounded-none border-0 border-b"
           @input="activo = 0"
           @keydown.arrow-down.prevent="mover(1)" @keydown.arrow-up.prevent="mover(-1)"
           @keydown.enter.prevent="confirmar()" @keydown.escape.stop="cerrar()">
    <ul class="max-h-60 overflow-y-auto py-1" role="listbox">
      {% if vacio %}<li><button type="button" class="combobox-opcion text-texto-muted" @click="elegir(null)">{{ vacio }}</button></li>{% endif %}
      <template x-for="(opcion, indice) in filtradas" :key="opcion[campoValor]">
        <li><button type="button" class="combobox-opcion" role="option" :aria-selected="indice === activo"
                    @mouseenter="activo = indice" @click="elegir(opcion)" x-text="opcion[campoTexto]"></button></li>
      </template>
      <li x-show="!filtradas.length" class="px-3 py-2 text-sm text-texto-muted">Sin resultados.</li>
    </ul>
  </div>
</div>
{%- endmacro %}
```

`form_field.html`:
```jinja
{% from "components/icons.html" import icono %}
{# Campos de formulario. `modelo` y `error` son expresiones Alpine
   (error = mensaje del campo, ej. "errores.nombre"; se muestra si tiene valor). #}
{% macro _etiqueta(nombre, etiqueta, requerido) -%}
<label for="{{ nombre }}" class="text-lg font-medium text-texto">{{ etiqueta }}{% if requerido %} <span class="text-danger">*</span>{% endif %}</label>
{%- endmacro %}

{% macro _error(error) -%}
{% if error %}<p class="text-sm text-danger" x-show="{{ error }}" x-text="{{ error }}" x-cloak></p>{% endif %}
{%- endmacro %}

{% macro campo(nombre, etiqueta, tipo="text", modelo=None, requerido=False, placeholder="", ayuda=None, error=None, atributos="") -%}
<div class="flex flex-col gap-1">
  {{ _etiqueta(nombre, etiqueta, requerido) }}
  <input id="{{ nombre }}" name="{{ nombre }}" type="{{ tipo }}" class="campo" placeholder="{{ placeholder }}"
         {% if modelo %}x-model="{{ modelo }}"{% endif %} {% if requerido %}required{% endif %}
         {% if error %}:class="{ 'campo-error': {{ error }} }"{% endif %} {{ atributos|safe }}>
  {{ _error(error) }}
  {% if ayuda %}<p class="text-sm text-texto-muted">{{ ayuda }}</p>{% endif %}
</div>
{%- endmacro %}

{% macro campo_select(nombre, etiqueta, opciones, modelo=None, requerido=False, vacio="Elegí una opción", error=None, atributos="") -%}
<div class="flex flex-col gap-1">
  {{ _etiqueta(nombre, etiqueta, requerido) }}
  <select id="{{ nombre }}" name="{{ nombre }}" class="campo" {% if modelo %}x-model="{{ modelo }}"{% endif %}
          {% if requerido %}required{% endif %} {% if error %}:class="{ 'campo-error': {{ error }} }"{% endif %} {{ atributos|safe }}>
    {% if vacio %}<option value="">{{ vacio }}</option>{% endif %}
    {% for valor, texto in opciones %}<option value="{{ valor }}">{{ texto }}</option>{% endfor %}
  </select>
  {{ _error(error) }}
</div>
{%- endmacro %}

{% macro campo_booleano(nombre, etiqueta, modelo, atributos="") -%}
<label for="{{ nombre }}" class="inline-flex min-h-toque cursor-pointer items-center gap-2 text-texto">
  <input id="{{ nombre }}" name="{{ nombre }}" type="checkbox" class="acceso-check" x-model="{{ modelo }}" {{ atributos|safe }}>
  <span>{{ etiqueta }}</span>
</label>
{%- endmacro %}

{% macro campo_rango(nombre, etiqueta, modelo_desde, modelo_hasta, tipo="number") -%}
<fieldset class="flex flex-col gap-1">
  <legend class="text-lg font-medium text-texto">{{ etiqueta }}</legend>
  <div class="grid grid-cols-2 gap-2">
    <input id="{{ nombre }}-desde" type="{{ tipo }}" class="campo" placeholder="Desde" aria-label="{{ etiqueta }} desde" x-model="{{ modelo_desde }}">
    <input id="{{ nombre }}-hasta" type="{{ tipo }}" class="campo" placeholder="Hasta" aria-label="{{ etiqueta }} hasta" x-model="{{ modelo_hasta }}">
  </div>
</fieldset>
{%- endmacro %}

{% macro boton(texto, variante="primario", tipo="button", atributos="", icono_nombre=None) -%}
<button type="{{ tipo }}" class="boton boton-{{ variante }}" {{ atributos|safe }}>{% if icono_nombre %}{{ icono(icono_nombre, "w-4 h-4") }}{% endif %}<span>{{ texto }}</span></button>
{%- endmacro %}
```

`hub.html`:
```jinja
{% from "components/icons.html" import icono %}
{# Grilla de tarjetas para páginas de menú (1 columna en mobile, 2 desde sm). #}
{% macro hub(secciones, vacio="No tenés secciones disponibles.") -%}
{% if secciones %}
<div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
  {% for s in secciones %}
  <a href="{{ s.url }}" class="tarjeta tarjeta-enlace flex items-center justify-between gap-4"{% if s.title %} title="{{ s.title }}"{% endif %}>
    <div class="min-w-0">
      <h2 class="text-lg font-semibold text-texto-header">{{ s.nombre }}</h2>
      {% if s.descripcion %}<p class="mt-1 text-sm text-texto-muted">{{ s.descripcion }}</p>{% endif %}
    </div>
    {{ icono("chevron-derecha", "w-5 h-5 shrink-0 text-texto-muted") }}
  </a>
  {% endfor %}
</div>
{% else %}
<p class="text-texto-muted">{{ vacio }}</p>
{% endif %}
{%- endmacro %}
```

`miniatura.html`:
```jinja
{% from "components/icons.html" import icono %}
{# Foto de producto con placeholder. `src` es una expresión Alpine. #}
{% set TAMANOS_MINIATURA = {"sm": "w-10 h-10", "md": "w-14 h-14", "lg": "w-24 h-24"} %}

{% macro miniatura(src, tamano="md", alt="Foto del producto") -%}
<div class="{{ TAMANOS_MINIATURA.get(tamano, TAMANOS_MINIATURA['md']) }} flex shrink-0 items-center justify-center overflow-hidden rounded-input bg-surface-alt">
  <template x-if="{{ src }}"><img :src="{{ src }}" alt="{{ alt }}" class="h-full w-full object-cover" loading="lazy"></template>
  <template x-if="!({{ src }})">{{ icono("foto", "w-1/2 h-1/2 text-texto-disabled") }}</template>
</div>
{%- endmacro %}
```

`modal.html`:
```jinja
{% from "components/icons.html" import icono %}
{# Modal genérico (call-block). Se cierra SOLO con la X: ni ESC ni clic afuera.
   `abierto` es la variable Alpine que lo muestra; `titulo_expr` (opcional)
   reemplaza al título fijo por una expresión Alpine. #}
{% macro modal(titulo, id, abierto="modal", ancho="max-w-2xl", titulo_expr=None) -%}
<div x-show="{{ abierto }}" x-cloak class="fondo-modal" id="{{ id }}" role="dialog" aria-modal="true" aria-labelledby="{{ id }}-titulo">
  <div class="tarjeta modal-panel {{ ancho }}">
    <div class="mb-4 flex items-start justify-between gap-4">
      <h2 id="{{ id }}-titulo" class="text-xl font-bold text-texto-header"{% if titulo_expr %} x-text="{{ titulo_expr }}"{% endif %}>{{ titulo }}</h2>
      <button type="button" class="btn-accion" @click="{{ abierto }} = false" aria-label="Cerrar">{{ icono("cerrar") }}</button>
    </div>
    {{ caller() }}
  </div>
</div>
{%- endmacro %}
```

`paginacion.html`:
```jinja
{# Paginación Alpine (de a `tamano`). Expresiones del componente de la página. #}
{% macro paginacion(pagina="pagina", total="total", tamano="tamano", al_cambiar="cargar()") -%}
<nav x-show="{{ total }} > {{ tamano }}" x-cloak class="mt-4 flex items-center justify-between gap-2 text-sm" aria-label="Paginación">
  <button type="button" class="boton boton-secundario" :disabled="{{ pagina }} <= 1" @click="{{ pagina }}--; {{ al_cambiar }}">Anterior</button>
  <span class="text-texto-muted">Página <span x-text="{{ pagina }}"></span> de <span x-text="Math.max(1, Math.ceil({{ total }} / {{ tamano }}))"></span></span>
  <button type="button" class="boton boton-secundario" :disabled="{{ pagina }} >= Math.ceil({{ total }} / {{ tamano }})" @click="{{ pagina }}++; {{ al_cambiar }}">Siguiente</button>
</nav>
{%- endmacro %}
```

`switch_activos.html`:
```jinja
{# Switch "Solo activos". `modelo` es una expresión Alpine booleana.
   switch_base es la única definición del markup (lo reusa switch_estado;
   no lleva guion bajo porque Jinja no deja importar macros "privadas"). #}
{% macro switch_base(modelo, al_cambiar, id, texto_html) -%}
<label for="{{ id }}" class="switch-contenedor">
  <button type="button" id="{{ id }}" role="switch" class="switch" :class="{ 'switch-on': {{ modelo }} }" :aria-checked="({{ modelo }}).toString()"
          @click="{{ modelo }} = !{{ modelo }}{% if al_cambiar %}; {{ al_cambiar }}{% endif %}"><span class="switch-perilla"></span></button>
  <span class="text-sm text-texto">{{ texto_html }}</span>
</label>
{%- endmacro %}

{% macro switch_activos(modelo="soloActivos", al_cambiar="", id="switch-activos", etiqueta="Solo activos") -%}
{{ switch_base(modelo, al_cambiar, id, etiqueta) }}
{%- endmacro %}
```

`switch_estado.html`:
```jinja
{% from "components/switch_activos.html" import switch_base %}
{# Alterna entre dos estados (Activos / Inactivos) y muestra el actual. #}
{% macro switch_estado(modelo="activos", al_cambiar="", id="switch-estado", etiquetas=("Activos", "Inactivos")) -%}
{%- set texto -%}<span x-text="{{ modelo }} ? {{ etiquetas[0]|js }} : {{ etiquetas[1]|js }}">{{ etiquetas[0] }}</span>{%- endset -%}
{{ switch_base(modelo, al_cambiar, id, texto|safe) }}
{%- endmacro %}
```
Nota: el test busca `"Inactivos"` — sale del `|js` escapado como `&#34;Inactivos&#34;`, que contiene la palabra.

`table.html`:
```jinja
{# Barra de filtros y tabla de listado (en tarjeta, sin filas alternadas).
   Los filtros se resuelven SIEMPRE en el backend. #}
{% macro barra_filtros(total="total", limpiar="limpiarFiltros()", buscar=None, etiqueta="registros encontrados", extras="") -%}
<section class="mb-4 flex flex-col gap-3" aria-label="Filtros">
  <div class="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-5">{{ caller() }}</div>
  <div class="flex flex-wrap items-center justify-between gap-3">
    <div class="flex flex-wrap items-center gap-4">
      <p class="text-sm text-texto-muted"><span class="font-semibold text-texto" x-text="{{ total }}"></span> {{ etiqueta }}</p>
      {{ extras }}
    </div>
    <div class="flex flex-wrap items-center gap-2">
      {% if buscar %}<button type="button" class="boton boton-primario" @click="{{ buscar }}">Buscar</button>{% endif %}
      <button type="button" class="boton boton-secundario" @click="{{ limpiar }}">Limpiar filtros</button>
    </div>
  </div>
</section>
{%- endmacro %}

{% macro tabla(columnas, filas="filas", clave="id", vacio="No se encontraron registros.", cargando=None) -%}
{%- set con_acciones = caller is defined -%}
{%- set total_columnas = columnas|length + (1 if con_acciones else 0) -%}
<div class="tarjeta overflow-hidden p-0">
  <div class="overflow-x-auto">
    <table class="tabla">
      <thead>
        <tr>
          {% for c in columnas %}<th scope="col" class="{{ c.clase|default('') }}">{{ c.titulo }}</th>{% endfor %}
          {% if con_acciones %}<th scope="col" class="text-right"><span class="sr-only">Acciones</span></th>{% endif %}
        </tr>
      </thead>
      <tbody>
        <template x-for="fila in {{ filas }}" :key="fila.{{ clave }}">
          <tr :class="fila.activo === false ? 'opacity-60' : ''">
            {% for c in columnas %}<td class="{{ c.clase|default('') }}" {% if c.html %}x-html{% else %}x-text{% endif %}="{{ c.expr }}"></td>{% endfor %}
            {% if con_acciones %}<td class="text-right">{{ caller() }}</td>{% endif %}
          </tr>
        </template>
        {% if cargando %}
        <tr x-show="{{ cargando }}"><td colspan="{{ total_columnas }}" class="py-10 text-center text-texto-muted">Cargando…</td></tr>
        <tr x-show="!{{ cargando }} && !{{ filas }}.length"><td colspan="{{ total_columnas }}" class="py-10 text-center text-texto-muted">{{ vacio }}</td></tr>
        {% else %}
        <tr x-show="!{{ filas }}.length"><td colspan="{{ total_columnas }}" class="py-10 text-center text-texto-muted">{{ vacio }}</td></tr>
        {% endif %}
      </tbody>
    </table>
  </div>
</div>
{%- endmacro %}
```

- [ ] **Step 4: Correr y ver que pasa**

Run: `docker compose exec backend pytest tests/test_componentes.py -v`
Expected: todos PASS. Si `caller is defined` falla cuando se llama sin call-block, reemplazar por `{%- set con_acciones = caller is defined and caller -%}` y re-correr.

- [ ] **Step 5: Commit** — `git add` de los archivos de la tarea y `git commit` en la rama (ver Global Constraints).

---

### Task 9: README y verificación final del módulo

**Files:**
- Create: `README.md`

- [ ] **Step 1: README**

`README.md`:
````markdown
# Stork Gestión

Sistema de gestión para comercios (una instancia por cliente). Backend FastAPI
que sirve la API (`/api/v1`) y las pantallas (Jinja2 + HTMX + Alpine + Tailwind).

## Requisitos
- Docker 24+ con Docker Compose v2.

## Puesta en marcha
```bash
cp .env.example .env        # y ajustar valores (JWT_SECRET, puertos, APP_NAME…)
docker compose up --build
```
Al arrancar, el backend aplica las migraciones (`alembic upgrade head`) y el
seed idempotente (`migrations/seed.sql`).

- App: http://localhost:8000
- Swagger: http://localhost:8000/docs (oculto con `APP_ENV=production`)
- Healthchecks: `/api/v1/health` y `/api/v1/health/db`

### Puerto ocupado
Si 5432, 8000 u 80 están en uso, cambiar en `.env` `POSTGRES_PORT_HOST`,
`BACKEND_PORT_HOST` o `BACKEND_PORT_PROD` (el puerto interno no cambia).

## Tests
```bash
docker compose exec backend pytest
```
Corren contra PostgreSQL real en la base `gestion_test` (se recrea en cada corrida).

## Migraciones
```bash
docker compose exec backend alembic upgrade head
docker compose exec backend alembic current
```
Las migraciones se escriben a mano en `backend/migrations/versions/` (numeradas 0001, 0002…).

## Instalar un cliente nuevo
1. Copiar el proyecto a una carpeta propia del cliente.
2. Crear su `.env` (nombre visible en `APP_NAME`, `JWT_SECRET` propio, puertos).
3. Logo: `backend/app/static/img/logo.svg` (si no existe se muestra `APP_NAME`).
   Favicon: reemplazar `favicon.svg`, `favicon-32.png` y `apple-touch-icon.png`.
4. Paleta: redefinir las variables `--color-*` en `backend/app/static/css/custom.css`.
5. `docker compose up -d --build`.

## Archivos subidos
Viven en `./uploads` (montado en `/uploads` del contenedor) y se sirven en
`/uploads/...`. No se versionan; incluirlos en los backups de archivos del servidor.

## Backups
El servicio `backup` hace un `pg_dump -Fc` diario a `./backups/gestion-AAAA-MM-DD_HHMM.dump`
y borra los que tienen más de `BACKUP_RETENCION_DIAS` días.
- Hora: `BACKUP_HORA` (hora del negocio, default 03:00).
- Backup inmediato: `BACKUP_AHORA=1` en `.env` y `docker compose up -d backup`.
- Restaurar:
  ```bash
  docker compose exec -T db pg_restore -U gestion -d gestion --clean --if-exists < backups/gestion-AAAA-MM-DD_HHMM.dump
  ```

## Credenciales iniciales
El usuario administrador se crea en la sesión 02 (`admin` / `Admin1234!`,
obliga a cambiar la contraseña en el primer ingreso).
````

- [ ] **Step 2: Suite completa y criterios de aceptación**

```bash
cd /Users/agustin/Documents/Stork-Gestion
docker compose down && docker compose up -d --build && sleep 15 && docker compose ps     # db, backend, backup: running/healthy
docker compose exec backend pytest -v                                                    # todos PASS
curl -fsS http://localhost:8000/api/v1/health; curl -fsS http://localhost:8000/api/v1/health/db
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/docs                       # 200
docker compose exec db psql -U gestion -d gestion -c "UPDATE auditoria SET accion='x';"   # ERROR: ... solo inserción
docker compose exec db psql -U gestion -d gestion -c "DELETE FROM auditoria;"             # ERROR
docker compose exec db psql -U gestion -d gestion -c "TRUNCATE auditoria;"                # ERROR
docker compose restart backend && docker compose exec db psql -U gestion -d gestion -c "SELECT count(*) FROM motivos_baja;"  # 4
curl -s http://localhost:8000/ | grep -c "Bienvenido"                                     # 1
```
Verificación visual (navegador, http://localhost:8000): tema claro/oscuro sin recargar; sidebar cajón con overlay < 1024px; sin scroll horizontal de 320px a 1920px; botones con área de toque ≥ 44px en modo táctil (DevTools, dispositivo móvil).

Producción (swagger oculto): `docker compose exec -e APP_ENV=production backend python -c "import importlib, config; import main; print(main.app.docs_url)"` → `None`.

- [ ] **Step 3: Commit** del README en la rama (nunca `git push`, nunca merge a `main`).
