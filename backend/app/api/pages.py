"""Rutas HTML (Jinja2). Fuera del esquema OpenAPI.

Toda página exige sesión (salvo login y recuperación de contraseña). La
visibilidad de ítems del sidebar, tarjetas de hubs y páginas usa la MISMA
barrera que la API (resolver_permiso). Las páginas solo arman el layout y el
contexto; los datos se cargan desde la API con Alpine.
"""
from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errores import NoEncontrado, SinPermiso
from app.core.permisos import Modulo, Recurso, ROL_ADMIN
from app.core.seguridad import resolver_permiso, token_de_request, usuario_de_token
from app.core.templates import templates
from app.core.utils import ahora_db
from app.models import NIVEL_MAXIMO, CondicionIva, EstadoTurno, TemporadaProducto, Usuario
from app.services import auditoria_inventario as servicio_auditorias
from app.services import descuentos as servicio_descuentos
from app.services import proveedores as servicio_proveedores
from app.services import roles as servicio_roles
from app.services import turnos as servicio_turnos
from app.services import usuarios as servicio_usuarios
from app.services import ventas as servicio_ventas
from app.services.auth import TokenInvalido
from app.services.configuracion import obtener_configuracion
from config import settings

router = APIRouter(include_in_schema=False)

# Tarjetas del hub Configuraciones (cada sesión agrega la suya).
SECCION_PROVEEDORES = {
    "nombre": "Proveedores", "descripcion": "Datos de proveedores nacionales e internacionales",
    "url": "/proveedores", "modulo": Modulo.PROVEEDORES,
}
SECCION_USUARIOS = {
    "nombre": "Usuarios", "descripcion": "Altas, permisos e historial de accesos",
    "url": "/usuarios", "modulo": Modulo.USUARIOS,
}
SECCION_ROLES = {
    "nombre": "Roles", "descripcion": "Perfiles de permisos y su alcance por módulo",
    "url": "/roles", "solo_admin": True,
}
CONFIGURACION_SECCIONES: list[dict] = [SECCION_PROVEEDORES, SECCION_USUARIOS, SECCION_ROLES]

# Catálogos de ventas en el hub Configuraciones (sesión 06).
_CATALOGOS_VENTAS = [
    {"nombre": "Medios de pago", "descripcion": "Formas de cobro y planes de cuotas", "url": "/medios-de-pago",
     "modulo": Modulo.CONFIGURACION, "plantilla": "pages/medios_pago/listado.html"},
    {"nombre": "Motivos de descuento", "descripcion": "Por qué se descuenta al vender y cuánto se sugiere",
     "url": "/motivos-descuento", "modulo": Modulo.CONFIGURACION,
     "plantilla": "pages/motivos_descuento/listado.html",
     # % sugerido del formulario: NO se pide a /ventas/opciones-descuento
     # porque exige VENTAS ver (un permiso que esta pantalla no requiere).
     "contexto_extra": lambda db: {"porcentajes_descuento": servicio_descuentos.porcentajes_validos(db)}},
    {"nombre": "Promociones", "descripcion": "2x1, 3x2 y descuentos por porcentaje", "url": "/promociones",
     "modulo": Modulo.CONFIGURACION, "recurso": Recurso.PROMOCIONES,
     "plantilla": "pages/promociones/listado.html"},
]
CONFIGURACION_SECCIONES.extend(_CATALOGOS_VENTAS)
# Las rutas de _CATALOGOS_VENTAS se registran más abajo, con _registrar_catalogo:
# necesitan requiere_pagina/contexto_base/_pagina, definidas después en este archivo.

# Página propia sin tarjeta en el hub: se entra desde el listado de proveedores.
PAGINA_DOLAR_MASIVO = {
    "nombre": "Cambio masivo del dólar", "url": "/proveedores/dolar-masivo",
    "modulo": Modulo.PROVEEDORES, "accion": "editar", "recurso": Recurso.DOLAR_CAMBIO_MASIVO,
}

