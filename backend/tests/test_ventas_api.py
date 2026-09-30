from decimal import Decimal

from app.services import stock as servicio_stock
from tests.fabricas import abrir_turno_de_test, catalogo

URL = "/api/v1/ventas"
URL_CONFIG = "/api/v1/configuracion"
URL_ROLES = "/api/v1/roles"


def _contiene_clave(obj, clave: str) -> bool:
    """Busca `clave` en cualquier nivel de un dict/list ya deserializado de
    JSON (test de que costo_unitario nunca sale en /api/v1/ventas)."""
    if isinstance(obj, dict):
        if clave in obj:
            return True
        return any(_contiene_clave(v, clave) for v in obj.values())
    if isinstance(obj, list):
        return any(_contiene_clave(v, clave) for v in obj)
    return False


def _medio_efectivo(client, h_admin) -> int:
    """"Efectivo" ya viene sembrado por la migración 0006 (junto con Débito,
    Tarjeta de Crédito y Transferencia): no hace falta crearlo."""
    r = client.get(f"{URL_CONFIG}/medios-de-pago", headers=h_admin)
    assert r.status_code == 200
    return next(m["id"] for m in r.json() if m["es_efectivo"])


def _motivo_descuento(client, h_admin) -> int:
    r = client.post(f"{URL_CONFIG}/motivos-descuento", json={"nombre": "Descuento prueba ventas"}, headers=h_admin)
    assert r.status_code == 201
    return r.json()["id"]


def _rol_sin_descuento(client, h_admin) -> str:
    """Rol personalizado con solo VENTAS ver (sin "ventas crear"). Sirve para
    probar `puede_vender`: sin "crear" no opera el carrito. No aísla
    venta.descuento, que se hereda de "ventas crear" (resolver_permiso trata
    el permiso general del módulo como válido para sus recursos)."""
    nombre = "Cajero sin descuento"
    r = client.post(URL_ROLES, json={"nombre": nombre}, headers=h_admin)
    assert r.status_code == 201
    rol_id = r.json()["id"]
    r = client.put(f"{URL_ROLES}/{rol_id}/permisos", json={"permisos": [
        {"modulo": "ventas", "recurso": None, "puede_ver": True},
    ]}, headers=h_admin)
    assert r.status_code == 200
    return nombre


def _producto_con_stock(db, admin, descripcion: str, cantidad: int = 10):
    producto = catalogo(db, admin)["alta"](descripcion, costo="1000")
    if cantidad:
        servicio_stock.registrar_ingreso(db, admin, producto.id, cantidad, None, None)
    return producto


def test_sin_auth_da_401(client):
    assert client.get(URL).status_code == 401


def test_en_curso_sin_venta_abierta_da_null_y_no_422(client, crear_usuario, headers_de):
    """Prueba a la vez que /en-curso responde null y que la ruta fija no
    choca contra el converter int de /{venta_id} (no da 422)."""
    h = headers_de(crear_usuario("vendedor"))
    r = client.get(f"{URL}/en-curso", headers=h)
    assert r.status_code == 200
    assert r.json() is None


def test_flujo_completo_de_venta_sin_cliente(client, crear_usuario, headers_de, db):
    admin = crear_usuario("admin")
    h_admin = headers_de(admin)
    abrir_turno_de_test(db, admin)
    producto = _producto_con_stock(db, admin, "Remera flujo completo")
    medio_id = _medio_efectivo(client, h_admin)

    vendedor = crear_usuario("vendedor")
    h = headers_de(vendedor)

    r = client.post(URL, headers=h)
    assert r.status_code == 200
    venta_id = r.json()["id"]

    r = client.post(f"{URL}/{venta_id}/items", json={"codigo": producto.codigo_con_verificador}, headers=h)
    assert r.status_code == 200
    total = r.json()["total"]

    r = client.post(f"{URL}/{venta_id}/pagos", json={"pagos": [{"medio_de_pago_id": medio_id, "monto": str(total)}]},
                    headers=h)
    assert r.status_code == 200
    total = r.json()["total"]

    r = client.post(f"{URL}/{venta_id}/confirmar", json={"total_esperado": total}, headers=h)
    assert r.status_code == 200
    confirmada = r.json()
    assert confirmada["estado"] == "confirmada"
    assert len(confirmada["codigo_cambio"]) == 4


