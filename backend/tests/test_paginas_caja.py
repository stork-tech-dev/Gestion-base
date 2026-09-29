"""Páginas de Caja (sesión 07)."""
from decimal import Decimal

from app.core.utils import ahora_db
from app.models import EstadoTurno
from app.services import turnos as servicio_turnos


def test_caja_visible_para_vendedor_y_en_el_menu(crear_usuario, iniciar_sesion):
    cliente = iniciar_sesion(crear_usuario("vendedor"))
    r = cliente.get("/caja")
    assert r.status_code == 200 and 'href="/caja"' in r.text and "cajaPantalla" in r.text


def test_cerrar_turno_abierto(db, crear_usuario, iniciar_sesion):
    vendedor = crear_usuario("vendedor")
    turno = servicio_turnos.abrir_turno(db, vendedor, Decimal("0"), None, None)
    r = iniciar_sesion(vendedor).get(f"/caja/cerrar/{turno.id}")
    assert r.status_code == 200 and "Completá las novedades de caja" in r.text


def test_cerrar_turno_cerrado_redirige_a_caja(db, crear_usuario, iniciar_sesion):
    admin = crear_usuario("admin")
    turno = servicio_turnos.abrir_turno(db, admin, Decimal("0"), None, None)
    turno.estado, turno.fecha_cierre, turno.usuario_cierre_id = EstadoTurno.CERRADO, ahora_db(), admin.id
    db.flush()
    r = iniciar_sesion(admin).get(f"/caja/cerrar/{turno.id}", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/caja"


def test_cerrar_turno_inexistente_404(crear_usuario, iniciar_sesion):
    assert iniciar_sesion(crear_usuario("admin")).get("/caja/cerrar/999999").status_code == 404


def test_venta_nueva_sin_turno_avisa(crear_usuario, iniciar_sesion):
    r = iniciar_sesion(crear_usuario("vendedor")).get("/ventas/nueva")
    assert "hayTurno: false" in r.text


def test_venta_nueva_con_turno_de_hoy(db, crear_usuario, iniciar_sesion):
    vendedor = crear_usuario("vendedor")
    servicio_turnos.abrir_turno(db, vendedor, Decimal("0"), None, None)
    assert "hayTurno: true" in iniciar_sesion(vendedor).get("/ventas/nueva").text


def test_campanita_habilitada(crear_usuario, iniciar_sesion):
    r = iniciar_sesion(crear_usuario("vendedor")).get("/")
    assert "notificaciones()" in r.text and "Notificaciones (próximamente)" not in r.text
