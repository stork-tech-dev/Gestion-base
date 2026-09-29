"""Pantalla /importacion (sesión 08)."""


def test_admin_ve_la_pantalla_y_la_tarjeta(iniciar_sesion, crear_usuario):
    cliente = iniciar_sesion(crear_usuario("admin"))
    r = cliente.get("/importacion")
    assert r.status_code == 200
    assert "Importar desde Excel" in r.text and "/static/js/importacion.js" in r.text
    assert 'href="/importacion"' in cliente.get("/configuracion").text


def test_sin_permiso_no_ve_la_pantalla_ni_la_tarjeta(iniciar_sesion, crear_usuario):
    cliente = iniciar_sesion(crear_usuario("vendedor"))
    assert cliente.get("/importacion").status_code == 403
    assert 'href="/importacion"' not in cliente.get("/configuracion").text
