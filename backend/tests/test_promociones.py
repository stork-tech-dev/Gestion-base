"""Tests de services/promociones.py (sesión 06)."""
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.core.errores import DatoInvalido, NoEncontrado, ReglaDeNegocio
from app.models import Auditoria, TipoAlcancePromocion, TipoPromocion
from app.schemas.clientes import ClienteCrear
from app.schemas.medios_pago import MedioDePagoCrear
from app.schemas.promociones import PromocionAlcanceDatos, PromocionCrear, PromocionEditar
from app.services import clientes as servicio_clientes
from app.services import medios_pago as servicio_medios
from app.services import promociones as servicio
from tests.fabricas import catalogo


def _item(id_, precio_unitario, orden):
    return SimpleNamespace(id=id_, precio_unitario=Decimal(precio_unitario), orden=orden)


def _promo_tipo(tipo):
    return SimpleNamespace(tipo=tipo)


def _todos():
    return PromocionAlcanceDatos(tipo_alcance=TipoAlcancePromocion.TODOS_PRODUCTOS, referencia_id=0)


def _crear(db, admin, **extra):
    datos = {"nombre": "Promo", "tipo": TipoPromocion.DOS_X_UNO, "alcances": [_todos()]}
    datos.update(extra)
    return servicio.crear_promocion(db, admin, PromocionCrear(**datos), None)


# --- unidades_gratis / elegir_unidades_gratis --------------------------------

def test_unidades_gratis_2x1():
    assert servicio.unidades_gratis(5, _promo_tipo(TipoPromocion.DOS_X_UNO)) == 2


def test_unidades_gratis_3x2():
    assert servicio.unidades_gratis(5, _promo_tipo(TipoPromocion.TRES_X_DOS)) == 1


def test_unidades_gratis_insuficientes_para_un_grupo():
    assert servicio.unidades_gratis(1, _promo_tipo(TipoPromocion.DOS_X_UNO)) == 0


def test_elegir_unidades_gratis_2x1():
    items = [_item(1, 100, 1), _item(2, 90, 2), _item(3, 80, 3), _item(4, 70, 4), _item(5, 60, 5)]
    en_grupo, gratis = servicio.elegir_unidades_gratis(items, _promo_tipo(TipoPromocion.DOS_X_UNO))
    assert en_grupo == {1, 2, 3, 4}
    assert gratis == {2, 4}


def test_elegir_unidades_gratis_3x2():
    items = [_item(1, 100, 1), _item(2, 90, 2), _item(3, 80, 3), _item(4, 70, 4)]
    en_grupo, gratis = servicio.elegir_unidades_gratis(items, _promo_tipo(TipoPromocion.TRES_X_DOS))
    assert en_grupo == {1, 2, 3}
    assert gratis == {3}


def test_elegir_unidades_gratis_empate_de_precio_gana_mayor_orden():
    items = [_item(1, 100, 1), _item(2, 100, 2)]
    en_grupo, gratis = servicio.elegir_unidades_gratis(items, _promo_tipo(TipoPromocion.DOS_X_UNO))
    assert en_grupo == {1, 2}
    assert gratis == {2}


# --- productos_alcanzados ------------------------------------------------------

def test_productos_alcanzados_por_categoria_incluye_subcategorias(db, crear_usuario):
    admin = crear_usuario("admin")
    cat = catalogo(db, admin)
    producto = cat["alta"]("Remera de subcategoria")
    promo = _crear(db, admin, nombre="Por categoria",
                   alcances=[PromocionAlcanceDatos(tipo_alcance=TipoAlcancePromocion.CATEGORIA,
                                                   referencia_id=cat["categoria"].id)])
    assert servicio.productos_alcanzados(db, promo) == {producto.id}


