"""Páginas HTML de la sesión de Ventas construidas en la Task 6: /clientes
(ítem propio del sidebar) y los tres catálogos de configuración registrados
en bucle (`_CATALOGOS_VENTAS`): /medios-de-pago, /motivos-descuento y
/promociones; las de la Task 7: el hub /ventas y la pantalla /ventas/nueva; y
la de la Task 8: /ventas/resumen-ventas (listado + detalle + anulación).
La visibilidad usa la misma barrera que la API
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


# --- Hub /ventas y /ventas/nueva (Task 7) -----------------------------------------

def test_sidebar_muestra_ventas_al_vendedor(crear_usuario, iniciar_sesion):
    # Vendedor tiene VENTAS ver + crear (seed.sql).
    html = iniciar_sesion(crear_usuario("vendedor")).get("/").text
    assert 'href="/ventas"' in html and ">Ventas<" in html


def test_hub_ventas_muestra_las_dos_tarjetas(crear_usuario, iniciar_sesion):
    html = iniciar_sesion(crear_usuario("vendedor")).get("/ventas").text
    assert 'href="/ventas/nueva"' in html and "Nueva venta" in html
    assert 'title="Cargar productos, aplicar descuentos y cobrar"' in html
    assert 'href="/ventas/resumen-ventas"' in html and "Resumen de Ventas" in html
    assert 'title="Ventas del período con subtotal, descuento, total y medio de pago"' in html


def test_hub_ventas_con_venta_en_curso_dice_continuar(db, crear_usuario, iniciar_sesion):
    from app.api.pages import SECCION_NUEVA_VENTA
    from app.services import ventas as servicio_ventas
    usuario = crear_usuario("vendedor")
    venta = servicio_ventas.iniciar_venta(db, usuario, None)
    html = iniciar_sesion(usuario).get("/ventas").text
    assert f"Continuar venta {venta.numero}" in html
    assert venta.numero.startswith("V-")
    # La constante compartida no se muta.
    assert SECCION_NUEVA_VENTA["nombre"] == "Nueva venta"


def test_hub_ventas_sin_permiso_da_403(db, crear_usuario, iniciar_sesion):
    respuesta = iniciar_sesion(_sin_permisos(db, crear_usuario)).get("/ventas")
    assert respuesta.status_code == 403


def test_venta_nueva_vendedor(db, crear_usuario, iniciar_sesion):
    from decimal import Decimal

    from app.services import turnos as servicio_turnos

    vendedor = crear_usuario("vendedor")
    # `hay_turno` sale de services.turnos (sesión 07): sin turno abierto de
    # hoy daría False, así que se abre uno para probar el resto del contexto.
    servicio_turnos.abrir_turno(db, vendedor, Decimal("0"), None, None)
    html = iniciar_sesion(vendedor).get("/ventas/nueva").text
    assert "ventaPantalla(" in html and "/static/js/venta.js?v=" in html
    assert "/static/js/cliente_form.js?v=" in html
    # Vendedor: venta.descuento (seed.sql) y CLIENTES ver + crear.
    assert "puedeDescontar: true" in html
    assert "puedeVerClientes: true" in html and "puedeCrearCliente: true" in html
    assert "hayTurno: true" in html
    assert 'href="/ventas"' in html


def test_venta_nueva_sin_ventas_crear_da_403(client, crear_usuario, iniciar_sesion, headers_de):
    # Rol con VENTAS ver solamente: ve el hub pero no la pantalla de venta.
    admin = crear_usuario("admin")
    h = headers_de(admin)
    r = client.post("/api/v1/roles", json={"nombre": "Solo mira ventas"}, headers=h)
    assert r.status_code == 201
    r = client.put(f"/api/v1/roles/{r.json()['id']}/permisos",
                   json={"permisos": [{"modulo": "ventas", "recurso": None, "puede_ver": True}]}, headers=h)
    assert r.status_code == 200
    sesion = iniciar_sesion(crear_usuario("Solo mira ventas"))
    assert sesion.get("/ventas/nueva").status_code == 403
    html = sesion.get("/ventas").text
    assert 'href="/ventas/nueva"' not in html
    assert 'href="/ventas/resumen-ventas"' in html


# --- /ventas/resumen-ventas (Task 8) -----------------------------------------------

def test_resumen_ventas_vendedor(crear_usuario, iniciar_sesion):
    html = iniciar_sesion(crear_usuario("vendedor")).get("/ventas/resumen-ventas").text
    assert "ventasResumen(" in html and "/static/js/ventas.js?v=" in html
    assert 'href="/ventas"' in html
    # Vendedor: VENTAS ver + crear, sin venta.anular (seed.sql: solo el
    # supervisor tiene el override puntual de ese recurso).
    assert "puedeAnular: false" in html


def test_resumen_ventas_supervisor_puede_anular(crear_usuario, iniciar_sesion):
    # Supervisor: VENTAS ver (general) + venta.anular (recurso puntual, seed.sql).
    html = iniciar_sesion(crear_usuario("supervisor")).get("/ventas/resumen-ventas").text
    assert "puedeAnular: true" in html


def test_resumen_ventas_admin_puede_anular(crear_usuario, iniciar_sesion):
    html = iniciar_sesion(crear_usuario("admin")).get("/ventas/resumen-ventas").text
    assert "puedeAnular: true" in html


def test_resumen_ventas_pasa_el_cliente_id_de_la_query(crear_usuario, iniciar_sesion):
    # Enlace desde la ficha del cliente ("Ver compras"): no es un filtro
    # persistido, solo el valor inicial del chip quitable.
    sesion = iniciar_sesion(crear_usuario("vendedor"))
    html = sesion.get("/ventas/resumen-ventas?cliente_id=42").text
    assert "clienteIdInicial: 42" in html
    html_sin_query = sesion.get("/ventas/resumen-ventas").text
    assert "clienteIdInicial: null" in html_sin_query


def test_resumen_ventas_sin_permiso_da_403(db, crear_usuario, iniciar_sesion):
    respuesta = iniciar_sesion(_sin_permisos(db, crear_usuario)).get("/ventas/resumen-ventas")
    assert respuesta.status_code == 403
