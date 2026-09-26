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
    """Ejecuta un archivo .sql completo (varias sentencias, bloques DO).

    Si el archivo no tiene ninguna sentencia real (solo comentarios `--` o
    líneas en blanco, como el seed antes de la sesión 02) no se ejecuta:
    psycopg2/Postgres tratan ese texto como "empty query" y psycopg2 lanza
    ProgrammingError en lugar de no hacer nada (a diferencia de `psql -f`,
    que sí lo tolera; por eso el entrypoint no tiene este problema).
    """
    contenido = ruta.read_text(encoding="utf-8")
    sin_comentarios = "\n".join(
        linea for linea in contenido.splitlines() if not linea.strip().startswith("--")
    )
    if not sin_comentarios.strip():
        return
    conexion.exec_driver_sql(contenido)


def _verificar_entorno_seguro() -> None:
    """Corta toda la corrida (no solo un test) si algo indica que `_recrear_base`
    podría estar apuntando a una base que no es la de test: DROP/CREATE sobre
    una base real sería irreversible."""
    if settings.DATABASE_URL_OVERRIDE is not None:
        pytest.exit(
            "Abortado: DATABASE_URL está seteada; los tests recrean la base "
            "y no deben correr contra una URL que podría ser de producción."
        )
    if not settings.POSTGRES_DB.endswith("_test"):
        pytest.exit(
            f"Abortado: POSTGRES_DB='{settings.POSTGRES_DB}' no termina en '_test'; "
            "los tests recrean la base y no deben correr contra una base real."
        )


def _recrear_base() -> None:
    _verificar_entorno_seguro()
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