def test_productos_alcanzados_por_producto(db, crear_usuario):
    admin = crear_usuario("admin")
    cat = catalogo(db, admin)
    producto = cat["alta"]("Remera suelta")
    cat["alta"]("Otro producto")
    promo = _crear(db, admin, nombre="Por producto",
                   alcances=[PromocionAlcanceDatos(tipo_alcance=TipoAlcancePromocion.PRODUCTO,
                                                   referencia_id=producto.id)])
    assert servicio.productos_alcanzados(db, promo) == {producto.id}


def test_productos_alcanzados_todos_productos_es_none(db, crear_usuario):
    admin = crear_usuario("admin")
    promo = _crear(db, admin, nombre="Todos productos")
    assert servicio.productos_alcanzados(db, promo) is None


def test_productos_alcanzados_todos_categorias_es_none(db, crear_usuario):
    admin = crear_usuario("admin")
    promo = _crear(db, admin, nombre="Todas categorias",
                   alcances=[PromocionAlcanceDatos(tipo_alcance=TipoAlcancePromocion.TODOS_CATEGORIAS,
                                                   referencia_id=0)])
    assert servicio.productos_alcanzados(db, promo) is None


def test_productos_alcanzados_solo_medio_de_pago_es_none(db, crear_usuario):
    admin = crear_usuario("admin")
    medio = servicio_medios.crear_medio(db, admin, MedioDePagoCrear(nombre="Medio alcance test"), None)
    # Alcance de productos "todos" + alcance de medio: sigue siendo None por productos.
    promo = _crear(db, admin, nombre="Con medio",
                   alcances=[_todos(),
                            PromocionAlcanceDatos(tipo_alcance=TipoAlcancePromocion.MEDIO_DE_PAGO,
                                                  referencia_id=medio.id)])
    assert servicio.productos_alcanzados(db, promo) is None


# --- simular (porcentaje) ------------------------------------------------------

def test_simular_porcentaje_encadena_con_descuento_de_producto(db, crear_usuario):
    admin = crear_usuario("admin")
    cat = catalogo(db, admin)
    producto = cat["alta"]("Campera con descuento", descuento_producto="10")
    promo = _crear(db, admin, nombre="20 porciento", tipo=TipoPromocion.PORCENTAJE, porcentaje_descuento=20)
    item = SimpleNamespace(id=1, producto_id=producto.id, precio_lista=Decimal("10000"),
                          precio_unitario=Decimal("10000"), orden=1, producto=producto)
    ahorro, finales, en_promo = servicio.simular(db, promo, [item])
    # 10000 × 0.9 × 0.8 = 7200 (múltiplo de $10 hacia abajo, REDONDEO_DESCUENTO)
    assert finales[1] == Decimal("7200")
    assert en_promo == {1}
    assert ahorro == Decimal("2800")


def test_simular_ignora_items_fuera_de_alcance(db, crear_usuario):
    admin = crear_usuario("admin")
    cat = catalogo(db, admin)
    dentro = cat["alta"]("Producto dentro")
    fuera = cat["alta"]("Producto fuera")
    promo = _crear(db, admin, nombre="Solo dentro", tipo=TipoPromocion.PORCENTAJE, porcentaje_descuento=10,
                   alcances=[PromocionAlcanceDatos(tipo_alcance=TipoAlcancePromocion.PRODUCTO,
                                                   referencia_id=dentro.id)])
    item_dentro = SimpleNamespace(id=1, producto_id=dentro.id, precio_lista=Decimal("1000"),
                                  precio_unitario=Decimal("1000"), orden=1, producto=dentro)
    item_fuera = SimpleNamespace(id=2, producto_id=fuera.id, precio_lista=Decimal("1000"),
                                 precio_unitario=Decimal("1000"), orden=2, producto=fuera)
    ahorro, finales, en_promo = servicio.simular(db, promo, [item_dentro, item_fuera])
    assert en_promo == {1}
    assert 2 not in finales
    assert ahorro > 0


