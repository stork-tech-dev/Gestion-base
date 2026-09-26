"""Autenticación: login, renovación, logout, recuperación y cambio de contraseña."""
from fastapi import APIRouter, Body, Depends, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.auditoria import registrar_auditoria
from app.core.cookies import borrar_cookies_sesion, poner_cookie_access, poner_cookies_sesion
from app.core.database import get_db
from app.core.errores import DatoInvalido
from app.core.seguridad import get_current_user
from app.core.utils import ip_de_request
from app.models import Usuario
from app.schemas.auth import (
    CambiarPasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    RefreshRequest,
    RefreshResponse,
    ResetPasswordRequest,
    TokenResponse,
    UsuarioSesion,
)
from app.schemas.comunes import MensajeResponse
from app.services import auth
from config import settings

router = APIRouter(prefix="/auth", tags=["auth"])

MENSAJE_RESET_SOLICITADO = "Si el usuario existe y tiene un email cargado, te enviamos las instrucciones."
MENSAJE_SESION_VENCIDA = "Sesión vencida. Volvé a ingresar."


def _token_response(usuario: Usuario, access: str, refresh: str) -> TokenResponse:
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.JWT_ACCESS_TOKEN_MINUTES * 60,
        usuario=UsuarioSesion.desde(usuario),
    )


def _refresh_de(request: Request, datos: RefreshRequest | None) -> str | None:
    return (datos.refresh_token if datos else None) or request.cookies.get(settings.JWT_REFRESH_COOKIE_NAME)


@router.post("/login", response_model=TokenResponse)
def login(datos: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    ip = ip_de_request(request)
    try:
        usuario = auth.autenticar_usuario(db, datos.username, datos.password, ip)
    except auth.CredencialesInvalidas:
        db.commit()  # el intento fallido queda registrado igual
        raise
    if not usuario.debe_cambiar_password:
        auth.marcar_acceso(db, usuario)
    access, refresh, _ = auth.generar_tokens(db, usuario, ip)
    db.commit()
    poner_cookies_sesion(response, access, refresh)
    return _token_response(usuario, access, refresh)


@router.post("/refresh", response_model=RefreshResponse)
def refresh(request: Request, response: Response, datos: RefreshRequest | None = Body(default=None),
            db: Session = Depends(get_db)):
    try:
        access = auth.refrescar_access_token(db, _refresh_de(request, datos))
    except auth.TokenInvalido:
        db.commit()  # conserva la marca de sesión revocada
        vencida = JSONResponse(status_code=401, content={"detail": MENSAJE_SESION_VENCIDA})
        borrar_cookies_sesion(vencida)
        return vencida
    db.commit()
    poner_cookie_access(response, access)
    return RefreshResponse(access_token=access, expires_in=settings.JWT_ACCESS_TOKEN_MINUTES * 60)


@router.post("/logout", response_model=MensajeResponse)
def logout(request: Request, datos: RefreshRequest | None = Body(default=None), db: Session = Depends(get_db)):
    sesion = auth.revocar_sesion(db, _refresh_de(request, datos))
    if sesion is not None:
        registrar_auditoria(
            db, accion="auth.logout", entidad="usuario", entidad_id=sesion.usuario_id,
            usuario_id=sesion.usuario_id, request=request,
        )
    db.commit()
    respuesta = JSONResponse(content={"mensaje": "Sesión cerrada."})
    borrar_cookies_sesion(respuesta)
    return respuesta


@router.post("/forgot-password", response_model=MensajeResponse)
def forgot_password(datos: ForgotPasswordRequest, request: Request, db: Session = Depends(get_db)):
    auth.solicitar_reset(db, datos.username, ip_de_request(request))
    db.commit()
    return MensajeResponse(mensaje=MENSAJE_RESET_SOLICITADO)


@router.post("/reset-password", response_model=MensajeResponse)
def reset_password(datos: ResetPasswordRequest, request: Request, db: Session = Depends(get_db)):
    try:
        usuario = auth.validar_token_reset(db, datos.token)
    except auth.TokenInvalido as exc:
        raise DatoInvalido("El enlace de recuperación es inválido, venció o ya se usó.") from exc
    auth.cambiar_password(
        db, usuario, datos.password_nueva, autor_id=usuario.id, ip=ip_de_request(request), debe_cambiarla=False
    )
    db.commit()
    return MensajeResponse(mensaje="Contraseña actualizada. Ya podés ingresar.")


@router.post("/cambiar-password", response_model=TokenResponse)
def cambiar_password(datos: CambiarPasswordRequest, request: Request, response: Response,
                     usuario: Usuario = Depends(get_current_user), db: Session = Depends(get_db)):
    if not auth.verificar_password(datos.password_actual, usuario.password_hash):
        raise DatoInvalido("La contraseña actual no es correcta.")
    if datos.password_actual == datos.password_nueva:
        raise DatoInvalido("La contraseña nueva tiene que ser distinta de la actual.")
    ip = ip_de_request(request)
    auth.cambiar_password(db, usuario, datos.password_nueva, autor_id=usuario.id, ip=ip, debe_cambiarla=False)
    access, refresh_nuevo, _ = auth.generar_tokens(db, usuario, ip)
    db.commit()
    poner_cookies_sesion(response, access, refresh_nuevo)
    return _token_response(usuario, access, refresh_nuevo)


@router.get("/me", response_model=UsuarioSesion)
def me(usuario: Usuario = Depends(get_current_user)):
    return UsuarioSesion.desde(usuario)
