URL = "/api/v1/configuracion"


def test_sin_auth_da_401(client):
    assert client.get(f"{URL}/medios-de-pago").status_code == 401


def test_permisos_generales(client, crear_usuario, headers_de):
    """Ni vendedor ni supervisor tienen CONFIGURACION sembrado: ambos deberían
    quedar afuera de medios de pago, planes y motivos de descuento."""
    admin = headers_de(crear_usuario("admin"))
    vendedor = headers_de(crear_usuario("vendedor"))
    supervisor = headers_de(crear_usuario("supervisor"))

    assert client.get(f"{URL}/medios-de-pago", headers=vendedor).status_code == 403
    assert client.get(f"{URL}/medios-de-pago", headers=supervisor).status_code == 403
    assert client.get(f"{URL}/medios-de-pago", headers=admin).status_code == 200

    r = client.post(f"{URL}/medios-de-pago", json={"nombre": "Efectivo permisos"}, headers=vendedor)
    assert r.status_code == 403
    r = client.post(f"{URL}/medios-de-pago", json={"nombre": "Efectivo permisos"}, headers=admin)
    assert r.status_code == 201


def test_permisos_promociones(client, crear_usuario, headers_de):
    """El recurso configuracion.promociones sí lo tiene sembrado el supervisor
    (ver/crear/editar), aunque no tenga CONFIGURACION general."""
    admin = headers_de(crear_usuario("admin"))
    vendedor = headers_de(crear_usuario("vendedor"))
    supervisor = headers_de(crear_usuario("supervisor"))

    assert client.get(f"{URL}/promociones", headers=vendedor).status_code == 403
    assert client.get(f"{URL}/promociones", headers=supervisor).status_code == 200
    assert client.get(f"{URL}/promociones/catalogos", headers=supervisor).status_code == 200

    datos = {"nombre": "Promo permisos", "tipo": "porcentaje", "porcentaje_descuento": 10,
            "alcances": [{"tipo_alcance": "todos_productos"}]}
    r = client.post(f"{URL}/promociones", json=datos, headers=vendedor)
    assert r.status_code == 403
    r = client.post(f"{URL}/promociones", json=datos, headers=supervisor)
    assert r.status_code == 201
    promo_id = r.json()["id"]

    r = client.put(f"{URL}/promociones/{promo_id}", json={**datos, "nombre": "Promo permisos editada"},
                   headers=supervisor)
    assert r.status_code == 200

    r = client.patch(f"{URL}/promociones/{promo_id}/estado", json={"activo": False}, headers=supervisor)
    assert r.status_code == 200 and r.json()["activo"] is False

    assert client.get(f"{URL}/promociones", headers=admin).status_code == 200


def test_medios_de_pago_y_planes_crud(client, crear_usuario, headers_de):
    h = headers_de(crear_usuario("admin"))

    r = client.post(f"{URL}/medios-de-pago", json={"nombre": "Tarjeta crédito", "soporta_cuotas": True}, headers=h)
    assert r.status_code == 201
    medio = r.json()
    assert medio["soporta_cuotas"] is True and medio["planes"] == []

    # Validación: efectivo no admite cuotas.
    r = client.post(f"{URL}/medios-de-pago", json={"nombre": "Efectivo inválido", "es_efectivo": True,
                                                    "soporta_cuotas": True}, headers=h)
    assert r.status_code == 400

    r = client.put(f"{URL}/medios-de-pago/{medio['id']}", json={"nombre": "Tarjeta crédito edit",
                                                                 "soporta_cuotas": True}, headers=h)
    assert r.status_code == 200 and r.json()["nombre"] == "Tarjeta crédito edit"

    r = client.patch(f"{URL}/medios-de-pago/{medio['id']}/estado", json={"activo": False}, headers=h)
    assert r.status_code == 200 and r.json()["activo"] is False

    r = client.post(f"{URL}/medios-de-pago/{medio['id']}/planes", json={"cuotas": 3, "recargo_cliente": "10"},
                    headers=h)
    assert r.status_code == 201
    plan = r.json()
    assert plan["cuotas"] == 3

    # Validación: plan duplicado (mismas cuotas y recargo).
    r = client.post(f"{URL}/medios-de-pago/{medio['id']}/planes", json={"cuotas": 3, "recargo_cliente": "10"},
                    headers=h)
    assert r.status_code == 409

    r = client.get(f"{URL}/medios-de-pago/{medio['id']}/planes", headers=h)
    assert r.status_code == 200 and len(r.json()) == 1

    r = client.put(f"{URL}/planes-cuotas/{plan['id']}", json={"cuotas": 6, "recargo_cliente": "15"}, headers=h)
    assert r.status_code == 200 and r.json()["cuotas"] == 6

    r = client.patch(f"{URL}/planes-cuotas/{plan['id']}/estado", json={"activo": False}, headers=h)
    assert r.status_code == 200 and r.json()["activo"] is False


def test_motivos_descuento_crud(client, crear_usuario, headers_de):
    h = headers_de(crear_usuario("admin"))

    r = client.post(f"{URL}/motivos-descuento", json={"nombre": "Descuento empleado", "porcentaje_sugerido": "10"},
                    headers=h)
    assert r.status_code == 201
    motivo = r.json()
    assert motivo["porcentaje_sugerido"] == "10.00"

    # Validación: nombre duplicado.
    r = client.post(f"{URL}/motivos-descuento", json={"nombre": "Descuento empleado"}, headers=h)
    assert r.status_code == 409

    r = client.put(f"{URL}/motivos-descuento/{motivo['id']}", json={"nombre": "Descuento empleado editado"},
                   headers=h)
    assert r.status_code == 200 and r.json()["nombre"] == "Descuento empleado editado"

    r = client.patch(f"{URL}/motivos-descuento/{motivo['id']}/estado", json={"activo": False}, headers=h)
    assert r.status_code == 200 and r.json()["activo"] is False

    r = client.get(f"{URL}/motivos-descuento", headers=h)
    assert r.status_code == 200 and len(r.json()) == 1


def test_promociones_crud_y_catalogos(client, crear_usuario, headers_de):
    h = headers_de(crear_usuario("admin"))

    r = client.get(f"{URL}/promociones/catalogos", headers=h)
    assert r.status_code == 200
    assert set(r.json().keys()) == {"productos", "categorias", "medios"}

    datos = {"nombre": "2x1 remeras", "tipo": "dos_x_uno", "alcances": [{"tipo_alcance": "todos_productos"}]}
    r = client.post(f"{URL}/promociones", json=datos, headers=h)
    assert r.status_code == 201
    promo = r.json()
    assert promo["tipo"] == "dos_x_uno" and len(promo["alcances"]) == 1

    # Validación: tipo porcentaje exige porcentaje_descuento.
    r = client.post(f"{URL}/promociones", json={"nombre": "Promo sin porcentaje", "tipo": "porcentaje",
                                                 "alcances": [{"tipo_alcance": "todos_productos"}]}, headers=h)
    assert r.status_code == 400

    r = client.put(f"{URL}/promociones/{promo['id']}", json={**datos, "nombre": "2x1 remeras editada"}, headers=h)
    assert r.status_code == 200 and r.json()["nombre"] == "2x1 remeras editada"

    r = client.patch(f"{URL}/promociones/{promo['id']}/estado", json={"activo": False}, headers=h)
    assert r.status_code == 200 and r.json()["activo"] is False
