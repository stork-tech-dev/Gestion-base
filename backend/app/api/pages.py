"""Rutas HTML (Jinja2). Fuera del esquema OpenAPI.

El sidebar se define acá y se filtra con _visible(); la sesión 02 agrega la
sesión obligatoria y los permisos, y cada módulo suma su ítem.
"""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.templates import templates
from config import settings

router = APIRouter(include_in_schema=False)

# Ítems: nombre, url, icono y, opcionalmente, oculto / solo_admin /
# hub_configuracion / modulo / recurso (se evalúan en _visible).
MENU_SIDEBAR: list[dict] = [
    {"nombre": "Inicio", "url": "/", "icono": "inicio"},
    # Sin pantalla HTML de auditoría: el ítem existe pero está oculto.
    {"nombre": "Auditoría", "url": "/auditoria", "icono": "auditoria", "oculto": True},
]
MENU_SIDEBAR_PIE: list[dict] = [
    {"nombre": "Ajustes", "url": "/ajustes", "icono": "ajustes"},
]


def _visible(item: dict, usuario, db: Session) -> bool:
    """Regla única de visibilidad para ítems del sidebar y tarjetas de hubs."""
    return not item.get("oculto", False)


def menu_visible(items: list[dict], usuario, db: Session) -> list[dict]:
    return [item for item in items if _visible(item, usuario, db)]


def contexto_base(request: Request, db: Session, actual: str, **extra) -> dict:
    """Contexto común de todas las páginas."""
    usuario = None  # sesión 02: usuario autenticado
    return {
        "request": request,
        "menu": menu_visible(MENU_SIDEBAR, usuario, db),
        "menu_pie": menu_visible(MENU_SIDEBAR_PIE, usuario, db),
        "actual": actual,
        "usuario_actual": usuario,
        "es_admin": False,
        "inactividad_minutos": settings.SESION_INACTIVIDAD_MINUTOS,
        **extra,
    }


@router.get("/")
def inicio(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(request, "pages/index.html", contexto_base(request, db, "/"))


@router.get("/ajustes")
def ajustes(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        request, "pages/pendiente.html", contexto_base(request, db, "/ajustes", titulo="Ajustes")
    )
