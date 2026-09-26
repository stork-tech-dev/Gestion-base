def test_inicio_renderiza_layout_y_saludo(crear_usuario, iniciar_sesion):
    html = iniciar_sesion(crear_usuario("admin", nombre="Ana")).get("/").text
    assert "Bienvenido, Ana" in html
    assert 'id="contenido"' in html
    assert 'aria-label="Menú principal"' in html
    assert ">Inicio<" in html and 'aria-current="page"' in html
    assert "Ajustes" in html
    assert "Auditoría" not in html
    assert "cdn.tailwindcss.com" in html
    assert "/static/js/app.js?v=" in html and "/static/css/custom.css?v=" in html
    assert 'x-data="toasts()"' in html
    assert "dialogoConfirmacion()" in html
    assert "buscador-global" in html
    assert "text-welcome" in html
    assert "avisoSesion(" in html  # aviso de sesión por vencer con usuario logueado


def test_ajustes_usa_la_pagina_pendiente(crear_usuario, iniciar_sesion):
    r = iniciar_sesion(crear_usuario("vendedor")).get("/ajustes")
    assert r.status_code == 200
    assert "Este módulo todavía no está disponible." in r.text


def test_la_api_tiene_prioridad_sobre_las_paginas(client):
    assert client.get("/api/v1/health").json() == {"status": "ok"}


def test_static_se_sirve(client):
    assert client.get("/static/js/app.js").status_code == 200
    assert client.get("/static/css/custom.css").status_code == 200
