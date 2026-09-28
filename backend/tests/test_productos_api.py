import pytest
from sqlalchemy import select

from app.models import ConfiguracionSistema

URL = "/api/v1/productos"
JPG = b"\xff\xd8\xff\xe0" + b"0" * 100


def _base(client, h, db):
    fila = db.scalar(select(ConfiguracionSistema))
    fila.redondeo = 100
    db.flush()
    raiz = client.post("/api/v1/categorias", json={"nombre": "Ropa API"}, headers=h).json()
    hoja = client.post("/api/v1/categorias", json={"nombre": "Remeras API", "parent_id": raiz["id"]}, headers=h).json()
    prov = client.post("/api/v1/proveedores", json={"nombre": "Prov API", "moneda": "usd", "dolar_actual": "1000"},
                       headers=h).json()
    return hoja, prov


def _alta(client, h, hoja, prov, **extra):
    datos = {"categoria_id": hoja["id"], "proveedor_id": prov["id"], "costo": "10", "margen": "0",
             "descripcion": "remera api"}
    datos.update(extra)
    return client.post(URL, json=datos, headers=h)


def test_alta_listado_detalle_y_edicion(client, crear_usuario, headers_de, db):
    h = headers_de(crear_usuario("admin"))
    hoja, prov = _base(client, h, db)
    r = _alta(client, h, hoja, prov)
    assert r.status_code == 201
    p = r.json()
    assert p["precio_venta"] == "10000.00" and p["moneda"] == "usd" and p["categoria"]["camino"] == "Ropa API > Remeras API"
    assert p["descripcion"] == "Remera api" and len(p["codigo_con_verificador"]) == 6
    lista = client.get(URL, params={"busqueda": p["codigo_con_verificador"]}, headers=h).json()
    assert lista["total"] == 1 and lista["resultados"][0]["id"] == p["id"]
    detalle = client.get(f"{URL}/{p['id']}", headers=h).json()
    assert detalle["fotos"] == []
    r = client.put(f"{URL}/{p['id']}", json={"categoria_id": hoja["id"], "costo": "20", "margen": "10",
                                            "descripcion": "Remera api"}, headers=h)
    assert r.status_code == 200 and r.json()["precio_venta"] == "22000.00"
    assert client.patch(f"{URL}/{p['id']}/estado", json={"activo": False}, headers=h).json()["activo"] is False
    assert client.get(f"{URL}/999999", headers=h).status_code == 404


def test_rutas_fijas(client, crear_usuario, headers_de, db):
    h = headers_de(crear_usuario("admin"))
    hoja, prov = _base(client, h, db)
    p = _alta(client, h, hoja, prov, descripcion="Remera lisa roja grande").json()
    vista = client.get(f"{URL}/precio-preview", params={"proveedor_id": prov["id"], "costo": "10.01", "margen": "10"},
                       headers=h).json()
    assert vista == {"moneda": "usd", "dolar_proveedor": "1000.00", "precio_venta": "11100.00"}
    similares = client.get(f"{URL}/similares", params={"descripcion": "remera lisa roja", "proveedor_id": prov["id"]},
                           headers=h).json()
    assert similares[0]["id"] == p["id"]
    assert client.get(f"{URL}/por-codigo", params={"codigo": p["codigo_con_verificador"]}, headers=h).json()["id"] == p["id"]
    assert client.get(f"{URL}/por-codigo", params={"codigo": "ZZ999"}, headers=h).status_code == 404
    r = client.get(f"{URL}/{p['id']}/barcode", headers=h)
    assert r.status_code == 200 and r.headers["content-type"].startswith("image/svg+xml")


def test_fotos_y_etiquetas(client, crear_usuario, headers_de, db):
    h = headers_de(crear_usuario("admin"))
    hoja, prov = _base(client, h, db)
    p = _alta(client, h, hoja, prov).json()
    r = client.post(f"{URL}/{p['id']}/fotos", files={"archivo": ("x.jpg", JPG, "image/jpeg")}, headers=h)
    assert r.status_code == 201 and r.json()["es_principal"]
    segunda = client.post(f"{URL}/{p['id']}/fotos", files={"archivo": ("y.png", JPG, "image/png")}, headers=h).json()
    assert client.patch(f"{URL}/fotos/{segunda['id']}/principal", headers=h).json()["es_principal"]
    assert client.delete(f"{URL}/fotos/{segunda['id']}", headers=h).status_code == 204
    assert client.get(f"{URL}/{p['id']}", headers=h).json()["fotos"][0]["es_principal"]
    r = client.post(f"{URL}/etiquetas", json={"items": [{"producto_id": p["id"], "cantidad": 2}], "tipo": "colita"},
                    headers=h)
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert r.headers["content-disposition"].startswith("inline") and r.content.startswith(b"%PDF")
    assert client.post(f"{URL}/etiquetas", json={"items": [{"producto_id": p["id"], "cantidad": 0}], "tipo": "colita"},
                       headers=h).status_code == 422