# Ítem del sidebar del módulo de productos.
PAGINA_PRODUCTOS = {"nombre": "Productos", "url": "/productos", "icono": "productos", "modulo": Modulo.PRODUCTOS}
# Textos de las temporadas: ÚNICA definición (la usan el select del formulario
# y, vía productosListado, el filtro y la ficha del listado).
TEMPORADAS = [
    (TemporadaProducto.ATEMPORAL.value, "Atemporal"),
    (TemporadaProducto.OTONO_INVIERNO.value, "Otoño-Invierno"),
    (TemporadaProducto.PRIMAVERA_VERANO.value, "Primavera-Verano"),
]

# Ítem del sidebar del módulo de stock: hub "Gestión de Stock".
PAGINA_STOCK_HUB = {"nombre": "Gestión de Stock", "url": "/gestion-de-stock", "icono": "stock", "modulo": Modulo.STOCK}
# Tarjetas del hub de stock (solo piden STOCK ver; qué se puede hacer adentro
# de cada pantalla lo resuelven los flags puntuales de _contexto_stock).
SECCION_STOCK = {
    "nombre": "Stock", "descripcion": "Lo que hay de cada producto, ingresos, mínimos y bajas",
    "url": "/stock", "modulo": Modulo.STOCK,
}
SECCION_AUDITORIAS = {
    "nombre": "Auditorías de Stock", "descripcion": "Conteos de inventario y sus diferencias",
    "url": "/auditorias-inventario", "modulo": Modulo.STOCK,
}
SECCIONES_STOCK: list[dict] = [SECCION_STOCK, SECCION_AUDITORIAS]
# Página propia sin tarjeta en el hub: se entra desde el listado de stock.
PAGINA_MOTIVOS_BAJA = {
    "nombre": "Motivos de baja", "url": "/motivos-baja",
    "modulo": Modulo.STOCK, "accion": "editar", "recurso": Recurso.STOCK_MOTIVOS_BAJA,
}

# Ítem del sidebar del módulo de clientes (sesión 06).
PAGINA_CLIENTES = {"nombre": "Clientes", "url": "/clientes", "icono": "clientes", "modulo": Modulo.CLIENTES}
# Textos de condición de IVA: ÚNICA definición (select del formulario y filtro del listado).
CONDICIONES_IVA = [
    (CondicionIva.CONSUMIDOR_FINAL.value, "Consumidor final"),
    (CondicionIva.RESPONSABLE_INSCRIPTO.value, "Responsable inscripto"),
    (CondicionIva.MONOTRIBUTISTA.value, "Monotributista"),
    (CondicionIva.EXENTO.value, "Exento"),
]

# Ítem del sidebar del módulo de ventas (sesión 06): hub "Ventas".
PAGINA_VENTAS_HUB = {"nombre": "Ventas", "url": "/ventas", "icono": "ventas", "modulo": Modulo.VENTAS}
# Tarjetas del hub de ventas (`title` = el texto explicativo de cada una).
SECCION_NUEVA_VENTA = {
    "nombre": "Nueva venta", "descripcion": "Cargar productos, aplicar descuentos y cobrar",
    "title": "Cargar productos, aplicar descuentos y cobrar",
    "url": "/ventas/nueva", "modulo": Modulo.VENTAS, "accion": "crear",
}
SECCION_RESUMEN_VENTAS = {
    "nombre": "Resumen de Ventas", "descripcion": "Ventas del período con subtotal, descuento, total y medio de pago",
    "title": "Ventas del período con subtotal, descuento, total y medio de pago",
    "url": "/ventas/resumen-ventas", "modulo": Modulo.VENTAS,
}
SECCIONES_VENTAS: list[dict] = [SECCION_NUEVA_VENTA, SECCION_RESUMEN_VENTAS]

# Ítem del sidebar del módulo de caja (sesión 07).
PAGINA_CAJA = {"nombre": "Caja", "url": "/caja", "icono": "caja", "modulo": Modulo.CAJA}
# Página propia sin tarjeta en el hub: se entra desde /caja ("Cerrar turno").
PAGINA_CERRAR_TURNO = {**PAGINA_CAJA, "accion": "crear", "recurso": Recurso.CAJA_ARQUEO}

