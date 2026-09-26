import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.errores import (
    DatoInvalido,
    NoAutenticado,
    NoEncontrado,
    ReglaDeNegocio,
    SinPermiso,
    registrar_manejadores,
)


@pytest.mark.parametrize(
    "error, status",
    [(NoEncontrado, 404), (SinPermiso, 403), (ReglaDeNegocio, 409), (NoAutenticado, 401), (DatoInvalido, 400)],
)
def test_errores_de_negocio_se_traducen_a_http(error, status):
    app = FastAPI()
    registrar_manejadores(app)

    @app.get("/falla")
    def falla():
        raise error("Mensaje para el usuario")

    r = TestClient(app).get("/falla")
    assert r.status_code == status
    assert r.json() == {"detail": "Mensaje para el usuario"}


def test_integrity_error_se_traduce_a_409():
    from sqlalchemy.exc import IntegrityError

    app = FastAPI()
    registrar_manejadores(app)

    @app.get("/duplicado")
    def duplicado():
        raise IntegrityError("INSERT ...", {}, Exception("duplicate key"))

    r = TestClient(app).get("/duplicado")
    assert r.status_code == 409
    assert r.json() == {"detail": "El dato ya existe o viola una restricción de la base."}
