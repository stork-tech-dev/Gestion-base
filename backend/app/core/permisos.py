"""Constantes de dominio de permisos: ÚNICA fuente de módulos, recursos,
acciones, roles de sistema y etiquetas. Nunca escribir estos literales fuera
de este archivo."""
from dataclasses import dataclass
from enum import Enum


class Modulo(str, Enum):
    CLIENTES = "clientes"
    PROVEEDORES = "proveedores"
    PRODUCTOS = "productos"
    STOCK = "stock"
    VENTAS = "ventas"
    CAJA = "caja"
    CONFIGURACION = "configuracion"
    USUARIOS = "usuarios"
    AUDITORIA = "auditoria"
    IMPORTACION = "importacion"  # sesión 08
    REPORTES = "reportes"  # sesión 09


class Recurso(str, Enum):
    """Operaciones puntuales que se pueden habilitar sin dar el módulo entero."""

    DOLAR_CAMBIO_MASIVO = "dolar.cambio_masivo"
    CAJA_ARQUEO = "caja.arqueo"
    CAJA_RETIRO = "caja.retiro"
    VENTA_DESCUENTO = "venta.descuento"
    VENTA_ANULAR = "venta.anular"
    STOCK_BAJA = "stock.baja"
    STOCK_AUDITORIA = "stock.auditoria"
    STOCK_MOTIVOS_BAJA = "stock.motivos_baja"
    PROMOCIONES = "configuracion.promociones"


ACCIONES = ("ver", "crear", "editar", "eliminar")

ROL_ADMIN = "admin"
ROL_SUPERVISOR = "supervisor"
ROL_VENDEDOR = "vendedor"
ROLES_SISTEMA = (ROL_ADMIN, ROL_SUPERVISOR, ROL_VENDEDOR)

LABEL_MODULO = {
    Modulo.CLIENTES: "Clientes",
    Modulo.PROVEEDORES: "Proveedores",
    Modulo.PRODUCTOS: "Productos",
    Modulo.STOCK: "Stock",
    Modulo.VENTAS: "Ventas",
    Modulo.CAJA: "Caja",
    Modulo.CONFIGURACION: "Configuración",
    Modulo.USUARIOS: "Usuarios",
    Modulo.AUDITORIA: "Auditoría",
    Modulo.IMPORTACION: "Importación",
    Modulo.REPORTES: "Reportes",
}

LABEL_RECURSO = {
    Recurso.DOLAR_CAMBIO_MASIVO: "Cambio masivo del dólar",
    Recurso.CAJA_ARQUEO: "Arqueo y cierre de turno",
    Recurso.CAJA_RETIRO: "Retiros de efectivo",
    Recurso.VENTA_DESCUENTO: "Descuentos en ventas",
    Recurso.VENTA_ANULAR: "Anulación de ventas",
    Recurso.STOCK_BAJA: "Bajas de stock",
    Recurso.STOCK_AUDITORIA: "Conteos de inventario",
    Recurso.STOCK_MOTIVOS_BAJA: "Motivos de baja",
    Recurso.PROMOCIONES: "Promociones",
}

# A qué módulo cuelga cada recurso (define el árbol de permisos).
MODULO_DE_RECURSO = {
    Recurso.DOLAR_CAMBIO_MASIVO: Modulo.PROVEEDORES,
    Recurso.CAJA_ARQUEO: Modulo.CAJA,
    Recurso.CAJA_RETIRO: Modulo.CAJA,
    Recurso.VENTA_DESCUENTO: Modulo.VENTAS,
    Recurso.VENTA_ANULAR: Modulo.VENTAS,
    Recurso.STOCK_BAJA: Modulo.STOCK,
    Recurso.STOCK_AUDITORIA: Modulo.STOCK,
    Recurso.STOCK_MOTIVOS_BAJA: Modulo.STOCK,
    Recurso.PROMOCIONES: Modulo.CONFIGURACION,
}

