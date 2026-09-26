"""Barrera de acceso ÚNICA del sistema (resolver_permiso) y dependencies de FastAPI."""
from fastapi import Depends, Request
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errores import NoAutenticado, SinPermiso
from app.core.permisos import ACCIONES, ROL_ADMIN, Modulo, Recurso, validar_destino
from app.models import RolPermiso, Usuario, UsuarioPermiso
from app.services.auth import TokenInvalido, sesion_de_access, verificar_token
from config import settings

MENSAJE_CAMBIAR_PASSWORD = "Tenés que cambiar la contraseña antes de continuar."
MENSAJE_SESION_INVALIDA = "Sesión inválida o vencida. Volvé a ingresar."


def resolver_permiso(db, usuario_id: int, modulo, accion: str, recurso=None) -> bool:
    """¿El usuario puede `accion` sobre el módulo (o el recurso puntual)?

    1. Usuario inexistente o inactivo → False.  2. Rol admin → True.
    3. Rol inactivo → False.  4. OR de overrides del usuario y permisos del rol,
    mirando la fila general del módulo y, si se pidió, la del recurso exacto:
    el permiso general habilita cualquier recurso del módulo; un recurso
    puntual NO da acceso general.
    """
    if accion not in ACCIONES:
        raise ValueError(f"Acción desconocida: {accion}")
    modulo_enum, recurso_enum = validar_destino(
        Modulo(modulo).value, Recurso(recurso).value if recurso else None
    )
    usuario = db.get(Usuario, usuario_id)
    if usuario is None or not usuario.activo:
        return False
    if usuario.rol.nombre == ROL_ADMIN:
        return True
    if not usuario.rol.activo:
        return False

    columna = f"puede_{accion}"
    for modelo, del_duenio in (
        (UsuarioPermiso, UsuarioPermiso.usuario_id == usuario.id),
        (RolPermiso, RolPermiso.rol_id == usuario.rol_id),
    ):
        destino = (
            modelo.recurso.is_(None)
            if recurso_enum is None
            else or_(modelo.recurso.is_(None), modelo.recurso == recurso_enum.value)
        )
        fila = db.scalar(
            select(modelo.id)
            .where(del_duenio, modelo.modulo == modulo_enum.value, destino, getattr(modelo, columna).is_(True))
            .limit(1)
        )
        if fila is not None:
            return True
    return False


def token_de_request(request: Request) -> str | None:
    """Prioridad: header Bearer → access renovado por el middleware → cookie."""
    autorizacion = request.headers.get("authorization", "")
    if autorizacion.lower().startswith("bearer "):
        return autorizacion[7:].strip() or None
    renovado = getattr(request.state, "access_renovado", None)
    if renovado:
        return renovado
    return request.cookies.get(settings.JWT_COOKIE_NAME)


def usuario_de_token(db, token: str | None) -> Usuario:
    """Usuario activo dueño de un access token con sesión vigente (o TokenInvalido)."""
    datos = verificar_token(token, "access")
    sesion_de_access(db, datos)
    try:
        usuario = db.get(Usuario, int(datos["sub"]))
    except (TypeError, ValueError) as exc:
        raise TokenInvalido("Token con sujeto inválido") from exc
    if usuario is None or not usuario.activo:
        raise TokenInvalido("Usuario inexistente o inactivo")
    return usuario


def get_current_user(request: Request, db: Session = Depends(get_db)) -> Usuario:
    try:
        return usuario_de_token(db, token_de_request(request))
    except TokenInvalido as exc:
        raise NoAutenticado(MENSAJE_SESION_INVALIDA) from exc


def _exigir_password_al_dia(usuario: Usuario) -> None:
    """Corta con 403 si el usuario todavía tiene la contraseña provisoria
    (única verificación: la usan requiere_permiso y requiere_admin)."""
    if usuario.debe_cambiar_password:
        raise SinPermiso(MENSAJE_CAMBIAR_PASSWORD)


def requiere_permiso(modulo, accion: str, recurso=None):
    """Dependency: devuelve el usuario si tiene el permiso; si no, 403."""
    modulo_enum = Modulo(modulo)
    recurso_enum = Recurso(recurso) if recurso else None
    destino = f"{modulo_enum.value}/{recurso_enum.value}" if recurso_enum else modulo_enum.value

    def dependencia(usuario: Usuario = Depends(get_current_user), db: Session = Depends(get_db)) -> Usuario:
        _exigir_password_al_dia(usuario)
        if not resolver_permiso(db, usuario.id, modulo_enum, accion, recurso_enum):
            raise SinPermiso(f"Sin permiso para '{accion}' en '{destino}'")
        return usuario

    return dependencia


def requiere_admin(usuario: Usuario = Depends(get_current_user)) -> Usuario:
    """Dependency para operaciones exclusivas del Admin (roles)."""
    _exigir_password_al_dia(usuario)
    if not usuario.es_admin:
        raise SinPermiso("Operación exclusiva del Admin")
    return usuario
