from typing import Annotated

from pydantic import BaseModel, Field

# Regla única de longitud de contraseñas (la reusan los schemas de usuarios).
Password = Annotated[str, Field(min_length=8, max_length=128)]


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=128)


class UsuarioSesion(BaseModel):
    id: int
    username: str
    nombre: str
    rol: str
    debe_cambiar_password: bool
    es_admin: bool

    @classmethod
    def desde(cls, usuario) -> "UsuarioSesion":
        return cls(
            id=usuario.id,
            username=usuario.username,
            nombre=usuario.nombre,
            rol=usuario.rol.nombre,
            debe_cambiar_password=usuario.debe_cambiar_password,
            es_admin=usuario.es_admin,
        )


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int  # segundos de vida del access token
    usuario: UsuarioSesion


class RefreshRequest(BaseModel):
    refresh_token: str | None = None


class RefreshResponse(BaseModel):
    access_token: str
    expires_in: int


class ForgotPasswordRequest(BaseModel):
    username: str = Field(min_length=1, max_length=50)


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=1, max_length=2048)
    password_nueva: Password


class CambiarPasswordRequest(BaseModel):
    password_actual: str = Field(min_length=1, max_length=128)
    password_nueva: Password
