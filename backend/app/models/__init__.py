"""Registro de todos los modelos (lo importan main.lifespan y Alembic)."""
from app.models.auditoria import Auditoria
from app.models.configuracion import ConfiguracionSistema
from app.models.motivo_baja import MotivoBaja
from app.models.permisos import RolPermiso, UsuarioPermiso
from app.models.productos import BAJO_MINIMO_SQL, NIVEL_MAXIMO, Categoria, Producto, ProductoFoto, TemporadaProducto
from app.models.proveedores import EstadoProveedor, Moneda, OrigenCambioDolar, Proveedor, ProveedorDolarHistorial
from app.models.sesiones import HistorialAcceso, ResultadoAcceso, Sesion
from app.models.stock import (
    AuditoriaInventario, AuditoriaItem, EstadoAuditoriaInventario, MovimientoStock, TipoMovimientoStock,
)
from app.models.usuarios import Rol, Usuario

__all__ = [
    "Auditoria",
    "AuditoriaInventario",
    "AuditoriaItem",
    "BAJO_MINIMO_SQL",
    "Categoria",
    "ConfiguracionSistema",
    "EstadoAuditoriaInventario",
    "EstadoProveedor",
    "HistorialAcceso",
    "Moneda",
    "MotivoBaja",
    "MovimientoStock",
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
    "TipoMovimientoStock",
    "Usuario",
    "UsuarioPermiso",
]
