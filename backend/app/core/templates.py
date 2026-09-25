"""Instancia única de Jinja2Templates y helpers globales de plantillas."""
import json
from pathlib import Path

from fastapi.templating import Jinja2Templates
from markupsafe import Markup, escape

from config import settings

APP_DIR = Path(__file__).resolve().parents[1]
STATIC_DIR = APP_DIR / "static"

templates = Jinja2Templates(directory=str(APP_DIR / "templates"))


def estatico(path: str) -> str:
    """URL de un archivo estático con ?v=<mtime> para romper la caché del navegador
    (StaticFiles no manda Cache-Control)."""
    relativo = path.lstrip("/")
    try:
        version = int((STATIC_DIR / relativo).stat().st_mtime)
    except OSError:
        return f"/static/{relativo}"
    return f"/static/{relativo}?v={version}"


def logo_url() -> str | None:
    """Logo del cliente si existe static/img/logo.svg; si no, se muestra APP_NAME."""
    return estatico("/img/logo.svg") if (STATIC_DIR / "img" / "logo.svg").is_file() else None


def js(valor) -> Markup:
    """Valor Python → literal JS seguro dentro de un atributo HTML (x-data, @click…)."""
    return Markup(escape(json.dumps(valor, ensure_ascii=False)))


templates.env.globals.update(
    APP_NAME=settings.APP_NAME,
    APP_ENV=settings.APP_ENV,
    estatico=estatico,
    logo_url=logo_url,
)
templates.env.filters["js"] = js