# Sidebar: nombre, url, icono y, opcionalmente, oculto / solo_admin /
# hub_configuracion / modulo (+ accion, recurso). Cada módulo suma su ítem
# ANTES de "Configuraciones".
MENU_SIDEBAR: list[dict] = [
    {"nombre": "Inicio", "url": "/", "icono": "inicio"},
    PAGINA_PRODUCTOS,
    PAGINA_STOCK_HUB,
    PAGINA_VENTAS_HUB,
    PAGINA_CLIENTES,
    PAGINA_CAJA,
    {"nombre": "Configuraciones", "url": "/configuracion", "icono": "configuracion", "hub_configuracion": True},
    # Sin pantalla HTML de auditoría: el ítem existe pero está oculto.
    {"nombre": "Auditoría", "url": "/auditoria", "icono": "auditoria", "oculto": True},
]
MENU_SIDEBAR_PIE: list[dict] = [
    {"nombre": "Ajustes", "url": "/ajustes", "icono": "ajustes"},
]


class Redireccion(Exception):
    """Corta la página y redirige (303)."""

    def __init__(self, url: str):
        self.url = url


class PaginaSinPermiso(Exception):
    """Página 403. Lleva el contexto ya armado (la sesión de DB puede estar cerrada al renderizar)."""

    def __init__(self, contexto: dict):
        self.contexto = contexto


class PaginaNoEncontrada(Exception):
    """Página 404 con el layout (no el JSON de la API). Lleva el contexto ya armado."""

    def __init__(self, contexto: dict):
        self.contexto = contexto


def registrar_manejadores_paginas(app: FastAPI) -> None:
    async def _redirigir(_request: Request, exc: Redireccion):
        return RedirectResponse(exc.url, status_code=303)

    async def _sin_permiso(request: Request, exc: PaginaSinPermiso):
        return templates.TemplateResponse(request, "pages/sin_permiso.html", exc.contexto, status_code=403)

    async def _no_encontrado(request: Request, exc: PaginaNoEncontrada):
        return templates.TemplateResponse(request, "pages/no_encontrado.html", exc.contexto, status_code=404)

    app.add_exception_handler(Redireccion, _redirigir)
    app.add_exception_handler(PaginaSinPermiso, _sin_permiso)
    app.add_exception_handler(PaginaNoEncontrada, _no_encontrado)


def usuario_de_pagina(request: Request, db: Session) -> Usuario | None:
    try:
        return usuario_de_token(db, token_de_request(request))
    except TokenInvalido:
        return None


def requiere_sesion(request: Request, db: Session = Depends(get_db)) -> Usuario:
    usuario = usuario_de_pagina(request, db)
    if usuario is None:
        raise Redireccion("/login")
    if usuario.debe_cambiar_password:
        raise Redireccion("/cambiar-password")
    return usuario


def _visible(item: dict, usuario: Usuario, db: Session) -> bool:
    """Regla única de visibilidad para ítems del sidebar, tarjetas y páginas."""
    if item.get("oculto"):
        return False
    if item.get("solo_admin") and not usuario.es_admin:
        return False
    if item.get("hub_configuracion"):
        return any(_visible(seccion, usuario, db) for seccion in CONFIGURACION_SECCIONES)
    if item.get("modulo") is not None:
        return resolver_permiso(db, usuario.id, item["modulo"], item.get("accion", "ver"), item.get("recurso"))
    return True


def menu_visible(items: list[dict], usuario: Usuario, db: Session) -> list[dict]:
    return [item for item in items if _visible(item, usuario, db)]


def contexto_base(request: Request, db: Session, actual: str, usuario: Usuario, **extra) -> dict:
    """Contexto común de todas las páginas con sesión."""
    return {
        "request": request,
        "menu": menu_visible(MENU_SIDEBAR, usuario, db),
        "menu_pie": menu_visible(MENU_SIDEBAR_PIE, usuario, db),
        "actual": actual,
        "usuario_actual": usuario,
        "es_admin": usuario.es_admin,
        "inactividad_minutos": settings.SESION_INACTIVIDAD_MINUTOS,
        **extra,
    }


