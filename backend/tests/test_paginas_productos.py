def test_sidebar_muestra_productos(crear_usuario, iniciar_sesion):
    html = iniciar_sesion(crear_usuario("vendedor")).get("/").text
    assert 'href="/productos"' in html


def test_categorias_admin(crear_usuario, iniciar_sesion):
    html = iniciar_sesion(crear_usuario("admin")).get("/categorias").text
    assert "categoriasArbol(" in html and "/static/js/categorias.js?v=" in html
    assert 'href="/productos"' in html and "Nueva categoría" in html


def test_categorias_solo_consulta(crear_usuario, iniciar_sesion):
    html = iniciar_sesion(crear_usuario("vendedor")).get("/categorias").text
    assert "Nueva categoría" not in html and "puedeEditar: false" in html


def test_listado_admin(crear_usuario, iniciar_sesion):
    html = iniciar_sesion(crear_usuario("admin")).get("/productos").text
    assert "productosListado(" in html and "/static/js/productos.js?v=" in html
    assert "/static/js/producto_form.js?v=" in html and "productoForm(" in html
    assert 'href="/categorias"' in html and "Crear nuevo" in html
    assert "Stock infinito" in html                       # solo Admin


def test_listado_vendedor(crear_usuario, iniciar_sesion):
    html = iniciar_sesion(crear_usuario("vendedor")).get("/productos").text
    assert "Crear nuevo" not in html and "puedeEditar: false" in html and "Stock infinito" not in html
