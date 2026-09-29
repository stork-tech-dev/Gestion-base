"""Motor único de reportes (sesión 09). Una DefinicionReporte (columnas +
consulta SQL agregada) alcanza para el JSON, el Excel y el PDF: agregar un
reporte es escribir su módulo en app/reports/definiciones/ y sumarlo al
registro REPORTES de esa carpeta, sin tocar exportadores, plantilla ni pantalla."""
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from app.core import excel
from app.core.errores import NoProcesable, ReglaDeNegocio
from app.core.etiquetas import AGRUPACIONES, ORDENES
from app.core.templates import STATIC_DIR
from app.core.utils import ahora, ahora_db, redondear
from app.models import MedioDePago, Proveedor, Usuario
from app.reports import pdf
from app.schemas.reportes import Agrupar, FiltrosReporte, Orden, TipoColumna
from app.services.categorias import caminos

RANGO_MAXIMO_DIAS = 366
NIVEL_POR_DEFECTO = 1
LIMITE_POR_DEFECTO = 50
PLANTILLA_PDF = "reports/reporte.html"
COLUMNAS_PDF_VERTICAL = 6   # con más columnas, A4 apaisado
NUMERICOS = (TipoColumna.ENTERO, TipoColumna.MONEDA, TipoColumna.PORCENTAJE)
FORMATO_EXCEL = {
    TipoColumna.TEXTO: None,
    TipoColumna.ENTERO: "#,##0",
    TipoColumna.MONEDA: '"$" #,##0.00',
    TipoColumna.PORCENTAJE: '0.0"%"',
    TipoColumna.FECHA: "DD/MM/YYYY",
    TipoColumna.MES: "MM/YYYY",
}


@dataclass(frozen=True)
class Columna:
    clave: str
    titulo: str
    tipo: TipoColumna


@dataclass(frozen=True)
class DefinicionReporte:
    clave: str
    nombre: str
    descripcion: str
    filtros_admitidos: tuple[str, ...]
    # Las columnas pueden depender de los filtros (ej. "Período" es fecha o mes según `agrupar`).
    columnas: Callable[[FiltrosReporte], list[Columna]]
    # consulta(db, filtros) -> (filas, totales): dicts por clave de columna, agregados en SQL.
    consulta: Callable
    agrupaciones: tuple[Agrupar, ...] = ()   # la primera es la de por defecto

    @property
    def usa_fechas(self) -> bool:
        return "desde" in self.filtros_admitidos


def titulo_de_agrupacion(agrupar: Agrupar) -> str:
    """Título de la columna del grupo ("Día", "Categoría"…): mismos textos que el selector."""
    return dict(AGRUPACIONES)[agrupar.value]


def normalizar_filtros(definicion: DefinicionReporte, filtros: FiltrosReporte, hoy: date | None = None) -> FiltrosReporte:
    """Valida los filtros contra lo que admite el reporte y completa los
    valores por defecto. NoProcesable (422) si llega un filtro que el reporte
    no admite o que no aplica; ReglaDeNegocio (409) si el rango supera
    RANGO_MAXIMO_DIAS (contando ambos extremos)."""
    datos = filtros.model_dump(exclude_none=True)
    no_admitidos = sorted(set(datos) - set(definicion.filtros_admitidos))
    if no_admitidos:
        raise NoProcesable(f"El reporte '{definicion.nombre}' no admite: {', '.join(no_admitidos)}.")
    if definicion.usa_fechas:
        hoy = hoy or ahora().date()
        # El 1° del mes de "hasta" si vino (no siempre el mes actual: si el
        # usuario solo manda "hasta" de un mes anterior, "desde" tiene que
        # acompañarlo y no quedar posterior a "hasta").
        datos.setdefault("desde", datos.get("hasta", hoy).replace(day=1))
        datos.setdefault("hasta", hoy)
        if datos["desde"] > datos["hasta"]:
            raise NoProcesable("La fecha 'desde' no puede ser posterior a 'hasta'.")
        if (datos["hasta"] - datos["desde"]).days + 1 > RANGO_MAXIMO_DIAS:
            raise ReglaDeNegocio(f"El rango de fechas no puede superar los {RANGO_MAXIMO_DIAS} días.")
    if definicion.agrupaciones:
        datos.setdefault("agrupar", definicion.agrupaciones[0])
        if datos["agrupar"] not in definicion.agrupaciones:
            raise NoProcesable(f"El reporte '{definicion.nombre}' no se agrupa por '{datos['agrupar'].value}'.")
    if "nivel" in definicion.filtros_admitidos:
        if datos.get("agrupar") is Agrupar.CATEGORIA:
            datos.setdefault("nivel", NIVEL_POR_DEFECTO)
        elif "nivel" in datos:
            raise NoProcesable("El nivel de categoría solo se usa al agrupar por categoría.")
    if "orden" in definicion.filtros_admitidos:
        datos.setdefault("orden", Orden.UNIDADES)
    if "limite" in definicion.filtros_admitidos:
        datos.setdefault("limite", LIMITE_POR_DEFECTO)
    return FiltrosReporte(**datos)


