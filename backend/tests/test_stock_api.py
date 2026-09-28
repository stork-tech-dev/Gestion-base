import pytest

from app.core.excel import TIPO_XLSX

URL = "/api/v1/stock"
URL_AUDITORIAS = "/api/v1/auditorias-inventario"
URL_PRODUCTOS = "/api/v1/productos"


def _base(client, h, db):
    raiz = client.post("/api/v1/categorias", json={"nombre": "Ropa stock API"}, headers=h).json()
    hoja = client.post("/api/v1/categorias", json={"nombre": "Remeras stock API", "parent_id": raiz["id"]},
                       headers=h).json()
    prov = client.post("/api/v1/proveedores", json={"nombre": "Prov stock API", "moneda": "ars"}, headers=h).json()
    return hoja, prov


def _alta(client, h, hoja, prov, **extra):
    datos = {"categoria_id": hoja["id"], "proveedor_id": prov["id"], "costo": "1000", "margen": "0",
             "descripcion": "Remera stock api"}
    datos.update(extra)
    return client.post(URL_PRODUCTOS, json=datos, headers=h).json()


def _motivo_id(client, h):
    return client.get(f"{URL}/motivos-baja", headers=h).json()[0]["id"]


def _stock_de(client, h, producto):
    resultados = client.get(URL, params={"busqueda": producto["codigo_con_verificador"]}, headers=h).json()["resultados"]
    return resultados[0]


def test_sin_auth_da_401(client):
    assert client.get(URL).status_code == 401


def test_permisos(client, crear_usuario, headers_de, db):
    admin = headers_de(crear_usuario("admin"))
    hoja, prov = _base(client, admin, db)
    p = _alta(client, admin, hoja, prov, descripcion="Remera permisos")
    motivo_id = _motivo_id(client, admin)
    client.post(f"{URL}/ingresos", json={"producto_id": p["id"], "cantidad": 5}, headers=admin)

    vendedor = headers_de(crear_usuario("vendedor"))
    assert client.get(URL, headers=vendedor).status_code == 200
    assert client.post(f"{URL}/ingresos", json={"producto_id": p["id"], "cantidad": 1},
                       headers=vendedor).status_code == 403
    r = client.post(f"{URL}/bajas", json={"producto_id": p["id"], "cantidad": 1, "motivo_baja_id": motivo_id},
                    headers=vendedor)
    assert r.status_code == 201            # el vendedor tiene el recurso stock.baja crear
    assert client.put(f"{URL}/minimos/{p['id']}", json={"stock_minimo": 1}, headers=vendedor).status_code == 403
    assert client.post(f"{URL}/motivos-baja", json={"nombre": "Motivo vendedor"}, headers=vendedor).status_code == 403
    r = client.post(URL_AUDITORIAS, json={}, headers=vendedor)
    assert r.status_code == 201            # el vendedor tiene el recurso stock.auditoria crear


def test_ingreso_minimo_baja_y_movimientos(client, crear_usuario, headers_de, db):
    admin = headers_de(crear_usuario("admin"))
    hoja, prov = _base(client, admin, db)
    p = _alta(client, admin, hoja, prov, descripcion="Remera flujo admin")
    motivo_id = _motivo_id(client, admin)

    r = client.post(f"{URL}/ingresos", json={"producto_id": p["id"], "cantidad": 10, "notas": "Compra"}, headers=admin)
    assert r.status_code == 201
    ingreso = r.json()
    assert ingreso["tipo"] == "ingreso_proveedor" and ingreso["cantidad"] == 10 and ingreso["stock_resultante"] == 10

    r = client.put(f"{URL}/minimos/{p['id']}", json={"stock_minimo": 3}, headers=admin)
    assert r.status_code == 200 and r.json()["stock_minimo"] == 3 and r.json()["bajo_minimo"] is False

    r = client.post(f"{URL}/bajas", json={"producto_id": p["id"], "cantidad": 2, "motivo_baja_id": motivo_id,
                                          "notas": "Rota"}, headers=admin)
    assert r.status_code == 201
    baja = r.json()
    assert baja["tipo"] == "baja" and baja["cantidad"] == -2 and baja["stock_resultante"] == 8 and baja["motivo_baja"]

    r = client.get(f"{URL}/movimientos", params={"producto_id": p["id"]}, headers=admin)
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["total"] == 2
    assert [m["tipo"] for m in cuerpo["resultados"]] == ["baja", "ingreso_proveedor"]      # más reciente primero

    assert client.get(f"{URL}/resumen", headers=admin).status_code == 200
    assert client.get(f"{URL}/alertas", headers=admin).status_code == 200

    r = client.get(URL, params={"proveedor_id": prov["id"], "solo_bajo_minimo": "true"}, headers=admin)
    assert r.status_code == 200 and r.json()["total"] == 0        # stock 8 > mínimo 3

    client.put(f"{URL}/minimos/{p['id']}", json={"stock_minimo": 20}, headers=admin)
    r = client.get(URL, params={"proveedor_id": prov["id"], "solo_bajo_minimo": "true"}, headers=admin)
    assert r.json()["total"] == 1