def test_agregar_item_sin_stock_da_409(client, crear_usuario, headers_de, db):
    admin = crear_usuario("admin")
    producto = _producto_con_stock(db, admin, "Remera sin stock venta", cantidad=0)
    vendedor = crear_usuario("vendedor")
    h = headers_de(vendedor)

    venta_id = client.post(URL, headers=h).json()["id"]
    r = client.post(f"{URL}/{venta_id}/items", json={"codigo": producto.codigo_con_verificador}, headers=h)
    assert r.status_code == 409
    assert "No hay stock de" in r.json()["detail"]


def test_put_cantidad_y_lineas_en_la_respuesta(client, crear_usuario, headers_de, db):
    admin = crear_usuario("admin")
    producto = _producto_con_stock(db, admin, "Vaso API cantidad", cantidad=5)
    h = headers_de(crear_usuario("vendedor"))
    venta_id = client.post(URL, headers=h).json()["id"]
    r = client.post(f"{URL}/{venta_id}/items", json={"producto_id": producto.id, "cantidad": 2}, headers=h)
    assert r.status_code == 200
    linea = r.json()["lineas"][0]
    assert linea["cantidad"] == 2 and len(linea["item_ids"]) == 2 and linea["stock"] == 5
    assert linea["precio_final"] == str(Decimal(r.json()["items"][0]["precio_final"]) * 2)
    r = client.put(f"{URL}/{venta_id}/items/{linea['item_id']}/cantidad", json={"cantidad": 5}, headers=h)
    assert r.status_code == 200 and r.json()["lineas"][0]["cantidad"] == 5
    r = client.put(f"{URL}/{venta_id}/items/{linea['item_id']}/cantidad", json={"cantidad": 6}, headers=h)
    assert r.status_code == 409 and "Solo quedan 5 unidades" in r.json()["detail"]
    assert client.put(f"{URL}/{venta_id}/items/{linea['item_id']}/cantidad", json={"cantidad": 1000},
                      headers=h).status_code == 422


def test_put_cantidad_venta_ajena_403(client, crear_usuario, headers_de, db):
    """`_venta_propia_en_curso` levanta SinPermiso (403), no NoEncontrado: la
    venta existe, pero es de otro usuario."""
    admin = crear_usuario("admin")
    producto = _producto_con_stock(db, admin, "Vaso ajeno", cantidad=5)
    h1 = headers_de(crear_usuario("vendedor"))
    h2 = headers_de(crear_usuario("vendedor"))
    venta_id = client.post(URL, headers=h1).json()["id"]
    r = client.post(f"{URL}/{venta_id}/items", json={"producto_id": producto.id}, headers=h1)
    item_id = r.json()["items"][0]["id"]
    r = client.put(f"{URL}/{venta_id}/items/{item_id}/cantidad", json={"cantidad": 2}, headers=h2)
    assert r.status_code == 403


def test_costo_unitario_nunca_aparece(client, crear_usuario, headers_de, db):
    admin = crear_usuario("admin")
    producto = _producto_con_stock(db, admin, "Remera costo oculto")
    vendedor = crear_usuario("vendedor")
    h = headers_de(vendedor)

    venta_id = client.post(URL, headers=h).json()["id"]
    client.post(f"{URL}/{venta_id}/items", json={"codigo": producto.codigo_con_verificador}, headers=h)

    detalle = client.get(f"{URL}/{venta_id}", headers=h).json()
    assert not _contiene_clave(detalle, "costo_unitario")

    listado = client.get(URL, headers=h).json()
    assert not _contiene_clave(listado, "costo_unitario")


