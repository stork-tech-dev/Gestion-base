"""Tablero de inicio (/): cada bloque se renderiza solo con su permiso; los
datos los carga cada bloque desde su API (inicio.js)."""
from app.models import Rol, RolPermiso
from app.services import ventas as servicio_ventas
from tests.fabricas import abrir_turno_de_test


def _html(iniciar_sesion, usuario):
    r = iniciar_sesion(usuario).get("/")
    assert r.status_code == 200
    return r.text


def test_admin_ve_los_tres_bloques_y_los_accesos(crear_usuario, iniciar_sesion):
    html = _html(iniciar_sesion, crear_usuario("admin", nombre="Ana"))
    assert "Bienvenido, Ana" in html and "/static/js/inicio.js" in html
    assert 'id="inicio-caja"' in html and 'id="inicio-ventas"' in html and 'id="inicio-stock"' in html
    for url in ("/ventas/nueva", "/productos", "/gestion-de-stock", "/caja"):
        assert f'href="{url}"' in html
    assert 'href="/stock?solo_bajo_minimo=1"' in html
    assert 'href="/reportes/ventas-periodo"' in html


def test_vendedor_no_ve_ventas_de_hoy(crear_usuario, iniciar_sesion):
    # El vendedor no tiene REPORTES ver (seed.sql): la tarjeta ni se renderiza.
    html = _html(iniciar_sesion, crear_usuario("vendedor"))
    assert 'id="inicio-caja"' in html and 'id="inicio-stock"' in html
    assert 'id="inicio-ventas"' not in html
    assert 'href="/ventas/nueva"' in html


def test_rol_sin_permisos_solo_ve_el_saludo(db, crear_usuario, iniciar_sesion):
    rol = Rol(nombre="sin permisos inicio", es_sistema=False)
    db.add(rol)
    db.flush()
    html = _html(iniciar_sesion, crear_usuario(rol, nombre="Beto"))
    assert "Bienvenido, Beto" in html
    assert 'id="inicio-caja"' not in html and 'id="inicio-ventas"' not in html and 'id="inicio-stock"' not in html
    assert 'aria-label="Accesos rápidos"' not in html


def test_acceso_continuar_venta_si_hay_una_en_curso(db, crear_usuario, iniciar_sesion):
    vendedor = crear_usuario("vendedor")
    abrir_turno_de_test(db, crear_usuario("admin"))
    venta = servicio_ventas.iniciar_venta(db, vendedor, None)
    html = _html(iniciar_sesion, vendedor)
    assert f"Continuar venta {venta.numero}" in html


def test_stock_con_filtro_bajo_minimo_desde_el_link(crear_usuario, iniciar_sesion):
    cliente = iniciar_sesion(crear_usuario("admin"))
    assert "soloBajoMinimoInicial: true" in cliente.get("/stock?solo_bajo_minimo=1").text
    assert "soloBajoMinimoInicial: false" in cliente.get("/stock").text


def test_boton_cerrar_turno_solo_con_el_permiso_de_arqueo(db, crear_usuario, iniciar_sesion):
    # El Admin tiene todos los permisos: ve el botón "Cerrar turno" del bloque
    # de Caja (dentro del template Alpine, gateado en el servidor por
    # puede_cerrar_turno). Un rol con solo CAJA ver (sin CAJA_ARQUEO crear) ve
    # el bloque pero no el botón.
    html_admin = _html(iniciar_sesion, crear_usuario("admin"))
    assert "Cerrar turno" in html_admin and "/caja/cerrar/" in html_admin

    rol = Rol(nombre="solo ve caja", es_sistema=False)
    db.add(rol)
    db.flush()
    db.add(RolPermiso(rol_id=rol.id, modulo="caja", recurso=None, puede_ver=True))
    db.flush()
    html = _html(iniciar_sesion, crear_usuario(rol))
    assert 'id="inicio-caja"' in html
    assert "Cerrar turno" not in html and "/caja/cerrar/" not in html
