from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.models import Categoria, Moneda, Producto, ProductoFoto, Proveedor, TemporadaProducto


def _base(db):
    raiz = Categoria(nombre="Ropa", nivel=1, parent_id=None)
    db.add(raiz)
    db.flush()
    hoja = Categoria(nombre="Remeras", nivel=2, parent_id=raiz.id)
    pesos = Proveedor(nombre="Textil Pesos", moneda=Moneda.ARS)
    dolares = Proveedor(nombre="Import Dólar", moneda=Moneda.USD, dolar_actual=Decimal("1000.50"))
    db.add_all([hoja, pesos, dolares])
    db.flush()
    return hoja, pesos, dolares


def _producto(hoja, proveedor, **extra):
    datos = dict(sku="AA001", verificador="9", descripcion="Remera lisa roja", categoria_id=hoja.id,
                 proveedor_id=proveedor.id, costo=Decimal("10.00"), margen=Decimal("100"),
                 precio_venta=Decimal("20.00"))
    datos.update(extra)
    return Producto(**datos)


def test_producto_y_propiedades(db):
    hoja, _, dolares = _base(db)
    p = _producto(hoja, dolares)
    db.add(p)
    db.flush()
    db.refresh(p)
    assert p.temporada is TemporadaProducto.ATEMPORAL and p.activo and not p.stock_infinito
    assert p.descuento_producto == Decimal("0")
    assert p.codigo_con_verificador == "AA0019"
    assert p.moneda is Moneda.USD
    assert p.costo_en_pesos == Decimal("10005.00")
    assert p.foto_principal_url is None
    assert db.execute(text("SELECT temporada::text FROM productos WHERE id = :i"), {"i": p.id}).scalar_one() == "atemporal"


def test_costo_en_pesos_de_proveedor_en_pesos(db):
    hoja, pesos, _ = _base(db)
    p = _producto(hoja, pesos, costo=Decimal("1234.56"))
    db.add(p)
    db.flush()
    db.refresh(p)
    assert p.moneda is Moneda.ARS and p.costo_en_pesos == Decimal("1234.56")


def test_foto_principal_url(db):
    hoja, pesos, _ = _base(db)
    p = _producto(hoja, pesos)
    db.add(p)
    db.flush()
    db.add_all([ProductoFoto(producto_id=p.id, url="/uploads/productos/b.jpg", orden=2),
                ProductoFoto(producto_id=p.id, url="/uploads/productos/a.jpg", orden=1)])
    db.flush()
    db.refresh(p)
    assert p.foto_principal_url == "/uploads/productos/a.jpg"   # sin principal: la primera por orden
    p.fotos[1].es_principal = True
    db.flush()
    db.refresh(p)
    assert p.foto_principal_url == "/uploads/productos/b.jpg"


def test_una_sola_foto_principal(db):
    hoja, pesos, _ = _base(db)
    p = _producto(hoja, pesos)
    db.add(p)
    db.flush()
    db.add_all([ProductoFoto(producto_id=p.id, url="/u/1.jpg", es_principal=True),
                ProductoFoto(producto_id=p.id, url="/u/2.jpg", es_principal=True)])
    with pytest.raises(IntegrityError):
        db.flush()


def test_descripcion_unica_por_categoria_y_proveedor_sin_tildes(db):
    hoja, pesos, dolares = _base(db)
    db.add(_producto(hoja, pesos, descripcion="Pantalón azul"))
    db.flush()
    db.add(_producto(hoja, dolares, sku="AA002", descripcion="pantalon AZUL"))   # otro proveedor: ok
    db.flush()
    db.add(_producto(hoja, pesos, sku="AA003", descripcion="PANTALON azul"))
    with pytest.raises(IntegrityError):
        db.flush()


@pytest.mark.parametrize("campo, valor", [
    ("costo", Decimal("0")), ("margen", Decimal("-1")), ("margen", Decimal("1000.01")),
    ("precio_venta", Decimal("-1")), ("descuento_producto", Decimal("100.01")), ("peso_gramos", Decimal("0")),
])
def test_checks_de_productos(db, campo, valor):
    hoja, pesos, _ = _base(db)
    db.add(_producto(hoja, pesos, **{campo: valor}))
    with pytest.raises(IntegrityError):
        db.flush()


def test_sku_unico(db):
    hoja, pesos, _ = _base(db)
    db.add(_producto(hoja, pesos))
    db.flush()
    db.add(_producto(hoja, pesos, descripcion="Otra"))
    with pytest.raises(IntegrityError):
        db.flush()


@pytest.mark.parametrize("nivel, con_padre", [(1, True), (2, False), (0, False), (6, True)])
def test_check_de_nivel_de_categoria(db, nivel, con_padre):
    raiz = Categoria(nombre="Raíz", nivel=1)
    db.add(raiz)
    db.flush()
    db.add(Categoria(nombre="Mal", nivel=nivel, parent_id=raiz.id if con_padre else None))
    with pytest.raises(IntegrityError):
        db.flush()


def test_categorias_hermanas_con_mismo_nombre(db):
    db.add(Categoria(nombre="Ropa", nivel=1))
    db.flush()
    db.add(Categoria(nombre="Ropa", nivel=1))          # NULLS NOT DISTINCT: dos raíces iguales chocan
    with pytest.raises(IntegrityError):
        db.flush()


def test_secuencia_del_sku(db):
    a = db.execute(text("SELECT nextval('productos_sku_seq')")).scalar_one()
    b = db.execute(text("SELECT nextval('productos_sku_seq')")).scalar_one()
    assert b == a + 1
