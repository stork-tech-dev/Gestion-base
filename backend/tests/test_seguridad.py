import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.core.errores import registrar_manejadores
from app.core.permisos import Modulo, Recurso
from app.core.seguridad import requiere_admin, requiere_permiso, resolver_permiso
from app.models import RolPermiso, UsuarioPermiso
from app.services import auth


# ---------- resolver_permiso ----------
def test_admin_puede_todo(db, crear_usuario):
    admin = crear_usuario("admin")
    assert resolver_permiso(db, admin.id, Modulo.AUDITORIA, "eliminar")
    assert resolver_permiso(db, admin.id, "caja", "crear", "caja.retiro")


def test_usuario_inexistente_o_inactivo_no_puede(db, crear_usuario):
    inactivo = crear_usuario("admin", activo=False)
    assert not resolver_permiso(db, inactivo.id, Modulo.STOCK, "ver")
    assert not resolver_permiso(db, 999_999, Modulo.STOCK, "ver")


def test_rol_inactivo_no_puede(db, crear_usuario):
    vendedor = crear_usuario("vendedor")
    vendedor.rol.activo = False
    db.flush()
    assert not resolver_permiso(db, vendedor.id, Modulo.STOCK, "ver")


def test_permiso_general_habilita_recursos_pero_no_al_reves(db, crear_usuario):
    vendedor = crear_usuario("vendedor")
    assert resolver_permiso(db, vendedor.id, Modulo.STOCK, "ver")
    assert resolver_permiso(db, vendedor.id, Modulo.STOCK, "crear", Recurso.STOCK_BAJA)  # recurso puntual
    assert not resolver_permiso(db, vendedor.id, Modulo.STOCK, "crear")  # el recurso no da el general
    supervisor = crear_usuario("supervisor")
    assert resolver_permiso(db, supervisor.id, Modulo.CAJA, "crear", Recurso.CAJA_RETIRO)  # general caja crear


def test_override_individual_suma_al_rol(db, crear_usuario):
    vendedor = crear_usuario("vendedor")
    assert not resolver_permiso(db, vendedor.id, Modulo.CAJA, "crear", Recurso.CAJA_RETIRO)
    db.add(UsuarioPermiso(usuario_id=vendedor.id, modulo="caja", recurso="caja.retiro", puede_crear=True))
    db.flush()
    assert resolver_permiso(db, vendedor.id, Modulo.CAJA, "crear", Recurso.CAJA_RETIRO)


def test_sin_filas_no_hay_permiso(db, crear_usuario):
    vendedor = crear_usuario("vendedor")
    assert not resolver_permiso(db, vendedor.id, Modulo.PROVEEDORES, "ver")


def test_accion_invalida_levanta_error(db, crear_usuario):
    vendedor = crear_usuario("vendedor")
    with pytest.raises(ValueError):
        resolver_permiso(db, vendedor.id, Modulo.STOCK, "borrar")


# ---------- dependencies ----------
@pytest.fixture
def cliente_protegido(db):
    app = FastAPI()
    registrar_manejadores(app)

    @app.get("/stock")
    def ver_stock(usuario=Depends(requiere_permiso(Modulo.STOCK, "ver"))):
        return {"id": usuario.id}

    @app.get("/retiro")
    def retiro(usuario=Depends(requiere_permiso(Modulo.CAJA, "crear", Recurso.CAJA_RETIRO))):
        return {"id": usuario.id}

    @app.get("/admin")
    def solo_admin(usuario=Depends(requiere_admin)):
        return {"id": usuario.id}

    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


def test_sin_token_da_401(cliente_protegido):
    r = cliente_protegido.get("/stock")
    assert r.status_code == 401


def test_con_permiso_pasa_y_sin_permiso_da_403(cliente_protegido, crear_usuario, headers_de):
    vendedor = crear_usuario("vendedor")
    h = headers_de(vendedor)
    assert cliente_protegido.get("/stock", headers=h).json() == {"id": vendedor.id}
    r = cliente_protegido.get("/retiro", headers=h)
    assert r.status_code == 403
    assert r.json()["detail"] == "Sin permiso para 'crear' en 'caja/caja.retiro'"


def test_token_por_cookie(cliente_protegido, crear_usuario, db):
    vendedor = crear_usuario("vendedor")
    access, _, _ = auth.generar_tokens(db, vendedor, None)
    cliente_protegido.cookies.set("access_token", access)
    assert cliente_protegido.get("/stock").status_code == 200


def test_sesion_revocada_corta_el_access(cliente_protegido, crear_usuario, db):
    vendedor = crear_usuario("vendedor")
    access, refresh, _ = auth.generar_tokens(db, vendedor, None)
    auth.revocar_sesion(db, refresh)
    r = cliente_protegido.get("/stock", headers={"Authorization": f"Bearer {access}"})
    assert r.status_code == 401


def test_usuario_desactivado_da_401(cliente_protegido, crear_usuario, headers_de, db):
    vendedor = crear_usuario("vendedor")
    h = headers_de(vendedor)
    vendedor.activo = False
    db.flush()
    assert cliente_protegido.get("/stock", headers=h).status_code == 401


def test_debe_cambiar_password_bloquea_la_api(cliente_protegido, crear_usuario, headers_de):
    nuevo = crear_usuario("admin", debe_cambiar=True)
    r = cliente_protegido.get("/stock", headers=headers_de(nuevo))
    assert r.status_code == 403 and "cambiar la contraseña" in r.json()["detail"]


def test_requiere_admin(cliente_protegido, crear_usuario, headers_de):
    assert cliente_protegido.get("/admin", headers=headers_de(crear_usuario("supervisor"))).status_code == 403
    admin = crear_usuario("admin")
    assert cliente_protegido.get("/admin", headers=headers_de(admin)).json() == {"id": admin.id}
