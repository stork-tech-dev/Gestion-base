"""Páginas de autenticación: login, cambio de contraseña y recuperación."""


def test_login_sin_sesion(client):
    r = client.get("/login")
    assert r.status_code == 200
    assert 'x-data="login()"' in r.text and "Iniciar Sesión" in r.text and "¿Olvidé mi contraseña?" in r.text
    assert "/static/js/auth.js?v=" in r.text


def test_login_con_sesion_va_al_inicio(crear_usuario, iniciar_sesion):
    r = iniciar_sesion(crear_usuario("vendedor")).get("/login", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/"


def test_cambiar_password(client, crear_usuario, iniciar_sesion):
    assert client.get("/cambiar-password", follow_redirects=False).headers["location"] == "/login"
    html = iniciar_sesion(crear_usuario("vendedor", debe_cambiar=True)).get("/cambiar-password").text
    assert 'x-data="cambiarPassword()"' in html and "elegí una propia" in html


def test_cambiar_password_voluntario(crear_usuario, iniciar_sesion):
    html = iniciar_sesion(crear_usuario("vendedor")).get("/cambiar-password").text
    assert 'x-data="cambiarPassword()"' in html and "elegí una propia" not in html


def test_reset_password(client):
    r = client.get("/reset-password", params={"token": "abc.def"})
    assert r.status_code == 200 and r.headers["referrer-policy"] == "no-referrer"
    assert "resetPassword(&#34;abc.def&#34;)" in r.text
    r = client.get("/reset-password")
    assert "El enlace no es válido" in r.text
