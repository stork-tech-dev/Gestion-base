"""Registro de todos los modelos (lo importan main.lifespan y Alembic)."""
from app.models.auditoria import Auditoria
from app.models.caja import Arqueo, ArqueoItem, EstadoTurno, MedioPagoArqueoConfig, RetiroEfectivo, Turno, TurnoUsuario
from app.models.clientes import Cliente, ClientePromocion, CondicionIva
from app.models.configuracion import ConfiguracionSistema
from app.models.descuentos import MotivoDescuento, motivo_medios_pago
from app.models.medios_pago import MedioDePago, PlanCuotas
from app.models.motivo_baja import MotivoBaja
from app.models.notificaciones import Notificacion, TipoNotificacion
from app.models.permisos import RolPermiso, UsuarioPermiso
from app.models.productos import BAJO_MINIMO_SQL, NIVEL_MAXIMO, Categoria, Producto, ProductoFoto, TemporadaProducto
from app.models.promociones import (
    PAGAS_POR_GRUPO, TAMANO_GRUPO, Promocion, PromocionAlcance, TipoAlcancePromocion, TipoPromocion,
)
from app.models.proveedores import EstadoProveedor, Moneda, OrigenCambioDolar, Proveedor, ProveedorDolarHistorial
from app.models.sesiones import HistorialAcceso, ResultadoAcceso, Sesion
from app.models.stock import (
    AuditoriaInventario, AuditoriaItem, EstadoAuditoriaInventario, MovimientoStock, TipoMovimientoStock,
)
from app.models.usuarios import Rol, Usuario
from app.models.ventas import EstadoVenta, Venta, VentaItem, VentaPago

__all__ = [
    "Arqueo",
    "ArqueoItem",
    "Auditoria",
    "AuditoriaInventario",
    "AuditoriaItem",
    "BAJO_MINIMO_SQL",
    "Categoria",
    "Cliente",
    "ClientePromocion",
    "CondicionIva",
    "ConfiguracionSistema",
    "EstadoAuditoriaInventario",
    "EstadoProveedor",
    "EstadoTurno",
    "EstadoVenta",
    "HistorialAcceso",
    "MedioDePago",
    "MedioPagoArqueoConfig",
    "Moneda",
    "MotivoBaja",
    "MotivoDescuento",
    "MovimientoStock",
    "NIVEL_MAXIMO",
    "Notificacion",
    "OrigenCambioDolar",
    "PAGAS_POR_GRUPO",
    "PlanCuotas",
    "Producto",
    "ProductoFoto",
    "Promocion",
    "PromocionAlcance",
    "Proveedor",
    "ProveedorDolarHistorial",
    "ResultadoAcceso",
    "RetiroEfectivo",
    "Rol",
    "RolPermiso",
    "Sesion",
    "TAMANO_GRUPO",
    "TemporadaProducto",
    "TipoAlcancePromocion",
    "TipoMovimientoStock",
    "TipoNotificacion",
    "TipoPromocion",
    "Turno",
    "TurnoUsuario",
    "Usuario",
    "UsuarioPermiso",
    "Venta",
    "VentaItem",
    "VentaPago",
    "motivo_medios_pago",
]