def requiere_pagina(item: dict, actual: str = "/configuracion"):
    """Dependency: sesión + visibilidad del ítem; si no, página 403."""

    def dependencia(request: Request, db: Session = Depends(get_db),
                    usuario: Usuario = Depends(requiere_sesion)) -> Usuario:
        if not _visible(item, usuario, db):
            raise PaginaSinPermiso(contexto_base(request, db, actual, usuario))
        return usuario

    return dependencia


def _contexto_stock(request: Request, db: Session, usuario: Usuario, **extra) -> dict:
    """Contexto común a las páginas del módulo de stock: mismos permisos
    puntuales que exige la API (app/api/v1/stock.py), para mostrar/ocultar
    acciones sin depender de que el backend las rechace. `actual` siempre
    apunta al hub: todas las pantallas del módulo resaltan "Gestión de Stock"
    en el sidebar."""
    return contexto_base(
        request, db, "/gestion-de-stock", usuario,
        puede_ingresar=resolver_permiso(db, usuario.id, Modulo.STOCK, "crear"),
        puede_minimos=resolver_permiso(db, usuario.id, Modulo.STOCK, "editar"),
        puede_baja=resolver_permiso(db, usuario.id, Modulo.STOCK, "crear", Recurso.STOCK_BAJA),
        puede_motivos=resolver_permiso(db, usuario.id, Modulo.STOCK, "editar", Recurso.STOCK_MOTIVOS_BAJA),
        puede_auditar=resolver_permiso(db, usuario.id, Modulo.STOCK, "crear", Recurso.STOCK_AUDITORIA),
        **extra,
    )


def _o_no_encontrado(request: Request, db: Session, usuario: Usuario, funcion, *args, actual: str = "/configuracion"):
    """Llama a un obtener_* del servicio; si levanta NoEncontrado, página 404
    HTML. `actual`: qué ítem del sidebar queda resaltado (por defecto,
    Configuraciones; las pantallas de otros módulos pasan el suyo)."""
    try:
        return funcion(db, *args)
    except NoEncontrado:
        raise PaginaNoEncontrada(contexto_base(request, db, actual, usuario))


def _pagina(request: Request, plantilla: str, contexto: dict):
    return templates.TemplateResponse(request, plantilla, contexto)


@router.get("/")
def inicio(request: Request, db: Session = Depends(get_db), usuario: Usuario = Depends(requiere_sesion)):
    return _pagina(request, "pages/index.html", contexto_base(request, db, "/", usuario))


@router.get("/ajustes")
def ajustes(request: Request, db: Session = Depends(get_db), usuario: Usuario = Depends(requiere_sesion)):
    return _pagina(request, "pages/pendiente.html", contexto_base(request, db, "/ajustes", usuario, titulo="Ajustes"))


@router.get("/configuracion")
def configuracion(request: Request, db: Session = Depends(get_db), usuario: Usuario = Depends(requiere_sesion)):
    secciones = menu_visible(CONFIGURACION_SECCIONES, usuario, db)
    return _pagina(request, "pages/configuracion/index.html",
                   contexto_base(request, db, "/configuracion", usuario, secciones=secciones))


def _registrar_catalogo(seccion: dict) -> None:
    """Registra la ruta GET de un catálogo de `_CATALOGOS_VENTAS`: mismo
    contexto (puede_ver/crear/editar) para los tres, más lo puntual de cada
    uno vía `contexto_extra`."""
    def pagina(request: Request, db: Session = Depends(get_db),
               usuario: Usuario = Depends(requiere_pagina(seccion))):
        extra = seccion["contexto_extra"](db) if "contexto_extra" in seccion else {}
        return _pagina(request, seccion["plantilla"], contexto_base(
            request, db, "/configuracion", usuario,
            puede_editar=resolver_permiso(db, usuario.id, seccion["modulo"], "editar", seccion.get("recurso")),
            puede_crear=resolver_permiso(db, usuario.id, seccion["modulo"],
                                         "crear" if seccion.get("recurso") else "editar", seccion.get("recurso")),
            **extra,
        ))
    router.add_api_route(seccion["url"], pagina, methods=["GET"])