def test_permisos(client, crear_usuario, headers_de, db):
    admin = headers_de(crear_usuario("admin"))
    hoja, prov = _base(client, admin, db)
    p = _alta(client, admin, hoja, prov).json()
    vendedor = headers_de(crear_usuario("vendedor"))
    assert client.get(URL, headers=vendedor).status_code == 200
    assert _alta(client, vendedor, hoja, prov, descripcion="Otra").status_code == 403
    assert client.patch(f"{URL}/{p['id']}/estado", json={"activo": False}, headers=vendedor).status_code == 403
    assert client.post(f"{URL}/etiquetas", json={"items": [{"producto_id": p["id"], "cantidad": 1}],
                                                  "tipo": "rectangular"}, headers=vendedor).status_code == 200


# ---------- Revisión final del módulo 04 ----------

def _prov(client, h, nombre, moneda="usd", dolar="1000"):
    datos = {"nombre": nombre, "moneda": moneda}
    if moneda == "usd":
        datos["dolar_actual"] = dolar
    return client.post("/api/v1/proveedores", json=datos, headers=h).json()


def _precio(client, h, producto):
    return client.get(f"{URL}/{producto['id']}", headers=h).json()["precio_venta"]


def _xlsx(filas):
    from io import BytesIO

    from openpyxl import Workbook

    libro = Workbook()
    for fila in filas:
        libro.active.append(fila)
    salida = BytesIO()
    libro.save(salida)
    return salida.getvalue()


def test_proveedores_para_productos_con_vendedor(client, crear_usuario, headers_de, db):
    """El Vendedor no tiene PROVEEDORES ver: la pantalla de productos usa
    GET /productos/proveedores (PRODUCTOS ver), sin datos de contacto."""
    admin = headers_de(crear_usuario("admin"))
    activo = _prov(client, admin, "Zeta para productos", moneda="ars")
    inactivo = _prov(client, admin, "Alfa para productos", moneda="usd")
    client.patch(f"/api/v1/proveedores/{inactivo['id']}/estado", json={"estado": "desactivado"}, headers=admin)
    vendedor = headers_de(crear_usuario("vendedor"))
    assert client.get("/api/v1/proveedores", headers=vendedor).status_code == 403

    r = client.get(f"{URL}/proveedores", headers=vendedor)
    assert r.status_code == 200
    todos = r.json()
    assert all(set(p) == {"id", "nombre", "moneda", "activo"} for p in todos)
    ids = [p["id"] for p in todos]
    assert ids.index(inactivo["id"]) < ids.index(activo["id"])            # orden por nombre
    assert {"id": inactivo["id"], "nombre": "Alfa para productos", "moneda": "usd", "activo": False} in todos

    solo_activos = client.get(f"{URL}/proveedores", params={"solo_activos": "true"}, headers=vendedor).json()
    assert activo["id"] in {p["id"] for p in solo_activos}
    assert inactivo["id"] not in {p["id"] for p in solo_activos}


@pytest.mark.parametrize("params", [
    {"pagina": "99999999999999999999"},       # desbordaba el OFFSET (BIGINT): era un 500
    {"pagina": "100001"},
    {"precio_desde": "1e30"},
    {"precio_hasta": "100000000"},
    {"precio_desde": "-1"},
])
def test_filtros_fuera_de_rango_dan_422(client, crear_usuario, headers_de, params):
    h = headers_de(crear_usuario("admin"))
    assert client.get(URL, params=params, headers=h).status_code == 422


def test_ids_enormes_no_dan_500(client, crear_usuario, headers_de):
    h = headers_de(crear_usuario("admin"))
    enorme = "99999999999999999999"
    assert client.get(f"{URL}/{enorme}", headers=h).status_code == 404
    assert client.get(URL, params={"categoria_id": enorme, "proveedor_id": enorme}, headers=h).json()["total"] == 0
    assert client.delete(f"{URL}/fotos/{enorme}", headers=h).status_code == 404


def test_cambio_de_dolar_por_api_recalcula_precios(client, crear_usuario, headers_de, db):
    h = headers_de(crear_usuario("admin"))
    hoja, prov = _base(client, h, db)
    p = _alta(client, h, hoja, prov).json()                               # 10 US$ × 1000 = 10000
    assert p["precio_venta"] == "10000.00"

    r = client.patch(f"/api/v1/proveedores/{prov['id']}/dolar", json={"valor_nuevo": "1500"}, headers=h)
    assert r.status_code == 200 and _precio(client, h, p) == "15000.00"

    r = client.post("/api/v1/proveedores/dolar/masivo",
                    json={"proveedor_ids": [prov["id"]], "modalidad": "valor", "valor": "2000"}, headers=h)
    assert r.status_code == 200 and _precio(client, h, p) == "20000.00"

    archivo = _xlsx([["proveedor_id", "nombre", "dolar_nuevo"], [prov["id"], prov["nombre"], 2500]])
    r = client.post("/api/v1/proveedores/dolar/importar", headers=h,
                    files={"archivo": ("dolar.xlsx", archivo, "application/octet-stream")})
    assert r.status_code == 200 and r.json()["aplicados"] == 1
    assert _precio(client, h, p) == "25000.00"