def test_permisos_del_carrito_descuento_y_anulacion(client, crear_usuario, headers_de, db):
    admin = crear_usuario("admin")
    h_admin = headers_de(admin)
    abrir_turno_de_test(db, admin)
    producto = _producto_con_stock(db, admin, "Remera permisos ventas", cantidad=20)
    medio_id = _medio_efectivo(client, h_admin)
    motivo_id = _motivo_descuento(client, h_admin)

    vendedor = crear_usuario("vendedor")
    h = headers_de(vendedor)

    venta_id = client.post(URL, headers=h).json()["id"]
    r = client.post(f"{URL}/{venta_id}/items", json={"codigo": producto.codigo_con_verificador}, headers=h)
    item_id = r.json()["items"][0]["id"]

    # El vendedor sembrado tiene venta.descuento.
    r = client.post(f"{URL}/{venta_id}/descuento", json={"item_id": item_id, "motivo_id": motivo_id,
                                                         "porcentaje": 10}, headers=h)
    assert r.status_code == 200
    total = r.json()["total"]

    r = client.post(f"{URL}/{venta_id}/pagos", json={"pagos": [{"medio_de_pago_id": medio_id, "monto": str(total)}]},
                    headers=h)
    assert r.status_code == 200
    total = r.json()["total"]

    r = client.post(f"{URL}/{venta_id}/confirmar", json={"total_esperado": total}, headers=h)
    assert r.status_code == 200
    confirmada = r.json()

    # El vendedor NO puede anular (no tiene venta.anular).
    r = client.post(f"{URL}/{confirmada['id']}/anular", json={"motivo": "Intento vendedor"}, headers=h)
    assert r.status_code == 403

    # El supervisor sí anula, aunque no tenga "ventas eliminar" sembrado
    # (decisión 6: el permiso real es VENTAS ver + venta.anular).
    supervisor = crear_usuario("supervisor")
    h_sup = headers_de(supervisor)
    r = client.post(f"{URL}/{confirmada['id']}/anular", json={"motivo": "Anulo de prueba"}, headers=h_sup)
    assert r.status_code == 200
    assert r.json()["estado"] == "anulada"

    # Esto cubre `puede_vender`, no `puede_descontar`: un rol con solo VENTAS
    # ver no puede operar el carrito (403 de Depends(puede_vender), que corta
    # antes de evaluar el descuento). `venta.descuento` no se puede aislar: se
    # hereda de "ventas crear" (decisión del usuario, docs/pendientes.md).
    rol_sin_descuento = _rol_sin_descuento(client, h_admin)
    otro = crear_usuario(rol=rol_sin_descuento)
    h_otro = headers_de(otro)
    r = client.post(f"{URL}/{venta_id}/descuento", json={"item_id": item_id, "motivo_id": motivo_id,
                                                         "porcentaje": 10}, headers=h_otro)
    assert r.status_code == 403


def test_descuento_general_api(client, crear_usuario, headers_de, db):
    admin = crear_usuario("admin")
    h_admin = headers_de(admin)
    producto = _producto_con_stock(db, admin, "Remera descuento general", cantidad=10)

    vendedor = crear_usuario("vendedor")
    h = headers_de(vendedor)

    venta_id = client.post(URL, headers=h).json()["id"]
    r = client.post(f"{URL}/{venta_id}/items", json={"codigo": producto.codigo_con_verificador}, headers=h)
    total = r.json()["total"]

    # Los dos a la vez: 400.
    r = client.post(f"{URL}/{venta_id}/descuento-general", json={"porcentaje": "10", "total": "100"}, headers=h)
    assert r.status_code == 400

    # Por total final: 200 y descuento_general en la respuesta.
    objetivo = str(Decimal(total) - Decimal("100"))
    r = client.post(f"{URL}/{venta_id}/descuento-general", json={"total": objetivo}, headers=h)
    assert r.status_code == 200
    assert r.json()["descuento_general"] == "100.00"

    # Sin "ventas crear" (donde se hereda venta.descuento): 403.
    rol_sin_descuento = _rol_sin_descuento(client, h_admin)
    otro = crear_usuario(rol=rol_sin_descuento)
    h_otro = headers_de(otro)
    r = client.post(f"{URL}/{venta_id}/descuento-general", json={"total": objetivo}, headers=h_otro)
    assert r.status_code == 403


def test_auditoria_de_anulacion(client, crear_usuario, headers_de, db):
    admin = crear_usuario("admin")
    h_admin = headers_de(admin)
    abrir_turno_de_test(db, admin)
    producto = _producto_con_stock(db, admin, "Remera auditoria anular")
    medio_id = _medio_efectivo(client, h_admin)

    vendedor = crear_usuario("vendedor")
    h = headers_de(vendedor)
    venta_id = client.post(URL, headers=h).json()["id"]
    r = client.post(f"{URL}/{venta_id}/items", json={"codigo": producto.codigo_con_verificador}, headers=h)
    total = r.json()["total"]
    r = client.post(f"{URL}/{venta_id}/pagos", json={"pagos": [{"medio_de_pago_id": medio_id, "monto": str(total)}]},
                    headers=h)
    total = r.json()["total"]
    r = client.post(f"{URL}/{venta_id}/confirmar", json={"total_esperado": total}, headers=h)
    confirmada_id = r.json()["id"]

    r = client.post(f"{URL}/{confirmada_id}/anular", json={"motivo": "Motivo de auditoría"}, headers=h_admin)
    assert r.status_code == 200

    r = client.get("/api/v1/auditoria", params={"accion": "venta.anular"}, headers=h_admin)
    assert r.status_code == 200
    registros = r.json()["resultados"]
    assert any(reg["entidad_id"] == confirmada_id for reg in registros)