for _seccion in _CATALOGOS_VENTAS:
    _registrar_catalogo(_seccion)


@router.get("/login")
def login(request: Request, db: Session = Depends(get_db)):
    if usuario_de_pagina(request, db) is not None:
        return RedirectResponse("/", status_code=303)
    return _pagina(request, "auth/login.html", {"request": request})


@router.get("/cambiar-password")
def cambiar_password(request: Request, db: Session = Depends(get_db)):
    usuario = usuario_de_pagina(request, db)
    if usuario is None:
        return RedirectResponse("/login", status_code=303)
    return _pagina(request, "auth/cambiar_password.html",
                   {"request": request, "obligatorio": usuario.debe_cambiar_password})


@router.get("/reset-password")
def reset_password(request: Request, token: str = ""):
    respuesta = _pagina(request, "auth/reset_password.html", {"request": request, "token": token})
    # El token viaja en la URL: que no se filtre a los CDN por el Referer.
    respuesta.headers["Referrer-Policy"] = "no-referrer"
    return respuesta


@router.get("/proveedores")
def proveedores(request: Request, db: Session = Depends(get_db),
                usuario: Usuario = Depends(requiere_pagina(SECCION_PROVEEDORES))):
    return _pagina(request, "pages/proveedores/listado.html", contexto_base(
        request, db, "/configuracion", usuario,
        usa_dolar=servicio_proveedores.hay_proveedores_en_dolares(db),
        puede_crear=resolver_permiso(db, usuario.id, Modulo.PROVEEDORES, "crear"),
        puede_editar=resolver_permiso(db, usuario.id, Modulo.PROVEEDORES, "editar"),
        puede_masivo=_visible(PAGINA_DOLAR_MASIVO, usuario, db),
    ))


@router.get("/proveedores/dolar-masivo")
def dolar_masivo(request: Request, db: Session = Depends(get_db),
                 usuario: Usuario = Depends(requiere_pagina(PAGINA_DOLAR_MASIVO))):
    return _pagina(request, "pages/proveedores/dolar_masivo.html", contexto_base(
        request, db, "/configuracion", usuario, usa_dolar=servicio_proveedores.hay_proveedores_en_dolares(db),
        # Con solo el permiso puntual del masivo, /proveedores da 403: el "volver" va al hub.
        puede_ver=_visible(SECCION_PROVEEDORES, usuario, db),
    ))


@router.get("/productos")
def productos(request: Request, db: Session = Depends(get_db),
              usuario: Usuario = Depends(requiere_pagina(PAGINA_PRODUCTOS, actual="/productos"))):
    config = obtener_configuracion(db)
    return _pagina(request, "pages/productos/listado.html", contexto_base(
        request, db, "/productos", usuario,
        puede_crear=resolver_permiso(db, usuario.id, Modulo.PRODUCTOS, "crear"),
        puede_editar=resolver_permiso(db, usuario.id, Modulo.PRODUCTOS, "editar"),
        # Gatea el link "Ver en Stock" de la ficha: sin STOCK ver, /stock da 403.
        puede_ver_stock=resolver_permiso(db, usuario.id, Modulo.STOCK, "ver"),
        # Gatea el campo "Stock inicial" del alta: cargarlo es, en los
        # hechos, un ingreso de stock (mismo permiso que services.stock).
        puede_stock_inicial=resolver_permiso(db, usuario.id, Modulo.STOCK, "crear"),
        nivel_maximo=NIVEL_MAXIMO, margen_default=str(config.margen_default),
        descuento_maximo=str(config.descuento_maximo), temporadas=TEMPORADAS,
    ))