def test_simular_grupo_ignora_items_fuera_de_alcance(db, crear_usuario):
    """2x1 con un producto dentro del alcance y dos caros fuera: no se forma
    ningún grupo (un producto caro fuera de alcance nunca sale gratis)."""
    admin = crear_usuario("admin")
    cat = catalogo(db, admin)
    dentro = cat["alta"]("Producto dentro 2x1")
    fuera = cat["alta"]("Producto caro fuera 2x1")
    promo = _crear(db, admin, nombre="2x1 solo dentro", tipo=TipoPromocion.DOS_X_UNO,
                   alcances=[PromocionAlcanceDatos(tipo_alcance=TipoAlcancePromocion.PRODUCTO,
                                                   referencia_id=dentro.id)])
    items = [
        SimpleNamespace(id=1, producto_id=dentro.id, precio_lista=Decimal("1000"),
                        precio_unitario=Decimal("1000"), orden=1, producto=dentro),
        SimpleNamespace(id=2, producto_id=fuera.id, precio_lista=Decimal("50000"),
                        precio_unitario=Decimal("50000"), orden=2, producto=fuera),
        SimpleNamespace(id=3, producto_id=fuera.id, precio_lista=Decimal("50000"),
                        precio_unitario=Decimal("50000"), orden=3, producto=fuera),
    ]
    ahorro, finales, en_promo = servicio.simular(db, promo, items)
    assert en_promo == set()
    assert finales == {}
    assert ahorro == Decimal("0")


# --- aplica_con_medios ---------------------------------------------------------

def test_aplica_con_medios_sin_pagos_cargados_true(db, crear_usuario):
    admin = crear_usuario("admin")
    medio = servicio_medios.crear_medio(db, admin, MedioDePagoCrear(nombre="Medio sin pagos test"), None)
    promo = _crear(db, admin, nombre="Con alcance de medio",
                   alcances=[_todos(),
                            PromocionAlcanceDatos(tipo_alcance=TipoAlcancePromocion.MEDIO_DE_PAGO,
                                                  referencia_id=medio.id)])
    assert servicio.aplica_con_medios(promo, set()) is True


def test_aplica_con_medios_todos_alcanzados_true(db, crear_usuario):
    admin = crear_usuario("admin")
    medio = servicio_medios.crear_medio(db, admin, MedioDePagoCrear(nombre="Medio alcanzado test"), None)
    promo = _crear(db, admin, nombre="Con medio alcanzado",
                   alcances=[_todos(),
                            PromocionAlcanceDatos(tipo_alcance=TipoAlcancePromocion.MEDIO_DE_PAGO,
                                                  referencia_id=medio.id)])
    assert servicio.aplica_con_medios(promo, {medio.id}) is True


def test_aplica_con_medios_uno_fuera_false(db, crear_usuario):
    admin = crear_usuario("admin")
    medio_a = servicio_medios.crear_medio(db, admin, MedioDePagoCrear(nombre="Medio a test"), None)
    medio_b = servicio_medios.crear_medio(db, admin, MedioDePagoCrear(nombre="Medio b test"), None)
    promo = _crear(db, admin, nombre="Solo medio a",
                   alcances=[_todos(),
                            PromocionAlcanceDatos(tipo_alcance=TipoAlcancePromocion.MEDIO_DE_PAGO,
                                                  referencia_id=medio_a.id)])
    assert servicio.aplica_con_medios(promo, {medio_a.id}) is True
    assert servicio.aplica_con_medios(promo, {medio_a.id, medio_b.id}) is False


# --- mejor_promocion ------------------------------------------------------------

