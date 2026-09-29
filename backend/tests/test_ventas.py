"""Tests de services/ventas.py (sesión 06): carrito, recálculo, promociones,
pagos, confirmación, descarte y listado."""
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.core.errores import DatoInvalido, NoEncontrado, ReglaDeNegocio, SinPermiso
from app.core.utils import ahora_db
from app.models import (
    Auditoria, EstadoTurno, EstadoVenta, MedioDePago, MovimientoStock, TipoAlcancePromocion, TipoMovimientoStock,
    TipoPromocion, Venta, VentaItem, VentaPago,
)
from app.schemas.clientes import ClienteCrear
from app.schemas.descuentos import MotivoDescuentoCrear
from app.schemas.medios_pago import PlanCuotasCrear
from app.schemas.productos import ProductoEditar
from app.schemas.promociones import PromocionAlcanceDatos, PromocionCrear
from app.schemas.ventas import VentaResponse
from app.services import categorias as servicio_categorias
from app.services import clientes as servicio_clientes
from app.services import descuentos as servicio_descuentos
from app.services import medios_pago as servicio_medios
from app.services import productos as servicio_productos
from app.services import promociones as servicio_promociones
from app.services import ventas as servicio
from app.services.stock import registrar_ingreso
from tests.fabricas import abrir_turno_de_test, catalogo

D = Decimal


@pytest.fixture
def e(db, crear_usuario):
    admin = crear_usuario("admin")
    cat = catalogo(db, admin)
    p10 = cat["alta"]("Campera", costo="10000")
    p8 = cat["alta"]("Buzo", costo="8000")
    p6 = cat["alta"]("Remera", costo="6000")
    for p in (p10, p8, p6):
        registrar_ingreso(db, admin, p.id, 10, None, None)
    turno = abrir_turno_de_test(db, admin)
    return SimpleNamespace(
        admin=admin, cat=cat, p10=p10, p8=p8, p6=p6, turno=turno,
        vendedor=crear_usuario("vendedor", nombre="Vendedor Uno"),
        supervisor=crear_usuario("supervisor", nombre="Supervisor Uno"),
    )


def _medio(db, nombre) -> MedioDePago:
    return db.scalar(select(MedioDePago).where(MedioDePago.nombre == nombre))


def _venta(db, autor, *productos):
    venta = servicio.iniciar_venta(db, autor, None)
    for p in productos:
        venta, _ = servicio.agregar_item(db, autor, venta.id, producto_id=p.id)
    return venta


def _pagar(db, autor, venta, *pagos):
    """pagos: (medio, monto) o (medio, monto, plan)."""
    datos = [{"medio_de_pago_id": p[0].id, "monto": D(str(p[1])),
              "plan_cuotas_id": p[2].id if len(p) > 2 else None} for p in pagos]
    return servicio.registrar_pagos(db, autor, venta.id, datos)


def _confirmar(db, autor, venta, *pagos):
    if pagos:
        venta = _pagar(db, autor, venta, *pagos)
    return servicio.confirmar_venta(db, autor, venta.id, venta.total, None)


def _motivo(db, admin, nombre="Cliente frecuente", **extra):
    return servicio_descuentos.crear_motivo(db, admin, MotivoDescuentoCrear(nombre=nombre, **extra), None)


def _todos():
    return PromocionAlcanceDatos(tipo_alcance=TipoAlcancePromocion.TODOS_PRODUCTOS, referencia_id=0)


def _promo(db, admin, nombre, tipo=TipoPromocion.DOS_X_UNO, alcances=None, **extra):
    return servicio_promociones.crear_promocion(
        db, admin, PromocionCrear(nombre=nombre, tipo=tipo, alcances=alcances or [_todos()], **extra), None)


def _editar_producto(db, autor, producto, **cambios):
    datos = {"categoria_id": producto.categoria_id, "costo": str(producto.costo), "margen": str(producto.margen),
             "descripcion": producto.descripcion}
    datos.update(cambios)
    return servicio_productos.editar_producto(db, autor, producto, ProductoEditar(**datos), None)


def _auditorias(db, accion, venta_id):
    return db.scalars(select(Auditoria).where(Auditoria.accion == accion, Auditoria.entidad_id == venta_id)).all()


# --- Iniciar / dueño ------------------------------------------------------------

def test_iniciar_dos_veces_devuelve_la_misma(db, e):
    v1 = servicio.iniciar_venta(db, e.vendedor, None)
    v2 = servicio.iniciar_venta(db, e.vendedor, None)
    assert v1.id == v2.id
    assert v1.numero.startswith("V-") and len(v1.numero) == 8 and v1.numero[2:].isdigit()
    assert v1.estado is EstadoVenta.EN_CURSO
    assert len(_auditorias(db, "venta.iniciar", v1.id)) == 1
    assert servicio.venta_en_curso(db, e.vendedor).id == v1.id


