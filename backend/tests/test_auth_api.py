from sqlalchemy import select

from app.api.v1 import auth as auth_router
from app.models import HistorialAcceso, ResultadoAcceso, Sesion


def _login(client, username, password):
    return client.post("/api/v1/auth/login", json={"username": username, "password": password})


def test_login_devuelve_tokens_y_setea_cookies(client, crear_usuario):
    usuario = crear_usuario(username="ana", password="Clave1234", nombre="Ana Pérez")
    r = _login(client, "ana", "Clave1234")
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["expires_in"] == 30 * 60
    assert cuerpo["usuario"] == {
        "id": usuario.id, "username": "ana", "nombre": "Ana Pérez", "rol": "vendedor",
        "debe_cambiar_password": False, "es_admin": False,
    }
    assert r.cookies.get("access_token") and r.cookies.get("refresh_token")
    set_cookie = " ".join(r.headers.get_list("set-cookie")).lower()
    assert "httponly" in set_cookie and "samesite=lax" in set_cookie


def test_login_fallido_es_generico_y_queda_registrado(client, crear_usuario, db):
    usuario = crear_usuario(username="beto", password="Clave1234")
    r = _login(client, "beto", "mala")
    assert r.status_code == 401
    assert r.json() == {"detail": "Usuario o contraseña incorrectos"}
    fila = db.scalar(select(HistorialAcceso).where(HistorialAcceso.usuario_id == usuario.id))
    assert fila.resultado is ResultadoAcceso.FALLIDO


def test_admin_del_seed_debe_cambiar_la_password(client):
    r = _login(client, "admin", "Admin1234!")
    assert r.status_code == 200
    assert r.json()["usuario"]["debe_cambiar_password"] is True


def test_me(client, crear_usuario, headers_de):
    usuario = crear_usuario("supervisor", nombre="Sofía")
    r = client.get("/api/v1/auth/me", headers=headers_de(usuario))
    assert r.json()["nombre"] == "Sofía" and r.json()["rol"] == "supervisor"
    assert client.get("/api/v1/auth/me").status_code == 401


def test_refresh_por_cookie_y_por_body(client, crear_usuario, db):
    crear_usuario(username="caro", password="Clave1234")
    login = _login(client, "caro", "Clave1234").json()
    r = client.post("/api/v1/auth/refresh")  # cookie del login
    assert r.status_code == 200 and r.json()["access_token"]
    assert r.cookies.get("access_token")
    client.cookies.clear()
    r = client.post("/api/v1/auth/refresh", json={"refresh_token": login["refresh_token"]})
    assert r.status_code == 200


def test_refresh_invalido_da_401_y_borra_cookies(client):
    client.cookies.set("refresh_token", "basura")
    r = client.post("/api/v1/auth/refresh")
    assert r.status_code == 401
    assert 'refresh_token=""' in " ".join(r.headers.get_list("set-cookie"))


def test_logout_revoca_y_no_se_puede_renovar(client, crear_usuario, db):
    usuario = crear_usuario(username="dani", password="Clave1234")
    login = _login(client, "dani", "Clave1234").json()
    r = client.post("/api/v1/auth/logout")
    assert r.status_code == 200
    assert 'access_token=""' in " ".join(r.headers.get_list("set-cookie"))
    sesion = db.scalar(select(Sesion).where(Sesion.usuario_id == usuario.id))
    assert sesion.revocada
    r = client.post("/api/v1/auth/refresh", json={"refresh_token": login["refresh_token"]})
    assert r.status_code == 401


def test_forgot_password_siempre_responde_lo_mismo(client, crear_usuario, monkeypatch):
    enviados = []
    monkeypatch.setattr(auth_router, "enviar_reset_password", lambda e, n, t: enviados.append(t) or True)
    crear_usuario(username="eli", email="eli@example.com")
    r1 = client.post("/api/v1/auth/forgot-password", json={"username": "eli"})
    r2 = client.post("/api/v1/auth/forgot-password", json={"username": "noexiste"})
    assert r1.status_code == r2.status_code == 200 and r1.json() == r2.json()
    assert len(enviados) == 1


def test_reset_password_de_un_solo_uso(client, crear_usuario, monkeypatch):
    enviados = []
    monkeypatch.setattr(auth_router, "enviar_reset_password", lambda e, n, t: enviados.append(t) or True)
    crear_usuario(username="fede", email="fede@example.com")
    client.post("/api/v1/auth/forgot-password", json={"username": "fede"})
    cuerpo = {"token": enviados[0], "password_nueva": "NuevaClave1"}
    assert client.post("/api/v1/auth/reset-password", json=cuerpo).status_code == 200
    assert _login(client, "fede", "NuevaClave1").status_code == 200
    r = client.post("/api/v1/auth/reset-password", json=cuerpo)
    assert r.status_code == 400


def test_cambiar_password(client, crear_usuario, db):
    crear_usuario(username="gabi", password="Clave1234", debe_cambiar=True)
    viejo = _login(client, "gabi", "Clave1234").json()
    r = client.post("/api/v1/auth/cambiar-password", json={"password_actual": "mala", "password_nueva": "OtraClave1"})
    assert r.status_code == 400
    r = client.post("/api/v1/auth/cambiar-password", json={"password_actual": "Clave1234", "password_nueva": "Clave1234"})
    assert r.status_code == 400
    r = client.post("/api/v1/auth/cambiar-password", json={"password_actual": "Clave1234", "password_nueva": "OtraClave1"})
    assert r.status_code == 200
    assert r.json()["usuario"]["debe_cambiar_password"] is False
    # la sesión anterior quedó revocada; la nueva funciona
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": viejo["refresh_token"]}).status_code == 401
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {r.json()['access_token']}"}).status_code == 200


def test_password_nueva_corta_da_422(client, crear_usuario):
    crear_usuario(username="hugo", password="Clave1234")
    _login(client, "hugo", "Clave1234")
    r = client.post("/api/v1/auth/cambiar-password", json={"password_actual": "Clave1234", "password_nueva": "corta"})
    assert r.status_code == 422


def test_password_de_mas_de_72_bytes_da_422(client):
    r = client.post("/api/v1/auth/reset-password", json={"token": "x", "password_nueva": "a" * 73})
    assert r.status_code == 422
    assert "72 bytes" in str(r.json())
    # 40 caracteres pero 80 bytes en UTF-8.
    assert client.post("/api/v1/auth/reset-password", json={"token": "x", "password_nueva": "ñ" * 40}).status_code == 422
    # 72 bytes exactos: pasa la validación (falla después por el token).
    assert client.post("/api/v1/auth/reset-password", json={"token": "x", "password_nueva": "a" * 72}).status_code == 400