def test_mejor_promocion_elige_mayor_ahorro(db, crear_usuario):
    admin = crear_usuario("admin")
    cat = catalogo(db, admin)
    producto = cat["alta"]("Producto mejor promo")
    promo_10 = _crear(db, admin, nombre="Promo 10", tipo=TipoPromocion.PORCENTAJE, porcentaje_descuento=10)
    promo_30 = _crear(db, admin, nombre="Promo 30", tipo=TipoPromocion.PORCENTAJE, porcentaje_descuento=30)
    item = SimpleNamespace(id=1, producto_id=producto.id, precio_lista=Decimal("10000"),
                          precio_unitario=Decimal("10000"), orden=1, producto=producto)
    elegida = servicio.mejor_promocion(db, [promo_10, promo_30], [item])
    assert elegida.id == promo_30.id


def test_mejor_promocion_empate_elige_menor_id(db, crear_usuario):
    admin = crear_usuario("admin")
    cat = catalogo(db, admin)
    producto = cat["alta"]("Producto empate promo")
    promo_a = _crear(db, admin, nombre="Empate A", tipo=TipoPromocion.PORCENTAJE, porcentaje_descuento=15)
    promo_b = _crear(db, admin, nombre="Empate B", tipo=TipoPromocion.PORCENTAJE, porcentaje_descuento=15)
    item = SimpleNamespace(id=1, producto_id=producto.id, precio_lista=Decimal("10000"),
                          precio_unitario=Decimal("10000"), orden=1, producto=producto)
    elegida = servicio.mejor_promocion(db, [promo_b, promo_a], [item])
    assert elegida.id == min(promo_a.id, promo_b.id)


def test_mejor_promocion_ninguna_ahorra_none(db, crear_usuario):
    admin = crear_usuario("admin")
    cat = catalogo(db, admin)
    producto = cat["alta"]("Producto A sin promo")
    otro = cat["alta"]("Producto B sin promo")
    promo = _crear(db, admin, nombre="Promo de otro producto", tipo=TipoPromocion.PORCENTAJE, porcentaje_descuento=10,
                   alcances=[PromocionAlcanceDatos(tipo_alcance=TipoAlcancePromocion.PRODUCTO,
                                                   referencia_id=otro.id)])
    item = SimpleNamespace(id=1, producto_id=producto.id, precio_lista=Decimal("10000"),
                          precio_unitario=Decimal("10000"), orden=1, producto=producto)
    assert servicio.mejor_promocion(db, [promo], [item]) is None


# --- promociones_aplicables: exclusividad y vigencia ---------------------------

def test_promociones_aplicables_exclusiva_solo_para_su_cliente(db, crear_usuario):
    admin = crear_usuario("admin")
    cliente_a = servicio_clientes.crear_cliente(db, admin, ClienteCrear(nombre="Cliente promo A"), None)
    cliente_b = servicio_clientes.crear_cliente(db, admin, ClienteCrear(nombre="Cliente promo B"), None)
    promo = _crear(db, admin, nombre="Promo exclusiva")
    servicio.asignar_a_cliente(db, admin, cliente_a, promo.id, None)

    hoy = date.today()
    ids_a = {p.id for p in servicio.promociones_aplicables(db, cliente_a.id, hoy, set())}
    ids_b = {p.id for p in servicio.promociones_aplicables(db, cliente_b.id, hoy, set())}
    ids_sin_cliente = {p.id for p in servicio.promociones_aplicables(db, None, hoy, set())}
    assert promo.id in ids_a
    assert promo.id not in ids_b
    assert promo.id not in ids_sin_cliente


def test_promociones_aplicables_no_exclusiva_para_todos(db, crear_usuario):
    admin = crear_usuario("admin")
    promo = _crear(db, admin, nombre="Promo para todos")
    hoy = date.today()
    assert promo.id in {p.id for p in servicio.promociones_aplicables(db, None, hoy, set())}


def test_promociones_aplicables_fuera_de_fechas_no_aparece(db, crear_usuario):
    admin = crear_usuario("admin")
    promo = _crear(db, admin, nombre="Promo vencida", fecha_inicio=date(2020, 1, 1), fecha_fin=date(2020, 1, 31))
    hoy = date.today()
    assert promo.id not in {p.id for p in servicio.promociones_aplicables(db, None, hoy, set())}


