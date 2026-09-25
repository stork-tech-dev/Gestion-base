"""Punto de entrada de la aplicación FastAPI."""
import importlib
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.pages import router as pages_router
from app.api.v1 import api_router
from config import settings

BASE_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Registra todos los modelos en el metadata de SQLAlchemy.
    importlib.import_module("app.models")
    yield


docs_habilitadas = settings.APP_ENV != "production"

app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if docs_habilitadas else None,
    redoc_url="/redoc" if docs_habilitadas else None,
    openapi_url="/openapi.json" if docs_habilitadas else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS_LIST,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Punto de montaje del AuthRefreshMiddleware (sesión 02):
# app.add_middleware(AuthRefreshMiddleware)

app.mount("/static", StaticFiles(directory=BASE_DIR / "app" / "static"), name="static")

# La API tiene prioridad: las páginas HTML se montan al final.
app.include_router(api_router, prefix=settings.API_V1_PREFIX)
app.include_router(pages_router)
