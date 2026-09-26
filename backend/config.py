"""Configuración única del sistema, leída del entorno / .env.

Ningún módulo lee os.environ directamente: todos importan `settings`.
"""
from zoneinfo import ZoneInfo

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    # Aplicación
    APP_NAME: str = "Sistema de Gestión"
    APP_ENV: str = "development"  # development | production (| test)
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"
    APP_URL: str = "http://localhost:8000"
    TIMEZONE: str = "America/Argentina/Buenos_Aires"

    # Base de datos
    POSTGRES_USER: str = "gestion"
    POSTGRES_PASSWORD: str = "gestion"
    POSTGRES_DB: str = "gestion"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    DATABASE_URL_OVERRIDE: str | None = Field(default=None, alias="DATABASE_URL")

    # Cantidad de proxies inversos PROPIOS delante de la app (afecta cómo se
    # confía en X-Forwarded-For para la IP de auditoría; ver ip_de_request).
    # 0 = conexión directa (docker compose local, default).
    # 1 = detrás de un único proxy propio (ej. Railway o un nginx propio).
    PROXIES_DE_CONFIANZA: int = 0

    # JWT y sesión
    JWT_SECRET: str = "cambiar-en-produccion"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_MINUTES: int = 30
    JWT_REFRESH_TOKEN_DAYS: int = 7
    SESION_INACTIVIDAD_MINUTOS: int = 30  # debe ser >= JWT_ACCESS_TOKEN_MINUTES
    JWT_COOKIE_NAME: str = "access_token"
    JWT_REFRESH_COOKIE_NAME: str = "refresh_token"
    COOKIE_SECURE: bool = False
    BCRYPT_ROUNDS: int = 12  # costo de bcrypt (los tests usan 4 para ir rápido)

    # CORS
    CORS_ORIGINS: str = "http://localhost:8000"

    # SMTP
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_FROM: str = "no-reply@example.com"
    SMTP_TLS: bool = True

    # Archivos subidos (volumen persistente)
    UPLOADS_DIR: str = "/uploads"

    # Backups (los usa el servicio backup; se documentan acá)
    BACKUP_HORA: str = "03:00"
    BACKUP_RETENCION_DIAS: int = 14

    @property
    def TZ(self) -> ZoneInfo:
        return ZoneInfo(self.TIMEZONE)

    @property
    def DATABASE_URL(self) -> str:
        """URL SQLAlchemy. DATABASE_URL (si viene) pisa las variables POSTGRES_*."""
        if self.DATABASE_URL_OVERRIDE:
            url = self.DATABASE_URL_OVERRIDE
            for prefijo in ("postgres://", "postgresql://"):
                if url.startswith(prefijo):
                    return "postgresql+psycopg2://" + url[len(prefijo):]
            return url
        # URL.create hace el URL-encoding de usuario/contraseña: armar la URL
        # a mano con un f-string rompe el parseo si la contraseña tiene
        # caracteres especiales (@ / # ? % ...).
        return URL.create(
            drivername="postgresql+psycopg2",
            username=self.POSTGRES_USER,
            password=self.POSTGRES_PASSWORD,
            host=self.POSTGRES_HOST,
            port=self.POSTGRES_PORT,
            database=self.POSTGRES_DB,
        ).render_as_string(hide_password=False)

    @property
    def CORS_ORIGINS_LIST(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @model_validator(mode="after")
    def _validar_defaults_de_seguridad(self) -> "Settings":
        """Defaults inseguros que no deben llegar a producción (Principio 3/6)."""
        secretos_de_ejemplo = {"cambiar-en-produccion", "cambiar-por-un-secreto-largo-y-aleatorio"}
        if self.APP_ENV == "production" and (
            self.JWT_SECRET in secretos_de_ejemplo or len(self.JWT_SECRET) < 32
        ):
            raise ValueError(
                "JWT_SECRET debe reemplazarse por un secreto de al menos 32 caracteres en producción"
            )
        if self.APP_ENV == "production" and any(h in self.APP_URL for h in ("localhost", "127.0.0.1")):
            # APP_URL arma el enlace de recuperación de contraseña de los mails.
            raise ValueError("APP_URL debe ser la URL pública del sistema en producción")
        if self.SESION_INACTIVIDAD_MINUTOS < self.JWT_ACCESS_TOKEN_MINUTES:
            raise ValueError(
                "SESION_INACTIVIDAD_MINUTOS debe ser mayor o igual a JWT_ACCESS_TOKEN_MINUTES"
            )
        if "*" in self.CORS_ORIGINS_LIST:
            raise ValueError('CORS_ORIGINS no puede incluir "*": es incompatible con credenciales')
        return self


settings = Settings()
