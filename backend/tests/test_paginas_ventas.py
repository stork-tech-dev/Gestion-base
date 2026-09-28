"""Páginas HTML de la sesión de Ventas construidas en la Task 6: /clientes
(ítem propio del sidebar) y los tres catálogos de configuración registrados
en bucle (`_CATALOGOS_VENTAS`): /medios-de-pago, /motivos-descuento y
/promociones. La visibilidad usa la misma barrera que la API
(resolver_permiso); acá solo se verifica que el layout arme lo esperado."""
from app.models import Rol


def _sin_permisos(db, crear_usuario):
    """Usuario con un rol de sistema propio, sin ninguna fila en rol_permisos:
    sirve para probar el 403 de páginas que todos los roles sembrados pueden ver."""
    rol = Rol(nombre="sin permisos ventas", es_sistema=False)
    db.add(rol)
    db.flush()
    return crear_usuario(rol)


# --- Sidebar y hub Configuraciones --------------------------------------------

def test_sidebar_muestra_clientes_al_vendedor(crear_usuario, iniciar_sesion):
    # Vendedor tiene CLIENTES ver (seed.sql).
    html = iniciar_sesion(crear_usuario("vendedor")).get("/").text
    assert 'href="/clientes"' in html


def test_hub_admin_muestra_las_tres_tarjetas_de_ventas(crear_usuario, iniciar_sesion):
    html = iniciar_sesion(crear_usuario("admin")).get("/configuracion").text
    assert 'href="/medios-de-pago"' in html and "Medios de pago" in html
    assert 'href="/motivos-descuento"' in html and "Motivos de descuento" in html
    assert 'href="/promociones"' in html and "Promociones" in html


def test_hub_vendedor_no_ve_promociones(crear_usuario, iniciar_sesion):
    # El vendedor no tiene configuracion.promociones ni configuracion ver (seed.sql).
    html = iniciar_sesion(crear_usuario("vendedor")).get("/configuracion").text
    assert 'href="/promociones"' not in html
    assert 'href="/medios-de-pago"' not in html
    assert 'href="/motivos-descuento"' not in html


def test_hub_supervisor_ve_solo_promociones(crear_usuario, iniciar_sesion):
    # El supervisor tiene configuracion.promociones ver/crear/editar pero no
    # configuracion ver general (seed.sql): ve Promociones, no los otros dos.
    html = iniciar_sesion(crear_usuario("supervisor")).get("/configuracion").text
    assert 'href="/promociones"' in html
    assert 'href="/medios-de-pago"' not in html
    assert 'href="/motivos-descuento"' not in html


# --- /clientes -----------------------------------------------------------------

def test_clientes_admin(crear_usuario, iniciar_sesion):
    html = iniciar_sesion(crear_usuario("admin")).get("/clientes").text
    assert "clientesListado(" in html and "/static/js/clientes.js?v=" in html
    assert "puedeCrear: true" in html and "puedeEditar: true" in html


def test_clientes_vendedor_ve_crear_pero_no_editar(crear_usuario, iniciar_sesion):
    # Vendedor tiene CLIENTES ver + crear, no editar (seed.sql).
    html = iniciar_sesion(crear_usuario("vendedor")).get("/clientes").text
    assert "puedeCrear: true" in html
    assert "puedeEditar: false" in html


def test_clientes_sin_permiso_da_403(db, crear_usuario, iniciar_sesion):
    respuesta = iniciar_sesion(_sin_permisos(db, crear_usuario)).get("/clientes")
    assert respuesta.status_code == 403


# --- /medios-de-pago -------------------------------------------------------------

def test_medios_de_pago_admin(crear_usuario, iniciar_sesion):
    html = iniciar_sesion(crear_usuario("admin")).get("/medios-de-pago").text
    assert "mediosPagoListado(" in html and "/static/js/medios_pago.js?v=" in html
    assert 'href="/configuracion"' in html


def test_medios_de_pago_vendedor_da_403(crear_usuario, iniciar_sesion):
    # El vendedor no tiene CONFIGURACION ver (seed.sql).
    respuesta = iniciar_sesion(crear_usuario("vendedor")).get("/medios-de-pago")
    assert respuesta.status_code == 403


# --- /motivos-descuento -----------------------------------------------------------

def test_motivos_descuento_admin(crear_usuario, iniciar_sesion):
    html = iniciar_sesion(crear_usuario("admin")).get("/motivos-descuento").text
    assert "motivosDescuentoListado(" in html and "/static/js/motivos_descuento.js?v=" in html
    # porcentajes_descuento sale de configuracion_sistema.tope_descuento_venta
    # (seed: 50.00), de 5 en 5: services.descuentos.porcentajes_validos.
    assert "porcentajesDescuento: [5, 10, 15, 20, 25, 30, 35, 40, 45, 50]" in html


def test_motivos_descuento_vendedor_da_403(crear_usuario, iniciar_sesion):
    respuesta = iniciar_sesion(crear_usuario("vendedor")).get("/motivos-descuento")
    assert respuesta.status_code == 403


# --- /promociones ------------------------------------------------------------------

def test_promociones_admin(crear_usuario, iniciar_sesion):
    html = iniciar_sesion(crear_usuario("admin")).get("/promociones").text
    assert "promocionesListado(" in html and "/static/js/promociones.js?v=" in html


def test_promociones_supervisor_puede_ver_y_editar(crear_usuario, iniciar_sesion):
    # Supervisor tiene configuracion.promociones ver/crear/editar (seed.sql).
    html = iniciar_sesion(crear_usuario("supervisor")).get("/promociones").text
    assert "puedeEditar: true" in html


def test_promociones_vendedor_da_403(crear_usuario, iniciar_sesion):
    respuesta = iniciar_sesion(crear_usuario("vendedor")).get("/promociones")
    assert respuesta.status_code == 403
