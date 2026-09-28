"""Task 5 del módulo 05: stock inicial en el alta de productos, los campos
stock/stock_minimo/bajo_minimo en la respuesta y el filtro stock_cero de
listar_productos."""
import pytest
from sqlalchemy import select

from app.core.errores import SinPermiso
from app.models import Auditoria, MovimientoStock, Producto, TipoMovimientoStock, UsuarioPermiso
from app.schemas.categorias import CategoriaCrear
from app.schemas.productos import ProductoCrear
from app.schemas.proveedores import ProveedorCrear
from app.services import categorias as servicio_categorias
from app.services import productos as servicio
from app.services import proveedores as servicio_proveedores
from app.services import stock as servicio_stock


@pytest.fixture
def admin(crear_usuario):
    return crear_usuario("admin")


@pytest.fixture
def base(db, admin):
    ropa = servicio_categorias.crear_categoria(db, admin, CategoriaCrear(nombre="Ropa stock inicial"), None)
    hoja = servicio_categorias.crear_categoria(
        db, admin, CategoriaCrear(nombre="Remeras stock inicial", parent_id=ropa.id), None)
    prov = servicio_proveedores.crear_proveedor(db, admin, ProveedorCrear(nombre="Prov stock inicial", moneda="ars"), None)
    return {"hoja": hoja, "prov": prov}


def _alta(db, autor, base, **extra):
    datos = {"categoria_id": base["hoja"].id, "proveedor_id": base["prov"].id, "costo": "1000", "margen": "0",
             "descripcion": "Remera stock inicial"}
    datos.update(extra)
    return servicio.crear_producto(db, autor, ProductoCrear(**datos), None)


def test_alta_con_stock_inicial_genera_ingreso_y_auditorias(db, admin, base):
    p = _alta(db, admin, base, stock_inicial=7)
    assert p.stock == 7

    movimiento = db.scalar(select(MovimientoStock).where(MovimientoStock.producto_id == p.id))
    assert movimiento is not None
    assert (movimiento.tipo, movimiento.cantidad, movimiento.stock_resultante, movimiento.notas) == (
        TipoMovimientoStock.INGRESO_PROVEEDOR, 7, 7, "Stock inicial")

    assert db.scalar(select(Auditoria).where(Auditoria.accion == "producto.crear", Auditoria.entidad_id == p.id))
    registro_stock = db.scalar(
        select(Auditoria).where(Auditoria.accion == "stock.ingreso_proveedor", Auditoria.entidad_id == p.id))
    assert registro_stock is not None
    assert registro_stock.estado_anterior == {"stock": 0}
    assert registro_stock.estado_nuevo["stock"] == 7


def test_alta_sin_stock_inicial_no_genera_movimiento(db, admin, base):
    p = _alta(db, admin, base, descripcion="Remera sin stock inicial", stock_inicial=0)
    assert p.stock == 0
    assert db.scalar(select(MovimientoStock).where(MovimientoStock.producto_id == p.id)) is None
    # Tampoco queda auditoría de stock si no hubo movimiento.
    assert db.scalar(
        select(Auditoria).where(Auditoria.accion == "stock.ingreso_proveedor", Auditoria.entidad_id == p.id)) is None


def test_alta_stock_infinito_ignora_stock_inicial(db, admin, base):
    """Decisión del brief: con stock_infinito=True se ignora el stock inicial
    (ni error, ni movimiento)."""
    p = _alta(db, admin, base, descripcion="Remera infinita", stock_infinito=True, stock_inicial=5)
    assert p.stock == 0
    assert p.stock_infinito is True
    assert db.scalar(select(MovimientoStock).where(MovimientoStock.producto_id == p.id)) is None