def test_otro_usuario_no_opera_la_venta(db, e):
    venta = servicio.iniciar_venta(db, e.vendedor, None)
    with pytest.raises(SinPermiso, match="Solo quien inició"):
        servicio.agregar_item(db, e.supervisor, venta.id, producto_id=e.p10.id)


def test_obtener_venta_inexistente(db):
    with pytest.raises(NoEncontrado, match="Venta no encontrada"):
        servicio.obtener_venta(db, 999_999_999)


# --- Ítems ------------------------------------------------------------------------

def test_agregar_por_codigo_y_por_id(db, e):
    venta = servicio.iniciar_venta(db, e.vendedor, None)
    venta, aviso = servicio.agregar_item(db, e.vendedor, venta.id, codigo=e.p10.codigo_con_verificador)
    assert aviso is None
    venta, _ = servicio.agregar_item(db, e.vendedor, venta.id, producto_id=e.p8.id)
    assert [i.producto_id for i in venta.items] == [e.p10.id, e.p8.id]
    assert [i.orden for i in venta.items] == [1, 2]
    item = venta.items[0]
    assert item.precio_lista == D("10000") and item.precio_final == D("10000")
    assert item.costo_unitario == D("10000")
    assert venta.subtotal == D("18000") and venta.total == D("18000") and venta.descuento_total == 0


def test_agregar_exige_codigo_o_producto(db, e):
    venta = servicio.iniciar_venta(db, e.vendedor, None)
    with pytest.raises(DatoInvalido):
        servicio.agregar_item(db, e.vendedor, venta.id)
    with pytest.raises(DatoInvalido):
        servicio.agregar_item(db, e.vendedor, venta.id, codigo="X", producto_id=e.p10.id)


def test_agregar_codigo_inexistente_404(db, e):
    venta = servicio.iniciar_venta(db, e.vendedor, None)
    with pytest.raises(NoEncontrado):
        servicio.agregar_item(db, e.vendedor, venta.id, codigo="ZZZZZ9")


def test_agregar_producto_inactivo_409(db, e):
    servicio_productos.cambiar_estado_producto(db, e.admin, e.p10, False, None)
    venta = servicio.iniciar_venta(db, e.vendedor, None)
    with pytest.raises(ReglaDeNegocio, match="está inactivo"):
        servicio.agregar_item(db, e.vendedor, venta.id, producto_id=e.p10.id)


def test_agregar_sin_stock_avisa_y_agrega(db, e):
    sin_stock = e.cat["alta"]("Gorro", costo="3000")
    venta = servicio.iniciar_venta(db, e.vendedor, None)
    venta, aviso = servicio.agregar_item(db, e.vendedor, venta.id, producto_id=sin_stock.id)
    assert aviso == "Sin stock de 'Gorro': controlá bien el código antes de continuar."
    assert len(venta.items) == 1


def test_aviso_cuenta_lo_ya_cargado(db, e):
    uno = e.cat["alta"]("Bufanda", costo="3000")
    registrar_ingreso(db, e.admin, uno.id, 1, None, None)
    venta = servicio.iniciar_venta(db, e.vendedor, None)
    _, aviso = servicio.agregar_item(db, e.vendedor, venta.id, producto_id=uno.id)
    assert aviso is None
    venta, aviso = servicio.agregar_item(db, e.vendedor, venta.id, producto_id=uno.id)
    assert aviso is not None and "Bufanda" in aviso
    assert len(venta.items) == 2


def test_quitar_item(db, e):
    venta = _venta(db, e.vendedor, e.p10, e.p8)
    venta = servicio.quitar_item(db, e.vendedor, venta.id, venta.items[0].id)
    assert [i.producto_id for i in venta.items] == [e.p8.id]
    assert venta.total == D("8000")


def test_quitar_item_ajeno_404(db, e):
    otra = _venta(db, e.supervisor, e.p10)
    venta = _venta(db, e.vendedor, e.p8)
    with pytest.raises(NoEncontrado):
        servicio.quitar_item(db, e.vendedor, venta.id, otra.items[0].id)


# --- Cliente ------------------------------------------------------------------------

def test_asociar_y_quitar_cliente(db, e):
    cliente = servicio_clientes.crear_cliente(db, e.admin, ClienteCrear(nombre="Juana Pérez"), None)
    venta = _venta(db, e.vendedor, e.p10)
    venta = servicio.asociar_cliente(db, e.vendedor, venta.id, cliente.id)
    assert venta.cliente_id == cliente.id and venta.cliente.nombre == "Juana Pérez"
    venta = servicio.asociar_cliente(db, e.vendedor, venta.id, None)
    assert venta.cliente_id is None and venta.cliente is None