# Acciones con sentido en cada recurso (el resto se muestra "—" y se guarda FALSE).
ACCIONES_DE_RECURSO = {
    Recurso.DOLAR_CAMBIO_MASIVO: ("editar",),
    Recurso.CAJA_ARQUEO: ("crear",),
    Recurso.CAJA_RETIRO: ("crear",),
    Recurso.VENTA_DESCUENTO: ("crear",),
    Recurso.VENTA_ANULAR: ("eliminar",),
    Recurso.STOCK_BAJA: ("crear",),
    Recurso.STOCK_AUDITORIA: ("crear",),
    Recurso.STOCK_MOTIVOS_BAJA: ("editar",),
    Recurso.PROMOCIONES: ("ver", "crear", "editar"),
}

# Módulos cuyo permiso general no admite las 4 acciones.
ACCIONES_DE_MODULO = {
    Modulo.AUDITORIA: ("ver",),
    Modulo.REPORTES: ("ver",),
    Modulo.IMPORTACION: ("crear",),
}

# Verbo de cada acción en las etiquetas de "Accesos permitidos".
VERBO_DE_ACCION = {"ver": "Consultar", "crear": "Registrar", "editar": "Modificar", "eliminar": "Realizar"}

# Casilleros de módulo completo del catálogo de accesos (el resto sale de los recursos).
ACCESOS_DE_MODULO = (
    (Modulo.CONFIGURACION, "ver", "Acceso a tablas y configuración"),
    (Modulo.USUARIOS, "crear", "Crear usuarios"),
    (Modulo.AUDITORIA, "ver", "Consultar la auditoría"),
    (Modulo.IMPORTACION, "crear", "Importar datos desde Excel"),
    (Modulo.REPORTES, "ver", "Consultar reportes"),
)


def acciones_aplicables(modulo: Modulo, recurso: Recurso | None = None) -> tuple[str, ...]:
    if recurso is not None:
        return ACCIONES_DE_RECURSO[recurso]
    return ACCIONES_DE_MODULO.get(modulo, ACCIONES)


def recursos_de_modulo(modulo: Modulo) -> list[Recurso]:
    return [r for r in Recurso if MODULO_DE_RECURSO[r] is modulo]


def validar_destino(modulo: str, recurso: str | None) -> tuple[Modulo, Recurso | None]:
    """Convierte y valida (módulo, recurso). ValueError si no existen o el
    recurso no pertenece al módulo."""
    try:
        modulo_enum = Modulo(modulo)
        recurso_enum = Recurso(recurso) if recurso else None
    except ValueError as exc:
        raise ValueError(f"Módulo o recurso desconocido: {modulo}/{recurso}") from exc
    if recurso_enum is not None and MODULO_DE_RECURSO[recurso_enum] is not modulo_enum:
        raise ValueError(f"El recurso '{recurso}' no pertenece al módulo '{modulo}'")
    return modulo_enum, recurso_enum


@dataclass(frozen=True)
class Acceso:
    """Un casillero de "Accesos permitidos" = una acción sobre módulo o recurso."""

    clave: str
    modulo: Modulo
    recurso: Recurso | None
    accion: str
    label: str


def clave_acceso(modulo: Modulo, recurso: Recurso | None, accion: str) -> str:
    return f"{modulo.value}:{recurso.value if recurso else ''}:{accion}"


def _minuscula_inicial(texto: str) -> str:
    return texto[:1].lower() + texto[1:]


def catalogo_accesos() -> list[Acceso]:
    accesos = [
        Acceso(clave_acceso(modulo, None, accion), modulo, None, accion, label)
        for modulo, accion, label in ACCESOS_DE_MODULO
    ]
    for recurso in Recurso:
        modulo = MODULO_DE_RECURSO[recurso]
        for accion in ACCIONES_DE_RECURSO[recurso]:
            label = f"{VERBO_DE_ACCION[accion]}: {_minuscula_inicial(LABEL_RECURSO[recurso])}"
            accesos.append(Acceso(clave_acceso(modulo, recurso, accion), modulo, recurso, accion, label))
    return accesos


def acceso_por_clave(clave: str) -> Acceso | None:
    return next((a for a in catalogo_accesos() if a.clave == clave), None)