def _valor(tipo: TipoColumna, valor):
    """Valor crudo normalizado por tipo: enteros como int, importes y
    porcentajes con 2 decimales (un SUM sin filas da NULL → 0), fechas como date."""
    if tipo is TipoColumna.ENTERO:
        return int(valor or 0)
    if tipo in (TipoColumna.MONEDA, TipoColumna.PORCENTAJE):
        return redondear(valor or 0)
    if tipo in (TipoColumna.FECHA, TipoColumna.MES) and isinstance(valor, datetime):
        return valor.date()
    return valor


def _normalizar_fila(columnas: list[Columna], fila: dict) -> dict:
    return {c.clave: _valor(c.tipo, fila.get(c.clave)) for c in columnas}


def generar(db, definicion: DefinicionReporte, filtros: FiltrosReporte) -> dict:
    """Corre la consulta del reporte. Devuelve {clave, nombre, filtros
    (normalizados), columnas (list[Columna]), filas, totales, generado_en}."""
    filtros = normalizar_filtros(definicion, filtros)
    columnas = definicion.columnas(filtros)
    filas, totales = definicion.consulta(db, filtros)
    return {
        "clave": definicion.clave,
        "nombre": definicion.nombre,
        "filtros": filtros,
        "columnas": columnas,
        "filas": [_normalizar_fila(columnas, f) for f in filas],
        "totales": _normalizar_fila(columnas, totales),
        "generado_en": ahora_db(),
    }


def _nombre(db, modelo, id_: int) -> str:
    objeto = db.get(modelo, id_)
    return objeto.nombre if objeto is not None else f"#{id_}"


def describir_filtros(db, filtros: FiltrosReporte) -> list[tuple[str, str]]:
    """Filtros aplicados en texto legible (encabezado del Excel y del PDF)."""
    partes = []
    if filtros.desde:
        partes.append(("Desde", f"{filtros.desde:%d/%m/%Y}"))
    if filtros.hasta:
        partes.append(("Hasta", f"{filtros.hasta:%d/%m/%Y}"))
    if filtros.agrupar:
        partes.append(("Agrupar por", titulo_de_agrupacion(filtros.agrupar)))
    if filtros.nivel:
        partes.append(("Nivel de categoría", str(filtros.nivel)))
    if filtros.orden:
        partes.append(("Orden", dict(ORDENES)[filtros.orden.value]))
    if filtros.limite:
        partes.append(("Límite", str(filtros.limite)))
    if filtros.proveedor_id:
        partes.append(("Proveedor", _nombre(db, Proveedor, filtros.proveedor_id)))
    if filtros.categoria_id:
        partes.append(("Categoría", caminos(db).get(filtros.categoria_id, f"#{filtros.categoria_id}")))
    if filtros.usuario_id:
        partes.append(("Vendedor", _nombre(db, Usuario, filtros.usuario_id)))
    if filtros.medio_de_pago_id:
        partes.append(("Medio de pago", _nombre(db, MedioDePago, filtros.medio_de_pago_id)))
    return partes


def _con_etiqueta_total(valores: list) -> list:
    """Fila de totales: "Total" en la primera celda (siempre la del grupo, que no se totaliza)."""
    return ["Total", *valores[1:]]


def exportar_excel(db, resultado: dict) -> bytes:
    columnas = resultado["columnas"]
    return excel.generar_reporte(
        resultado["nombre"],
        describir_filtros(db, resultado["filtros"]),
        [(c.titulo, FORMATO_EXCEL[c.tipo]) for c in columnas],
        [[fila[c.clave] for c in columnas] for fila in resultado["filas"]],
        _con_etiqueta_total([resultado["totales"][c.clave] for c in columnas]),
    )


def _miles(valor, decimales: int = 2) -> str:
    """1234.5 → "1.234,50" (formato argentino)."""
    texto = f"{Decimal(valor):,.{decimales}f}"
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")


def formatear(valor, tipo: TipoColumna) -> str:
    """Celda del PDF en formato argentino (el JSON y el Excel van crudos)."""
    if valor is None:
        return ""
    if tipo is TipoColumna.ENTERO:
        return _miles(valor, 0)
    if tipo is TipoColumna.MONEDA:
        return "$ " + _miles(valor)
    if tipo is TipoColumna.PORCENTAJE:
        return _miles(valor, 1) + " %"
    if tipo is TipoColumna.FECHA:
        return f"{valor:%d/%m/%Y}"
    if tipo is TipoColumna.MES:
        return f"{valor:%m/%Y}"
    return str(valor)


def exportar_pdf(db, resultado: dict) -> bytes:
    columnas = resultado["columnas"]
    logo = STATIC_DIR / "img" / "logo.svg"
    return pdf.imprimir(PLANTILLA_PDF, {
        "titulo": resultado["nombre"],
        "filtros": describir_filtros(db, resultado["filtros"]),
        "columnas": columnas,
        "alineaciones": ["numero" if c.tipo in NUMERICOS else "" for c in columnas],
        "filas": [[formatear(fila[c.clave], c.tipo) for c in columnas] for fila in resultado["filas"]],
        "totales": _con_etiqueta_total([formatear(resultado["totales"][c.clave], c.tipo) for c in columnas]),
        "apaisado": len(columnas) > COLUMNAS_PDF_VERTICAL,
        "emitido": f"{resultado['generado_en']:%d/%m/%Y %H:%M}",
        "logo": logo.resolve().as_uri() if logo.is_file() else None,
    })