def test_asociar_cliente_inactivo_409(db, e):
    cliente = servicio_clientes.crear_cliente(db, e.admin, ClienteCrear(nombre="Inactivo"), None)
    servicio_clientes.cambiar_estado(db, e.admin, cliente, False, None)
    venta = _venta(db, e.vendedor, e.p10)
    with pytest.raises(ReglaDeNegocio, match="está inactivo"):
        servicio.asociar_cliente(db, e.vendedor, venta.id, cliente.id)


# --- Descuentos ------------------------------------------------------------------------

def test_descuento_encadenado_hacia_abajo(db, e):
    con_desc = e.cat["alta"]("Saco", costo="10000", descuento_producto="10")
    motivo = _motivo(db, e.admin)
    venta = _venta(db, e.vendedor, con_desc)
    item = venta.items[0]
    assert item.precio_unitario == D("9000")
    venta = servicio.aplicar_descuento_item(db, e.vendedor, venta.id, item.id, motivo.id, 15, None)
    item = venta.items[0]
    # 10000 × 0.9 × 0.85 = 7650 → hacia abajo al múltiplo de $10 = 7650
    assert item.precio_final == D("7650")
    assert item.descuento_item == D("15") and item.motivo_descuento_id == motivo.id
    assert venta.total == D("7650") and venta.descuento_total == D("2350")
    audit = _auditorias(db, "venta.descuento", venta.id)
    assert len(audit) == 1
    assert audit[0].estado_anterior == {"item_id": item.id, "descuento_item": "0.00", "motivo_descuento_id": None}
    assert audit[0].estado_nuevo["motivo_descuento_id"] == motivo.id


def test_descuento_tope_suma_descuento_de_producto(db, e):
    # 30% propio + 25% de venta = 55% > tope 50%; 20% de venta (= 50%) sí vale.
    con_desc = e.cat["alta"]("Tapado", costo="10000", descuento_producto="30")
    motivo = _motivo(db, e.admin)
    venta = _venta(db, e.vendedor, con_desc)
    with pytest.raises(DatoInvalido, match="no puede superar"):
        servicio.aplicar_descuento_item(db, e.vendedor, venta.id, venta.items[0].id, motivo.id, 25, None)
    venta = servicio.aplicar_descuento_item(db, e.vendedor, venta.id, venta.items[0].id, motivo.id, 20, None)
    assert venta.items[0].descuento_item == D("20")


def test_descuento_no_en_item_en_promocion(db, e):
    _promo(db, e.admin, "2x1 todo")
    motivo = _motivo(db, e.admin)
    venta = _venta(db, e.vendedor, e.p10, e.p8)
    assert all(i.en_promocion for i in venta.items)
    with pytest.raises(ReglaDeNegocio, match="está en una promoción"):
        servicio.aplicar_descuento_item(db, e.vendedor, venta.id, venta.items[0].id, motivo.id, 10, None)


def test_quitar_descuento(db, e):
    motivo = _motivo(db, e.admin)
    venta = _venta(db, e.vendedor, e.p10)
    item_id = venta.items[0].id
    servicio.aplicar_descuento_item(db, e.vendedor, venta.id, item_id, motivo.id, 10, None)
    venta = servicio.aplicar_descuento_item(db, e.vendedor, venta.id, item_id, None, None, None)
    item = venta.items[0]
    assert item.descuento_item == 0 and item.motivo_descuento_id is None and item.porcentaje_modificado is False
    assert item.precio_final == D("10000") and venta.total == D("10000")


def test_porcentaje_modificado(db, e):
    motivo = _motivo(db, e.admin, porcentaje_sugerido=D("10"))
    venta = _venta(db, e.vendedor, e.p10)
    item_id = venta.items[0].id
    venta = servicio.aplicar_descuento_item(db, e.vendedor, venta.id, item_id, motivo.id, None, None)
    assert venta.items[0].descuento_item == D("10") and venta.items[0].porcentaje_modificado is False
    venta = servicio.aplicar_descuento_item(db, e.vendedor, venta.id, item_id, motivo.id, 15, None)
    assert venta.items[0].porcentaje_modificado is True


def test_descuento_item_inexistente_404(db, e):
    motivo = _motivo(db, e.admin)
    venta = _venta(db, e.vendedor, e.p10)
    with pytest.raises(NoEncontrado):
        servicio.aplicar_descuento_item(db, e.vendedor, venta.id, 999_999_999, motivo.id, 10, None)


# --- Promociones ------------------------------------------------------------------------

def test_promocion_automatica_2x1(db, e):
    promo = _promo(db, e.admin, "2x1 auto")
    venta = _venta(db, e.vendedor, e.p10, e.p8, e.p6)
    por_producto = {i.producto_id: i for i in venta.items}
    # Grupo [10000, 8000]: gratis el de 8000; el de 6000 sobra y se cobra.
    assert por_producto[e.p10.id].precio_final == D("10000") and por_producto[e.p10.id].en_promocion
    assert por_producto[e.p8.id].precio_final == 0 and por_producto[e.p8.id].en_promocion
    assert por_producto[e.p6.id].precio_final == D("6000") and not por_producto[e.p6.id].en_promocion
    assert venta.promocion_id == promo.id and venta.promocion_a_mano is False
    assert venta.subtotal == D("24000") and venta.total == D("16000") and venta.descuento_total == D("8000")


