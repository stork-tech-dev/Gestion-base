"""Fábricas de datos para tests (catálogo mínimo de productos). Solo tests:
nunca se usan contra la base de desarrollo."""
import itertools
from decimal import Decimal

from app.schemas.categorias import CategoriaCrear
from app.schemas.productos import ProductoCrear
from app.schemas.proveedores import ProveedorCrear
from app.services import categorias as servicio_categorias
from app.services import productos as servicio_productos
from app.services import proveedores as servicio_proveedores
from app.services import turnos as servicio_turnos

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


def abrir_turno_de_test(db, usuario, efectivo="0"):
    """Turno de caja abierto hoy (confirmar y anular ventas lo exigen)."""
    return servicio_turnos.abrir_turno(db, usuario, Decimal(efectivo), None, None)
