"""Páginas HTML del módulo de stock: hub "Gestión de Stock", /stock y
/motivos-baja (Tasks 7 y 8). La visibilidad usa la misma barrera que la API
(resolver_permiso); acá solo se verifica que el layout arme lo esperado."""


def test_sidebar_muestra_gestion_de_stock(crear_usuario, iniciar_sesion):
    html = iniciar_sesion(crear_usuario("vendedor")).get("/").text
    assert 'href="/gestion-de-stock"' in html


def test_hub_admin_muestra_las_dos_tarjetas(crear_usuario, iniciar_sesion):
    html = iniciar_sesion(crear_usuario("admin")).get("/gestion-de-stock").text
    assert 'href="/stock"' in html and "Stock" in html
    assert 'href="/auditorias-inventario"' in html and "Auditorías de Stock" in html


def test_hub_vendedor_ve_las_dos_tarjetas(crear_usuario, iniciar_sesion):
    # Vendedor tiene STOCK ver (seed.sql): ambas tarjetas solo piden eso.
    html = iniciar_sesion(crear_usuario("vendedor")).get("/gestion-de-stock").text
    assert 'href="/stock"' in html
    assert 'href="/auditorias-inventario"' in html


def test_listado_stock_admin(crear_usuario, iniciar_sesion):
    html = iniciar_sesion(crear_usuario("admin")).get("/stock").text
    assert "stockListado(" in html and "/static/js/stock.js?v=" in html
    assert "Motivos de baja" in html
    assert "puedeIngresar: true" in html and "puedeMinimos: true" in html and "puedeBaja: true" in html


def test_listado_stock_vendedor(crear_usuario, iniciar_sesion):
    html = iniciar_sesion(crear_usuario("vendedor")).get("/stock").text
    assert "puedeBaja: true" in html
    assert "puedeIngresar: false" in html
    assert "Motivos de baja" not in html


def test_stock_volver_al_hub(crear_usuario, iniciar_sesion):
    html = iniciar_sesion(crear_usuario("admin")).get("/stock").text
    assert 'href="/gestion-de-stock"' in html


def test_motivos_baja_admin(crear_usuario, iniciar_sesion):
    html = iniciar_sesion(crear_usuario("admin")).get("/motivos-baja").text
    assert "motivosBaja(" in html and "/static/js/motivos_baja.js?v=" in html
    assert 'href="/stock"' in html


def test_motivos_baja_vendedor_da_403(crear_usuario, iniciar_sesion):
    # Vendedor no tiene STOCK editar (seed.sql): la página, no solo la API, corta con 403.
    respuesta = iniciar_sesion(crear_usuario("vendedor")).get("/motivos-baja")
    assert respuesta.status_code == 403
