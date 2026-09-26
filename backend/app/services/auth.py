"""Autenticación: contraseñas, tokens JWT y sesiones con ventana de inactividad.

- access token: 30 min, claim `sid` = jti de la sesión (se valida en cada request).
- refresh token: 7 días, claim `jti`; la fila de `sesiones` guarda la ventana
  deslizante de inactividad (`expira_en`), con tope `creada_en + 7 días`.
- reset token: 30 min, claim `pwd` = últimos 16 caracteres del hash actual
  (queda inválido apenas cambia la contraseña: un solo uso sin tabla).
"""
import secrets
from datetime import datetime, timedelta

import bcrypt
import jwt
from sqlalchemy import select, update

from app.core.auditoria import registrar_auditoria
from app.core.email import enviar_reset_password
from app.core.errores import NoAutenticado
from app.core.utils import ahora, ahora_db
from app.models import HistorialAcceso, ResultadoAcceso, Sesion, Usuario
from config import settings

MENSAJE_CREDENCIALES = "Usuario o contraseña incorrectos"
ACTIVIDAD_MINIMA = timedelta(minutes=1)  # registrar_actividad escribe como mucho una vez por minuto
RESET_MINUTOS = 30


class TokenInvalido(Exception):
    """Token ausente, mal firmado, vencido, de otro tipo o de una sesión caída."""


class CredencialesInvalidas(NoAutenticado):
    def __init__(self):
        super().__init__(MENSAJE_CREDENCIALES)


# ---------------------------------------------------------------- contraseñas
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(settings.BCRYPT_ROUNDS)).decode("ascii")


def verificar_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("ascii"))
    except ValueError:
        return False


# Hash señuelo: con usuario inexistente igual se paga el costo de bcrypt
# (el tiempo de respuesta no revela qué usernames existen).
_HASH_SENUELO = hash_password("señuelo-para-igualar-tiempos")


# ---------------------------------------------------------------- tokens
def _codificar(claims: dict, vence: datetime) -> str:
    return jwt.encode({**claims, "iat": ahora(), "exp": vence}, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def crear_access_token(usuario_id: int, sid: str) -> str:
    vence = ahora() + timedelta(minutes=settings.JWT_ACCESS_TOKEN_MINUTES)
    return _codificar({"sub": str(usuario_id), "tipo": "access", "sid": sid}, vence)


def verificar_token(token: str | None, tipo: str) -> dict:
    if not token:
        raise TokenInvalido("Falta el token")
    try:
        datos = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
            options={"require": ["exp", "sub", "tipo"]},
        )
    except jwt.PyJWTError as exc:
        raise TokenInvalido(str(exc)) from exc
    if datos.get("tipo") != tipo:
        raise TokenInvalido("Tipo de token incorrecto")
    return datos


# ---------------------------------------------------------------- sesiones
def _fin_de_ventana(sesion: Sesion) -> datetime:
    inactividad = ahora_db() + timedelta(minutes=settings.SESION_INACTIVIDAD_MINUTOS)
    tope = sesion.creada_en + timedelta(days=settings.JWT_REFRESH_TOKEN_DAYS)
    return min(inactividad, tope)


def generar_tokens(db, usuario: Usuario, ip: str | None) -> tuple[str, str, Sesion]:
    jti = secrets.token_hex(16)
    creada = ahora_db()
    sesion = Sesion(
        usuario_id=usuario.id,
        jti=jti,
        creada_en=creada,
        expira_en=creada + timedelta(minutes=settings.SESION_INACTIVIDAD_MINUTOS),
        revocada=False,
        ip_origen=ip,
    )
    db.add(sesion)
    db.flush()
    vence_refresh = ahora() + timedelta(days=settings.JWT_REFRESH_TOKEN_DAYS)
    refresh = _codificar({"sub": str(usuario.id), "tipo": "refresh", "jti": jti}, vence_refresh)
    return crear_access_token(usuario.id, jti), refresh, sesion


def registrar_actividad(db, sesion: Sesion) -> None:
    """Corre la ventana de inactividad (como mucho una escritura por minuto)."""
    nueva = _fin_de_ventana(sesion)
    if nueva - sesion.expira_en >= ACTIVIDAD_MINIMA:
        sesion.expira_en = nueva
        db.flush()


def _sesion_por_jti(db, jti: str | None) -> Sesion:
    sesion = db.scalar(select(Sesion).where(Sesion.jti == jti)) if jti else None
    if sesion is None or sesion.revocada:
        raise TokenInvalido("Sesión inexistente o revocada")
    if sesion.expira_en <= ahora_db():
        sesion.revocada = True
        db.flush()
        raise TokenInvalido("Sesión vencida por inactividad")
    return sesion


def sesion_vigente(db, refresh: str | None) -> Sesion:
    return _sesion_por_jti(db, verificar_token(refresh, "refresh").get("jti"))


def sesion_de_access(db, datos_access: dict) -> Sesion:
    return _sesion_por_jti(db, datos_access.get("sid"))


def refrescar_access_token(db, refresh: str | None) -> str:
    sesion = sesion_vigente(db, refresh)
    usuario = db.get(Usuario, sesion.usuario_id)
    if usuario is None or not usuario.activo or not usuario.rol.activo:
        sesion.revocada = True
        db.flush()
        raise TokenInvalido("Usuario o rol inactivo")
    registrar_actividad(db, sesion)
    return crear_access_token(usuario.id, sesion.jti)


