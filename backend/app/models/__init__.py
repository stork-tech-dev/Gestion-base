"""Registro de todos los modelos (lo importan main.lifespan y Alembic)."""
from app.models.auditoria import Auditoria
from app.models.configuracion import ConfiguracionSistema
from app.models.motivo_baja import MotivoBaja
from app.models.permisos import RolPermiso, UsuarioPermiso
from app.models.sesiones import HistorialAcceso, ResultadoAcceso, Sesion
from app.models.usuarios import Rol, Usuario

__all__ = [
    "Auditoria",
    "ConfiguracionSistema",
    "HistorialAcceso",
    "MotivoBaja",
    "ResultadoAcceso",
    "Rol",
    "RolPermiso",
    "Sesion",
    "Usuario",
    "UsuarioPermiso",
]
