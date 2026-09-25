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
