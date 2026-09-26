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
