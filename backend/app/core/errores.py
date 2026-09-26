"""Errores de negocio y su traducción a HTTP (una sola definición).

Los services levantan estos errores; nunca HTTPException. main.py registra un
único handler que responde {"detail": mensaje} con el status de cada clase.
"""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class ErrorDeNegocio(Exception):
    status_code = 400

    def __init__(self, mensaje: str):
        super().__init__(mensaje)
        self.mensaje = mensaje


class DatoInvalido(ErrorDeNegocio):
    status_code = 400


class NoAutenticado(ErrorDeNegocio):
    status_code = 401


class SinPermiso(ErrorDeNegocio):
    status_code = 403


class NoEncontrado(ErrorDeNegocio):
    status_code = 404


class ReglaDeNegocio(ErrorDeNegocio):
    status_code = 409


async def _manejar_error_de_negocio(_request: Request, exc: ErrorDeNegocio) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.mensaje})


def registrar_manejadores(app: FastAPI) -> None:
    app.add_exception_handler(ErrorDeNegocio, _manejar_error_de_negocio)
