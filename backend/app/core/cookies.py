"""Cookies de sesión: HttpOnly, SameSite=Lax, Secure según configuración."""
from config import settings


def _opciones() -> dict:
    return {"httponly": True, "samesite": "lax", "secure": settings.COOKIE_SECURE, "path": "/"}


def poner_cookie_access(response, token: str) -> None:
    response.set_cookie(settings.JWT_COOKIE_NAME, token, max_age=settings.JWT_ACCESS_TOKEN_MINUTES * 60, **_opciones())


def poner_cookies_sesion(response, access: str, refresh: str) -> None:
    poner_cookie_access(response, access)
    response.set_cookie(
        settings.JWT_REFRESH_COOKIE_NAME, refresh, max_age=settings.JWT_REFRESH_TOKEN_DAYS * 86400, **_opciones()
    )


def borrar_cookies_sesion(response) -> None:
    for nombre in (settings.JWT_COOKIE_NAME, settings.JWT_REFRESH_COOKIE_NAME):
        response.delete_cookie(nombre, **_opciones())
