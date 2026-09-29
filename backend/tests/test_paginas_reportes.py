"""Pantallas de Reportes (sesión 09): ítem del sidebar, hub y pantalla genérica."""
from app.api.pages import MENU_SIDEBAR

CLAVES = ("ventas-periodo", "medios-pago", "vendedores", "productos-vendidos", "rentabilidad", "stock-valorizado")


def test_reportes_va_entre_caja_y_configuraciones():
    urls = [item["url"] for item in MENU_SIDEBAR]
    assert urls[urls.index("/caja") + 1] == "/reportes"
    assert urls[urls.index("/reportes") + 1] == "/configuracion"


def test_admin_ve_el_item_y_el_hub_con_los_seis_reportes(crear_usuario, iniciar_sesion):
    cliente = iniciar_sesion(crear_usuario("admin"))
    assert 'href="/reportes"' in cliente.get("/").text
    html = cliente.get("/reportes").text
    for clave in CLAVES:
        assert f'href="/reportes/{clave}"' in html


def test_supervisor_ve_la_pantalla_de_un_reporte(crear_usuario, iniciar_sesion):
    r = iniciar_sesion(crear_usuario("supervisor")).get("/reportes/rentabilidad")
    assert r.status_code == 200
    assert "Rentabilidad" in r.text and "/static/js/reporte.js" in r.text
    assert 'id="reporte-proveedor"' in r.text and 'id="reporte-categoria"' in r.text


def test_vendedor_no_ve_reportes(crear_usuario, iniciar_sesion):
    cliente = iniciar_sesion(crear_usuario("vendedor"))
    assert 'href="/reportes"' not in cliente.get("/").text
    assert cliente.get("/reportes").status_code == 403
    assert cliente.get("/reportes/rentabilidad").status_code == 403


def test_reporte_inexistente_404(crear_usuario, iniciar_sesion):
    assert iniciar_sesion(crear_usuario("admin")).get("/reportes/no-existe").status_code == 404


def test_la_pantalla_muestra_solo_los_filtros_que_admite(crear_usuario, iniciar_sesion):
    cliente = iniciar_sesion(crear_usuario("admin"))
    periodo = cliente.get("/reportes/ventas-periodo").text
    assert 'id="reporte-desde"' in periodo and 'id="reporte-agrupar"' in periodo
    assert 'id="reporte-proveedor"' not in periodo and 'id="reporte-limite"' not in periodo
    stock = cliente.get("/reportes/stock-valorizado").text
    assert 'id="reporte-desde"' not in stock and 'id="reporte-nivel"' in stock
    medios = cliente.get("/reportes/medios-pago").text
    assert 'id="reporte-vendedor"' in medios and 'id="reporte-medio"' in medios
