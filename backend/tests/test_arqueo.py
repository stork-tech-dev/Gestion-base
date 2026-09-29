"""Tests de services/arqueo.py y services/notificaciones.py (sesión 07)."""
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.core.errores import DatoInvalido, NoEncontrado, ReglaDeNegocio
from app.core.utils import ahora_db
from app.models import Auditoria, EstadoTurno, MedioDePago, Notificacion, Rol, Usuario
from app.services import arqueo as servicio
from app.services import notificaciones as servicio_notificaciones
from app.services import turnos as servicio_turnos
from app.services import ventas as servicio_ventas
from app.services.stock import registrar_ingreso
from tests.fabricas import abrir_turno_de_test, catalogo

D = Decimal
GRUPO = "Clover/Payway"


def _medio(db, nombre):
    return db.scalar(select(MedioDePago).where(MedioDePago.nombre == nombre))


@pytest.fixture
def e(db, crear_usuario):
    admin = crear_usuario("admin", nombre="Admin Uno")
    cat = catalogo(db, admin)
    producto = cat["alta"]("Campera", costo="10000")  # margen 0 → precio 10000
    registrar_ingreso(db, admin, producto.id, 50, None, None)
    return SimpleNamespace(admin=admin, producto=producto, vendedor=crear_usuario("vendedor", nombre="Vendedor Uno"),
                           turno=abrir_turno_de_test(db, admin, efectivo="5000"))


def _vender(db, e, medio_nombre):
    venta = servicio_ventas.iniciar_venta(db, e.vendedor, None)
    venta, _ = servicio_ventas.agregar_item(db, e.vendedor, venta.id, producto_id=e.producto.id)
    venta = servicio_ventas.registrar_pagos(db, e.vendedor, venta.id, [
        {"medio_de_pago_id": _medio(db, medio_nombre).id, "monto": venta.cobrable, "plan_cuotas_id": None}])
    return servicio_ventas.confirmar_venta(db, e.vendedor, venta.id, venta.total, None)


def _linea(lineas, nombre):
    return next(l for l in lineas if l.medio_nombre == nombre)


def _declarar(lineas, **montos):
    """Declara lo esperado salvo los medios pasados por nombre (con _ por espacio)."""
    return [SimpleNamespace(medio_de_pago_id=l.medio_de_pago_id, grupo_terminal=l.grupo_terminal,
                            monto_declarado=D(montos.get(l.medio_nombre.replace(" ", "_"), l.monto_esperado)))
            for l in lineas]


def _cerrar_a_mano(db, turno, usuario):
    turno.estado = EstadoTurno.CERRADO
    turno.fecha_cierre = ahora_db()
    turno.usuario_cierre_id = usuario.id
    db.flush()


def test_esperado_efectivo_es_apertura_mas_cobros_menos_anulaciones_menos_retiros(db, e):
    _vender(db, e, "Efectivo")
    anulada = _vender(db, e, "Efectivo")
    servicio_ventas.anular_venta(db, e.admin, anulada.id, "Error", None)
    servicio_turnos.registrar_retiro(db, e.admin, D("2000"), "Proveedor", None)
    lineas, total = servicio.calcular_esperado(db, e.turno)
    # 5000 + 10000 + 10000 - 10000 - 2000
    assert _linea(lineas, "Efectivo").monto_esperado == D("13000")
    assert lineas[0].es_efectivo
    assert total == D("13000")


def test_debito_y_credito_van_en_la_linea_del_grupo(db, e):
    _vender(db, e, "Débito")
    lineas, total = servicio.calcular_esperado(db, e.turno)
    nombres = [l.medio_nombre for l in lineas]
    assert GRUPO in nombres and "Débito" not in nombres and "Tarjeta de Crédito" not in nombres
    grupo = _linea(lineas, GRUPO)
    assert (grupo.medio_de_pago_id, grupo.grupo_terminal, grupo.monto_esperado) == (None, GRUPO, D("10000"))
    assert total == D("15000")


