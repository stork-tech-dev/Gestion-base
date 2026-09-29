"""Importación inicial desde Excel (sesión 08): proveedores, clientes y productos.

Un único motor (`_procesar`) parametrizado por una `Definicion` por tipo. Cada
alta pasa por el service del módulo dueño, así que se aplican exactamente las
mismas validaciones y la misma auditoría que el alta manual (Principio 2): acá
solo se parsean celdas, se detectan repetidos dentro del archivo y se resuelven
nombres a ids. Solo altas: nunca modifica registros existentes.

Validar e importar recorren el mismo camino (un SAVEPOINT exterior con uno por
fila) y solo difieren al final: validar siempre revierte; importar confirma si
no hubo ningún error. Así la vista previa nunca promete algo que la
importación después rechaza. Lo único que el rollback no deshace son las
secuencias (ids y SKU): validar puede dejar huecos en la numeración."""
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Callable

from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app.core.auditoria import registrar_auditoria
from app.core.errores import MENSAJE_INTEGRIDAD, ErrorDeNegocio, ReglaDeNegocio
from app.core.etiquetas import CONDICIONES_IVA, MONEDAS
from app.core.excel import celda_decimal, celda_entero, clave_columna, generar_plantilla as _plantilla, leer_tabla
from app.models import Moneda
from app.schemas.clientes import ClienteCrear
from app.schemas.importacion import TipoImportacion
from app.schemas.proveedores import ProveedorCrear
from app.services import clientes as servicio_clientes
from app.services import proveedores as servicio_proveedores

# Mismo tope que ProductoCrear.stock_inicial y StockMinimo.stock_minimo.
ENTERO_MAXIMO = 1_000_000
ENCABEZADO_INSTRUCCIONES = ["Columna", "Obligatoria", "Formato", "Valores posibles", "Ejemplo"]


class ErrorDeFila(Exception):
    """Error de una fila ubicado en una columna (None = la fila en general)."""

    def __init__(self, mensaje: str, columna: str | None = None):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.columna = columna


@contextmanager
def _en_columna(columna: str):
    """Ubica en `columna` el error de negocio que levante el bloque."""
    try:
        yield
    except ErrorDeNegocio as exc:
        raise ErrorDeFila(exc.mensaje, columna) from exc


# ---------- Parsers de celdas: valor crudo → valor Python (ValueError = mensaje para el usuario) ----------

def _texto(valor):
    if valor is None:
        return None
    if isinstance(valor, float) and valor.is_integer():
        valor = int(valor)          # un DNI tipeado como número llega como 30123456.0
    return str(valor).strip() or None   # la normalización fina la hace el service dueño


def _decimal(valor):
    try:
        return celda_decimal(valor)
    except ValueError:
        raise ValueError("Tiene que ser un número.") from None


def _entero_no_negativo(valor):
    try:
        numero = celda_entero(valor)
    except ValueError:
        raise ValueError("Tiene que ser un número entero.") from None
    if numero is not None and not 0 <= numero <= ENTERO_MAXIMO:
        raise ValueError("Tiene que ser un número entero entre 0 y 1.000.000.")
    return numero


def _opcion(opciones):
    """Parser de un enum: acepta la etiqueta legible o el valor, sin importar
    mayúsculas ni tildes. Devuelve el valor."""
    por_clave = {}
    for valor, etiqueta in opciones:
        por_clave[clave_columna(valor)] = valor
        por_clave[clave_columna(etiqueta)] = valor
    posibles = " / ".join(etiqueta for _, etiqueta in opciones)

    def parsear(celda):
        texto = _texto(celda)
        if texto is None:
            return None
        try:
            return por_clave[clave_columna(texto)]
        except KeyError:
            raise ValueError(f"Valor no válido: usá {posibles}.") from None

    parsear.posibles = posibles
    return parsear


# ---------- Definiciones ----------

@dataclass(frozen=True)
class Columna:
    nombre: str                     # encabezado (ya en la forma de clave_columna)
    formato: str
    ejemplo: str
    obligatoria: bool = False
    valores: str = ""
    parser: Callable = _texto


@dataclass(frozen=True)
class Definicion:
    hoja: str
    columnas: tuple[Columna, ...]
    # alta(db, autor, valores, ip, nuevas): crea el registro con el service
    # dueño; `nuevas` recibe los caminos de categorías que creó esa fila.
    alta: Callable
    # claves(valores) → [(columna, clave)]: dos filas con la misma clave en la
    # misma columna son un error ("Repetido en el archivo"). Clave None = no se compara.
    claves: Callable

    @property
    def requeridas(self) -> list[str]:
        return [c.nombre for c in self.columnas if c.obligatoria]

    @property
    def opcionales(self) -> list[str]:
        return [c.nombre for c in self.columnas if not c.obligatoria]


