from sqlalchemy import select

from app.models import Auditoria, Rol, Sesion, Usuario
from app.services import auth

URL = "/api/v1/usuarios"


def _rol_id(db, nombre):
    return db.scalar(select(Rol.id).where(Rol.nombre == nombre))


def _alta(**extra):
    datos = {"username": "Nuevo.Vendedor", "nombre": "Nuevo Vendedor", "password": "Clave1234"}
    datos.update(extra)
    return datos


def test_admin_crea_vendedor(client, crear_usuario, headers_de, db):
    h = headers_de(crear_usuario("admin"))
    r = client.post(URL, json=_alta(rol_id=_rol_id(db, "vendedor"), celular="+54 9 351-210-8190", email="Nuevo@Example.com"), headers=h)
    assert r.status_code == 201
    u = r.json()
    assert u["username"] == "nuevo.vendedor" and u["rol"] == "vendedor"
    assert u["celular"] == "+5493512108190" and u["email"] == "nuevo@example.com"
    assert u["ultimo_acceso"] is None and "password_hash" not in u
    registro = db.scalar(select(Auditoria).where(Auditoria.accion == "usuario.crear", Auditoria.entidad_id == u["id"]))
    assert "password_hash" not in registro.estado_nuevo


def test_validaciones_del_alta(client, crear_usuario, headers_de, db):
    h = headers_de(crear_usuario("admin"))
    vendedor = _rol_id(db, "vendedor")
    assert client.post(URL, json=_alta(rol_id=_rol_id(db, "admin")), headers=h).status_code == 409
    assert client.post(URL, json=_alta(rol_id=vendedor), headers=h).status_code == 201
    assert client.post(URL, json=_alta(rol_id=vendedor), headers=h).status_code == 409  # username repetido
    assert client.post(URL, json=_alta(rol_id=vendedor, username="otro", email="a@b.com"), headers=h).status_code == 201
    assert client.post(URL, json=_alta(rol_id=vendedor, username="otro2", email="A@B.com"), headers=h).status_code == 409
    assert client.post(URL, json=_alta(rol_id=vendedor, username="x3", celular="12ab"), headers=h).status_code == 422
    assert client.post(URL, json=_alta(rol_id=vendedor, username="ab"), headers=h).status_code == 422


def test_supervisor_solo_gestiona_vendedores(client, crear_usuario, headers_de, db):
    h = headers_de(crear_usuario("supervisor"))
    assert client.post(URL, json=_alta(rol_id=_rol_id(db, "vendedor")), headers=h).status_code == 201
    assert client.post(URL, json=_alta(username="sup2", rol_id=_rol_id(db, "supervisor")), headers=h).status_code == 403
    otro_supervisor = crear_usuario("supervisor")
    assert client.put(f"{URL}/{otro_supervisor.id}", json={"nombre": "X"}, headers=h).status_code == 403
    asignables = [r["nombre"] for r in client.get(f"{URL}/roles-asignables", headers=h).json()]
    assert asignables == ["vendedor"]


def test_vendedor_no_gestiona_usuarios(client, crear_usuario, headers_de, db):
    h = headers_de(crear_usuario("vendedor"))
    assert client.get(URL, headers=h).status_code == 403
    assert client.post(URL, json=_alta(rol_id=_rol_id(db, "vendedor")), headers=h).status_code == 403


def test_edicion(client, crear_usuario, headers_de, db):
    h = headers_de(crear_usuario("admin"))
    u = crear_usuario("vendedor", celular="3511111111", email="viejo@example.com")
    assert client.put(f"{URL}/{u.id}", json={"username": "otro"}, headers=h).status_code == 422
    r = client.put(f"{URL}/{u.id}", json={"nombre": "Nombre Nuevo", "celular": None}, headers=h)
    assert r.status_code == 200
    assert r.json()["nombre"] == "Nombre Nuevo" and r.json()["celular"] is None
    assert r.json()["email"] == "viejo@example.com"  # no enviado: se conserva
    assert db.scalar(select(Auditoria).where(Auditoria.accion == "usuario.editar", Auditoria.entidad_id == u.id))


def test_editar_password_fuerza_cambio_y_revoca_sesiones(client, crear_usuario, headers_de, db):
    h = headers_de(crear_usuario("admin"))
    u = crear_usuario("vendedor")
    _, refresh, _ = auth.generar_tokens(db, u, None)
    r = client.put(f"{URL}/{u.id}", json={"password": "Reseteada1"}, headers=h)
    assert r.status_code == 200 and r.json()["ultimo_acceso"] is None
    assert db.scalar(select(Sesion.revocada).where(Sesion.usuario_id == u.id))


