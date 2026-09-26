from sqlalchemy import select

from app.models import Auditoria, RolPermiso

URL = "/api/v1/roles"


def test_solo_admin(client, crear_usuario, headers_de):
    assert client.get(URL, headers=headers_de(crear_usuario("supervisor"))).status_code == 403


def test_crear_listar_y_permisos_vacios(client, crear_usuario, headers_de, db):
    h = headers_de(crear_usuario("admin"))
    r = client.post(URL, json={"nombre": "Cajero", "descripcion": "Solo caja"}, headers=h)
    assert r.status_code == 201
    rol = r.json()
    assert rol["es_sistema"] is False and rol["cantidad_usuarios"] == 0
    filas = db.scalars(select(RolPermiso).where(RolPermiso.rol_id == rol["id"])).all()
    assert filas and not any(f.puede_ver for f in filas)
    assert db.scalar(select(Auditoria).where(Auditoria.accion == "rol.crear", Auditoria.entidad_id == rol["id"]))
    nombres = [x["nombre"] for x in client.get(URL, params={"es_sistema": False}, headers=h).json()]
    assert "Cajero" in nombres and "admin" not in nombres
    assert client.post(URL, json={"nombre": "cajero"}, headers=h).status_code == 409  # duplicado sin importar mayúsculas


def test_roles_de_sistema_no_se_renombran_ni_eliminan(client, crear_usuario, headers_de, db):
    h = headers_de(crear_usuario("admin"))
    vendedor = next(x for x in client.get(URL, headers=h).json() if x["nombre"] == "vendedor")
    r = client.put(f"{URL}/{vendedor['id']}", json={"nombre": "vendedores", "descripcion": "x"}, headers=h)
    assert r.status_code == 409
    r = client.put(f"{URL}/{vendedor['id']}", json={"nombre": "vendedor", "descripcion": "Nueva descripción"}, headers=h)
    assert r.status_code == 200 and r.json()["descripcion"] == "Nueva descripción"
    assert client.delete(f"{URL}/{vendedor['id']}", headers=h).status_code == 409


def test_no_se_desactiva_con_usuarios_activos(client, crear_usuario, headers_de, db):
    from app.models import Rol

    h = headers_de(crear_usuario("admin"))
    rol_id = client.post(URL, json={"nombre": "Temporal"}, headers=h).json()["id"]
    r = client.patch(f"{URL}/{rol_id}/estado", json={"activo": False}, headers=h)
    assert r.status_code == 200 and r.json()["activo"] is False
    client.patch(f"{URL}/{rol_id}/estado", json={"activo": True}, headers=h)
    crear_usuario(db.get(Rol, rol_id))
    r = client.patch(f"{URL}/{rol_id}/estado", json={"activo": False}, headers=h)
    assert r.status_code == 409 and "usuario(s) activo(s)" in r.json()["detail"]


def test_eliminar_rol(client, crear_usuario, headers_de, db):
    from app.models import Rol

    h = headers_de(crear_usuario("admin"))
    libre = client.post(URL, json={"nombre": "Libre"}, headers=h).json()["id"]
    assert client.delete(f"{URL}/{libre}", headers=h).status_code == 204
    assert db.get(Rol, libre) is None
    ocupado = client.post(URL, json={"nombre": "Ocupado"}, headers=h).json()["id"]
    crear_usuario(db.get(Rol, ocupado), activo=False)
    assert client.delete(f"{URL}/{ocupado}", headers=h).status_code == 409


def test_arbol_de_permisos_del_rol(client, crear_usuario, headers_de):
    h = headers_de(crear_usuario("admin"))
    rol_id = client.post(URL, json={"nombre": "Depósito"}, headers=h).json()["id"]
    cuerpo = {"permisos": [{"modulo": "stock", "recurso": None, "puede_ver": True}]}
    r = client.put(f"{URL}/{rol_id}/permisos", json=cuerpo, headers=h)
    assert r.status_code == 200
    stock = next(n for n in r.json()["modulos"] if n["modulo"] == "stock")
    assert stock["puede_ver"] is True
    assert client.get(f"{URL}/{rol_id}/permisos", headers=h).json() == r.json()
    malo = {"permisos": [{"modulo": "inventado", "recurso": None}]}
    assert client.put(f"{URL}/{rol_id}/permisos", json=malo, headers=h).status_code == 400


def test_rol_inexistente(client, crear_usuario, headers_de):
    h = headers_de(crear_usuario("admin"))
    assert client.get(f"{URL}/999999/permisos", headers=h).status_code == 404
