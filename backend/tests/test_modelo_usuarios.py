import bcrypt
import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.core.utils import ahora_db
from app.models import HistorialAcceso, ResultadoAcceso, Rol, RolPermiso, Usuario
from tests.conftest import BACKEND_DIR, ejecutar_sql


def _rol(db, nombre):
    return db.scalar(select(Rol).where(Rol.nombre == nombre))


def test_seed_crea_roles_de_sistema_y_admin(db):
    nombres = db.scalars(select(Rol.nombre).where(Rol.es_sistema.is_(True)).order_by(Rol.nombre)).all()
    assert nombres == ["admin", "supervisor", "vendedor"]
    admin = db.scalar(select(Usuario).where(Usuario.username == "admin"))
    assert admin.rol.nombre == "admin" and admin.es_admin
    assert admin.debe_cambiar_password  # ultimo_acceso NULL
    assert bcrypt.checkpw(b"Admin1234!", admin.password_hash.encode())


def test_seed_de_permisos(db):
    supervisor = _rol(db, "supervisor")
    fila = db.scalar(select(RolPermiso).where(RolPermiso.rol_id == supervisor.id, RolPermiso.modulo == "ventas", RolPermiso.recurso.is_(None)))
    assert (fila.puede_ver, fila.puede_crear, fila.puede_editar, fila.puede_eliminar) == (True, True, True, False)
    anular = db.scalar(select(RolPermiso).where(RolPermiso.rol_id == supervisor.id, RolPermiso.recurso == "venta.anular"))
    assert anular.puede("eliminar") and not anular.puede("crear")
    vendedor = _rol(db, "vendedor")
    arqueo = db.scalar(select(RolPermiso).where(RolPermiso.rol_id == vendedor.id, RolPermiso.recurso == "caja.arqueo"))
    assert arqueo.puede_crear


def test_seed_idempotente(db):
    antes = db.scalar(select(func.count()).select_from(RolPermiso))
    ejecutar_sql(db.connection(), BACKEND_DIR / "migrations" / "seed.sql")
    ejecutar_sql(db.connection(), BACKEND_DIR / "migrations" / "seed.sql")
    assert db.scalar(select(func.count()).select_from(RolPermiso)) == antes
    assert db.scalar(select(func.count()).select_from(Usuario).where(Usuario.username == "admin")) == 1


def test_permiso_de_modulo_no_se_duplica_con_recurso_null(db):
    vendedor = _rol(db, "vendedor")
    db.add(RolPermiso(rol_id=vendedor.id, modulo="clientes", recurso=None))
    with pytest.raises(IntegrityError):
        db.flush()


@pytest.mark.parametrize("sentencia", ["UPDATE historial_accesos SET detalle = 'x'", "DELETE FROM historial_accesos", "TRUNCATE historial_accesos"])
def test_historial_de_accesos_es_inmutable(db, sentencia):
    admin = db.scalar(select(Usuario).where(Usuario.username == "admin"))
    db.add(HistorialAcceso(usuario_id=admin.id, timestamp=ahora_db(), resultado=ResultadoAcceso.EXITOSO))
    db.flush()
    with pytest.raises(DBAPIError) as error:
        db.execute(text(sentencia))
    assert "solo inserción" in str(error.value)


def test_enum_resultado_se_guarda_en_minuscula(db):
    admin = db.scalar(select(Usuario).where(Usuario.username == "admin"))
    db.add(HistorialAcceso(usuario_id=admin.id, timestamp=ahora_db(), resultado=ResultadoAcceso.FALLIDO, detalle="Contraseña incorrecta"))
    db.flush()
    assert db.execute(text("SELECT resultado::text FROM historial_accesos ORDER BY id DESC LIMIT 1")).scalar_one() == "fallido"
