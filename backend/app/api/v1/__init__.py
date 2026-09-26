"""Router único de la API v1: agrega los routers de cada módulo."""
from fastapi import APIRouter

from app.api.v1 import auditoria, auth, health, roles, usuarios

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(roles.router)
api_router.include_router(usuarios.router)
api_router.include_router(auditoria.router)
