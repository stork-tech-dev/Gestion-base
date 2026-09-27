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
