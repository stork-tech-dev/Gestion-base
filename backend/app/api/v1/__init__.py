"""Router único de la API v1: agrega los routers de cada módulo."""
from fastapi import APIRouter

from app.api.v1 import (
    auditoria, auditorias_inventario, auth, categorias, clientes, configuracion, health, notificaciones, productos,
    proveedores, roles, stock, turnos, usuarios, ventas,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(roles.router)
api_router.include_router(usuarios.router)
api_router.include_router(proveedores.router)
api_router.include_router(categorias.router)
api_router.include_router(productos.router)
api_router.include_router(auditoria.router)
api_router.include_router(stock.router)
api_router.include_router(auditorias_inventario.router)
api_router.include_router(clientes.router)
api_router.include_router(configuracion.router)
api_router.include_router(ventas.router)
api_router.include_router(turnos.router)
api_router.include_router(notificaciones.router)