def test_no_se_cambia_el_rol_del_admin_ni_se_asigna_admin(client, crear_usuario, headers_de, db):
    admin = crear_usuario("admin")
    h = headers_de(admin)
    otro_admin = db.scalar(select(Usuario).where(Usuario.username == "admin"))
    assert client.put(f"{URL}/{otro_admin.id}", json={"rol_id": _rol_id(db, "vendedor")}, headers=h).status_code == 409
    vendedor = crear_usuario("vendedor")
    assert client.put(f"{URL}/{vendedor.id}", json={"rol_id": _rol_id(db, "admin")}, headers=h).status_code == 409


def test_estado(client, crear_usuario, headers_de, db):
    admin = crear_usuario("admin")
    h = headers_de(admin)
    assert client.patch(f"{URL}/{admin.id}/estado", json={"activo": False}, headers=h).status_code == 409
    seed_admin = db.scalar(select(Usuario).where(Usuario.username == "admin"))
    assert client.patch(f"{URL}/{seed_admin.id}/estado", json={"activo": False}, headers=h).status_code == 409
    vendedor = crear_usuario("vendedor")
    auth.generar_tokens(db, vendedor, None)
    r = client.patch(f"{URL}/{vendedor.id}/estado", json={"activo": False}, headers=h)
    assert r.status_code == 200 and r.json()["activo"] is False
    assert db.scalar(select(Sesion.revocada).where(Sesion.usuario_id == vendedor.id))


def test_listado_con_filtros_y_paginacion(client, crear_usuario, headers_de, db):
    h = headers_de(crear_usuario("admin"))
    crear_usuario("vendedor", nombre="José Gómez")
    crear_usuario("vendedor", nombre="Josefina Díaz", activo=False)
    r = client.get(URL, params={"nombre": "jose"}, headers=h).json()
    assert r["total"] == 2 and r["tamano"] == 10
    r = client.get(URL, params={"nombre": "jose", "activo": True}, headers=h).json()
    assert [u["nombre"] for u in r["resultados"]] == ["José Gómez"]
    r = client.get(URL, params={"nombre": "jose", "tamano": 1, "pagina": 2}, headers=h).json()
    assert r["total"] == 2 and len(r["resultados"]) == 1


def test_historial_de_accesos(client, crear_usuario, headers_de):
    h = headers_de(crear_usuario("admin"))
    u = crear_usuario("vendedor", username="histo", password="Clave1234")
    client.post("/api/v1/auth/login", json={"username": "histo", "password": "mala"})
    client.post("/api/v1/auth/login", json={"username": "histo", "password": "Clave1234"})
    r = client.get(f"{URL}/{u.id}/historial", headers=h).json()
    assert r["total"] == 2 and r["resultados"][0]["resultado"] == "exitoso"
    r = client.get(f"{URL}/{u.id}/historial", params={"resultado": "fallido"}, headers=h).json()
    assert r["total"] == 1 and r["resultados"][0]["detalle"] == "Contraseña incorrecta"


def test_accesos_y_permisos_de_usuario(client, crear_usuario, headers_de, db):
    h = headers_de(crear_usuario("admin"))
    vendedor = crear_usuario("vendedor")
    base = client.get(f"{URL}/accesos", params={"rol_id": _rol_id(db, "vendedor")}, headers=h).json()
    assert next(a for a in base if a["clave"] == "stock:stock.baja:crear")["heredado"]
    r = client.put(f"{URL}/{vendedor.id}/accesos", json={"accesos": ["caja:caja.retiro:crear"]}, headers=h)
    assert r.status_code == 200
    retiro = next(a for a in r.json() if a["clave"] == "caja:caja.retiro:crear")
    assert retiro["override"] and retiro["permitido"]
    arbol = client.get(f"{URL}/{vendedor.id}/permisos", headers=h).json()
    caja = next(n for n in arbol["modulos"] if n["modulo"] == "caja")
    nodo = next(r for r in caja["recursos"] if r["recurso"] == "caja.retiro")
    assert nodo["override_crear"] is True and nodo["heredado_crear"] is False
    r = client.put(f"{URL}/{vendedor.id}/permisos", json={"permisos": []}, headers=h)
    assert r.status_code == 200


