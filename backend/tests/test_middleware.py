from datetime import timedelta

from sqlalchemy import select

from app.core.utils import ahora, ahora_db
from app.models import Sesion
from app.services import auth


def _cookies_de_sesion(client, db, usuario):
    access, refresh, sesion = auth.generar_tokens(db, usuario, None)
    client.cookies.set("access_token", access)
    client.cookies.set("refresh_token", refresh)
    return access, refresh, sesion


def test_access_vencido_se_renueva_con_el_refresh(client, crear_usuario, db):
    usuario = crear_usuario()
    _, _, sesion = _cookies_de_sesion(client, db, usuario)
    vencido = auth._codificar({"sub": str(usuario.id), "tipo": "access", "sid": sesion.jti}, ahora() - timedelta(seconds=5))
    client.cookies.set("access_token", vencido)
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 200 and r.json()["id"] == usuario.id
    nuevo = r.cookies.get("access_token")
    assert nuevo and nuevo != vencido
    assert auth.verificar_token(nuevo, "access")["sid"] == sesion.jti


def test_access_vigente_corre_la_ventana_de_inactividad(client, crear_usuario, db):
    usuario = crear_usuario()
    _, _, sesion = _cookies_de_sesion(client, db, usuario)
    sesion.expira_en = ahora_db() + timedelta(minutes=3)
    db.flush()
    assert client.get("/api/v1/auth/me").status_code == 200
    db.refresh(sesion)
    assert sesion.expira_en > ahora_db() + timedelta(minutes=29)


def test_sesion_caida_por_inactividad_borra_cookies_y_da_401(client, crear_usuario, db):
    usuario = crear_usuario()
    _, _, sesion = _cookies_de_sesion(client, db, usuario)
    sesion.expira_en = ahora_db() - timedelta(seconds=1)
    db.flush()
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 401
    cookies = " ".join(r.headers.get_list("set-cookie"))
    assert 'access_token=""' in cookies and 'refresh_token=""' in cookies
    assert db.scalar(select(Sesion.revocada).where(Sesion.id == sesion.id))


def test_logout_no_es_pisado_por_el_middleware(client, crear_usuario, db):
    usuario = crear_usuario()
    _cookies_de_sesion(client, db, usuario)
    r = client.post("/api/v1/auth/logout")
    cookies = r.headers.get_list("set-cookie")
    assert all(c.startswith(('access_token=""', 'refresh_token=""')) for c in cookies)


def test_bearer_corre_la_ventana_sin_tocar_cookies(client, crear_usuario, db):
    access, _, sesion = auth.generar_tokens(db, crear_usuario(), None)
    sesion.expira_en = ahora_db() + timedelta(minutes=3)
    db.flush()
    r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access}"})
    assert r.status_code == 200 and not r.headers.get_list("set-cookie")
    db.refresh(sesion)
    assert sesion.expira_en > ahora_db() + timedelta(minutes=29)


def test_bearer_invalido_no_toca_cookies(client):
    r = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer basura"})
    assert r.status_code == 401 and not r.headers.get_list("set-cookie")


def test_logout_con_access_vencido_no_reinserta_access(client, crear_usuario, db):
    usuario = crear_usuario()
    _, _, sesion = _cookies_de_sesion(client, db, usuario)
    vencido = auth._codificar({"sub": str(usuario.id), "tipo": "access", "sid": sesion.jti}, ahora() - timedelta(seconds=5))
    client.cookies.set("access_token", vencido)
    r = client.post("/api/v1/auth/logout")
    assert r.status_code == 200
    cookies = r.headers.get_list("set-cookie")
    assert len(cookies) == 2
    assert all(c.startswith(('access_token=""', 'refresh_token=""')) for c in cookies)


def test_rutas_estaticas_excluidas(client):
    client.cookies.set("refresh_token", "basura")
    r = client.get("/static/css/custom.css")
    assert r.status_code == 200 and not r.headers.get_list("set-cookie")


def test_el_middleware_nunca_rompe_el_request(client, crear_usuario, db):
    from contextlib import contextmanager

    from main import app

    @contextmanager
    def _falla():
        raise RuntimeError("base caída")
        yield  # noqa

    _cookies_de_sesion(client, db, crear_usuario())
    app.state.abrir_sesion_db = _falla
    assert client.get("/api/v1/health").status_code == 200