def test_venta_de_turno_a_anulada_en_turno_b_resta_en_b_y_no_cambia_a(db, e, crear_usuario):
    venta = _vender(db, e, "Transferencia")
    antes_a, _ = servicio.calcular_esperado(db, e.turno)
    servicio.registrar_arqueo(db, e.admin, e.turno.id, _declarar(antes_a),
                              sum(l.monto_esperado for l in antes_a), None)
    turno_b = abrir_turno_de_test(db, e.admin, efectivo="0")
    servicio_ventas.anular_venta(db, e.admin, venta.id, "Devolución", None)
    lineas_b, _ = servicio.calcular_esperado(db, turno_b)
    assert _linea(lineas_b, "Transferencia").monto_esperado == D("-10000")  # negativa, se muestra tal cual
    despues_a, _ = servicio.calcular_esperado(db, db.get(type(e.turno), e.turno.id))
    assert _linea(despues_a, "Transferencia").monto_esperado == D("10000")


def test_medio_inactivo_con_movimientos_sigue_en_el_arqueo(db, e):
    _vender(db, e, "Transferencia")
    _medio(db, "Transferencia").activo = False
    db.flush()
    lineas, _ = servicio.calcular_esperado(db, e.turno)
    assert _linea(lineas, "Transferencia").monto_esperado == D("10000")


def test_arqueo_sin_diferencia_cierra_el_turno_sin_notificar(db, e):
    _vender(db, e, "Efectivo")
    lineas, total = servicio.calcular_esperado(db, e.turno)
    arqueo = servicio.registrar_arqueo(db, e.vendedor, e.turno.id, _declarar(lineas), total, "10.0.0.1")
    assert arqueo.diferencia == D("0") and not arqueo.notificacion_enviada
    turno = servicio_turnos.obtener_turno(db, e.turno.id)
    assert (turno.estado, turno.usuario_cierre_id) == (EstadoTurno.CERRADO, e.vendedor.id)
    assert turno.fecha_cierre is not None
    assert db.scalar(select(Auditoria.id).where(Auditoria.accion == "caja.arqueo_cerrado",
                                                Auditoria.entidad_id == e.turno.id)) is not None
    assert db.scalar(select(Notificacion.id)) is None


def test_arqueo_con_diferencia_notifica_a_cada_admin_activo(db, e, crear_usuario):
    otro_admin = crear_usuario("admin")
    inactivo = crear_usuario("admin", activo=False)
    _vender(db, e, "Efectivo")
    lineas, total = servicio.calcular_esperado(db, e.turno)
    declarados = _declarar(lineas, Efectivo="14000")  # esperado 15000
    arqueo = servicio.registrar_arqueo(db, e.vendedor, e.turno.id, declarados, total - D("1000"), None)
    db.refresh(arqueo)
    assert arqueo.diferencia == D("-1000.00") and arqueo.notificacion_enviada
    item = next(i for i in arqueo.items if i.medio_de_pago_id == _medio(db, "Efectivo").id)
    assert item.diferencia == D("-1000.00")
    notificaciones = db.scalars(select(Notificacion)).all()
    # La base de test ya trae el admin del seed (migrations/seed.sql): se
    # compara contra TODOS los admin activos, no contra una lista fija.
    admins_activos = db.scalars(select(Usuario.id).join(Rol, Rol.id == Usuario.rol_id)
                                .where(Rol.nombre == "admin", Usuario.activo.is_(True))).all()
    assert {e.admin.id, otro_admin.id} <= set(admins_activos)
    assert sorted(n.usuario_id for n in notificaciones) == sorted(admins_activos)
    assert inactivo.id not in [n.usuario_id for n in notificaciones]
    n = notificaciones[0]
    assert n.titulo == f"Diferencia en arqueo — {e.turno.fecha_apertura:%d/%m/%Y}"
    assert "-$ 1.000,00" in n.cuerpo and "Vendedor Uno" in n.cuerpo and "Efectivo" in n.cuerpo
    assert n.metadata_["turno_id"] == e.turno.id and n.metadata_["diferencia"] == "-1000.00"


