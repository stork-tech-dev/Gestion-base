from sqlalchemy.exc import OperationalError

from app.core.database import get_db


def test_health_no_toca_la_base(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_health_db_ok(client):
    r = client.get("/api/v1/health/db")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "database": "ok"}


def test_health_db_caida(client):
    from main import app

    class SesionCaida:
        def execute(self, *args, **kwargs):
            raise OperationalError("SELECT 1", {}, Exception("sin conexión"))

    app.dependency_overrides[get_db] = lambda: SesionCaida()
    r = client.get("/api/v1/health/db")
    assert r.status_code == 503
    cuerpo = r.json()
    assert cuerpo["status"] == "degraded" and cuerpo["database"] == "error"
    assert "sin conexión" in cuerpo["detalle"]


def test_swagger_disponible_fuera_de_produccion(client):
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200