def test_baja_sin_stock_suficiente(client, crear_usuario, headers_de, db):
    admin = headers_de(crear_usuario("admin"))
    hoja, prov = _base(client, admin, db)
    p = _alta(client, admin, hoja, prov, descripcion="Remera sin stock baja")
    motivo_id = _motivo_id(client, admin)
    client.post(f"{URL}/ingresos", json={"producto_id": p["id"], "cantidad": 2}, headers=admin)

    r = client.post(f"{URL}/bajas", json={"producto_id": p["id"], "cantidad": 5, "motivo_baja_id": motivo_id},
                    headers=admin)
    assert r.status_code == 409
    assert r.json()["detail"] == f"No hay stock suficiente de '{p['descripcion']}': hay 2 y se piden 5"


@pytest.mark.parametrize("cantidad", [0, 1_000_001])
def test_cantidad_fuera_de_rango_da_422(client, crear_usuario, headers_de, db, cantidad):
    admin = headers_de(crear_usuario("admin"))
    hoja, prov = _base(client, admin, db)
    p = _alta(client, admin, hoja, prov, descripcion="Remera rango cantidad")
    motivo_id = _motivo_id(client, admin)
    assert client.post(f"{URL}/ingresos", json={"producto_id": p["id"], "cantidad": cantidad},
                       headers=admin).status_code == 422
    assert client.post(f"{URL}/bajas", json={"producto_id": p["id"], "cantidad": cantidad, "motivo_baja_id": motivo_id},
                       headers=admin).status_code == 422


def test_stock_cero_filtra_productos(client, crear_usuario, headers_de, db):
    admin = headers_de(crear_usuario("admin"))
    hoja, prov = _base(client, admin, db)
    con_stock = _alta(client, admin, hoja, prov, descripcion="Remera con stock")
    sin_stock = _alta(client, admin, hoja, prov, descripcion="Remera sin stock")
    client.post(f"{URL}/ingresos", json={"producto_id": con_stock["id"], "cantidad": 5}, headers=admin)

    r = client.get(URL_PRODUCTOS, params={"proveedor_id": prov["id"], "stock_cero": "true"}, headers=admin)
    assert r.status_code == 200
    ids = {p["id"] for p in r.json()["resultados"]}
    assert sin_stock["id"] in ids and con_stock["id"] not in ids


