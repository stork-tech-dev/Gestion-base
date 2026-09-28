from decimal import Decimal

import pytest

from app.core.errores import NoEncontrado
from app.models import TemporadaProducto
from app.schemas.categorias import CategoriaCrear
from app.schemas.productos import ProductoCrear
from app.schemas.proveedores import ProveedorCrear
from app.services import categorias as servicio_categorias
from app.services import productos as servicio
from app.services import proveedores as servicio_proveedores


@pytest.fixture
def datos(db, crear_usuario):
    admin = crear_usuario("admin")
    ropa = servicio_categorias.crear_categoria(db, admin, CategoriaCrear(nombre="Ropa"), None)
    remeras = servicio_categorias.crear_categoria(db, admin, CategoriaCrear(nombre="Remeras", parent_id=ropa.id), None)
    calzado = servicio_categorias.crear_categoria(db, admin, CategoriaCrear(nombre="Calzado"), None)
    prov = servicio_proveedores.crear_proveedor(db, admin, ProveedorCrear(nombre="Prov búsqueda", moneda="ars"), None)
    otro = servicio_proveedores.crear_proveedor(db, admin, ProveedorCrear(nombre="Otro prov", moneda="ars"), None)

    def alta(descripcion, categoria=remeras, proveedor=prov, **extra):
        # Desvío del brief: costo="1000"/margen="0" fijos colisionaban con el
        # costo="5000" que pasa el alta de "zapa" (keyword duplicado). Se
        # usan como default vía setdefault para permitir el override.
        extra.setdefault("costo", "1000")
        extra.setdefault("margen", "0")
        return servicio.crear_producto(db, admin, ProductoCrear(
            categoria_id=categoria.id, proveedor_id=proveedor.id,
            descripcion=descripcion, **extra), None)

    productos = {
        "roja": alta("Remera lisa roja", sku_proveedor="PRV-100"),
        "azul": alta("Remera lisa azul", temporada=TemporadaProducto.PRIMAVERA_VERANO),
        "zapa": alta("Zapatilla urbana", categoria=calzado, costo="5000"),
        "otra": alta("Remera lisa roja", proveedor=otro),
    }
    return {"admin": admin, "ropa": ropa, "remeras": remeras, "calzado": calzado, "prov": prov, "otro": otro, **productos}


def _ids(resultado):
    items, _ = resultado
    return {p.id for p in items}


def test_buscar_por_codigo(db, datos):
    p = datos["roja"]
    assert servicio.buscar_por_codigo(db, p.codigo_con_verificador).id == p.id
    assert servicio.buscar_por_codigo(db, p.codigo_con_verificador.lower()).id == p.id
    assert servicio.buscar_por_codigo(db, p.sku).id == p.id
    malo = p.sku + ("0" if p.verificador != "0" else "1")
    with pytest.raises(NoEncontrado):
        servicio.buscar_por_codigo(db, malo)
    with pytest.raises(NoEncontrado):
        servicio.buscar_por_codigo(db, "ZZ999")


def test_listado_busqueda_por_codigo_sku_proveedor_y_descripcion(db, datos):
    p = datos["roja"]
    assert p.id in _ids(servicio.listar_productos(db, busqueda=p.codigo_con_verificador))
    assert _ids(servicio.listar_productos(db, busqueda=p.codigo_con_verificador)) == {p.id}
    assert _ids(servicio.listar_productos(db, busqueda="prv-100")) == {p.id}
    assert _ids(servicio.listar_productos(db, busqueda="LISA")) >= {datos["roja"].id, datos["azul"].id, datos["otra"].id}


def test_listado_filtros(db, datos):
    assert _ids(servicio.listar_productos(db, categoria_id=datos["ropa"].id)) >= {datos["roja"].id, datos["azul"].id}
    assert datos["zapa"].id not in _ids(servicio.listar_productos(db, categoria_id=datos["ropa"].id))
    assert _ids(servicio.listar_productos(db, proveedor_id=datos["otro"].id)) == {datos["otra"].id}
    assert _ids(servicio.listar_productos(db, temporada=TemporadaProducto.PRIMAVERA_VERANO)) == {datos["azul"].id}
    assert datos["zapa"].id in _ids(servicio.listar_productos(db, precio_desde=Decimal("4000")))
    assert datos["roja"].id not in _ids(servicio.listar_productos(db, precio_desde=Decimal("4000")))
    servicio.cambiar_estado_producto(db, datos["admin"], datos["azul"], False, None)
    assert datos["azul"].id not in _ids(servicio.listar_productos(db, activo=True))
    assert datos["azul"].id in _ids(servicio.listar_productos(db, activo=False))


def test_listado_paginado_y_ordenado(db, datos):
    items, total = servicio.listar_productos(db, proveedor_id=datos["prov"].id, pagina=1, tamano=2)
    assert total == 3 and len(items) == 2
    assert [p.descripcion for p in items] == ["Remera lisa azul", "Remera lisa roja"]


def test_similares(db, datos):
    assert servicio.buscar_similares(db, "Remera") == []                     # menos de 10 caracteres
    similares = servicio.buscar_similares(db, "remera LISA", categoria_id=datos["ropa"].id, proveedor_id=datos["prov"].id)
    assert {s["id"] for s in similares} == {datos["roja"].id, datos["azul"].id}
    assert set(similares[0]) == {"id", "sku", "descripcion", "activo"}
    assert servicio.buscar_similares(db, "remera lisa verde") == []           # exige todas las palabras de 3+


def test_barcode_svg(db, datos):
    p = datos["roja"]
    svg = servicio.barcode_svg(db, p.id)
    assert svg.startswith("<svg") and "viewBox" in svg and "mm" not in svg.split(">", 1)[1]
    etiqueta = servicio.barcode_svg_para_etiqueta(db, p.id)
    assert 'width="16mm"' in etiqueta and 'height="4.5mm"' in etiqueta and 'preserveAspectRatio="none"' in etiqueta
    with pytest.raises(NoEncontrado):
        servicio.barcode_svg(db, 999999)


@pytest.mark.parametrize("texto, esperado", [
    ("", None), ("   ", None), (None, None),
    ("ab123", "AB123"),                       # SKU solo: tal cual, en mayúsculas
    (" ab12 ", "AB12"),                       # parcial: tal cual
])
def test_sku_de_codigo(texto, esperado):
    assert servicio._sku_de_codigo(texto) == esperado


def test_sku_de_codigo_con_etiqueta(db, datos):
    p = datos["roja"]
    assert servicio._sku_de_codigo(p.codigo_con_verificador.lower()) == p.sku
    malo = p.sku + ("0" if p.verificador != "0" else "1")
    assert servicio._sku_de_codigo(malo) == malo                          # verificador incorrecto: el texto


def test_similares_incluye_inactivos(db, datos):
    servicio.cambiar_estado_producto(db, datos["admin"], datos["azul"], False, None)
    similares = servicio.buscar_similares(db, "remera lisa azul", proveedor_id=datos["prov"].id)
    assert [(s["id"], s["activo"]) for s in similares] == [(datos["azul"].id, False)]
