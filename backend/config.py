"""Configuración única del sistema, leída del entorno / .env.

Ningún módulo lee os.environ directamente: todos importan `settings`.
"""
from zoneinfo import ZoneInfo

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    # JWT y sesión
    JWT_SECRET: str = "cambiar-en-produccion"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_MINUTES: int = 30
    JWT_REFRESH_TOKEN_DAYS: int = 7
    SESION_INACTIVIDAD_MINUTOS: int = 30  # debe ser >= JWT_ACCESS_TOKEN_MINUTES
    JWT_COOKIE_NAME: str = "access_token"
    JWT_REFRESH_COOKIE_NAME: str = "refresh_token"
    COOKIE_SECURE: bool = False

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
        return (
            f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def CORS_ORIGINS_LIST(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


settings = Settings()