@router.get("/categorias")
def categorias(request: Request, db: Session = Depends(get_db),
               usuario: Usuario = Depends(requiere_pagina(PAGINA_PRODUCTOS, actual="/productos"))):
    return _pagina(request, "pages/categorias/arbol.html", contexto_base(
        request, db, "/productos", usuario,
        puede_crear=resolver_permiso(db, usuario.id, Modulo.PRODUCTOS, "crear"),
        puede_editar=resolver_permiso(db, usuario.id, Modulo.PRODUCTOS, "editar"),
        puede_eliminar=resolver_permiso(db, usuario.id, Modulo.PRODUCTOS, "eliminar"),
        nivel_maximo=NIVEL_MAXIMO,
    ))


@router.get("/gestion-de-stock")
def gestion_de_stock(request: Request, db: Session = Depends(get_db),
                     usuario: Usuario = Depends(requiere_pagina(PAGINA_STOCK_HUB, actual="/gestion-de-stock"))):
    secciones = menu_visible(SECCIONES_STOCK, usuario, db)
    return _pagina(request, "pages/stock/hub.html", _contexto_stock(request, db, usuario, secciones=secciones))


@router.get("/stock")
def stock(request: Request, db: Session = Depends(get_db),
         usuario: Usuario = Depends(requiere_pagina(SECCION_STOCK, actual="/gestion-de-stock"))):
    return _pagina(request, "pages/stock/listado.html", _contexto_stock(request, db, usuario))


@router.get("/motivos-baja")
def motivos_baja(request: Request, db: Session = Depends(get_db),
                 usuario: Usuario = Depends(requiere_pagina(PAGINA_MOTIVOS_BAJA, actual="/gestion-de-stock"))):
    # PAGINA_MOTIVOS_BAJA solo exige el recurso puntual (STOCK editar sobre
    # stock.motivos_baja): a diferencia del cambio masivo del dólar, acá
    # además hace falta poder VER stock (es una pantalla de stock, no una
    # herramienta aislada), así que se chequea a mano.
    if not resolver_permiso(db, usuario.id, Modulo.STOCK, "ver"):
        raise PaginaSinPermiso(contexto_base(request, db, "/gestion-de-stock", usuario))
    return _pagina(request, "pages/motivos_baja/listado.html", contexto_base(
        request, db, "/gestion-de-stock", usuario,
    ))


@router.get("/auditorias-inventario")
def auditorias_inventario(request: Request, db: Session = Depends(get_db),
                          usuario: Usuario = Depends(requiere_pagina(SECCION_AUDITORIAS, actual="/gestion-de-stock"))):
    return _pagina(request, "pages/auditorias/listado.html", _contexto_stock(request, db, usuario))


@router.get("/auditorias-inventario/{auditoria_id}")
def auditoria_conteo(auditoria_id: int, request: Request, db: Session = Depends(get_db),
                     usuario: Usuario = Depends(requiere_pagina(SECCION_AUDITORIAS, actual="/gestion-de-stock"))):
    _o_no_encontrado(request, db, usuario, servicio_auditorias.obtener_auditoria, auditoria_id,
                     actual="/gestion-de-stock")
    return _pagina(request, "pages/auditorias/conteo.html",
                   _contexto_stock(request, db, usuario, auditoria_id=auditoria_id))


@router.get("/usuarios")
def usuarios(request: Request, db: Session = Depends(get_db),
            usuario: Usuario = Depends(requiere_pagina(SECCION_USUARIOS))):
    if usuario.es_admin:
        roles_filtro = [{"id": r.id, "nombre": r.nombre} for r, _ in servicio_roles.listar_roles(db)]
        roles_gestionables = None  # el Admin gestiona a todos
    else:
        roles_filtro = [{"id": r.id, "nombre": r.nombre} for r in servicio_usuarios.roles_asignables(db, usuario)]
        roles_gestionables = [r["nombre"] for r in roles_filtro]  # misma regla que validar_puede_gestionar
    return _pagina(request, "pages/usuarios/listado.html", contexto_base(
        request, db, "/configuracion", usuario,
        roles_filtro=roles_filtro,
        roles_gestionables=roles_gestionables,
        puede_crear=resolver_permiso(db, usuario.id, Modulo.USUARIOS, "crear"),
        puede_editar=resolver_permiso(db, usuario.id, Modulo.USUARIOS, "editar"),
    ))