def test_elegir_promocion_a_mano_y_perderla_al_cambiar_el_carrito(db, e):
    dos_x_uno = _promo(db, e.admin, "2x1")
    porcentaje = _promo(db, e.admin, "10 off", tipo=TipoPromocion.PORCENTAJE, porcentaje_descuento=10)
    venta = _venta(db, e.vendedor, e.p10, e.p8, e.p6)
    assert venta.promocion_id == dos_x_uno.id
    ofrecidas = {o["promocion"].id: o["ahorro"] for o in servicio.promociones_para_venta(db, venta)}
    assert ofrecidas == {dos_x_uno.id: D("8000"), porcentaje.id: D("2400")}

    venta = servicio.elegir_promocion(db, e.vendedor, venta.id, porcentaje.id)
    assert venta.promocion_id == porcentaje.id and venta.promocion_a_mano is True
    assert venta.total == D("21600")          # 9000 + 7200 + 5400
    venta = servicio.recalcular(db, e.vendedor, venta.id)
    assert venta.promocion_id == porcentaje.id   # recalcular no la pierde

    venta, _ = servicio.agregar_item(db, e.vendedor, venta.id, producto_id=e.p6.id)
    assert venta.promocion_id == dos_x_uno.id and venta.promocion_a_mano is False


def test_elegir_sin_promocion_a_mano(db, e):
    _promo(db, e.admin, "2x1")
    venta = _venta(db, e.vendedor, e.p10, e.p8)
    venta = servicio.elegir_promocion(db, e.vendedor, venta.id, None)
    assert venta.promocion_id is None and venta.promocion_a_mano is True
    assert venta.total == D("18000") and not any(i.en_promocion for i in venta.items)


def test_elegir_promocion_que_no_aplica_409(db, e):
    otra = _promo(db, e.admin, "Vencida", fecha_inicio=ahora_db().date() - timedelta(days=10),
                  fecha_fin=ahora_db().date() - timedelta(days=5))
    venta = _venta(db, e.vendedor, e.p10)
    with pytest.raises(ReglaDeNegocio, match="no aplica"):
        servicio.elegir_promocion(db, e.vendedor, venta.id, otra.id)


def test_promocion_exclusiva_solo_con_su_cliente(db, e):
    cliente = servicio_clientes.crear_cliente(db, e.admin, ClienteCrear(nombre="Cliente VIP"), None)
    promo = _promo(db, e.admin, "VIP 20", tipo=TipoPromocion.PORCENTAJE, porcentaje_descuento=20)
    servicio_promociones.asignar_a_cliente(db, e.admin, cliente, promo.id, None)
    venta = _venta(db, e.vendedor, e.p10)
    assert servicio.promociones_para_venta(db, venta) == []
    assert venta.promocion_id is None and venta.total == D("10000")
    venta = servicio.asociar_cliente(db, e.vendedor, venta.id, cliente.id)
    assert [o["promocion"].id for o in servicio.promociones_para_venta(db, venta)] == [promo.id]
    assert venta.promocion_id == promo.id and venta.total == D("8000")


def test_promocion_con_alcance_de_medio(db, e):
    debito, efectivo = _medio(db, "Débito"), _medio(db, "Efectivo")
    promo = _promo(db, e.admin, "Débito 10", tipo=TipoPromocion.PORCENTAJE, porcentaje_descuento=10,
                   alcances=[_todos(), PromocionAlcanceDatos(tipo_alcance=TipoAlcancePromocion.MEDIO_DE_PAGO,
                                                             referencia_id=debito.id)])
    venta = _venta(db, e.vendedor, e.p10)
    venta = _pagar(db, e.vendedor, venta, (efectivo, 1))
    assert venta.promocion_id is None and venta.total == D("10000")
    venta = _pagar(db, e.vendedor, venta, (debito, 1))
    assert venta.promocion_id == promo.id and venta.total == D("9000")
    assert venta.pagos[0].monto == D("9000")
    venta = _pagar(db, e.vendedor, venta, (debito, 5000), (efectivo, 1))
    assert venta.promocion_id is None and venta.total == D("10000")


# --- Pagos ------------------------------------------------------------------------

def test_un_pago_toma_lo_cobrable(db, e):
    venta = _venta(db, e.vendedor, e.p10, e.p8)
    venta = _pagar(db, e.vendedor, venta, (_medio(db, "Efectivo"), 1))
    assert len(venta.pagos) == 1
    pago = venta.pagos[0]
    assert pago.monto == D("18000") and pago.recargo == 0 and pago.monto_total == D("18000")
    assert venta.total == D("18000") and venta.cobrable == D("18000")


