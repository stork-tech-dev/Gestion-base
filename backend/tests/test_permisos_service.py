import pytest
from sqlalchemy import select

from app.core.errores import DatoInvalido, ReglaDeNegocio
from app.core.permisos import Modulo, Recurso, recursos_de_modulo
from app.core.seguridad import resolver_permiso
from app.models import Rol, RolPermiso, UsuarioPermiso
from app.schemas.permisos import PermisoEntrada
from app.services import permisos


def _nodo(arbol, modulo, recurso=None):
    nodo = next(n for n in arbol["modulos"] if n["modulo"] == modulo)
    return nodo if recurso is None else next(r for r in nodo["recursos"] if r["recurso"] == recurso)


def test_crear_permisos_vacios(db):
    rol = Rol(nombre="cajero", es_sistema=False)
    db.add(rol)
    db.flush()
    permisos.crear_permisos_vacios(db, rol)
    filas = db.scalars(select(RolPermiso).where(RolPermiso.rol_id == rol.id)).all()
    assert len(filas) == len(Modulo) + len(Recurso)
    assert not any(f.puede_ver or f.puede_crear or f.puede_editar or f.puede_eliminar for f in filas)


def test_arbol_de_rol(db):
    vendedor = db.scalar(select(Rol).where(Rol.nombre == "vendedor"))
    arbol = permisos.arbol_de_rol(db, vendedor)
    stock = _nodo(arbol, "stock")
    assert stock["puede_ver"] is True and stock["puede_crear"] is False
    assert [r["recurso"] for r in stock["recursos"]] == [r.value for r in recursos_de_modulo(Modulo.STOCK)]
    baja = _nodo(arbol, "stock", "stock.baja")
    assert baja["puede_crear"] is True and baja["puede_ver"] is None  # "ver" no aplica
    assert _nodo(arbol, "auditoria")["acciones_aplicables"] == ["ver"]


def test_arbol_de_usuario_distingue_heredado_de_override(db, crear_usuario):
    vendedor = crear_usuario("vendedor")
    db.add(UsuarioPermiso(usuario_id=vendedor.id, modulo="proveedores", recurso=None, puede_ver=True))
    db.flush()
    arbol = permisos.arbol_de_usuario(db, vendedor)
    prov = _nodo(arbol, "proveedores")
    assert prov["puede_ver"] and prov["override_ver"] and not prov["heredado_ver"]
    stock = _nodo(arbol, "stock")
    assert stock["puede_ver"] and stock["heredado_ver"] and not stock["override_ver"]


def test_actualizar_permisos_de_rol(db, crear_usuario):
    rol = Rol(nombre="deposito", es_sistema=False)
    db.add(rol)
    db.flush()
    permisos.crear_permisos_vacios(db, rol)
    usuario = crear_usuario(rol)
    entradas = [
        PermisoEntrada(modulo="stock", recurso=None, puede_ver=True, puede_crear=True),
        PermisoEntrada(modulo="stock", recurso="stock.baja", puede_crear=True, puede_ver=True),  # ver no aplica
    ]
    permisos.actualizar_permisos_rol(db, None, rol, entradas, None)
    assert resolver_permiso(db, usuario.id, Modulo.STOCK, "crear")
    baja = db.scalar(select(RolPermiso).where(RolPermiso.rol_id == rol.id, RolPermiso.recurso == "stock.baja"))
    assert baja.puede_crear and not baja.puede_ver


def test_permisos_invalidos_o_del_admin(db):
    admin = db.scalar(select(Rol).where(Rol.nombre == "admin"))
    with pytest.raises(ReglaDeNegocio):
        permisos.actualizar_permisos_rol(db, None, admin, [], None)
    vendedor = db.scalar(select(Rol).where(Rol.nombre == "vendedor"))
    with pytest.raises(DatoInvalido):
        permisos.actualizar_permisos_rol(db, None, vendedor, [PermisoEntrada(modulo="ventas", recurso="stock.baja")], None)


def test_overrides_de_usuario_solo_guardan_lo_marcado(db, crear_usuario):
    vendedor = crear_usuario("vendedor")
    permisos.actualizar_permisos_usuario(
        db, None, vendedor, [PermisoEntrada(modulo="caja", recurso="caja.retiro", puede_crear=True)], None
    )
    assert resolver_permiso(db, vendedor.id, Modulo.CAJA, "crear", Recurso.CAJA_RETIRO)
    permisos.actualizar_permisos_usuario(db, None, vendedor, [PermisoEntrada(modulo="caja", recurso="caja.retiro")], None)
    assert db.scalars(select(UsuarioPermiso).where(UsuarioPermiso.usuario_id == vendedor.id)).all() == []


def test_accesos_de_rol_y_de_usuario(db, crear_usuario):
    vendedor = crear_usuario("vendedor")
    accesos = {a["clave"]: a for a in permisos.accesos_de_usuario(db, vendedor)}
    baja = accesos["stock:stock.baja:crear"]
    assert baja["heredado"] and baja["permitido"] and not baja["override"]
    retiro = accesos["caja:caja.retiro:crear"]
    assert not retiro["heredado"] and not retiro["permitido"]
    admin = db.scalar(select(Rol).where(Rol.nombre == "admin"))
    assert all(a["heredado"] for a in permisos.accesos_de_rol(db, admin))