@router.get("/roles")
def roles(request: Request, db: Session = Depends(get_db),
          usuario: Usuario = Depends(requiere_pagina(SECCION_ROLES))):
    return _pagina(request, "pages/roles/listado.html", contexto_base(request, db, "/configuracion", usuario))


@router.get("/roles/{rol_id}/permisos")
def permisos_de_rol(rol_id: int, request: Request, db: Session = Depends(get_db),
                    usuario: Usuario = Depends(requiere_pagina(SECCION_ROLES))):
    rol = _o_no_encontrado(request, db, usuario, servicio_roles.obtener_rol, rol_id)
    return _pagina(request, "pages/roles/permisos.html", contexto_base(
        request, db, "/configuracion", usuario, rol=rol, editable=rol.nombre != ROL_ADMIN,
    ))


@router.get("/usuarios/{usuario_id}/permisos")
def permisos_de_usuario(usuario_id: int, request: Request, db: Session = Depends(get_db),
                        usuario: Usuario = Depends(requiere_pagina(SECCION_USUARIOS))):
    objetivo = _o_no_encontrado(request, db, usuario, servicio_usuarios.obtener_usuario, usuario_id)
    editable = resolver_permiso(db, usuario.id, Modulo.USUARIOS, "editar")
    if editable:
        try:
            servicio_usuarios.validar_puede_gestionar(usuario, objetivo.rol, objetivo)
        except SinPermiso:
            editable = False
    return _pagina(request, "pages/usuarios/permisos.html", contexto_base(
        request, db, "/configuracion", usuario, objetivo=objetivo, editable=editable,
    ))


@router.get("/usuarios/{usuario_id}/historial")
def historial_de_usuario(usuario_id: int, request: Request, db: Session = Depends(get_db),
                         usuario: Usuario = Depends(requiere_pagina(SECCION_USUARIOS))):
    objetivo = _o_no_encontrado(request, db, usuario, servicio_usuarios.obtener_usuario, usuario_id)
    return _pagina(request, "pages/usuarios/historial.html",
                   contexto_base(request, db, "/configuracion", usuario, objetivo=objetivo))


# --- Clientes (sesión 06) ------------------------------------------------------

@router.get("/clientes")
def clientes(request: Request, db: Session = Depends(get_db),
            usuario: Usuario = Depends(requiere_pagina(PAGINA_CLIENTES, actual="/clientes"))):
    return _pagina(request, "pages/clientes/listado.html", contexto_base(
        request, db, "/clientes", usuario,
        puede_crear=resolver_permiso(db, usuario.id, Modulo.CLIENTES, "crear"),
        puede_editar=resolver_permiso(db, usuario.id, Modulo.CLIENTES, "editar"),
        # Gatea el select + "Asignar" de la ficha: sin este permiso no se pide
        # /configuracion/promociones (para no disparar toasts de 403).
        puede_ver_promociones=resolver_permiso(db, usuario.id, Modulo.CONFIGURACION, "ver", Recurso.PROMOCIONES),
        condiciones_iva=CONDICIONES_IVA,
    ))


# --- Ventas (sesión 06) ----------------------------------------------------------

def _contexto_ventas(request: Request, db: Session, usuario: Usuario, **extra) -> dict:
    """Contexto común a las páginas del módulo de ventas: mismos permisos
    puntuales que exige la API (app/api/v1/ventas.py y clientes.py), para
    mostrar/ocultar acciones sin depender de que el backend las rechace.
    `actual` siempre apunta al hub: todas resaltan "Ventas" en el sidebar."""
    return contexto_base(
        request, db, "/ventas", usuario,
        puede_vender=resolver_permiso(db, usuario.id, Modulo.VENTAS, "crear"),
        puede_descontar=resolver_permiso(db, usuario.id, Modulo.VENTAS, "crear", Recurso.VENTA_DESCUENTO),
        puede_anular=(resolver_permiso(db, usuario.id, Modulo.VENTAS, "ver")
                      and resolver_permiso(db, usuario.id, Modulo.VENTAS, "eliminar", Recurso.VENTA_ANULAR)),
        puede_crear_cliente=resolver_permiso(db, usuario.id, Modulo.CLIENTES, "crear"),
        puede_ver_clientes=resolver_permiso(db, usuario.id, Modulo.CLIENTES, "ver"),
        condiciones_iva=CONDICIONES_IVA,
        **extra,
    )


