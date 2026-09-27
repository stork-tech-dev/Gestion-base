"""Registro de todos los modelos (lo importan main.lifespan y Alembic)."""
from app.models.auditoria import Auditoria
from app.models.configuracion import ConfiguracionSistema
from app.models.motivo_baja import MotivoBaja
from app.models.permisos import RolPermiso, UsuarioPermiso
from app.models.productos import NIVEL_MAXIMO, Categoria, Producto, ProductoFoto, TemporadaProducto
from app.models.proveedores import EstadoProveedor, Moneda, OrigenCambioDolar, Proveedor, ProveedorDolarHistorial
from app.models.sesiones import HistorialAcceso, ResultadoAcceso, Sesion
from app.models.usuarios import Rol, Usuario

__all__ = [
    "Auditoria",
    "Categoria",
    "ConfiguracionSistema",
    "EstadoProveedor",
    "HistorialAcceso",
    "Moneda",
    "MotivoBaja",
    "NIVEL_MAXIMO",
    "OrigenCambioDolar",
    "Producto",
    "ProductoFoto",
    "Proveedor",
    "ProveedorDolarHistorial",
    "ResultadoAcceso",
    "Rol",
    "RolPermiso",
    "Sesion",
    "TemporadaProducto",
    "Usuario",
    "UsuarioPermiso",
]