def test_dos_pagos_el_segundo_es_el_resto(db, e):
    venta = _venta(db, e.vendedor, e.p10, e.p8)
    venta = _pagar(db, e.vendedor, venta, (_medio(db, "Efectivo"), 5000), (_medio(db, "Débito"), 99))
    assert [p.monto for p in venta.pagos] == [D("5000"), D("13000")]


def test_primer_pago_cubre_todo_con_dos_pagos_400(db, e):
    venta = _venta(db, e.vendedor, e.p10)
    with pytest.raises(DatoInvalido, match="El primer pago ya cubre todo"):
        _pagar(db, e.vendedor, venta, (_medio(db, "Efectivo"), 10000), (_medio(db, "Débito"), 1))


def test_mas_de_dos_pagos_400(db, e):
    venta = _venta(db, e.vendedor, e.p10)
    efectivo = _medio(db, "Efectivo")
    with pytest.raises(DatoInvalido, match="Hasta 2 medios"):
        _pagar(db, e.vendedor, venta, (efectivo, 1), (efectivo, 1), (efectivo, 1))


def test_pagos_sin_nada_para_cobrar_400(db, e):
    venta = servicio.iniciar_venta(db, e.vendedor, None)
    with pytest.raises(DatoInvalido, match="No hay nada para cobrar"):
        _pagar(db, e.vendedor, venta, (_medio(db, "Efectivo"), 1))


def test_lista_vacia_borra_los_pagos(db, e):
    venta = _venta(db, e.vendedor, e.p10)
    venta = _pagar(db, e.vendedor, venta, (_medio(db, "Efectivo"), 1))
    venta = servicio.registrar_pagos(db, e.vendedor, venta.id, [])
    assert venta.pagos == []


def test_plan_de_otro_medio_400(db, e):
    credito = _medio(db, "Tarjeta de Crédito")
    plan = servicio_medios.crear_plan(db, e.admin, credito, PlanCuotasCrear(cuotas=3), None)
    venta = _venta(db, e.vendedor, e.p10)
    with pytest.raises(DatoInvalido, match="no corresponde"):
        _pagar(db, e.vendedor, venta, (_medio(db, "Débito"), 1, plan))


def test_medio_inactivo_409(db, e):
    debito = _medio(db, "Débito")
    servicio_medios.cambiar_estado_medio(db, e.admin, debito, False, None)
    venta = _venta(db, e.vendedor, e.p10)
    with pytest.raises(ReglaDeNegocio):
        _pagar(db, e.vendedor, venta, (debito, 1))


def test_plan_bajo_el_minimo_400(db, e):
    credito = _medio(db, "Tarjeta de Crédito")
    plan = servicio_medios.crear_plan(
        db, e.admin, credito, PlanCuotasCrear(cuotas=3, recargo_cliente=D("10"), monto_minimo=D("50000")), None)
    venta = _venta(db, e.vendedor, e.p10)
    with pytest.raises(DatoInvalido, match="El plan de 3 cuotas no está disponible"):
        _pagar(db, e.vendedor, venta, (credito, 1, plan))


def test_plan_sin_interes_habilitado_por_motivo(db, e):
    credito = _medio(db, "Tarjeta de Crédito")
    plan = servicio_medios.crear_plan(
        db, e.admin, credito, PlanCuotasCrear(cuotas=6, monto_minimo=D("50000")), None)
    motivo = _motivo(db, e.admin, "Promo bancaria", habilita_cuotas_sin_interes=True)
    venta = _venta(db, e.vendedor, e.p10, e.p8)
    venta = servicio.aplicar_descuento_item(db, e.vendedor, venta.id, venta.items[0].id, motivo.id, 10, None)
    venta = _pagar(db, e.vendedor, venta, (credito, 1, plan))
    assert venta.pagos[0].plan_cuotas_id == plan.id and venta.pagos[0].recargo == 0
    planes = {m["medio"].id: m["planes"] for m in servicio.medios_para_venta(db, venta, None)}
    assert [p.id for p in planes[credito.id]] == [plan.id]


def test_recargo_solo_sobre_la_parte_financiada(db, e):
    credito = _medio(db, "Tarjeta de Crédito")
    plan = servicio_medios.crear_plan(db, e.admin, credito, PlanCuotasCrear(cuotas=3, recargo_cliente=D("10")), None)
    venta = _venta(db, e.vendedor, e.p10)
    venta = _pagar(db, e.vendedor, venta, (_medio(db, "Efectivo"), 5000), (credito, 1, plan))
    credito_pago = venta.pagos[1]
    assert credito_pago.monto == D("5000") and credito_pago.recargo == D("500")
    assert credito_pago.monto_total == D("5500")
    assert venta.recargo_total == D("500") and venta.total == D("10500") and venta.cobrable == D("10000")