def test_arqueo_recalcula_el_esperado_en_el_backend(db, e):
    lineas, _ = servicio.calcular_esperado(db, e.turno)
    _vender(db, e, "Efectivo")  # entra después de que la pantalla cargó el esperado
    arqueo = servicio.registrar_arqueo(db, e.admin, e.turno.id, _declarar(lineas),
                                       sum(l.monto_esperado for l in lineas), None)
    assert arqueo.total_esperado == D("15000") and arqueo.diferencia == D("-10000")


def test_arqueo_falta_declarar_un_medio_400(db, e):
    lineas, _ = servicio.calcular_esperado(db, e.turno)
    with pytest.raises(DatoInvalido, match="Falta declarar"):
        servicio.registrar_arqueo(db, e.admin, e.turno.id, _declarar(lineas)[1:], D("0"), None)


def test_arqueo_total_que_no_suma_400(db, e):
    lineas, total = servicio.calcular_esperado(db, e.turno)
    with pytest.raises(DatoInvalido, match="total declarado"):
        servicio.registrar_arqueo(db, e.admin, e.turno.id, _declarar(lineas), total + D("1"), None)


def test_arqueo_medio_que_no_esta_en_el_esperado_409(db, e):
    lineas, total = servicio.calcular_esperado(db, e.turno)
    declarados = _declarar(lineas) + [SimpleNamespace(medio_de_pago_id=None, grupo_terminal="Otro",
                                                      monto_declarado=D("0"))]
    with pytest.raises(ReglaDeNegocio, match="cambiaron"):
        servicio.registrar_arqueo(db, e.admin, e.turno.id, declarados, total, None)


def test_arqueo_de_turno_cerrado_409(db, e):
    lineas, total = servicio.calcular_esperado(db, e.turno)
    servicio.registrar_arqueo(db, e.admin, e.turno.id, _declarar(lineas), total, None)
    with pytest.raises(ReglaDeNegocio, match="ya está cerrado"):
        servicio.registrar_arqueo(db, e.admin, e.turno.id, _declarar(lineas), total, None)
    with pytest.raises(ReglaDeNegocio, match="ya está cerrado"):
        servicio.esperado_de_turno(db, e.turno.id)


def test_se_puede_cerrar_un_turno_de_dia_anterior(db, e):
    from datetime import timedelta
    e.turno.fecha_apertura = ahora_db() - timedelta(days=1)
    db.flush()
    lineas, total = servicio.calcular_esperado(db, e.turno)
    servicio.registrar_arqueo(db, e.admin, e.turno.id, _declarar(lineas), total, None)
    assert servicio_turnos.obtener_turno_activo(db) is None


def test_obtener_arqueo_de_turno_sin_arqueo_404(db, e):
    with pytest.raises(NoEncontrado):
        servicio.obtener_arqueo(db, e.turno.id)


def test_notificaciones_propias_y_marcar_leidas(db, e, crear_usuario):
    otro_admin = crear_usuario("admin")
    lineas, total = servicio.calcular_esperado(db, e.turno)
    servicio.registrar_arqueo(db, e.admin, e.turno.id, _declarar(lineas, Efectivo="4000"), total - D("1000"), None)
    propias, no_leidas = servicio_notificaciones.listar(db, e.admin)
    assert len(propias) == 1 and no_leidas == 1 and propias[0].usuario_id == e.admin.id
    with pytest.raises(NoEncontrado):
        servicio_notificaciones.marcar_leida(db, otro_admin, propias[0].id)
    assert servicio_notificaciones.marcar_leida(db, e.admin, propias[0].id).leida
    servicio_notificaciones.marcar_todas(db, otro_admin)
    assert servicio_notificaciones.listar(db, otro_admin)[1] == 0
