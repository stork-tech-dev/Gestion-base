def test_inicio_renderiza_layout_y_saludo(client):
    r = client.get("/")
    assert r.status_code == 200
    html = r.text
    assert "Bienvenido" in html
    assert 'id="contenido"' in html
    assert 'aria-label="Menú principal"' in html           # sidebar
    assert ">Inicio<" in html and 'aria-current="page"' in html
    assert "Ajustes" in html                               # pie del sidebar
    assert "Auditoría" not in html                         # ítem oculto
    assert "cdn.tailwindcss.com" in html
    assert "/static/js/app.js?v=" in html and "/static/css/custom.css?v=" in html
    assert 'x-data="toasts()"' in html                     # contenedor de toasts
    assert "dialogoConfirmacion()" in html                 # diálogo global
    assert "buscador-global" in html                       # buscador comentado
    assert "text-welcome" in html


def test_ajustes_usa_la_pagina_pendiente(client):
    r = client.get("/ajustes")
    assert r.status_code == 200
    assert "Este módulo todavía no está disponible." in r.text


def test_la_api_tiene_prioridad_sobre_las_paginas(client):
    assert client.get("/api/v1/health").json() == {"status": "ok"}


def test_static_se_sirve(client):
    assert client.get("/static/js/app.js").status_code == 200
    assert client.get("/static/css/custom.css").status_code == 200
