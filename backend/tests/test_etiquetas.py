import pytest

from app.core.errores import DatoInvalido, NoEncontrado, ReglaDeNegocio
from app.reports import etiquetas_pdf
from app.schemas.categorias import CategoriaCrear
from app.schemas.productos import ProductoCrear
from app.schemas.proveedores import ProveedorCrear
from app.services import categorias as servicio_categorias
from app.services import productos as servicio_productos
from app.services import proveedores as servicio_proveedores

MM = 96 / 25.4   # WeasyPrint mide las páginas en px CSS


@pytest.fixture
def productos(db, crear_usuario):
    admin = crear_usuario("admin")
    hoja = servicio_categorias.crear_categoria(db, admin, CategoriaCrear(nombre="Etiquetas"), None)
    prov = servicio_proveedores.crear_proveedor(db, admin, ProveedorCrear(nombre="Prov etiquetas", moneda="ars"), None)
    return [servicio_productos.crear_producto(db, admin, ProductoCrear(
        categoria_id=hoja.id, proveedor_id=prov.id, costo="10", descripcion=f"Etiqueta {i}"), None) for i in range(2)]


def _medidas(documento):
    return [(round(p.width / MM, 1), round(p.height / MM, 1)) for p in documento.pages]


def test_rectangular_tres_por_renglon(db, productos):
    documento = etiquetas_pdf.etiquetas_documento(db, [(productos[0].id, 4), (productos[1].id, 1)], "rectangular")
    assert _medidas(documento) == [(105.0, 10.0), (105.0, 10.0)]          # 5 etiquetas → 2 renglones


def test_colita_una_por_pagina(db, productos):
    documento = etiquetas_pdf.etiquetas_documento(db, [(productos[0].id, 3)], "colita")
    assert _medidas(documento) == [(66.0, 11.0)] * 3


def test_pdf_y_texto_del_codigo(db, productos):
    contenido = etiquetas_pdf.generar_etiquetas(db, [(productos[0].id, 1)], "rectangular")
    assert contenido.startswith(b"%PDF")
    html = etiquetas_pdf.html_etiquetas(db, [(productos[0].id, 1)], "rectangular")
    assert productos[0].codigo_con_verificador in html and "data:image/svg+xml;base64," in html


def test_validaciones(db, productos):
    with pytest.raises(DatoInvalido):
        etiquetas_pdf.generar_etiquetas(db, [(productos[0].id, 1)], "redonda")
    with pytest.raises(ReglaDeNegocio):
        etiquetas_pdf.generar_etiquetas(db, [(productos[0].id, 1001)], "colita")
    with pytest.raises(NoEncontrado):
        etiquetas_pdf.generar_etiquetas(db, [(999999, 1)], "colita")
