from app.models import UsuarioPermiso
from app.schemas.proveedores import ProveedorCrear
from app.services import proveedores as servicio


def test_hub_muestra_proveedores(crear_usuario, iniciar_sesion):
    html = iniciar_sesion(crear_usuario("supervisor")).get("/configuracion").text
    assert 'href="/proveedores"' in html and "Datos de proveedores nacionales e internacionales" in html


def test_admin_sin_proveedores_en_dolares(crear_usuario, iniciar_sesion):
    html = iniciar_sesion(crear_usuario("admin")).get("/proveedores").text
    assert "proveedoresListado(" in html and "/static/js/proveedores.js?v=" in html
    assert "Crear nuevo" in html and "usaDolar: false" in html
    assert "Cambio masivo del dólar" not in html and "Dólar desde" not in html


def test_admin_con_proveedores_en_dolares(crear_usuario, iniciar_sesion, db):
    admin = crear_usuario("admin")
    servicio.crear_proveedor(db, admin, ProveedorCrear(nombre="Importadora", moneda="usd", dolar_actual="1000"), None)
    html = iniciar_sesion(admin).get("/proveedores").text
    assert "usaDolar: true" in html and 'href="/proveedores/dolar-masivo"' in html and "Dólar desde" in html


def test_supervisor_solo_consulta(crear_usuario, iniciar_sesion):
    html = iniciar_sesion(crear_usuario("supervisor")).get("/proveedores").text
    assert "Crear nuevo" not in html and "puedeEditar: false" in html


def test_vendedor_no_entra(crear_usuario, iniciar_sesion):
    assert iniciar_sesion(crear_usuario("vendedor")).get("/proveedores").status_code == 403


def test_dolar_masivo_sin_proveedores_en_dolares(crear_usuario, iniciar_sesion):
    html = iniciar_sesion(crear_usuario("admin")).get("/proveedores/dolar-masivo").text
    assert "No hay proveedores que trabajen en dólares." in html and "dolarMasivo()" not in html


def test_dolar_masivo_con_proveedores(crear_usuario, iniciar_sesion, db):
    admin = crear_usuario("admin")
    servicio.crear_proveedor(db, admin, ProveedorCrear(nombre="Importadora", moneda="usd", dolar_actual="1000"), None)
    html = iniciar_sesion(admin).get("/proveedores/dolar-masivo").text
    assert 'x-data="dolarMasivo()"' in html and "/static/js/dolar_masivo.js?v=" in html
    assert 'href="/api/v1/proveedores/dolar/plantilla"' in html and "Vista previa" in html
    assert 'href="/proveedores"' in html  # volver


def test_supervisor_no_entra_al_masivo(crear_usuario, iniciar_sesion):
    assert iniciar_sesion(crear_usuario("supervisor")).get("/proveedores/dolar-masivo").status_code == 403


def test_permiso_puntual_entra_al_masivo(crear_usuario, iniciar_sesion, db):
    """Un usuario con SOLO el permiso puntual del cambio masivo (sin "ver"
    proveedores) también puede entrar a la pantalla: no depende de GET
    /proveedores para listar los proveedores en dólares."""
    admin = crear_usuario("admin")
    servicio.crear_proveedor(db, admin, ProveedorCrear(nombre="Importadora", moneda="usd", dolar_actual="1000"), None)
    vendedor = crear_usuario("vendedor")
    db.add(UsuarioPermiso(usuario_id=vendedor.id, modulo="proveedores", recurso="dolar.cambio_masivo", puede_editar=True))
    db.flush()
    assert iniciar_sesion(vendedor).get("/proveedores/dolar-masivo").status_code == 200


def test_masivo_con_solo_el_permiso_puntual_vuelve_al_hub(crear_usuario, iniciar_sesion, db):
    """Sin "ver" proveedores, /proveedores le da 403: el volver apunta a /configuracion."""
    vendedor = crear_usuario("vendedor")
    db.add(UsuarioPermiso(usuario_id=vendedor.id, modulo="proveedores", recurso="dolar.cambio_masivo", puede_editar=True))
    db.flush()
    html = iniciar_sesion(vendedor).get("/proveedores/dolar-masivo").text
    assert "Volver a Configuraciones" in html and 'href="/configuracion"' in html
    assert 'href="/proveedores"' not in html
