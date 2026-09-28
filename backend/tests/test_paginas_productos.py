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


def test_listado_vendedor_sin_rutas_de_proveedores(crear_usuario, iniciar_sesion):
    """La página del Vendedor carga y sus JS no piden GET /api/v1/proveedores
    (le daría 403): usan /api/v1/productos/proveedores."""
    cliente = iniciar_sesion(crear_usuario("vendedor"))
    assert cliente.get("/productos").status_code == 200
    for js in ("productos.js", "producto_form.js"):
        codigo = cliente.get(f"/static/js/{js}").text
        assert "'/api/v1/proveedores" not in codigo and "`/api/v1/proveedores" not in codigo
        assert "/proveedores" in codigo


def test_foto_inicial_solo_si_puede_editar(crear_usuario, iniciar_sesion):
    assert "Foto inicial" in iniciar_sesion(crear_usuario("admin")).get("/productos").text
    assert "Foto inicial" not in iniciar_sesion(crear_usuario("vendedor")).get("/productos").text


def test_temporadas_y_leyenda_de_inactivos(crear_usuario, iniciar_sesion):
    html = iniciar_sesion(crear_usuario("admin")).get("/productos").text
    # Una sola definición (pages.TEMPORADAS): el select del formulario y el listado.
    assert '<option value="otoño_invierno">Otoño-Invierno</option>' in html
    assert "temporadas: [[" in html and "Primavera-Verano" in html
    assert "¿Buscás un producto inactivo? Cambiá el switch a Inactivos." in html


# --- Task 10: stock en el formulario, el listado y la ficha ------------

def test_listado_tiene_stock_0_y_stock_inicial(crear_usuario, iniciar_sesion):
    html = iniciar_sesion(crear_usuario("admin")).get("/productos").text
    assert "Stock 0" in html
    assert "Stock inicial" in html
    assert "puedeStockInicial: true" in html


def test_stock_inicial_oculto_sin_permiso_de_stock(crear_usuario, iniciar_sesion):
    # Vendedor (seed.sql) no tiene STOCK crear: el campo no se muestra ni se manda.
    html = iniciar_sesion(crear_usuario("vendedor")).get("/productos").text
    assert "Stock inicial" not in html
    assert "puedeStockInicial: false" in html


def test_ficha_muestra_link_a_stock_con_permiso(crear_usuario, iniciar_sesion):
    # Admin y Vendedor (seed.sql) tienen STOCK ver: ven el link "Ver en Stock".
    assert "Ver en Stock" in iniciar_sesion(crear_usuario("admin")).get("/productos").text
    assert "Ver en Stock" in iniciar_sesion(crear_usuario("vendedor")).get("/productos").text
