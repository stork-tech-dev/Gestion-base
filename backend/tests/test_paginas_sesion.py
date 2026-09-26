def test_sin_sesion_redirige_al_login(client):
    for url in ("/", "/configuracion", "/ajustes"):
        r = client.get(url, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/login"


def test_con_cambio_pendiente_redirige_a_cambiar_password(crear_usuario, iniciar_sesion):
    cliente = iniciar_sesion(crear_usuario("vendedor", debe_cambiar=True))
    r = cliente.get("/", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/cambiar-password"


def test_sidebar_filtrado_por_permisos(crear_usuario, iniciar_sesion):
    html = iniciar_sesion(crear_usuario("admin", nombre="Ana Admin")).get("/").text
    assert "Bienvenido, Ana" in html and ">Configuraciones<" in html
    assert "Ana Admin" in html and ">admin<" in html  # nombre en el sidebar y rol en el menú del badge


def test_vendedor_no_ve_configuraciones(crear_usuario, iniciar_sesion):
    html = iniciar_sesion(crear_usuario("vendedor")).get("/").text
    assert ">Configuraciones<" not in html


def test_hub_de_configuraciones_segun_permisos(crear_usuario, iniciar_sesion, client):
    html = iniciar_sesion(crear_usuario("supervisor")).get("/configuracion").text
    assert 'href="/usuarios"' in html and 'href="/roles"' not in html
    client.cookies.clear()
    html = iniciar_sesion(crear_usuario("admin")).get("/configuracion").text
    assert 'href="/usuarios"' in html and 'href="/roles"' in html


def test_hub_vacio_para_quien_no_ve_ninguna_tarjeta(crear_usuario, iniciar_sesion):
    html = iniciar_sesion(crear_usuario("vendedor")).get("/configuracion").text
    assert "No tenés secciones disponibles." in html
