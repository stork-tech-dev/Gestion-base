URL = "/api/v1/clientes"
CUIT_VALIDO = "20390591587"


def test_sin_auth_da_401(client):
    assert client.get(URL).status_code == 401


def test_permisos(client, crear_usuario, headers_de):
    admin = headers_de(crear_usuario("admin"))
    vendedor = headers_de(crear_usuario("vendedor"))
    supervisor = headers_de(crear_usuario("supervisor"))

    # El vendedor tiene CLIENTES ver + crear (sembrado), pero no editar.
    assert client.get(URL, headers=vendedor).status_code == 200
    r = client.post(URL, json={"nombre": "Cliente de vendedor"}, headers=vendedor)
    assert r.status_code == 201
    cliente_id = r.json()["id"]
    assert client.put(f"{URL}/{cliente_id}", json={"nombre": "Editado"}, headers=vendedor).status_code == 403
    assert client.patch(f"{URL}/{cliente_id}/estado", json={"activo": False}, headers=vendedor).status_code == 403

    # El supervisor sí tiene editar.
    r = client.put(f"{URL}/{cliente_id}", json={"nombre": "Editado por supervisor"}, headers=supervisor)
    assert r.status_code == 200 and r.json()["nombre"] == "Editado por supervisor"

    assert client.get(URL, headers=admin).status_code == 200


def test_alta_cuit_invalido_da_400(client, crear_usuario, headers_de):
    h = headers_de(crear_usuario("admin"))
    r = client.post(URL, json={"nombre": "Cliente CUIT malo", "cuit": "20390591588"}, headers=h)
    assert r.status_code == 400


def test_alta_duplicada_da_409(client, crear_usuario, headers_de):
    h = headers_de(crear_usuario("admin"))
    datos = {"nombre": "Cliente CUIT único", "cuit": CUIT_VALIDO}
    assert client.post(URL, json=datos, headers=h).status_code == 201
    r = client.post(URL, json={"nombre": "Otro nombre", "cuit": CUIT_VALIDO}, headers=h)
    assert r.status_code == 409


def test_buscar(client, crear_usuario, headers_de):
    h = headers_de(crear_usuario("admin"))
    client.post(URL, json={"nombre": "Juan Buscar Pérez"}, headers=h)
    client.post(URL, json={"nombre": "Otro Cliente"}, headers=h)

    r = client.get(f"{URL}/buscar", params={"q": "buscar"}, headers=h)
    assert r.status_code == 200
    nombres = [c["nombre"] for c in r.json()]
    assert "Juan Buscar Pérez" in nombres and "Otro Cliente" not in nombres


def test_ficha_con_promociones_y_resumen_de_compras(client, crear_usuario, headers_de, db):
    h = headers_de(crear_usuario("admin"))
    cliente = client.post(URL, json={"nombre": "Cliente con ficha"}, headers=h).json()

    promo = client.post(
        "/api/v1/configuracion/promociones",
        json={"nombre": "Promo ficha cliente", "tipo": "porcentaje", "porcentaje_descuento": 10,
              "alcances": [{"tipo_alcance": "todos_productos"}]},
        headers=h,
    ).json()

    r = client.post(f"{URL}/{cliente['id']}/promociones", json={"promocion_id": promo["id"]}, headers=h)
    assert r.status_code == 201
    ficha = r.json()
    assert ficha["cliente"]["id"] == cliente["id"]
    assert ficha["promociones"] == [{"id": promo["id"], "nombre": promo["nombre"], "tipo": "porcentaje",
                                     "vigente": True}]
    assert ficha["compras_cantidad"] == 0
    assert ficha["compras_total"] == "0"

    r = client.get(f"{URL}/{cliente['id']}", headers=h)
    assert r.status_code == 200
    assert len(r.json()["promociones"]) == 1

    r = client.delete(f"{URL}/{cliente['id']}/promociones/{promo['id']}", headers=h)
    assert r.status_code == 204
    assert client.get(f"{URL}/{cliente['id']}", headers=h).json()["promociones"] == []


def test_ficha_de_cliente_inexistente_da_404(client, crear_usuario, headers_de):
    h = headers_de(crear_usuario("admin"))
    assert client.get(f"{URL}/999999", headers=h).status_code == 404
