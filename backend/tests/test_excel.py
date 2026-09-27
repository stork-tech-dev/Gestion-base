from decimal import Decimal
from io import BytesIO

import pytest
from openpyxl import Workbook, load_workbook

from app.core.errores import ReglaDeNegocio
from app.core.excel import (
    FILAS_MAXIMAS,
    celda_decimal,
    celda_entero,
    clave_columna,
    generar_plantilla,
    leer_tabla,
)


def _xlsx(filas) -> bytes:
    libro = Workbook()
    hoja = libro.active
    for fila in filas:
        hoja.append(fila)
    buffer = BytesIO()
    libro.save(buffer)
    return buffer.getvalue()


def test_clave_columna():
    assert clave_columna("  Dólar   Nuevo ") == "dolar nuevo"
    assert clave_columna("Proveedor_ID") == "proveedor_id"
    assert clave_columna(None) == ""


def test_leer_tabla_ubica_columnas_por_nombre_y_saltea_vacias():
    contenido = _xlsx([
        ["Extra", "DOLAR_NUEVO", "Proveedor_ID"],
        ["x", 1250.5, 3],
        [None, None, None],
        ["", "  ", None],
        ["y", "1.300,25", "4"],
    ])
    filas = leer_tabla(contenido, ["proveedor_id", "dolar_nuevo"], ["nombre"])
    assert filas == [
        (2, {"proveedor_id": 3, "dolar_nuevo": 1250.5, "nombre": None}),
        (5, {"proveedor_id": "4", "dolar_nuevo": "1.300,25", "nombre": None}),
    ]


@pytest.mark.parametrize(
    "contenido, mensaje",
    [
        (b"", "vacío"),
        (b"no soy un excel", "no es un Excel"),
        (None, "Faltan columnas: dolar_nuevo"),
    ],
)
def test_leer_tabla_rechaza_archivos_invalidos(contenido, mensaje):
    if contenido is None:
        contenido = _xlsx([["proveedor_id"], [1]])
    with pytest.raises(ReglaDeNegocio) as error:
        leer_tabla(contenido, ["proveedor_id", "dolar_nuevo"])
    assert mensaje in error.value.mensaje


def test_leer_tabla_limita_filas():
    contenido = _xlsx([["proveedor_id"]] + [[i] for i in range(FILAS_MAXIMAS + 1)])
    with pytest.raises(ReglaDeNegocio) as error:
        leer_tabla(contenido, ["proveedor_id"])
    assert str(FILAS_MAXIMAS) in error.value.mensaje


def test_plantilla_ida_y_vuelta():
    contenido = generar_plantilla(
        "Dolar", ["proveedor_id", "nombre", "dolar_nuevo"],
        [["Columna", "Qué poner"], ["dolar_nuevo", "El valor nuevo"]],
        filas=[[1, "Importadora Sur", Decimal("1250.50")]],
    )
    libro = load_workbook(BytesIO(contenido))
    assert libro.sheetnames == ["Dolar", "Instrucciones"]
    assert libro["Dolar"]["A1"].font.bold and libro["Dolar"].freeze_panes == "A2"
    assert libro["Instrucciones"]["A1"].value == "Columna"
    filas = leer_tabla(contenido, ["proveedor_id", "dolar_nuevo"], ["nombre"])
    assert filas == [(2, {"proveedor_id": 1, "dolar_nuevo": 1250.5, "nombre": "Importadora Sur"})]


@pytest.mark.parametrize(
    "valor, esperado",
    [
        (None, None), ("", None), ("  ", None), (3, Decimal("3")), (1250.5, Decimal("1250.5")),
        (Decimal("7.25"), Decimal("7.25")), ("1.234,56", Decimal("1234.56")), ("1234,5", Decimal("1234.5")),
        ("1234.5", Decimal("1234.5")), (" 1 250 ", Decimal("1250")),
    ],
)
def test_celda_decimal(valor, esperado):
    assert celda_decimal(valor) == esperado


@pytest.mark.parametrize("valor", ["abc", "NaN", "Infinity", True, "1,2,3"])
def test_celda_decimal_invalida(valor):
    with pytest.raises(ValueError):
        celda_decimal(valor)


def test_celda_entero():
    assert celda_entero(12) == 12 and celda_entero(12.0) == 12 and celda_entero("7") == 7
    assert celda_entero(None) is None
    with pytest.raises(ValueError):
        celda_entero(3.5)
