from decimal import Decimal

import pytest
from sqlalchemy import select, text

from app.core.errores import DatoInvalido, ReglaDeNegocio, SinPermiso
from app.models import Auditoria, EstadoProveedor, Moneda
from app.schemas.proveedores import ProveedorCrear, ProveedorEditar
from app.services import proveedores as servicio


def _crear(db, autor, **datos):
    base = {"nombre": "Proveedor de prueba", "moneda": "ars"}
    base.update(datos)
    return servicio.crear_proveedor(db, autor, ProveedorCrear(**base), None)


def _editar(db, autor, proveedor, **cambios):
    datos = {"nombre": proveedor.nombre, "moneda": proveedor.moneda.value}
    datos.update(cambios)
    return servicio.editar_proveedor(db, autor, proveedor, ProveedorEditar(**datos), None)


def test_alta_en_pesos_ignora_el_dolar(db, crear_usuario):
    admin = crear_usuario("admin")
    p = _crear(db, admin, nombre="  Textil   Norte ", dolar_actual="100", email="Ventas@Textil.com")
    assert p.nombre == "Textil Norte" and p.moneda is Moneda.ARS and p.dolar_actual is None
    assert p.email == "ventas@textil.com"
    assert db.scalar(select(Auditoria).where(Auditoria.accion == "proveedor.crear", Auditoria.entidad_id == p.id))


def test_alta_en_dolares_exige_dolar(db, crear_usuario):
    admin = crear_usuario("admin")
    with pytest.raises(DatoInvalido):
        _crear(db, admin, nombre="Importadora", moneda="usd")
    p = _crear(db, admin, nombre="Importadora", moneda="usd", dolar_actual="1250.456")
    assert p.dolar_actual == Decimal("1250.46")


def test_nombre_repetido_sin_tildes(db, crear_usuario):
    admin = crear_usuario("admin")
    _crear(db, admin, nombre="Córdoba Textil")
    with pytest.raises(ReglaDeNegocio) as error:
        _crear(db, admin, nombre="cordoba textil")
    assert "Córdoba Textil" in error.value.mensaje


def test_edicion_no_toca_el_dolar(db, crear_usuario):
    admin = crear_usuario("admin")
    p = _crear(db, admin, nombre="Importadora", moneda="usd", dolar_actual="1000")
    _editar(db, admin, p, provincia="Córdoba", dolar_actual="2000")
    assert p.provincia == "Córdoba" and p.dolar_actual == Decimal("1000")


def test_cambio_de_moneda_sin_productos(db, crear_usuario):
    admin = crear_usuario("admin")
    p = _crear(db, admin, nombre="Cambiante")
    with pytest.raises(DatoInvalido):
        _editar(db, admin, p, moneda="usd")
    _editar(db, admin, p, moneda="usd", dolar_actual="900")
    assert p.moneda is Moneda.USD and p.dolar_actual == Decimal("900")
    _editar(db, admin, p, moneda="ars")
    assert p.moneda is Moneda.ARS and p.dolar_actual is None


def test_cambio_de_moneda_con_productos_da_409(db, crear_usuario, monkeypatch):
    admin = crear_usuario("admin")
    p = _crear(db, admin, nombre="Con productos")
    monkeypatch.setattr(servicio, "contar_productos", lambda db, proveedor_id, solo_activos=False: 3)
    with pytest.raises(ReglaDeNegocio) as error:
        _editar(db, admin, p, moneda="usd", dolar_actual="900")
    assert error.value.mensaje == "No se puede cambiar la moneda de un proveedor con productos cargados."


def test_contar_productos_sin_tabla_da_cero(db, crear_usuario):
    admin = crear_usuario("admin")
    p = _crear(db, admin, nombre="Sin tabla")
    existe = db.execute(text("SELECT to_regclass('public.productos') IS NOT NULL")).scalar_one()
    if not existe:
        assert servicio.contar_productos(db, p.id) == 0


def test_estados(db, crear_usuario, monkeypatch):
    admin = crear_usuario("admin")
    supervisor = crear_usuario("supervisor")
    p = _crear(db, admin, nombre="Estados")
    servicio.cambiar_estado(db, admin, p, EstadoProveedor.DESACTIVADO, False, None)
    assert p.estado is EstadoProveedor.DESACTIVADO
    servicio.cambiar_estado(db, supervisor, p, EstadoProveedor.ACTIVO, False, None)  # desactivado: libre
    servicio.cambiar_estado(db, admin, p, EstadoProveedor.INHABILITADO, False, None)
    with pytest.raises(SinPermiso) as error:
        servicio.cambiar_estado(db, supervisor, p, EstadoProveedor.ACTIVO, False, None)
    assert error.value.mensaje == "Reactivar un proveedor inhabilitado requiere Admin"
    servicio.cambiar_estado(db, admin, p, EstadoProveedor.ACTIVO, False, None)
    acciones = db.scalars(select(Auditoria.accion).where(Auditoria.entidad == "proveedor", Auditoria.entidad_id == p.id)).all()
    assert {"proveedor.desactivar", "proveedor.reactivar", "proveedor.inhabilitar"} <= set(acciones)


def test_baja_con_productos_activos_exige_confirmacion(db, crear_usuario, monkeypatch):
    admin = crear_usuario("admin")
    p = _crear(db, admin, nombre="Con activos")
    monkeypatch.setattr(servicio, "contar_productos", lambda db, proveedor_id, solo_activos=False: 2)
    with pytest.raises(ReglaDeNegocio) as error:
        servicio.cambiar_estado(db, admin, p, EstadoProveedor.DESACTIVADO, False, None)
    assert "2 producto(s) activo(s)" in error.value.mensaje
    servicio.cambiar_estado(db, admin, p, EstadoProveedor.DESACTIVADO, True, None)
    assert p.estado is EstadoProveedor.DESACTIVADO


def test_listado_y_filtros(db, crear_usuario):
    admin = crear_usuario("admin")
    _crear(db, admin, nombre="Zeta Textil", provincia="Córdoba", pais="Argentina")
    _crear(db, admin, nombre="Alfa Import", moneda="usd", dolar_actual="1500", pais="China")
    _crear(db, admin, nombre="Beta Import", moneda="usd", dolar_actual="1100", pais="China")
    nombres = [p.nombre for p in servicio.listar_proveedores(db)]
    assert nombres[:3] == ["Alfa Import", "Beta Import", "Zeta Textil"]
    assert [p.nombre for p in servicio.listar_proveedores(db, provincia="cordoba")] == ["Zeta Textil"]
    assert [p.nombre for p in servicio.listar_proveedores(db, dolar_desde=Decimal("1200"))] == ["Alfa Import"]
    assert [p.nombre for p in servicio.listar_proveedores(db, moneda=Moneda.ARS, pais="argentina")] == ["Zeta Textil"]


def test_hay_proveedores_en_dolares_solo_activos(db, crear_usuario):
    admin = crear_usuario("admin")
    assert servicio.hay_proveedores_en_dolares(db) is False
    p = _crear(db, admin, nombre="Único en dólares", moneda="usd", dolar_actual="1000")
    assert servicio.hay_proveedores_en_dolares(db) is True
    servicio.cambiar_estado(db, admin, p, EstadoProveedor.DESACTIVADO, False, None)
    assert servicio.hay_proveedores_en_dolares(db) is False
