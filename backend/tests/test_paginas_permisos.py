from sqlalchemy import select

from app.models import Rol


def _rol_id(db, nombre):
    return db.scalar(select(Rol.id).where(Rol.nombre == nombre))


def test_permisos_de_un_rol(crear_usuario, iniciar_sesion, db):
    rol_id = _rol_id(db, "vendedor")
    html = iniciar_sesion(crear_usuario("admin")).get(f"/roles/{rol_id}/permisos").text
    assert "arbolPermisos(" in html and f"/api/v1/roles/{rol_id}/permisos" in html
    assert "Guardar permisos" in html and "Expandir todo" in html
    assert "/static/js/permisos.js?v=" in html


def test_permisos_del_rol_admin_son_de_solo_lectura(crear_usuario, iniciar_sesion, db):
    html = iniciar_sesion(crear_usuario("admin")).get(f"/roles/{_rol_id(db, 'admin')}/permisos").text
    assert "tiene acceso total" in html and "editable: false" in html


def test_permisos_de_un_usuario(crear_usuario, iniciar_sesion):
    vendedor = crear_usuario("vendedor", nombre="Vera")
    html = iniciar_sesion(crear_usuario("supervisor")).get(f"/usuarios/{vendedor.id}/permisos").text
    assert "Permisos de Vera" in html and "&#34;usuario&#34;" in html and "editable: true" in html


def test_supervisor_ve_pero_no_edita_a_otro_supervisor(crear_usuario, iniciar_sesion):
    otro = crear_usuario("supervisor")
    html = iniciar_sesion(crear_usuario("supervisor")).get(f"/usuarios/{otro.id}/permisos").text
    assert "editable: false" in html


def test_vendedor_no_entra(crear_usuario, iniciar_sesion, db):
    cliente = iniciar_sesion(crear_usuario("vendedor"))
    assert cliente.get(f"/roles/{_rol_id(db, 'vendedor')}/permisos").status_code == 403


def test_permisos_de_usuario_inexistente_da_pagina_404(crear_usuario, iniciar_sesion):
    r = iniciar_sesion(crear_usuario("admin")).get("/usuarios/999999/permisos")
    assert r.status_code == 404
    assert "text/html" in r.headers["content-type"]
    assert "No encontrado" in r.text


def test_historial_y_permisos_de_rol_inexistentes_dan_pagina_404(crear_usuario, iniciar_sesion):
    cliente = iniciar_sesion(crear_usuario("admin"))
    for url in ("/usuarios/999999/historial", "/roles/999999/permisos"):
        r = cliente.get(url)
        assert r.status_code == 404 and "text/html" in r.headers["content-type"], url
        assert "No encontrado" in r.text, url