def test_medios_para_venta_sin_costo_y_ordenados(db, e):
    venta = _venta(db, e.vendedor, e.p10)
    nombres = [m["medio"].nombre for m in servicio.medios_para_venta(db, venta, None)]
    assert nombres == sorted(nombres, key=str.lower)
    assert "Efectivo" in nombres


def test_cambio_del_carrito_que_invalida_los_pagos_los_borra(db, e):
    venta = _venta(db, e.vendedor, e.p10, e.p8, e.p6)
    venta = _pagar(db, e.vendedor, venta, (_medio(db, "Efectivo"), 15000), (_medio(db, "Débito"), 1))
    assert len(venta.pagos) == 2
    venta = servicio.quitar_item(db, e.vendedor, venta.id, venta.items[0].id)   # queda 14000 < 15000
    assert venta.pagos == []
    assert db.scalars(select(VentaPago).where(VentaPago.venta_id == venta.id)).all() == []
    assert venta.total == D("14000") and venta.recargo_total == 0


def test_cambio_del_carrito_que_deja_el_plan_bajo_el_minimo_borra_los_pagos(db, e):
    credito = _medio(db, "Tarjeta de Crédito")
    plan = servicio_medios.crear_plan(
        db, e.admin, credito, PlanCuotasCrear(cuotas=3, recargo_cliente=D("10"), monto_minimo=D("15000")), None)
    venta = _venta(db, e.vendedor, e.p10, e.p8)
    venta = _pagar(db, e.vendedor, venta, (credito, 1, plan))
    assert venta.total == D("19800")
    venta = servicio.quitar_item(db, e.vendedor, venta.id, venta.items[0].id)
    assert venta.pagos == [] and venta.total == D("8000")



def test_pagos_borrados_recalcula_la_promocion_sin_ellos(db, e):
    """Si un cambio del carrito borra los pagos, la promoción se vuelve a
    elegir sin medios cargados (una con alcance de medio ya no queda afuera)."""
    transferencia = _medio(db, "Transferencia")
    promo = _promo(db, e.admin, "Transferencia 10", tipo=TipoPromocion.PORCENTAJE, porcentaje_descuento=10,
                   alcances=[_todos(), PromocionAlcanceDatos(tipo_alcance=TipoAlcancePromocion.MEDIO_DE_PAGO,
                                                             referencia_id=transferencia.id)])
    venta = _venta(db, e.vendedor, e.p10, e.p6)
    venta = _pagar(db, e.vendedor, venta, (_medio(db, "Efectivo"), 12000), (_medio(db, "Débito"), 1))
    assert venta.promocion_id is None and venta.total == D("16000")
    venta = servicio.quitar_item(db, e.vendedor, venta.id, venta.items[0].id)   # 6000 < 12000: se borran
    assert venta.pagos == []
    assert venta.promocion_id == promo.id and venta.total == D("5400")   # 6000 × 0.9 = 5400 (múltiplo de $10)

# --- Precio vivo ------------------------------------------------------------------------

def test_precio_vivo_y_total_esperado(db, e):
    venta = _venta(db, e.vendedor, e.p10)
    venta = _pagar(db, e.vendedor, venta, (_medio(db, "Efectivo"), 1))
    total_visto = venta.total
    _editar_producto(db, e.admin, e.p10, costo="12000")
    venta = servicio.recalcular(db, e.vendedor, venta.id)
    assert venta.items[0].precio_lista == D("12000") and venta.total == D("12000")
    assert venta.pagos[0].monto == D("12000")
    with pytest.raises(ReglaDeNegocio, match="Los precios cambiaron"):
        servicio.confirmar_venta(db, e.vendedor, venta.id, total_visto, None)


# --- Confirmar ------------------------------------------------------------------------