def test_auditoria_flujo_completo(client, crear_usuario, headers_de, db):
    admin = headers_de(crear_usuario("admin"))
    hoja, prov = _base(client, admin, db)
    a = _alta(client, admin, hoja, prov, descripcion="Remera auditoria A")
    b = _alta(client, admin, hoja, prov, descripcion="Remera auditoria B")
    client.post(f"{URL}/ingresos", json={"producto_id": a["id"], "cantidad": 10}, headers=admin)
    client.post(f"{URL}/ingresos", json={"producto_id": b["id"], "cantidad": 6}, headers=admin)

    r = client.post(URL_AUDITORIAS, json={"notas": "Conteo API"}, headers=admin)
    assert r.status_code == 201
    auditoria = r.json()
    assert auditoria["estado"] == "en_curso" and auditoria["cantidad_items"] == 0

    # Una sola auditoría en curso a la vez.
    r = client.post(URL_AUDITORIAS, json={}, headers=admin)
    assert r.status_code == 409 and r.json()["detail"] == "Ya hay un conteo en curso."

    # Registrar por id.
    r = client.post(f"{URL_AUDITORIAS}/{auditoria['id']}/items",
                    json={"items": [{"producto_id": a["id"], "cantidad_contada": 7}]}, headers=admin)
    assert r.status_code == 201
    item_a = r.json()[0]
    assert item_a["cantidad_sistema"] == 10 and item_a["cantidad_contada"] == 7 and item_a["diferencia"] == -3

    # Registrar por código (con verificador), como el escáner de la pantalla.
    r = client.post(f"{URL_AUDITORIAS}/{auditoria['id']}/items/por-codigo",
                    json={"codigo": b["codigo_con_verificador"], "cantidad_contada": 6}, headers=admin)
    assert r.status_code == 201
    item_b = r.json()
    assert item_b["producto_id"] == b["id"] and item_b["cantidad_sistema"] == 6 and item_b["diferencia"] == 0

    # Editar ítem.
    r = client.patch(f"{URL_AUDITORIAS}/{auditoria['id']}/items/{item_a['id']}", json={"cantidad_contada": 9},
                     headers=admin)
    assert r.status_code == 200 and r.json()["cantidad_contada"] == 9 and r.json()["diferencia"] == -1

    # Eliminar ítem: solo queda el de A, sin diferencia sobre B.
    assert client.delete(f"{URL_AUDITORIAS}/{auditoria['id']}/items/{item_b['id']}", headers=admin).status_code == 204

    detalle = client.get(f"{URL_AUDITORIAS}/{auditoria['id']}", headers=admin).json()
    assert detalle["cantidad_items"] == 1

    # Finalizar: ajusta el stock según la diferencia.
    r = client.patch(f"{URL_AUDITORIAS}/{auditoria['id']}/finalizar", headers=admin)
    assert r.status_code == 200 and r.json()["estado"] == "cerrada"
    assert _stock_de(client, admin, a)["stock"] == 9

    # PDF y Excel.
    r = client.get(f"{URL_AUDITORIAS}/{auditoria['id']}/pdf", headers=admin)
    assert r.status_code == 200 and r.content.startswith(b"%PDF")
    r = client.get(f"{URL_AUDITORIAS}/{auditoria['id']}/xls", headers=admin)
    assert r.status_code == 200 and r.headers["content-type"] == TIPO_XLSX


def test_finalizar_con_segundo_item_sin_stock_no_aplica_ningun_ajuste(client, crear_usuario, headers_de, db):
    """Dos ítems: el ajuste del primero es válido, pero entre el conteo y el
    cierre se dio de baja gran parte del stock real del segundo, así que su
    ajuste dejaría el stock negativo -> 409. Ninguno de los dos ajustes debe
    quedar aplicado (ni siquiera el del primero, que por sí solo era válido),
    verificado con requests de API posteriores sobre la MISMA sesión."""
    admin = headers_de(crear_usuario("admin"))
    hoja, prov = _base(client, admin, db)
    a = _alta(client, admin, hoja, prov, descripcion="Remera cierre parcial A")
    b = _alta(client, admin, hoja, prov, descripcion="Remera cierre parcial B")
    client.post(f"{URL}/ingresos", json={"producto_id": a["id"], "cantidad": 10}, headers=admin)
    client.post(f"{URL}/ingresos", json={"producto_id": b["id"], "cantidad": 10}, headers=admin)

    auditoria = client.post(URL_AUDITORIAS, json={}, headers=admin).json()
    r = client.post(f"{URL_AUDITORIAS}/{auditoria['id']}/items",
                    json={"items": [{"producto_id": a["id"], "cantidad_contada": 7},
                                    {"producto_id": b["id"], "cantidad_contada": 8}]}, headers=admin)
    assert r.status_code == 201

    # Entre el conteo y el cierre, una baja consume casi todo el stock real de B
    # (cantidad_sistema del ítem sigue en 10: es la foto tomada al registrar).
    motivo_id = _motivo_id(client, admin)
    r = client.post(f"{URL}/bajas", json={"producto_id": b["id"], "cantidad": 9, "motivo_baja_id": motivo_id},
                    headers=admin)
    assert r.status_code == 201 and r.json()["stock_resultante"] == 1

    r = client.patch(f"{URL_AUDITORIAS}/{auditoria['id']}/finalizar", headers=admin)
    assert r.status_code == 409
    db.rollback()   # lo que hace get_db al cerrar la sesión de un request que falló (sin commit)

    # Ningún ajuste se aplicó: ni el de A (válido de haberse procesado solo) ni el de B.
    assert _stock_de(client, admin, a)["stock"] == 10
    assert _stock_de(client, admin, b)["stock"] == 1

    detalle = client.get(f"{URL_AUDITORIAS}/{auditoria['id']}", headers=admin).json()
    assert detalle["estado"] == "en_curso"
