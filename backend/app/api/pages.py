"""Rutas HTML (Jinja2). Fuera del esquema OpenAPI."""
from fastapi import APIRouter

router = APIRouter(include_in_schema=False)