def test_confirmar_descuenta_stock_y_congela(db, e):
    venta = _venta(db, e.vendedor, e.p10, e.p8, e.p10)
    venta = _confirmar(db, e.vendedor, venta, (_medio(db, "Efectivo"), 1))
    assert venta.estado is EstadoVenta.CONFIRMADA and venta.confirmada_en is not None
    assert venta.turno_id == e.turno.id
    assert len(venta.codigo_cambio) == servicio.LARGO_CODIGO
    assert all(c in servicio.ALFABETO_CODIGO for c in venta.codigo_cambio)
    movimientos = db.scalars(select(MovimientoStock).where(MovimientoStock.referencia_venta_id == venta.id)
                             .order_by(MovimientoStock.producto_id)).all()
    assert [(m.tipo, m.producto_id, m.cantidad) for m in movimientos] == sorted(
        [(TipoMovimientoStock.VENTA, e.p10.id, -2), (TipoMovimientoStock.VENTA, e.p8.id, -1)], key=lambda t: t[1])
    db.refresh(e.p10)
    db.refresh(e.p8)
    assert e.p10.stock == 8 and e.p8.stock == 9
    audit = _auditorias(db, "venta.confirmada", venta.id)
    assert len(audit) == 1
    assert len(audit[0].estado_nuevo["items"]) == 3 and len(audit[0].estado_nuevo["pagos"]) == 1
    # costo congelado: cambiar el costo después no altera el ítem confirmado.
    _editar_producto(db, e.admin, e.p10, costo="20000")
    item = db.scalar(select(VentaItem).where(VentaItem.venta_id == venta.id, VentaItem.producto_id == e.p10.id))
    db.refresh(item)
    assert item.costo_unitario == D("10000") and item.precio_lista == D("10000")
    # Ya confirmada: no se vuelve a confirmar ni se opera.
    with pytest.raises(ReglaDeNegocio, match="ya no está en curso"):
        servicio.confirmar_venta(db, e.vendedor, venta.id, venta.total, None)
    # Y el vendedor puede iniciar otra.
    assert servicio.iniciar_venta(db, e.vendedor, None).id != venta.id


def test_confirmar_puede_dejar_stock_negativo(db, e):
    sin_stock = e.cat["alta"]("Guantes", costo="2000")
    venta = _venta(db, e.vendedor, sin_stock)
    _confirmar(db, e.vendedor, venta, (_medio(db, "Efectivo"), 1))
    db.refresh(sin_stock)
    assert sin_stock.stock == -1


def test_confirmar_sin_items_409(db, e):
    venta = servicio.iniciar_venta(db, e.vendedor, None)
    with pytest.raises(ReglaDeNegocio, match="no tiene productos"):
        servicio.confirmar_venta(db, e.vendedor, venta.id, D("0"), None)


def test_confirmar_sin_pagos_409(db, e):
    venta = _venta(db, e.vendedor, e.p10)
    with pytest.raises(ReglaDeNegocio, match="Cargá los medios de pago"):
        servicio.confirmar_venta(db, e.vendedor, venta.id, venta.total, None)


def test_confirmar_sin_turno_de_hoy_409(db, e):
    venta = _venta(db, e.vendedor, e.p10)
    efectivo = _medio(db, "Efectivo")
    venta = _pagar(db, e.vendedor, venta, (efectivo, venta.cobrable))
    e.turno.estado = EstadoTurno.CERRADO
    e.turno.fecha_cierre = ahora_db()
    e.turno.usuario_cierre_id = e.admin.id
    db.flush()
    with pytest.raises(ReglaDeNegocio, match="No hay un turno de caja abierto."):
        servicio.confirmar_venta(db, e.vendedor, venta.id, venta.total, None)


def test_confirmar_con_turno_de_ayer_bloquea_con_la_fecha(db, e):
    venta = _venta(db, e.vendedor, e.p10)
    efectivo = _medio(db, "Efectivo")
    venta = _pagar(db, e.vendedor, venta, (efectivo, venta.cobrable))
    e.turno.fecha_apertura = e.turno.fecha_apertura - timedelta(days=1)
    db.flush()
    with pytest.raises(ReglaDeNegocio, match=f"Hay un turno del {e.turno.fecha_apertura:%d/%m/%Y} sin cerrar"):
        servicio.confirmar_venta(db, e.vendedor, venta.id, venta.total, None)


def test_confirmar_suma_al_vendedor_al_turno(db, e):
    venta = _venta(db, e.vendedor, e.p10)
    _confirmar(db, e.vendedor, venta, (_medio(db, "Efectivo"), venta.cobrable))
    assert e.vendedor.id in [p.usuario_id for p in e.turno.participantes]


def test_codigo_de_cambio_reintenta_ante_colision(db, e, monkeypatch):
    primera = _confirmar(db, e.vendedor, _venta(db, e.vendedor, e.p10), (_medio(db, "Efectivo"), 1))
    existente = primera.codigo_cambio
    otro = "".join("A" if c != "A" else "B" for c in existente)
    secuencia = iter(existente + otro)
    monkeypatch.setattr(servicio.secrets, "choice", lambda _alfabeto: next(secuencia))
    segunda = _confirmar(db, e.vendedor, _venta(db, e.vendedor, e.p8), (_medio(db, "Efectivo"), 1))
    assert segunda.codigo_cambio == otro


def test_codigo_de_cambio_agota_intentos_409(db, e, monkeypatch):
    primera = _confirmar(db, e.vendedor, _venta(db, e.vendedor, e.p10), (_medio(db, "Efectivo"), 1))
    existente = primera.codigo_cambio
    llamadas = iter(range(10_000))
    monkeypatch.setattr(servicio.secrets, "choice", lambda _a: existente[next(llamadas) % servicio.LARGO_CODIGO])
    venta = _pagar(db, e.vendedor, _venta(db, e.vendedor, e.p8), (_medio(db, "Efectivo"), 1))
    with pytest.raises(ReglaDeNegocio, match="No se pudo generar el código de cambio"):
        servicio.confirmar_venta(db, e.vendedor, venta.id, venta.total, None)


