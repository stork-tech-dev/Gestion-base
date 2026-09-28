from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.errores import DatoInvalido, NoEncontrado, ReglaDeNegocio
from app.models import Auditoria, MotivoBaja, MovimientoStock, TipoMovimientoStock
from app.schemas.categorias import CategoriaCrear
from app.schemas.productos import ProductoCrear, ProductoEditar
from app.schemas.proveedores import ProveedorCrear
from app.services import categorias as servicio_categorias
from app.services import productos as servicio_productos
from app.services import proveedores as servicio_proveedores
from app.services import stock as servicio


@pytest.fixture
def base(db, crear_usuario):
    admin = crear_usuario("admin")
    ropa = servicio_categorias.crear_categoria(db, admin, CategoriaCrear(nombre="Ropa stock"), None)
    hoja = servicio_categorias.crear_categoria(db, admin, CategoriaCrear(nombre="Remeras stock", parent_id=ropa.id), None)
    prov = servicio_proveedores.crear_proveedor(db, admin, ProveedorCrear(nombre="Prov stock", moneda="ars"), None)

    def alta(descripcion, **extra):
        datos = {"categoria_id": hoja.id, "proveedor_id": prov.id, "costo": "1000", "margen": "0",
                 "descripcion": descripcion}
        datos.update(extra)
        return servicio_productos.crear_producto(db, admin, ProductoCrear(**datos), None)

    return {"admin": admin, "ropa": ropa, "hoja": hoja, "prov": prov, "alta": alta,
            "motivo": db.scalar(select(MotivoBaja).limit(1))}


def test_ingreso_actualiza_stock_y_audita(db, base):
    p = base["alta"]("Remera ingreso")
    m = servicio.registrar_ingreso(db, base["admin"], p.id, 10, "Compra", None)
    assert (m.cantidad, m.stock_resultante, m.tipo) == (10, 10, TipoMovimientoStock.INGRESO_PROVEEDOR)
    assert p.stock == 10
    registro = db.scalar(select(Auditoria).where(Auditoria.accion == "stock.ingreso_proveedor", Auditoria.entidad_id == p.id))
    assert registro.estado_anterior == {"stock": 0} and registro.estado_nuevo["stock"] == 10


def test_salida_sin_stock_suficiente(db, base):
    p = base["alta"]("Remera faltante")
    servicio.registrar_ingreso(db, base["admin"], p.id, 2, None, None)
    with pytest.raises(ReglaDeNegocio) as error:
        servicio.aplicar_movimiento(db, base["admin"], tipo=TipoMovimientoStock.BAJA, producto_id=p.id, cantidad=-3,
                                    motivo_baja_id=base["motivo"].id)
    assert error.value.mensaje == "No hay stock suficiente de 'Remera faltante': hay 2 y se piden 3"
    assert p.stock == 2
    assert db.scalar(select(MovimientoStock).where(MovimientoStock.tipo == TipoMovimientoStock.BAJA)) is None


def test_venta_con_faltante_deja_negativo(db, base):
    p = base["alta"]("Remera venta")
    m = servicio.aplicar_movimiento(db, base["admin"], tipo=TipoMovimientoStock.VENTA, producto_id=p.id, cantidad=-2,
                                    referencia_venta_id=1, permitir_faltante=True)
    assert m.stock_resultante == -2 and p.stock == -2


def test_permitir_faltante_solo_ventas(db, base):
    p = base["alta"]("Remera sin faltante")
    with pytest.raises(DatoInvalido):
        servicio.aplicar_movimiento(db, base["admin"], tipo=TipoMovimientoStock.BAJA, producto_id=p.id, cantidad=-1,
                                    motivo_baja_id=base["motivo"].id, permitir_faltante=True)


@pytest.mark.parametrize("tipo, cantidad", [
    (TipoMovimientoStock.INGRESO_PROVEEDOR, -1), (TipoMovimientoStock.BAJA, 1), (TipoMovimientoStock.VENTA, 1),
    (TipoMovimientoStock.INGRESO_PROVEEDOR, 0),
])
def test_signo_incoherente(db, base, tipo, cantidad):
    p = base["alta"]("Remera signo")
    with pytest.raises(DatoInvalido):
        servicio.aplicar_movimiento(db, base["admin"], tipo=tipo, producto_id=p.id, cantidad=cantidad,
                                    motivo_baja_id=base["motivo"].id, referencia_venta_id=1)


def test_stock_infinito_no_se_toca(db, base):
    p = base["alta"]("Remera infinita", stock_infinito=True)
    m = servicio.aplicar_movimiento(db, base["admin"], tipo=TipoMovimientoStock.VENTA, producto_id=p.id, cantidad=-5,
                                    referencia_venta_id=1)
    assert p.stock == 0 and m.stock_resultante == 0
    m = servicio.aplicar_movimiento(db, base["admin"], tipo=TipoMovimientoStock.BAJA, producto_id=p.id, cantidad=-5,
                                    motivo_baja_id=base["motivo"].id)
    assert m.stock_resultante == 0