def test_actualizar_accesos_no_persiste_lo_heredado(db, crear_usuario):
    vendedor = crear_usuario("vendedor")
    permisos.actualizar_accesos_usuario(db, None, vendedor, ["caja:caja.retiro:crear", "stock:stock.baja:crear"], None)
    filas = db.scalars(select(UsuarioPermiso).where(UsuarioPermiso.usuario_id == vendedor.id)).all()
    assert [(f.modulo, f.recurso, f.puede_crear) for f in filas] == [("caja", "caja.retiro", True)]
    accesos = {a["clave"]: a for a in permisos.accesos_de_usuario(db, vendedor)}
    assert accesos["caja:caja.retiro:crear"]["override"] and accesos["caja:caja.retiro:crear"]["permitido"]
    permisos.actualizar_accesos_usuario(db, None, vendedor, [], None)
    assert db.scalars(select(UsuarioPermiso).where(UsuarioPermiso.usuario_id == vendedor.id)).all() == []


def test_acceso_desconocido(db, crear_usuario):
    with pytest.raises(DatoInvalido):
        permisos.actualizar_accesos_usuario(db, None, crear_usuario("vendedor"), ["no:existe:ver"], None)


def test_override_general_cubre_accesos_de_sus_recursos(db, crear_usuario):
    """Un override de módulo completo (recurso=None) debe habilitar también
    los accesos de los recursos de ese módulo, igual que resolver_permiso:
    override y permitido tienen que quedar coherentes (antes, override daba
    False para el acceso puntual mientras permitido ya daba True)."""
    vendedor = crear_usuario("vendedor")
    permisos.actualizar_permisos_usuario(
        db, None, vendedor, [PermisoEntrada(modulo="caja", recurso=None, puede_crear=True)], None
    )
    accesos = {a["clave"]: a for a in permisos.accesos_de_usuario(db, vendedor)}
    retiro = accesos["caja:caja.retiro:crear"]
    assert not retiro["heredado"] and retiro["override"] and retiro["permitido"]


def test_otorgable_segun_el_autor(db, crear_usuario):
    supervisor = crear_usuario("supervisor")
    vendedor = crear_usuario("vendedor")
    admin = crear_usuario("admin")
    accesos = {a["clave"]: a for a in permisos.accesos_de_usuario(db, vendedor, autor=supervisor)}
    assert accesos["auditoria::ver"]["otorgable"] is False          # reservado al Admin
    assert accesos["usuarios::crear"]["otorgable"] is False         # reservado al Admin
    assert accesos["stock:stock.baja:crear"]["otorgable"] is True   # el supervisor lo tiene
    assert accesos["caja:caja.retiro:crear"]["otorgable"] is True   # caja crear general del supervisor
    assert accesos["proveedores:dolar.cambio_masivo:editar"]["otorgable"] is False  # proveedores solo ver
    assert all(a["otorgable"] for a in permisos.accesos_de_usuario(db, vendedor, autor=admin))
    assert all(a["otorgable"] for a in permisos.accesos_de_usuario(db, vendedor))


def test_otorgable_en_el_arbol_y_en_los_accesos_del_rol(db, crear_usuario):
    supervisor = crear_usuario("supervisor")
    vendedor = crear_usuario("vendedor")
    arbol = permisos.arbol_de_usuario(db, vendedor, autor=supervisor)
    assert _nodo(arbol, "usuarios")["otorgable_ver"] is False
    assert _nodo(arbol, "stock", "stock.baja")["otorgable_crear"] is True
    assert _nodo(arbol, "proveedores")["otorgable_editar"] is False
    assert _nodo(arbol, "stock", "stock.baja").get("otorgable_ver") is None  # "ver" no aplica
    assert "otorgable_ver" not in _nodo(permisos.arbol_de_usuario(db, vendedor), "stock")
    rol_vendedor = vendedor.rol
    accesos_rol = {a["clave"]: a for a in permisos.accesos_de_rol(db, rol_vendedor, autor=supervisor)}
    assert accesos_rol["auditoria::ver"]["otorgable"] is False


def test_arbol_y_accesos_de_usuario_con_rol_inactivo(db, crear_usuario):
    """Mismo criterio que resolver_permiso: rol inactivo (no-admin) → nada se
    hereda y los overrides propios tampoco habilitan nada; el flag de
    override sigue mostrando lo guardado (vista de edición)."""
    vendedor = crear_usuario("vendedor")
    permisos.actualizar_permisos_usuario(
        db, None, vendedor, [PermisoEntrada(modulo="caja", recurso="caja.retiro", puede_crear=True)], None
    )
    vendedor.rol.activo = False
    db.flush()

    accesos = {a["clave"]: a for a in permisos.accesos_de_usuario(db, vendedor)}
    baja = accesos["stock:stock.baja:crear"]
    assert not baja["heredado"] and not baja["permitido"]
    retiro = accesos["caja:caja.retiro:crear"]
    assert retiro["override"] and not retiro["permitido"]  # lo guardado se ve, pero no habilita nada

    arbol = permisos.arbol_de_usuario(db, vendedor)
    stock = _nodo(arbol, "stock")
    assert stock["puede_ver"] is False and not stock["heredado_ver"]