# --- Descartar ------------------------------------------------------------------------

def test_descartar_borra_items_y_pagos_y_audita(db, e):
    venta = _venta(db, e.vendedor, e.p10, e.p8)
    venta = _pagar(db, e.vendedor, venta, (_medio(db, "Efectivo"), 1))
    venta_id, numero = venta.id, venta.numero
    servicio.descartar_venta(db, e.vendedor, venta_id, None)
    assert db.get(Venta, venta_id) is None
    assert db.scalars(select(VentaItem).where(VentaItem.venta_id == venta_id)).all() == []
    assert db.scalars(select(VentaPago).where(VentaPago.venta_id == venta_id)).all() == []
    audit = _auditorias(db, "venta.descartar", venta_id)
    assert len(audit) == 1
    assert audit[0].estado_anterior["numero"] == numero and audit[0].estado_anterior["items"] == 2
    assert servicio.venta_en_curso(db, e.vendedor) is None


def test_descartar_venta_ajena_403(db, e):
    venta = _venta(db, e.vendedor, e.p10)
    with pytest.raises(SinPermiso):
        servicio.descartar_venta(db, e.supervisor, venta.id, None)


# --- Listado ------------------------------------------------------------------------

def test_listar_ventas_filtros(db, e):
    cliente = servicio_clientes.crear_cliente(db, e.admin, ClienteCrear(nombre="Cliente Listado"), None)
    efectivo = _medio(db, "Efectivo")
    v1 = _venta(db, e.vendedor, e.p10)
    servicio.asociar_cliente(db, e.vendedor, v1.id, cliente.id)
    v1 = _confirmar(db, e.vendedor, v1, (efectivo, 1))
    v2 = _confirmar(db, e.supervisor, _venta(db, e.supervisor, e.p6), (_medio(db, "Débito"), 1))
    en_curso = _venta(db, e.vendedor, e.p8)
    hoy = ahora_db().date()

    def ids(**filtros):
        ventas, total = servicio.listar_ventas(db, **filtros)
        assert total == len(ventas)
        return {v.id for v in ventas}

    todas = ids()
    assert {v1.id, v2.id, en_curso.id} <= todas
    assert ids(numero=v1.numero) == {v1.id}
    assert ids(numero=v1.numero[-3:]) >= {v1.id}
    assert ids(codigo_cambio=v1.codigo_cambio.lower()) == {v1.id}
    assert ids(estado=EstadoVenta.EN_CURSO) >= {en_curso.id} and v1.id not in ids(estado=EstadoVenta.EN_CURSO)
    assert ids(cliente_id=cliente.id) == {v1.id}
    assert ids(usuario_id=e.supervisor.id) == {v2.id}
    assert v1.id in ids(total_desde=D("10000"), total_hasta=D("10000"))
    assert v2.id not in ids(total_desde=D("10000"), total_hasta=D("10000"))
    assert {v1.id, v2.id} <= ids(fecha_desde=hoy, fecha_hasta=hoy)
    assert v1.id not in ids(fecha_hasta=hoy - timedelta(days=1))
    assert v1.id not in ids(fecha_desde=hoy + timedelta(days=1))
    ventas, _ = servicio.listar_ventas(db, cliente_id=cliente.id)
    assert [p.medio_de_pago.nombre for p in ventas[0].pagos] == ["Efectivo"]


def test_listar_ventas_pagina(db, e):
    for autor in (e.vendedor, e.supervisor):
        _confirmar(db, autor, _venta(db, autor, e.p6), (_medio(db, "Efectivo"), 1))
    ventas, total = servicio.listar_ventas(db, pagina=1, tamano=1)
    assert len(ventas) == 1 and total >= 2


def test_vendedores_activos(db, e, crear_usuario):
    inactivo = crear_usuario("vendedor", nombre="Inactivo", activo=False)
    ids = {u.id for u in servicio.vendedores(db)}
    assert {e.vendedor.id, e.supervisor.id} <= ids and inactivo.id not in ids


# --- Respuesta ------------------------------------------------------------------------

def test_respuesta_sin_costo_unitario(db, e):
    venta = _venta(db, e.vendedor, e.p10)
    venta = _pagar(db, e.vendedor, venta, (_medio(db, "Efectivo"), 1))
    datos = VentaResponse.desde(venta, servicio_categorias.caminos(db)).model_dump()
    assert "costo_unitario" not in datos
    assert all("costo_unitario" not in i for i in datos["items"])
    assert "costo" not in str(datos)
    assert datos["items"][0]["categoria"]
    assert datos["cobrable"] == D("10000")
