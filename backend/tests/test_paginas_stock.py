"""Páginas HTML del módulo de stock: hub "Gestión de Stock", /stock,
/motivos-baja (Tasks 7 y 8) y /auditorias-inventario (Task 9). La
visibilidad usa la misma barrera que la API (resolver_permiso); acá solo se
verifica que el layout arme lo esperado."""
from app.schemas.stock import AuditoriaIniciar
from app.services import auditoria_inventario as servicio_auditorias


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


# --- Task 9: auditorías de stock (listado y conteo) --------------------

def test_listado_auditorias_vendedor_ve_iniciar_conteo(crear_usuario, iniciar_sesion):
    # Vendedor tiene STOCK_AUDITORIA crear (seed.sql): ve el botón de iniciar conteo.
    html = iniciar_sesion(crear_usuario("vendedor")).get("/auditorias-inventario").text
    assert "auditoriasListado(" in html and "/static/js/auditorias.js?v=" in html
    assert "Iniciar conteo" in html
    assert "puedeAuditar: true" in html


def test_auditorias_volver_al_hub(crear_usuario, iniciar_sesion):
    html = iniciar_sesion(crear_usuario("admin")).get("/auditorias-inventario").text
    assert 'href="/gestion-de-stock"' in html


def test_pantalla_de_conteo_de_una_auditoria_existente(db, crear_usuario, iniciar_sesion):
    admin = crear_usuario("admin")
    auditoria = servicio_auditorias.iniciar(db, admin, AuditoriaIniciar(notas="Conteo de prueba"), None)
    html = iniciar_sesion(crear_usuario("vendedor")).get(f"/auditorias-inventario/{auditoria.id}").text
    assert "auditoriaConteo(" in html and "/static/js/auditorias.js?v=" in html
    assert f"id: {auditoria.id}" in html
    assert "puedeAuditar: true" in html


def test_pantalla_de_conteo_id_inexistente_da_404(crear_usuario, iniciar_sesion):
    respuesta = iniciar_sesion(crear_usuario("admin")).get("/auditorias-inventario/999999")
    assert respuesta.status_code == 404
    assert "text/html" in respuesta.headers["content-type"]