def test_promociones_aplicables_inactiva_no_aparece(db, crear_usuario):
    admin = crear_usuario("admin")
    promo = _crear(db, admin, nombre="Promo a desactivar")
    servicio.cambiar_estado_promocion(db, admin, promo, False, None)
    hoy = date.today()
    assert promo.id not in {p.id for p in servicio.promociones_aplicables(db, None, hoy, set())}


# --- CRUD: validaciones ---------------------------------------------------------

def test_crear_promocion_porcentaje_obligatorio_en_tipo_porcentaje(db, crear_usuario):
    admin = crear_usuario("admin")
    with pytest.raises(DatoInvalido):
        _crear(db, admin, nombre="Sin porcentaje", tipo=TipoPromocion.PORCENTAJE)


def test_crear_promocion_porcentaje_no_permitido_fuera_de_tipo_porcentaje(db, crear_usuario):
    admin = crear_usuario("admin")
    with pytest.raises(DatoInvalido):
        _crear(db, admin, nombre="2x1 con porcentaje", tipo=TipoPromocion.DOS_X_UNO, porcentaje_descuento=10)


def test_crear_promocion_sin_alcance_de_productos(db, crear_usuario):
    admin = crear_usuario("admin")
    with pytest.raises(DatoInvalido, match="Elegí a qué productos alcanza"):
        _crear(db, admin, nombre="Sin alcance", alcances=[])


def test_crear_promocion_solo_medio_de_pago_no_alcanza(db, crear_usuario):
    admin = crear_usuario("admin")
    medio = servicio_medios.crear_medio(db, admin, MedioDePagoCrear(nombre="Medio unico alcance"), None)
    with pytest.raises(DatoInvalido, match="Elegí a qué productos alcanza"):
        _crear(db, admin, nombre="Solo medio",
              alcances=[PromocionAlcanceDatos(tipo_alcance=TipoAlcancePromocion.MEDIO_DE_PAGO,
                                              referencia_id=medio.id)])


def test_crear_promocion_alcance_repetido(db, crear_usuario):
    admin = crear_usuario("admin")
    with pytest.raises(DatoInvalido):
        _crear(db, admin, nombre="Alcance repetido", alcances=[_todos(), _todos()])


def test_crear_promocion_referencia_de_producto_inexistente(db, crear_usuario):
    admin = crear_usuario("admin")
    with pytest.raises(NoEncontrado):
        _crear(db, admin, nombre="Producto inexistente",
              alcances=[PromocionAlcanceDatos(tipo_alcance=TipoAlcancePromocion.PRODUCTO, referencia_id=999999)])


def test_crear_promocion_referencia_de_categoria_inexistente(db, crear_usuario):
    admin = crear_usuario("admin")
    with pytest.raises(NoEncontrado):
        _crear(db, admin, nombre="Categoria inexistente",
              alcances=[PromocionAlcanceDatos(tipo_alcance=TipoAlcancePromocion.CATEGORIA, referencia_id=999999)])


def test_crear_promocion_referencia_de_medio_inexistente(db, crear_usuario):
    admin = crear_usuario("admin")
    with pytest.raises(NoEncontrado):
        _crear(db, admin, nombre="Medio inexistente",
              alcances=[_todos(),
                       PromocionAlcanceDatos(tipo_alcance=TipoAlcancePromocion.MEDIO_DE_PAGO, referencia_id=999999)])


def test_crear_promocion_fechas_incoherentes(db, crear_usuario):
    admin = crear_usuario("admin")
    with pytest.raises(DatoInvalido):
        _crear(db, admin, nombre="Fechas incoherentes", fecha_inicio=date(2026, 2, 1), fecha_fin=date(2026, 1, 1))


