"""Lectura y generación de planillas Excel (.xlsx) con openpyxl.

Única vía para importar/exportar tablas simples: el dólar por proveedor
(módulo 03) y la importación inicial (módulo 08)."""
from decimal import Decimal, InvalidOperation
from io import BytesIO
from zipfile import BadZipFile

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter
from openpyxl.utils.exceptions import InvalidFileException

from app.core.errores import ReglaDeNegocio
from app.core.utils import normalizar_texto, sin_tildes

TAMANO_MAXIMO_BYTES = 5 * 1024 * 1024
FILAS_MAXIMAS = 5000
TIPO_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def clave_columna(texto) -> str:
    """Encabezado normalizado: sin tildes, en minúscula y con espacios colapsados."""
    if texto is None:
        return ""
    return sin_tildes(normalizar_texto(str(texto)) or "").lower()


def _fila_vacia(valores) -> bool:
    return all(v is None or (isinstance(v, str) and not v.strip()) for v in valores)


def leer_tabla(contenido: bytes, requeridas, opcionales=()) -> list[tuple[int, dict]]:
    """Filas de la primera hoja como (número de fila en Excel, {columna: valor}).

    Las columnas se ubican por nombre de encabezado (cualquier orden, sin
    importar mayúsculas ni tildes; las columnas extra se ignoran). `requeridas`
    y `opcionales` se pasan ya normalizadas (ej. "proveedor_id")."""
    if not contenido:
        raise ReglaDeNegocio("El archivo está vacío.")
    if len(contenido) > TAMANO_MAXIMO_BYTES:
        raise ReglaDeNegocio("El archivo supera los 5 MB.")
    try:
        libro = load_workbook(BytesIO(contenido), read_only=True, data_only=True)
    except (InvalidFileException, BadZipFile, KeyError, OSError, ValueError) as exc:
        raise ReglaDeNegocio("El archivo no es un Excel (.xlsx) válido.") from exc
    try:
        filas = libro.worksheets[0].iter_rows(values_only=True)
        encabezado = next(filas, None)
        if encabezado is None:
            raise ReglaDeNegocio("El archivo no tiene encabezados.")
        posiciones: dict[str, int] = {}
        for indice, celda in enumerate(encabezado):
            clave = clave_columna(celda)
            if clave and clave not in posiciones:
                posiciones[clave] = indice
        faltan = [c for c in requeridas if c not in posiciones]
        if faltan:
            raise ReglaDeNegocio(f"Faltan columnas: {', '.join(faltan)}")
        resultado = []
        for numero, valores in enumerate(filas, start=2):
            if valores is None or _fila_vacia(valores):
                continue
            if len(resultado) >= FILAS_MAXIMAS:
                raise ReglaDeNegocio(f"El archivo supera las {FILAS_MAXIMAS} filas.")
            fila = {}
            for columna in (*requeridas, *opcionales):
                indice = posiciones.get(columna)
                fila[columna] = valores[indice] if indice is not None and indice < len(valores) else None
            resultado.append((numero, fila))
        return resultado
    finally:
        libro.close()


def generar_plantilla(hoja: str, columnas: list[str], instrucciones: list[list], filas=None) -> bytes:
    """Libro con la hoja de datos (encabezados en negrita, filas precargadas
    opcionales) y una hoja "Instrucciones" (la primera fila en negrita)."""
    libro = Workbook()
    datos = libro.active
    datos.title = hoja
    datos.append(list(columnas))
    for fila in filas or []:
        datos.append(list(fila))
    for celda in datos[1]:
        celda.font = Font(bold=True)
    for indice, columna in enumerate(columnas, start=1):
        largo = max([len(str(columna))] + [len(str(f[indice - 1] or "")) for f in (filas or []) if len(f) >= indice])
        datos.column_dimensions[get_column_letter(indice)].width = min(max(12, largo + 4), 60)
    datos.freeze_panes = "A2"

    ayuda = libro.create_sheet("Instrucciones")
    for fila in instrucciones:
        ayuda.append(list(fila))
    for celda in ayuda[1] if instrucciones else []:
        celda.font = Font(bold=True)
    for indice in range(1, max((len(f) for f in instrucciones), default=0) + 1):
        ayuda.column_dimensions[get_column_letter(indice)].width = 40

    buffer = BytesIO()
    libro.save(buffer)
    return buffer.getvalue()


def celda_decimal(valor) -> Decimal | None:
    """Número de una celda. Acepta números y texto con coma o punto decimal
    ("1.234,56", "1234,5", "1234.5"). None si está vacía; ValueError si no es
    un número finito."""
    if valor is None:
        return None
    if isinstance(valor, bool):
        raise ValueError("no es un número")
    if isinstance(valor, (int, Decimal)):
        numero = Decimal(valor)
    elif isinstance(valor, float):
        numero = Decimal(str(valor))
    else:
        texto = str(valor).strip().replace(" ", "")
        if not texto:
            return None
        if "," in texto and "." in texto:
            texto = texto.replace(".", "").replace(",", ".")
        elif "," in texto:
            texto = texto.replace(",", ".")
        try:
            numero = Decimal(texto)
        except InvalidOperation as exc:
            raise ValueError("no es un número") from exc
    if not numero.is_finite():
        raise ValueError("no es un número")
    return numero


def celda_entero(valor) -> int | None:
    numero = celda_decimal(valor)
    if numero is None:
        return None
    if numero != numero.to_integral_value():
        raise ValueError("no es un número entero")
    return int(numero)