def test_stock_inicial_sin_permiso_de_stock_da_sin_permiso(db, crear_usuario, base):
    """Vendedor (seed.sql) tiene PRODUCTOS crear pero NO STOCK crear: cargar
    stock inicial es, en los hechos, un ingreso de stock. Se valida ANTES de
    crear nada: no queda producto ni movimiento."""
    vendedor = crear_usuario("vendedor")
    with pytest.raises(SinPermiso) as error:
        _alta(db, vendedor, base, descripcion="Remera sin permiso de stock", stock_inicial=5)
    assert error.value.mensaje == "Cargar stock inicial requiere permiso de ingreso de stock"
    assert db.scalar(select(Producto).where(Producto.descripcion == "Remera sin permiso de stock")) is None


def test_stock_inicial_sin_permiso_pero_sin_cantidad_no_molesta(db, crear_usuario, base):
    """Sin stock_inicial (0, el default) no hace falta el permiso de stock."""
    vendedor = crear_usuario("vendedor")
    p = _alta(db, vendedor, base, descripcion="Remera stock cero sin permiso")
    assert p.stock == 0


def test_stock_inicial_con_permiso_puntual_de_stock_funciona(db, crear_usuario, base):
    """Con un override que da STOCK crear (aunque no sea el rol Admin), el
    alta con stock inicial funciona igual que para el Admin."""
    vendedor = crear_usuario("vendedor")
    db.add(UsuarioPermiso(usuario_id=vendedor.id, modulo="stock", puede_crear=True))
    db.flush()
    p = _alta(db, vendedor, base, descripcion="Remera con permiso puntual de stock", stock_inicial=4)
    assert p.stock == 4


def test_stock_inicial_infinito_no_exige_permiso_de_stock(db, admin, base, monkeypatch):
    """stock_infinito=True ignora el stock inicial (no genera movimiento): no
    debe ni consultar el permiso de stock. Stock infinito solo lo puede
    definir el Admin (regla aparte, no relacionada), así que se usa admin y
    se parchea resolver_permiso para que niegue todo: si el chequeo de
    stock_inicial igual se evaluara, esto lo haría fallar con SinPermiso."""
    monkeypatch.setattr(servicio, "resolver_permiso", lambda *a, **k: False)
    p = _alta(db, admin, base, descripcion="Remera infinita sin permiso de stock",
              stock_infinito=True, stock_inicial=5)
    assert p.stock == 0 and p.stock_infinito is True


def test_a_respuesta_trae_stock_stock_minimo_y_bajo_minimo(db, admin, base):
    p = _alta(db, admin, base, descripcion="Remera para la respuesta", stock_inicial=3)
    servicio_stock.definir_minimo(db, admin, p.id, 5, None)
    db.refresh(p)

    [respuesta] = servicio.a_respuesta(db, [p])
    assert (respuesta.stock, respuesta.stock_minimo, respuesta.bajo_minimo) == (3, 5, True)

    detalle = servicio.a_detalle(db, p)
    assert (detalle.stock, detalle.stock_minimo, detalle.bajo_minimo) == (3, 5, True)


def test_listar_productos_stock_cero_incluye_cero_y_negativo_excluye_resto(db, admin, base):
    con_stock = _alta(db, admin, base, descripcion="Remera con stock", stock_inicial=5)
    sin_stock = _alta(db, admin, base, descripcion="Remera sin stock")
    negativa = _alta(db, admin, base, descripcion="Remera con faltante")
    servicio_stock.aplicar_movimiento(db, admin, tipo=TipoMovimientoStock.VENTA, producto_id=negativa.id,
                                      cantidad=-3, referencia_venta_id=1, permitir_faltante=True)
    infinita = _alta(db, admin, base, descripcion="Remera infinita sin stock", stock_infinito=True)

    productos, total = servicio.listar_productos(db, stock_cero=True, tamano=50)
    ids = {p.id for p in productos}

    assert ids == {sin_stock.id, negativa.id}
    assert con_stock.id not in ids
    assert infinita.id not in ids
    assert total == 2

    # Por defecto (stock_cero=False) no filtra por stock.
    todos, total_todos = servicio.listar_productos(db, tamano=50)
    assert total_todos == 4
    assert {p.id for p in todos} == {con_stock.id, sin_stock.id, negativa.id, infinita.id}