def _sin_vacios(valores: dict, *excluir: str) -> dict:
    """Campos con valor, para que el schema aplique sus defaults a los vacíos."""
    return {k: v for k, v in valores.items() if v is not None and k not in excluir}


def _alta_proveedor(db, autor, valores, ip, nuevas):
    campos = _sin_vacios(valores)
    if campos.get("moneda") == Moneda.USD.value:
        # La regla (obligatorio y > 0) es la del service; acá solo se ubica el error en su columna.
        with _en_columna("dolar_actual"):
            campos["dolar_actual"] = servicio_proveedores.validar_dolar(campos.get("dolar_actual"))
    else:
        campos.pop("dolar_actual", None)        # en pesos el dólar se ignora
    servicio_proveedores.crear_proveedor(db, autor, ProveedorCrear(**campos), ip)


def _alta_cliente(db, autor, valores, ip, nuevas):
    servicio_clientes.crear_cliente(db, autor, ClienteCrear(**_sin_vacios(valores)), ip)


_MONEDA = _opcion(MONEDAS)
_CONDICION_IVA = _opcion(CONDICIONES_IVA)

DEFINICIONES: dict[TipoImportacion, Definicion] = {
    TipoImportacion.PROVEEDORES: Definicion(
        hoja="Proveedores",
        columnas=(
            Columna("nombre", "Texto (único, hasta 200 caracteres)", "Textil Norte", obligatoria=True),
            Columna("moneda", "Texto", "Pesos", obligatoria=True, valores=_MONEDA.posibles, parser=_MONEDA),
            Columna("dolar_actual", "Número mayor a 0 (obligatorio si es en dólares; se ignora si es en pesos)",
                    "1050,50", parser=_decimal),
            Columna("pais", "Texto", "Argentina"),
            Columna("provincia", "Texto", "Buenos Aires"),
            Columna("telefono", "Texto", "11 4444-5555"),
            Columna("email", "Email", "ventas@textilnorte.com"),
            Columna("notas", "Texto libre", "Entrega los martes"),
        ),
        alta=_alta_proveedor,
        claves=lambda v: [("nombre", clave_columna(v["nombre"]))],
    ),
    TipoImportacion.CLIENTES: Definicion(
        hoja="Clientes",
        columnas=(
            Columna("nombre", "Texto (nombre o razón social)", "María López", obligatoria=True),
            Columna("dni", "7 u 8 dígitos (único)", "30123456"),
            Columna("cuit", "11 dígitos, con o sin guiones (único; obligatorio si no es consumidor final)",
                    "20-39059158-7"),
            Columna("condicion_iva", "Texto (vacío = Consumidor final)", "Consumidor final",
                    valores=_CONDICION_IVA.posibles, parser=_CONDICION_IVA),
            Columna("domicilio", "Texto", "Av. Siempreviva 742"),
            Columna("codigo_postal", "Texto", "1414"),
            Columna("localidad", "Texto", "CABA"),
            Columna("telefono", "Texto", "11 5555-6666"),
            Columna("email", "Email", "maria@mail.com"),
        ),
        alta=_alta_cliente,
        claves=lambda v: [("dni", servicio_clientes.solo_digitos(v["dni"])),
                          ("cuit", servicio_clientes.solo_digitos(v["cuit"]))],
    ),
}


# ---------- Motor ----------

_MENSAJES_PYDANTIC = {
    "missing": lambda ctx: "Es obligatoria.",
    "string_too_short": lambda ctx: "Es obligatoria.",
    "string_too_long": lambda ctx: f"Admite hasta {ctx['max_length']} caracteres.",
    "greater_than": lambda ctx: f"Tiene que ser mayor a {ctx['gt']}.",
    "greater_than_equal": lambda ctx: f"Tiene que ser mayor o igual a {ctx['ge']}.",
    "less_than": lambda ctx: f"Tiene que ser menor a {ctx['lt']}.",
    "less_than_equal": lambda ctx: f"Tiene que ser menor o igual a {ctx['le']}.",
    "decimal_max_places": lambda ctx: f"Admite hasta {ctx['decimal_places']} decimales.",
    "decimal_max_digits": lambda ctx: "El número es demasiado grande.",
}


