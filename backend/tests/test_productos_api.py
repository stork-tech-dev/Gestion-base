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