def test_masivo_con_desborde_no_aplica_nada(client, crear_usuario, headers_de, db):
    h = headers_de(crear_usuario("admin"))
    hoja, prov = _base(client, h, db)                                      # "Prov API": se procesa primero
    otro = _prov(client, h, "Prov B desborde")
    p = _alta(client, h, hoja, prov).json()
    grande = _alta(client, h, hoja, otro, costo="99999", descripcion="Casi el máximo").json()
    assert grande["precio_venta"] == "99999000.00"

    r = client.post("/api/v1/proveedores/dolar/masivo",
                    json={"proveedor_ids": [prov["id"], otro["id"]], "modalidad": "valor", "valor": "2000"}, headers=h)
    assert r.status_code == 409 and grande["sku"] in r.json()["detail"]
    db.rollback()   # lo que hace get_db al cerrar la sesión de un request que falló (sin commit)

    for proveedor in (prov, otro):
        assert client.get(f"/api/v1/proveedores/{proveedor['id']}", headers=h).json()["dolar_actual"] == "1000.00"
    assert _precio(client, h, p) == "10000.00" and _precio(client, h, grande) == "99999000.00"


def test_fotos_por_api_tamano_y_firma(client, crear_usuario, headers_de, db):
    h = headers_de(crear_usuario("admin"))
    hoja, prov = _base(client, h, db)
    p = _alta(client, h, hoja, prov).json()
    grande = JPG + b"0" * (5 * 1024 * 1024)
    r = client.post(f"{URL}/{p['id']}/fotos", files={"archivo": ("x.jpg", grande, "image/jpeg")}, headers=h)
    assert r.status_code == 409 and "5 MB" in r.json()["detail"]
    r = client.post(f"{URL}/{p['id']}/fotos", files={"archivo": ("x.jpg", b"GIF89a" + b"0" * 50, "image/jpeg")},
                    headers=h)
    assert r.status_code == 400
    assert client.get(f"{URL}/{p['id']}", headers=h).json()["fotos"] == []


def test_categorias_y_productos_por_api(client, crear_usuario, headers_de, db):
    h = headers_de(crear_usuario("admin"))
    hoja, prov = _base(client, h, db)
    raiz_id = hoja["parent_id"]
    # Producto en una categoría que no es hoja: 409.
    r = _alta(client, h, {"id": raiz_id}, prov, descripcion="En la raíz")
    assert r.status_code == 409
    p = _alta(client, h, hoja, prov).json()
    # Borrar una categoría con productos: 409.
    assert client.delete(f"/api/v1/categorias/{hoja['id']}", headers=h).status_code == 409
    # Subcategoría (o mover una) bajo una categoría con productos, aunque estén inactivos: 409.
    client.patch(f"{URL}/{p['id']}/estado", json={"activo": False}, headers=h)
    r = client.post("/api/v1/categorias", json={"nombre": "Lisas", "parent_id": hoja["id"]}, headers=h)
    assert r.status_code == 409 and "movelos a otra categoría" in r.json()["detail"]
    suelta = client.post("/api/v1/categorias", json={"nombre": "Suelta API"}, headers=h).json()
    r = client.patch(f"/api/v1/categorias/{suelta['id']}/mover", json={"parent_id": hoja["id"]}, headers=h)
    assert r.status_code == 409 and "movelos a otra categoría" in r.json()["detail"]


def test_listado_pagina_dos_sin_duplicar(client, crear_usuario, headers_de, db):
    """20 productos con descripciones repetidas de a pares (dos proveedores):
    el desempate por SKU hace que las dos páginas completas no se pisen."""
    h = headers_de(crear_usuario("admin"))
    hoja, prov = _base(client, h, db)
    otro = _prov(client, h, "Prov paginado", moneda="ars")
    creados = {_alta(client, h, hoja, proveedor, descripcion=f"Paginado {i:02d}").json()["id"]
               for i in range(10) for proveedor in (prov, otro)}
    params = {"busqueda": "paginado", "tamano": 10}
    uno = client.get(URL, params={**params, "pagina": 1}, headers=h).json()
    dos = client.get(URL, params={**params, "pagina": 2}, headers=h).json()
    ids_uno = [p["id"] for p in uno["resultados"]]
    ids_dos = [p["id"] for p in dos["resultados"]]
    assert uno["total"] == dos["total"] == 20 and len(ids_uno) == len(ids_dos) == 10
    assert set(ids_uno).isdisjoint(ids_dos) and set(ids_uno) | set(ids_dos) == creados
