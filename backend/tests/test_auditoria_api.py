URL = "/api/v1/auditoria"


def test_admin_consulta_la_auditoria(client, crear_usuario, headers_de):
    h = headers_de(crear_usuario("admin"))
    r = client.get(URL, params={"accion": "sistema.seed"}, headers=h)
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["total"] == 1 and cuerpo["tamano"] == 50
    assert cuerpo["resultados"][0]["accion"] == "sistema.seed"


def test_solo_con_permiso_de_auditoria(client, crear_usuario, headers_de):
    assert client.get(URL, headers=headers_de(crear_usuario("supervisor"))).status_code == 403
    assert client.get(URL, headers=headers_de(crear_usuario("vendedor"))).status_code == 403
    assert client.get(URL).status_code == 401


def test_tamano_maximo(client, crear_usuario, headers_de):
    h = headers_de(crear_usuario("admin"))
    assert client.get(URL, params={"tamano": 201}, headers=h).status_code == 422


def test_login_queda_en_la_auditoria(client, crear_usuario, headers_de):
    h = headers_de(crear_usuario("admin"))
    crear_usuario(username="audit1", password="Clave1234")
    client.post("/api/v1/auth/login", json={"username": "audit1", "password": "Clave1234"})
    r = client.get(URL, params={"accion": "auth.login"}, headers=h).json()
    assert r["total"] >= 1
