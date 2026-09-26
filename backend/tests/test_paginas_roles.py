def test_admin_ve_roles(crear_usuario, iniciar_sesion):
    r = iniciar_sesion(crear_usuario("admin")).get("/roles")
    assert r.status_code == 200
    assert 'x-data="rolesListado()"' in r.text and "/static/js/roles.js?v=" in r.text
    assert "Tipo (todos)" in r.text and "Limpiar filtros" in r.text


def test_supervisor_no_ve_roles(crear_usuario, iniciar_sesion):
    r = iniciar_sesion(crear_usuario("supervisor")).get("/roles")
    assert r.status_code == 403
