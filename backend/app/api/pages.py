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
from app.core.permisos import Modulo
from app.core.seguridad import resolver_permiso, token_de_request, usuario_de_token
from app.core.templates import templates
from app.models import Usuario
from app.services import roles as servicio_roles
from app.services import usuarios as servicio_usuarios
from app.services.auth import TokenInvalido
from config import settings

router = APIRouter(include_in_schema=False)

# Tarjetas del hub Configuraciones (cada sesión agrega la suya).
SECCION_USUARIOS = {
    "nombre": "Usuarios", "descripcion": "Altas, permisos e historial de accesos",
    "url": "/usuarios", "modulo": Modulo.USUARIOS,
}
SECCION_ROLES = {
    "nombre": "Roles", "descripcion": "Perfiles de permisos y su alcance por módulo",
    "url": "/roles", "solo_admin": True,
}
CONFIGURACION_SECCIONES: list[dict] = [SECCION_USUARIOS, SECCION_ROLES]

# Sidebar: nombre, url, icono y, opcionalmente, oculto / solo_admin /
# hub_configuracion / modulo (+ accion, recurso). Cada módulo suma su ítem
# ANTES de "Configuraciones".
MENU_SIDEBAR: list[dict] = [
    {"nombre": "Inicio", "url": "/", "icono": "inicio"},
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


def registrar_manejadores_paginas(app: FastAPI) -> None:
    async def _redirigir(_request: Request, exc: Redireccion):
        return RedirectResponse(exc.url, status_code=303)

    async def _sin_permiso(request: Request, exc: PaginaSinPermiso):
        return templates.TemplateResponse(request, "pages/sin_permiso.html", exc.contexto, status_code=403)

    app.add_exception_handler(Redireccion, _redirigir)
    app.add_exception_handler(PaginaSinPermiso, _sin_permiso)


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


# (Las rutas de permisos e historial se agregan en las tareas siguientes,
# en este mismo archivo.)
