"""Fábricas de datos para tests (catálogo mínimo de productos). Solo tests:
nunca se usan contra la base de desarrollo."""
import itertools

from app.schemas.categorias import CategoriaCrear
from app.schemas.productos import ProductoCrear
from app.schemas.proveedores import ProveedorCrear
from app.services import categorias as servicio_categorias
from app.services import productos as servicio_productos
from app.services import proveedores as servicio_proveedores

_numeros = itertools.count(1)


def catalogo(db, admin) -> dict:
    n = next(_numeros)
    categoria = servicio_categorias.crear_categoria(db, admin, CategoriaCrear(nombre=f"Ropa fab {n}"), None)
    subcategoria = servicio_categorias.crear_categoria(
        db, admin, CategoriaCrear(nombre=f"Remeras fab {n}", parent_id=categoria.id), None)
    proveedor = servicio_proveedores.crear_proveedor(
        db, admin, ProveedorCrear(nombre=f"Prov fab {n}", moneda="ars"), None)

    def alta(descripcion, costo="1000", categoria_id=None, **extra):
        datos = {"categoria_id": categoria_id or subcategoria.id, "proveedor_id": proveedor.id,
                 "costo": costo, "margen": "0", "descripcion": descripcion}
        datos.update(extra)
        return servicio_productos.crear_producto(db, admin, ProductoCrear(**datos), None)

    return {"categoria": categoria, "subcategoria": subcategoria, "proveedor": proveedor, "alta": alta}