def test_tope_de_stock(db, base):
    p = base["alta"]("Remera tope")
    servicio.registrar_ingreso(db, base["admin"], p.id, 1_000_000, None, None)
    p.stock = servicio.STOCK_MAXIMO - 10          # simula un stock enorme (solo para el test)
    db.flush()
    with pytest.raises(DatoInvalido):
        servicio.registrar_ingreso(db, base["admin"], p.id, 11, None, None)


def test_producto_inexistente(db, base):
    with pytest.raises(NoEncontrado):
        servicio.registrar_ingreso(db, base["admin"], 999999, 1, None, None)


def test_bloquear_producto_inexistente(db):
    with pytest.raises(NoEncontrado):
        servicio.bloquear_producto(db, 999999)


def test_minimo(db, base):
    p = base["alta"]("Remera mínimo")
    servicio.definir_minimo(db, base["admin"], p.id, 3, None)
    assert p.stock_minimo == 3 and p.bajo_minimo
    assert db.scalar(select(Auditoria).where(Auditoria.accion == "stock.minimo", Auditoria.entidad_id == p.id))
    infinito = base["alta"]("Remera infinita mínimo", stock_infinito=True)
    with pytest.raises(DatoInvalido):
        servicio.definir_minimo(db, base["admin"], infinito.id, 1, None)


def test_listar_stock(db, base):
    a = base["alta"]("Remera lista A")
    b = base["alta"]("Remera lista B")
    infinito = base["alta"]("Remera lista infinita", stock_infinito=True)
    inactivo = base["alta"]("Remera lista inactiva")
    servicio_productos.cambiar_estado_producto(db, base["admin"], inactivo, False, None)
    servicio.registrar_ingreso(db, base["admin"], a.id, 5, None, None)
    servicio.definir_minimo(db, base["admin"], b.id, 2, None)
    ids = lambda **f: {p.id for p in servicio.listar_stock(db, proveedor_id=base["prov"].id, **f)[0]}
    assert ids() == {a.id, b.id}                                  # sin infinitos ni inactivos
    assert ids(solo_bajo_minimo=True) == {b.id}
    assert ids(incluir_sin_stock=False) == {a.id}
    assert ids(busqueda=infinito.codigo_con_verificador) == {infinito.id}   # por código sí aparece
    assert ids(categoria_id=base["ropa"].id) == {a.id, b.id}      # filtro por rama
    assert ids(busqueda="lista a") == {a.id}


def test_listar_stock_infinito_solo_por_sku_exacto(db, base):
    """Una coincidencia PARCIAL (ILIKE) del SKU de un infinito no alcanza
    para mostrarlo: solo aparece con el código completo (exacto)."""
    infinito = base["alta"]("Remera lista infinita exacta", stock_infinito=True)
    parcial = infinito.sku[:3]                                    # ej. "AB0" de "AB003"
    ids = lambda **f: {p.id for p in servicio.listar_stock(db, proveedor_id=base["prov"].id, **f)[0]}
    assert infinito.id not in ids(busqueda=parcial)                # coincidencia parcial: no aparece
    assert ids(busqueda=infinito.sku) == {infinito.id}             # SKU exacto: sí aparece
    assert ids(busqueda=infinito.codigo_con_verificador) == {infinito.id}   # con verificador: también


def test_alertas_y_resumen(db, base):
    a = base["alta"]("Remera resumen A", costo="100")
    b = base["alta"]("Remera resumen B", costo="100")
    servicio.registrar_ingreso(db, base["admin"], a.id, 4, None, None)
    servicio.definir_minimo(db, base["admin"], b.id, 1, None)
    assert b.id in {p.id for p in servicio.alertas(db)}
    r = servicio.resumen(db)
    assert r["productos_con_stock"] >= 1 and r["unidades"] >= 4 and r["bajo_minimo"] >= 1
    assert r["valorizado"] >= Decimal("4") * a.precio_venta


def test_movimientos(db, base):
    p = base["alta"]("Remera movimientos")
    servicio.registrar_ingreso(db, base["admin"], p.id, 3, "Primera", None)
    servicio.registrar_ingreso(db, base["admin"], p.id, 2, "Segunda", None)
    items, total = servicio.listar_movimientos(db, producto_id=p.id)
    assert total == 2 and [m.notas for m in items] == ["Segunda", "Primera"]      # más reciente primero
    assert servicio.listar_movimientos(db, producto_id=p.id, tipo=TipoMovimientoStock.BAJA)[1] == 0
    assert servicio.listar_movimientos(db, producto_id=p.id, desde=date(2000, 1, 1), hasta=date.today())[1] == 2


def test_stock_no_esta_en_los_schemas_de_producto():
    assert "stock" not in ProductoEditar.model_fields and "stock" not in ProductoCrear.model_fields