def test_usuario_inexistente(client, crear_usuario, headers_de):
    h = headers_de(crear_usuario("admin"))
    assert client.get(f"{URL}/999999", headers=h).status_code == 404


# ---------- Escalada de privilegios (revisión final) ----------
def test_supervisor_no_otorga_auditoria_por_accesos(client, crear_usuario, headers_de, db):
    h = headers_de(crear_usuario("supervisor"))
    vendedor = crear_usuario("vendedor")
    r = client.put(f"{URL}/{vendedor.id}/accesos", json={"accesos": ["caja:caja.retiro:crear", "auditoria::ver"]}, headers=h)
    assert r.status_code == 403
    assert r.json()["detail"] == "Solo el Admin puede otorgar permisos de Auditoría"
    # Se valida todo antes de escribir: el retiro (que sí podía otorgar) tampoco quedó.
    retiro = next(a for a in client.get(f"{URL}/{vendedor.id}/accesos", headers=h).json()
                  if a["clave"] == "caja:caja.retiro:crear")
    assert retiro["override"] is False


def test_supervisor_no_otorga_un_permiso_que_no_tiene(client, crear_usuario, headers_de):
    h = headers_de(crear_usuario("supervisor"))
    vendedor = crear_usuario("vendedor")
    r = client.put(f"{URL}/{vendedor.id}/permisos",
                   json={"permisos": [{"modulo": "configuracion", "puede_editar": True}]}, headers=h)
    assert r.status_code == 403
    assert r.json()["detail"] == "No podés otorgar un permiso que no tenés: editar en configuracion"


def test_supervisor_otorga_un_permiso_que_tiene(client, crear_usuario, headers_de):
    h = headers_de(crear_usuario("supervisor"))
    vendedor = crear_usuario("vendedor")
    r = client.put(f"{URL}/{vendedor.id}/permisos",
                   json={"permisos": [{"modulo": "stock", "recurso": "stock.baja", "puede_crear": True}]}, headers=h)
    assert r.status_code == 200


def test_supervisor_no_otorga_usuarios(client, crear_usuario, headers_de):
    h = headers_de(crear_usuario("supervisor"))
    vendedor = crear_usuario("vendedor")
    r = client.put(f"{URL}/{vendedor.id}/accesos", json={"accesos": ["usuarios::crear"]}, headers=h)
    assert r.status_code == 403
    assert r.json()["detail"] == "Solo el Admin puede otorgar permisos de Usuarios"


def test_supervisor_puede_quitar_permisos(client, crear_usuario, headers_de):
    admin_h = headers_de(crear_usuario("admin"))
    vendedor = crear_usuario("vendedor")
    assert client.put(f"{URL}/{vendedor.id}/accesos", json={"accesos": ["auditoria::ver"]}, headers=admin_h).status_code == 200
    h = headers_de(crear_usuario("supervisor"))
    assert client.put(f"{URL}/{vendedor.id}/accesos", json={"accesos": []}, headers=h).status_code == 200


def test_no_admin_no_se_gestiona_a_si_mismo(client, crear_usuario, headers_de):
    admin_h = headers_de(crear_usuario("admin"))
    vendedor = crear_usuario("vendedor")
    r = client.put(f"{URL}/{vendedor.id}/permisos",
                   json={"permisos": [{"modulo": "usuarios", "puede_ver": True, "puede_editar": True}]}, headers=admin_h)
    assert r.status_code == 200
    h = headers_de(vendedor)
    assert client.put(f"{URL}/{vendedor.id}/accesos", json={"accesos": ["caja:caja.retiro:crear"]}, headers=h).status_code == 403
    r = client.put(f"{URL}/{vendedor.id}/permisos", json={"permisos": []}, headers=h)
    assert r.status_code == 403 and r.json()["detail"] == "No podés gestionar tu propio usuario"
    assert client.put(f"{URL}/{vendedor.id}", json={"nombre": "Yo Mismo"}, headers=h).status_code == 403
    assert client.patch(f"{URL}/{vendedor.id}/estado", json={"activo": True}, headers=h).status_code == 403


def test_admin_otorga_auditoria(client, crear_usuario, headers_de):
    h = headers_de(crear_usuario("admin"))
    vendedor = crear_usuario("vendedor")
    r = client.put(f"{URL}/{vendedor.id}/accesos", json={"accesos": ["auditoria::ver"]}, headers=h)
    assert r.status_code == 200
    assert next(a for a in r.json() if a["clave"] == "auditoria::ver")["permitido"]