def revocar_sesion(db, refresh: str | None) -> Sesion | None:
    """Idempotente: un token inválido o ya revocado no es error."""
    try:
        jti = verificar_token(refresh, "refresh").get("jti")
    except TokenInvalido:
        return None
    sesion = db.scalar(select(Sesion).where(Sesion.jti == jti))
    if sesion is not None and not sesion.revocada:
        sesion.revocada = True
        db.flush()
    return sesion


def revocar_sesiones_de_usuario(db, usuario_id: int) -> None:
    db.execute(
        update(Sesion)
        .where(Sesion.usuario_id == usuario_id, Sesion.revocada.is_(False))
        .values(revocada=True)
    )


# ---------------------------------------------------------------- login
def _registrar_intento(db, usuario, username, exitoso, detalle, ip) -> None:
    if usuario is not None:
        db.add(
            HistorialAcceso(
                usuario_id=usuario.id,
                timestamp=ahora_db(),
                ip_origen=ip,
                resultado=ResultadoAcceso.EXITOSO if exitoso else ResultadoAcceso.FALLIDO,
                detalle=detalle,
            )
        )
    registrar_auditoria(
        db,
        accion="auth.login" if exitoso else "auth.login_fallido",
        entidad="usuario",
        entidad_id=usuario.id if usuario else None,
        usuario_id=usuario.id if usuario else None,
        estado_nuevo=None if exitoso else {"username": username, "detalle": detalle},
        ip_origen=ip,
    )


def autenticar_usuario(db, username: str, password: str, ip: str | None) -> Usuario:
    """Registra SIEMPRE el intento; el mensaje de error es siempre genérico.
    El llamador debe hacer commit aunque falle (para conservar el registro)."""
    username = (username or "").strip().lower()
    usuario = db.scalar(select(Usuario).where(Usuario.username == username))
    if usuario is None:
        verificar_password(password, _HASH_SENUELO)
        detalle = "Usuario inexistente"
    elif not verificar_password(password, usuario.password_hash):
        detalle = "Contraseña incorrecta"
    elif not usuario.activo:
        detalle = "Usuario inactivo"
    elif not usuario.rol.activo:
        detalle = "Rol inactivo"
    else:
        _registrar_intento(db, usuario, username, True, None, ip)
        return usuario
    _registrar_intento(db, usuario, username, False, detalle, ip)
    raise CredencialesInvalidas()


def marcar_acceso(db, usuario: Usuario) -> None:
    usuario.ultimo_acceso = ahora_db()
    db.flush()


def debe_cambiar_password(usuario: Usuario) -> bool:
    return usuario.debe_cambiar_password


# ---------------------------------------------------------------- contraseñas olvidadas
def _huella(usuario: Usuario) -> str:
    return usuario.password_hash[-16:]


def generar_token_reset(usuario: Usuario) -> str:
    vence = ahora() + timedelta(minutes=RESET_MINUTOS)
    return _codificar({"sub": str(usuario.id), "tipo": "reset", "pwd": _huella(usuario)}, vence)


def validar_token_reset(db, token: str | None) -> Usuario:
    datos = verificar_token(token, "reset")
    try:
        usuario = db.get(Usuario, int(datos["sub"]))
    except (TypeError, ValueError) as exc:
        raise TokenInvalido("Token de recuperación inválido") from exc
    if usuario is None or not usuario.activo or datos.get("pwd") != _huella(usuario):
        raise TokenInvalido("Token de recuperación inválido o ya usado")
    return usuario


def solicitar_reset(db, username: str, ip: str | None) -> None:
    """Envía el mail solo si el usuario existe, está activo y tiene email.
    El llamador responde siempre lo mismo (no revela qué usuarios existen)."""
    username = (username or "").strip().lower()
    usuario = db.scalar(select(Usuario).where(Usuario.username == username))
    enviado = False
    if usuario is not None and usuario.activo and usuario.email:
        enviado = enviar_reset_password(usuario.email, usuario.nombre, generar_token_reset(usuario))
    registrar_auditoria(
        db,
        accion="auth.reset_solicitar",
        entidad="usuario",
        entidad_id=usuario.id if usuario else None,
        estado_nuevo={"username": username, "enviado": enviado},
        ip_origen=ip,
    )


def cambiar_password(db, usuario: Usuario, nueva: str, *, autor_id: int | None, ip: str | None,
                     debe_cambiarla: bool) -> None:
    """Cambia el hash, revoca todas las sesiones del usuario y audita (sin la clave).
    `debe_cambiarla=True` (reseteo por un admin) obliga a cambiarla al próximo ingreso."""
    usuario.password_hash = hash_password(nueva)
    usuario.ultimo_acceso = None if debe_cambiarla else ahora_db()
    db.flush()
    revocar_sesiones_de_usuario(db, usuario.id)
    registrar_auditoria(
        db,
        accion="usuario.cambiar_password",
        entidad="usuario",
        entidad_id=usuario.id,
        usuario_id=autor_id,
        estado_nuevo={"debe_cambiarla": debe_cambiarla},
        ip_origen=ip,
    )