def test_crear_promocion_nombre_duplicado_sin_tildes(db, crear_usuario):
    admin = crear_usuario("admin")
    _crear(db, admin, nombre="Promoción duplicada")
    with pytest.raises(ReglaDeNegocio):
        _crear(db, admin, nombre="PROMOCION DUPLICADA")


# --- CRUD: alta, edición, estado y auditoría ------------------------------------

def test_crear_promocion_audita_con_alcances(db, crear_usuario):
    admin = crear_usuario("admin")
    promo = _crear(db, admin, nombre="Promo auditada")
    registro = db.scalar(
        select(Auditoria).where(Auditoria.accion == "promocion.crear", Auditoria.entidad_id == promo.id))
    assert registro is not None
    assert registro.estado_nuevo["alcances"] == [{"tipo_alcance": "todos_productos", "referencia_id": 0}]


def test_editar_promocion_sincroniza_alcances_y_audita(db, crear_usuario):
    admin = crear_usuario("admin")
    cat = catalogo(db, admin)
    producto = cat["alta"]("Producto editar promo")
    promo = _crear(db, admin, nombre="Promo editable")

    editada = servicio.editar_promocion(
        db, admin, promo,
        PromocionEditar(nombre="Promo editable", tipo=TipoPromocion.DOS_X_UNO,
                        alcances=[PromocionAlcanceDatos(tipo_alcance=TipoAlcancePromocion.PRODUCTO,
                                                        referencia_id=producto.id)]),
        None,
    )
    assert {a.tipo_alcance for a in editada.alcances} == {TipoAlcancePromocion.PRODUCTO}
    assert servicio.productos_alcanzados(db, editada) == {producto.id}
    registro = db.scalar(
        select(Auditoria).where(Auditoria.accion == "promocion.editar", Auditoria.entidad_id == promo.id))
    assert registro.estado_anterior["alcances"] == [{"tipo_alcance": "todos_productos", "referencia_id": 0}]
    assert registro.estado_nuevo["alcances"] == [{"tipo_alcance": "producto", "referencia_id": producto.id}]


def test_editar_promocion_con_el_mismo_alcance_no_rompe_el_unique(db, crear_usuario):
    admin = crear_usuario("admin")
    promo = _crear(db, admin, nombre="Promo sin cambio de alcance")
    editada = servicio.editar_promocion(
        db, admin, promo, PromocionEditar(nombre="Promo sin cambio de alcance", tipo=TipoPromocion.DOS_X_UNO,
                                          alcances=[_todos()]),
        None,
    )
    assert len(editada.alcances) == 1


def test_cambiar_estado_promocion_audita(db, crear_usuario):
    admin = crear_usuario("admin")
    promo = _crear(db, admin, nombre="Promo estado")
    servicio.cambiar_estado_promocion(db, admin, promo, False, None)
    assert promo.activo is False
    registro = db.scalar(
        select(Auditoria).where(Auditoria.accion == "promocion.desactivar", Auditoria.entidad_id == promo.id))
    assert registro is not None


def test_obtener_promocion_inexistente(db):
    with pytest.raises(NoEncontrado):
        servicio.obtener_promocion(db, 999999)


def test_listar_promociones_filtra_por_activo(db, crear_usuario):
    admin = crear_usuario("admin")
    activa = _crear(db, admin, nombre="Promo listado activa")
    inactiva = _crear(db, admin, nombre="Promo listado inactiva")
    servicio.cambiar_estado_promocion(db, admin, inactiva, False, None)
    ids = {p.id for p in servicio.listar_promociones(db, activo=True)}
    assert activa.id in ids
    assert inactiva.id not in ids


def test_listar_promociones_rige_hoy(db, crear_usuario):
    admin = crear_usuario("admin")
    vigente = _crear(db, admin, nombre="Promo rige hoy")
    vencida = _crear(db, admin, nombre="Promo no rige hoy", fecha_inicio=date(2020, 1, 1), fecha_fin=date(2020, 1, 31))
    vigentes = {p.id for p in servicio.listar_promociones(db, rige_hoy=True)}
    no_vigentes = {p.id for p in servicio.listar_promociones(db, rige_hoy=False)}
    assert vigente.id in vigentes and vencida.id not in vigentes
    assert vencida.id in no_vigentes and vigente.id not in no_vigentes


