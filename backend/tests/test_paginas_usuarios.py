def test_admin_ve_la_pantalla_de_usuarios(crear_usuario, iniciar_sesion):
    r = iniciar_sesion(crear_usuario("admin")).get("/usuarios")
    assert r.status_code == 200
    html = r.text
    assert "usuariosListado(" in html and "/static/js/usuarios.js?v=" in html
    assert "Crear nuevo" in html
    assert 'href="/configuracion"' in html  # volver a Configuraciones
    assert "Accesos permitidos:" in html
    assert "&#34;supervisor&#34;" in html  # roles del filtro (todos, para el Admin)


def test_supervisor_ve_solo_vendedores_como_gestionables(crear_usuario, iniciar_sesion):
    html = iniciar_sesion(crear_usuario("supervisor")).get("/usuarios").text
    assert "rolesGestionables: [&#34;vendedor&#34;]" in html


def test_vendedor_no_entra_a_usuarios(crear_usuario, iniciar_sesion):
    r = iniciar_sesion(crear_usuario("vendedor")).get("/usuarios")
    assert r.status_code == 403 and "No tenés permiso" in r.text


def test_historial_de_accesos(crear_usuario, iniciar_sesion):
    vendedor = crear_usuario("vendedor", nombre="Hugo")
    html = iniciar_sesion(crear_usuario("admin")).get(f"/usuarios/{vendedor.id}/historial").text
    assert "Historial de accesos de Hugo" in html
    assert f"historialAccesos({vendedor.id})" in html and "/static/js/historial.js?v=" in html
    assert "Resultado (todos)" in html


def test_formulario_de_usuario_protege_los_accesos(crear_usuario, iniciar_sesion):
    html = iniciar_sesion(crear_usuario("admin")).get("/usuarios").text
    # No se puede guardar hasta conocer los accesos (evita mandar accesos: []).
    assert 'guardando || !accesosCargados' in html
    # En la edición, el rol no se puede cambiar hasta que lleguen los accesos del usuario
    # (solo la carga inicial: si falla la carga de un rol nuevo, se puede volver a elegir).
    assert ':disabled="form.id &amp;&amp; !_cargaInicialLista"' in html
    # La contraseña es obligatoria solo en el alta.
    assert 'x-show="!form.id">*</span>' in html
