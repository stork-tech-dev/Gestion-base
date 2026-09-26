"""Sesión deslizante: renueva el access vencido usando la cookie de refresh y
corre la ventana de inactividad en cada request con access vigente (por
cookie o por header Bearer; a los clientes Bearer nunca se les tocan cookies).
Nunca levanta excepción: ante cualquier error deja pasar el request."""
import logging
from contextlib import contextmanager
from dataclasses import dataclass

from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.cookies import borrar_cookies_sesion, poner_cookie_access
from app.core.database import SessionLocal
from app.services import auth
from config import settings

log = logging.getLogger(__name__)

RUTAS_EXCLUIDAS = (
    "/api/v1/auth/login",
    "/api/v1/auth/refresh",
    "/static",
    "/uploads",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/favicon",
)


@contextmanager
def sesion_por_defecto():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@dataclass
class _Resultado:
    nuevo_access: str | None = None
    borrar_cookies: bool = False


def _access_vigente(token: str | None) -> bool:
    try:
        auth.verificar_token(token, "access")
    except auth.TokenInvalido:
        return False
    return True


def _bearer_de(request) -> str | None:
    autorizacion = request.headers.get("authorization", "")
    if autorizacion.lower().startswith("bearer "):
        return autorizacion[7:].strip()
    return None


def _registrar_actividad_bearer(abrir, token: str) -> _Resultado:
    """Clientes Bearer (API, apps): también corren la ventana de inactividad
    de su sesión, pero NUNCA se les tocan cookies. Si el token es inválido o
    la sesión cayó no se hace nada más: la dependency responde 401."""
    try:
        with abrir() as db:
            try:
                auth.registrar_actividad(db, auth.sesion_de_access(db, auth.verificar_token(token, "access")))
            except auth.TokenInvalido:
                pass
            db.commit()  # también conserva la marca de sesión revocada por inactividad
    except Exception:  # noqa: BLE001 - el middleware nunca rompe el request
        log.exception("Error en AuthRefreshMiddleware (Bearer)")
    return _Resultado()


class AuthRefreshMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if self._excluida(request):
            return await call_next(request)
        resultado = await run_in_threadpool(self._procesar, request)
        if resultado.nuevo_access:
            request.state.access_renovado = resultado.nuevo_access
        response = await call_next(request)
        tocadas = {c.split("=", 1)[0].strip() for c in response.headers.getlist("set-cookie")}
        if resultado.nuevo_access and settings.JWT_COOKIE_NAME not in tocadas:
            poner_cookie_access(response, resultado.nuevo_access)
        if resultado.borrar_cookies and settings.JWT_REFRESH_COOKIE_NAME not in tocadas:
            borrar_cookies_sesion(response)
        return response

    @staticmethod
    def _excluida(request) -> bool:
        return request.url.path.startswith(RUTAS_EXCLUIDAS)

    @staticmethod
    def _procesar(request) -> _Resultado:
        abrir = getattr(request.app.state, "abrir_sesion_db", sesion_por_defecto)
        bearer = _bearer_de(request)
        if bearer is not None:
            return _registrar_actividad_bearer(abrir, bearer)
        refresh = request.cookies.get(settings.JWT_REFRESH_COOKIE_NAME)
        if not refresh:
            return _Resultado()
        try:
            with abrir() as db:
                try:
                    if _access_vigente(request.cookies.get(settings.JWT_COOKIE_NAME)):
                        auth.registrar_actividad(db, auth.sesion_vigente(db, refresh))
                        db.commit()
                        return _Resultado()
                    nuevo = auth.refrescar_access_token(db, refresh)
                    db.commit()
                    return _Resultado(nuevo_access=nuevo)
                except auth.TokenInvalido:
                    db.commit()  # conserva la marca de sesión revocada
                    return _Resultado(borrar_cookies=True)
        except Exception:  # noqa: BLE001 - el middleware nunca rompe el request
            log.exception("Error en AuthRefreshMiddleware")
            return _Resultado()