@router.get("/ventas")
def ventas_hub(request: Request, db: Session = Depends(get_db),
               usuario: Usuario = Depends(requiere_pagina(PAGINA_VENTAS_HUB, actual="/ventas"))):
    secciones = menu_visible(SECCIONES_VENTAS, usuario, db)
    en_curso = servicio_ventas.venta_en_curso(db, usuario)
    if en_curso is not None:
        # Copia: la constante la comparten el sidebar y la página.
        secciones = [{**s, "nombre": f"Continuar venta {en_curso.numero}"} if s is SECCION_NUEVA_VENTA else s
                     for s in secciones]
    return _pagina(request, "pages/ventas/hub.html", _contexto_ventas(request, db, usuario, secciones=secciones))


def _hay_turno_para_operar(db) -> bool:
    """Mismo criterio que services.turnos.turno_para_operar (sin bloquear ni sumar)."""
    turno = servicio_turnos.obtener_turno_activo(db)
    return turno is not None and not servicio_turnos.es_de_dia_anterior(turno)


@router.get("/ventas/nueva")
def venta_nueva(request: Request, db: Session = Depends(get_db),
                usuario: Usuario = Depends(requiere_pagina(SECCION_NUEVA_VENTA, actual="/ventas"))):
    # La venta en curso (si hay) la retoma la pantalla con GET /ventas/en-curso.
    return _pagina(request, "pages/ventas/nueva.html", _contexto_ventas(
        request, db, usuario,
        hay_turno=_hay_turno_para_operar(db),
    ))


@router.get("/ventas/resumen-ventas")
def resumen_ventas(request: Request, cliente_id: int | None = None, db: Session = Depends(get_db),
                   usuario: Usuario = Depends(requiere_pagina(SECCION_RESUMEN_VENTAS, actual="/ventas"))):
    # `cliente_id` es un enlace desde la ficha del cliente (chip quitable en
    # la pantalla), no un filtro que la pantalla persista entre visitas.
    return _pagina(request, "pages/ventas/listado.html", _contexto_ventas(
        request, db, usuario,
        cliente_id_inicial=cliente_id,
        hoy_iso=ahora_db().date().isoformat(),
    ))


# --- Caja (sesión 07) ------------------------------------------------------------

@router.get("/caja")
def caja(request: Request, db: Session = Depends(get_db),
         usuario: Usuario = Depends(requiere_pagina(PAGINA_CAJA, actual="/caja"))):
    return _pagina(request, "pages/caja/index.html", contexto_base(
        request, db, "/caja", usuario,
        puede_retirar=resolver_permiso(db, usuario.id, Modulo.CAJA, "crear", Recurso.CAJA_RETIRO),
        puede_arquear=resolver_permiso(db, usuario.id, Modulo.CAJA, "crear", Recurso.CAJA_ARQUEO),
    ))


@router.get("/caja/cerrar/{turno_id}")
def cerrar_turno(turno_id: int, request: Request, db: Session = Depends(get_db),
                 usuario: Usuario = Depends(requiere_pagina(PAGINA_CERRAR_TURNO, actual="/caja"))):
    turno = _o_no_encontrado(request, db, usuario, servicio_turnos.obtener_turno, turno_id, actual="/caja")
    if turno.estado is not EstadoTurno.ABIERTO:
        raise Redireccion("/caja")
    return _pagina(request, "pages/caja/cerrar_turno.html", contexto_base(request, db, "/caja", usuario,
                                                                         turno_id=turno.id))