def _mensaje_pydantic(error: dict) -> str:
    armar = _MENSAJES_PYDANTIC.get(error["type"])
    if armar is not None:
        return armar(error.get("ctx") or {})
    if error["loc"] and error["loc"][0] == "email":
        return "El email no es válido."
    return "Dato inválido."


def _parsear(definicion: Definicion, celdas: dict) -> tuple[dict, list[tuple[str, str]]]:
    """Valores parseados y la lista de (columna, error) de TODAS las columnas con error."""
    valores, errores = {}, []
    for columna in definicion.columnas:
        try:
            valor = columna.parser(celdas.get(columna.nombre))
        except ValueError as exc:
            errores.append((columna.nombre, str(exc)))
            continue
        if valor is None and columna.obligatoria:
            errores.append((columna.nombre, "Es obligatoria."))
            continue
        valores[columna.nombre] = valor
    return valores, errores


def _procesar(db, autor, tipo: TipoImportacion, contenido: bytes, archivo: str | None, ip, aplicar: bool) -> dict:
    definicion = DEFINICIONES[tipo]
    filas = leer_tabla(contenido, definicion.requeridas, definicion.opcionales)
    if not filas:
        raise ReglaDeNegocio("El archivo no tiene filas para importar.")
    errores, categorias_nuevas, vistas = [], [], {}
    validas = 0

    def error(fila, columna, mensaje):
        errores.append({"fila": fila, "columna": columna, "error": mensaje})

    exterior = db.begin_nested()
    try:
        for numero, celdas in filas:
            valores, errores_de_parseo = _parsear(definicion, celdas)
            for columna, mensaje in errores_de_parseo:
                error(numero, columna, mensaje)
            if errores_de_parseo:
                continue
            repetida = False
            for columna, clave in definicion.claves(valores):
                if clave is None:
                    continue
                anterior = vistas.setdefault((columna, clave), numero)
                if anterior != numero:
                    error(numero, columna, f"Repetido en el archivo (fila {anterior}).")
                    repetida = True
            if repetida:
                continue
            nuevas: list[str] = []
            try:
                # Savepoint por fila: un error (incluso de la base) deshace solo
                # esta fila y la sesión sigue usable para las siguientes.
                with db.begin_nested():
                    definicion.alta(db, autor, valores, ip, nuevas)
            except ErrorDeFila as exc:
                error(numero, exc.columna, exc.mensaje)
            except ValidationError as exc:
                for detalle in exc.errors():
                    campo = detalle["loc"][0] if detalle["loc"] else None
                    error(numero, campo if campo in valores else None, _mensaje_pydantic(detalle))
            except ErrorDeNegocio as exc:
                error(numero, None, exc.mensaje)
            except IntegrityError:
                error(numero, None, MENSAJE_INTEGRIDAD)
            else:
                validas += 1
                categorias_nuevas.extend(nuevas)
        aplicado = aplicar and not errores
        if aplicado:
            registrar_auditoria(db, accion=f"importacion.{tipo.value}", entidad="importacion", entidad_id=None,
                                usuario_id=autor.id,
                                estado_nuevo={"archivo": archivo, "filas": len(filas), "creados": validas},
                                ip_origen=ip)
            exterior.commit()
        else:
            exterior.rollback()
    except BaseException:
        if exterior.is_active:
            exterior.rollback()
        raise
    return {"tipo": tipo, "filas_leidas": len(filas), "filas_validas": validas,
            "creados": validas if aplicado else 0, "categorias_nuevas": categorias_nuevas,
            "errores": errores, "aplicado": aplicado}


def validar(db, autor, tipo: TipoImportacion, contenido: bytes, archivo: str | None) -> dict:
    """Vista previa: todos los errores de una vez, sin dejar nada en la base."""
    return _procesar(db, autor, tipo, contenido, archivo, None, aplicar=False)


def importar(db, autor, tipo: TipoImportacion, contenido: bytes, archivo: str | None, ip) -> dict:
    """Todo o nada: vuelve a validar desde cero y aplica solo si no hay ningún error."""
    return _procesar(db, autor, tipo, contenido, archivo, ip, aplicar=True)


def generar_plantilla(tipo: TipoImportacion) -> bytes:
    definicion = DEFINICIONES[tipo]
    instrucciones = [ENCABEZADO_INSTRUCCIONES] + [
        [c.nombre, "Sí" if c.obligatoria else "No", c.formato, c.valores, c.ejemplo] for c in definicion.columnas
    ]
    return _plantilla(definicion.hoja, [c.nombre for c in definicion.columnas], instrucciones)