# --- Catálogos -------------------------------------------------------------------

def test_catalogos(db, crear_usuario):
    admin = crear_usuario("admin")
    cat = catalogo(db, admin)
    producto = cat["alta"]("Producto catalogo promo")
    medio = servicio_medios.crear_medio(db, admin, MedioDePagoCrear(nombre="Medio catalogo promo"), None)
    resultado = servicio.catalogos(db)
    assert any(p["id"] == producto.id and p["codigo"] == producto.codigo_con_verificador
              for p in resultado["productos"])
    assert any(c["id"] == cat["categoria"].id for c in resultado["categorias"])
    assert any(m["id"] == medio.id for m in resultado["medios"])


# --- Promociones exclusivas de un cliente ----------------------------------------

def test_asignar_a_cliente_duplicado_409(db, crear_usuario):
    admin = crear_usuario("admin")
    cliente = servicio_clientes.crear_cliente(db, admin, ClienteCrear(nombre="Cliente asignar promo"), None)
    promo = _crear(db, admin, nombre="Promo asignar")
    servicio.asignar_a_cliente(db, admin, cliente, promo.id, None)
    with pytest.raises(ReglaDeNegocio, match="ya tiene esa promoción"):
        servicio.asignar_a_cliente(db, admin, cliente, promo.id, None)
    registro = db.scalar(select(Auditoria).where(
        Auditoria.accion == "cliente.promocion_asignar", Auditoria.entidad_id == cliente.id))
    assert registro is not None


def test_quitar_de_cliente(db, crear_usuario):
    admin = crear_usuario("admin")
    cliente = servicio_clientes.crear_cliente(db, admin, ClienteCrear(nombre="Cliente quitar promo"), None)
    promo = _crear(db, admin, nombre="Promo quitar")
    servicio.asignar_a_cliente(db, admin, cliente, promo.id, None)
    servicio.quitar_de_cliente(db, admin, cliente, promo.id, None)
    assert servicio.promociones_de_cliente(db, cliente.id) == []
    registro = db.scalar(select(Auditoria).where(
        Auditoria.accion == "cliente.promocion_quitar", Auditoria.entidad_id == cliente.id))
    assert registro is not None


def test_quitar_de_cliente_no_asignada_404(db, crear_usuario):
    admin = crear_usuario("admin")
    cliente = servicio_clientes.crear_cliente(db, admin, ClienteCrear(nombre="Cliente sin promo"), None)
    promo = _crear(db, admin, nombre="Promo no asignada")
    with pytest.raises(NoEncontrado):
        servicio.quitar_de_cliente(db, admin, cliente, promo.id, None)


def test_promociones_de_cliente(db, crear_usuario):
    admin = crear_usuario("admin")
    cliente = servicio_clientes.crear_cliente(db, admin, ClienteCrear(nombre="Cliente con promos"), None)
    promo = _crear(db, admin, nombre="Promo de cliente")
    servicio.asignar_a_cliente(db, admin, cliente, promo.id, None)
    assert [p.id for p in servicio.promociones_de_cliente(db, cliente.id)] == [promo.id]


def test_ficha_de_cliente_usa_promociones_de_cliente(db, crear_usuario):
    admin = crear_usuario("admin")
    cliente = servicio_clientes.crear_cliente(db, admin, ClienteCrear(nombre="Cliente ficha con promo"), None)
    promo = _crear(db, admin, nombre="Promo en ficha")
    servicio.asignar_a_cliente(db, admin, cliente, promo.id, None)
    ficha = servicio_clientes.ficha(db, cliente.id)
    assert [p.id for p in ficha["promociones"]] == [promo.id]
