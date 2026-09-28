URL = "/api/v1/categorias"


def test_crud_de_categorias(client, crear_usuario, headers_de):
    h = headers_de(crear_usuario("admin"))
    r = client.post(URL, json={"nombre": "Ropa"}, headers=h)
    assert r.status_code == 201
    ropa = r.json()
    hija = client.post(URL, json={"nombre": "Remeras", "parent_id": ropa["id"]}, headers=h).json()
    assert hija["nivel"] == 2
    arbol = client.get(f"{URL}/arbol", headers=h).json()
    nodo = next(n for n in arbol if n["id"] == ropa["id"])
    assert nodo["hijos"][0]["nombre"] == "Remeras"
    assert [c["nombre"] for c in client.get(URL, params={"parent_id": ropa["id"]}, headers=h).json()] == ["Remeras"]
    assert client.put(f"{URL}/{hija['id']}", json={"nombre": "Remeras lisas", "orden": 1}, headers=h).json()["nombre"] == "Remeras lisas"
    assert client.patch(f"{URL}/{hija['id']}/mover", json={"parent_id": None}, headers=h).json()["nivel"] == 1
    assert client.delete(f"{URL}/{hija['id']}", headers=h).status_code == 204
    assert client.get(f"{URL}/{hija['id']}", headers=h).status_code == 404
    assert client.get(URL, params={"nivel": 6}, headers=h).status_code == 422


def test_permisos_de_categorias(client, crear_usuario, headers_de):
    vendedor = headers_de(crear_usuario("vendedor"))
    assert client.get(f"{URL}/arbol", headers=vendedor).status_code == 200      # vendedor: productos ver
    assert client.post(URL, json={"nombre": "X"}, headers=vendedor).status_code == 403
