"""Tests de /api/v1/turnos y /api/v1/notificaciones (sesión 07)."""
from decimal import Decimal

import pytest

from app.services import turnos as servicio_turnos

URL = "/api/v1/turnos"


@pytest.fixture
def usuarios(crear_usuario):
    return {rol: crear_usuario(rol, nombre=f"{rol.title()} Uno") for rol in ("admin", "supervisor", "vendedor")}


def test_activo_sin_turno_es_null(client, usuarios, headers_de):
    r = client.get(f"{URL}/activo", headers=headers_de(usuarios["vendedor"]))
    assert r.status_code == 200 and r.json() is None


def test_vendedor_abre_y_otro_se_suma(client, usuarios, headers_de):
    r = client.post(f"{URL}/abrir", json={"efectivo_apertura": "5000", "notas": None},
                    headers=headers_de(usuarios["vendedor"]))
    assert r.status_code == 201
    turno = r.json()
    assert turno["estado"] == "abierto" and turno["efectivo_apertura"] == "5000.00"
    assert turno["es_de_dia_anterior"] is False and turno["diferencia_arqueo"] is None
    assert [u["nombre"] for u in turno["usuarios"]] == ["Vendedor Uno"]
    r = client.post(f"{URL}/abrir", json={"efectivo_apertura": "0"}, headers=headers_de(usuarios["supervisor"]))
    assert r.status_code == 409 and "Unirme al turno" in r.json()["detail"]
    r = client.post(f"{URL}/unirse", headers=headers_de(usuarios["supervisor"]))
    assert r.status_code == 200 and len(r.json()["usuarios"]) == 2


def test_abrir_con_monto_negativo_422(client, usuarios, headers_de):
    r = client.post(f"{URL}/abrir", json={"efectivo_apertura": "-1"}, headers=headers_de(usuarios["vendedor"]))
    assert r.status_code == 422


def test_retiro_requiere_caja_retiro(client, db, usuarios, headers_de):
    servicio_turnos.abrir_turno(db, usuarios["admin"], Decimal("0"), None, None)
    datos = {"monto": "1000", "motivo": "Proveedor"}
    assert client.post(f"{URL}/retiros", json=datos, headers=headers_de(usuarios["vendedor"])).status_code == 403
    r = client.post(f"{URL}/retiros", json=datos, headers=headers_de(usuarios["supervisor"]))
    assert r.status_code == 201 and r.json()["usuario_nombre"] == "Supervisor Uno"
    turno_id = r.json()["turno_id"]
    r = client.get(f"{URL}/{turno_id}/retiros", headers=headers_de(usuarios["vendedor"]))
    assert r.status_code == 200 and len(r.json()) == 1


def test_vendedor_cierra_con_arqueo(client, db, usuarios, headers_de):
    turno = servicio_turnos.abrir_turno(db, usuarios["admin"], Decimal("5000"), None, None)
    h = headers_de(usuarios["vendedor"])
    esperado = client.get(f"{URL}/{turno.id}/arqueo/esperado", headers=h).json()
    assert esperado["total_esperado"] == "5000.00"
    efectivo = next(i for i in esperado["items"] if i["es_efectivo"])
    assert efectivo["monto_esperado"] == "5000.00"
    items = [{"medio_de_pago_id": i["medio_de_pago_id"], "grupo_terminal": i["grupo_terminal"],
              "monto_declarado": i["monto_esperado"]} for i in esperado["items"]]
    items[0]["monto_declarado"] = "4500"  # efectivo va primero
    r = client.post(f"{URL}/{turno.id}/arqueo", json={"items_declarados": items, "total_declarado": "4500"},
                    headers=h)
    assert r.status_code == 201, r.text
    assert r.json()["diferencia"] == "-500.00" and r.json()["notificacion_enviada"] is True
    r = client.get(f"{URL}/{turno.id}", headers=h)
    assert r.json()["estado"] == "cerrado" and r.json()["diferencia_arqueo"] == "-500.00"
    assert client.get(f"{URL}/{turno.id}/arqueo", headers=h).json()["total_declarado"] == "4500.00"
    listado = client.get(URL, params={"estado": "cerrado"}, headers=h).json()
    assert listado["tamano"] == 20 and turno.id in [t["id"] for t in listado["resultados"]]


def test_sin_caja_arqueo_no_ve_el_esperado(client, db, usuarios, headers_de, crear_usuario):
    from app.models import Rol
    turno = servicio_turnos.abrir_turno(db, usuarios["admin"], Decimal("0"), None, None)
    # Rol personalizado sin ningún permiso de caja.
    rol = Rol(nombre="solo_ventas_test", descripcion="Test", es_sistema=False)
    db.add(rol)
    db.flush()
    sin_caja = crear_usuario(rol)
    assert client.get(f"{URL}/{turno.id}/arqueo/esperado", headers=headers_de(sin_caja)).status_code == 403
    assert client.get(f"{URL}/activo", headers=headers_de(sin_caja)).status_code == 403


def test_turno_inexistente_404(client, usuarios, headers_de):
    assert client.get(f"{URL}/999999", headers=headers_de(usuarios["admin"])).status_code == 404


def test_notificaciones_solo_piden_sesion(client, db, usuarios, headers_de):
    turno = servicio_turnos.abrir_turno(db, usuarios["admin"], Decimal("100"), None, None)
    h_admin = headers_de(usuarios["admin"])
    esperado = client.get(f"{URL}/{turno.id}/arqueo/esperado", headers=h_admin).json()
    items = [{"medio_de_pago_id": i["medio_de_pago_id"], "grupo_terminal": i["grupo_terminal"],
              "monto_declarado": "0"} for i in esperado["items"]]
    client.post(f"{URL}/{turno.id}/arqueo", json={"items_declarados": items, "total_declarado": "0"},
                headers=h_admin)
    r = client.get("/api/v1/notificaciones", headers=h_admin)
    assert r.status_code == 200 and r.json()["no_leidas"] == 1
    n = r.json()["resultados"][0]
    assert n["tipo"] == "diferencia_arqueo" and n["metadata"]["turno_id"] == turno.id
    assert client.patch(f"/api/v1/notificaciones/{n['id']}/leer",
                        headers=headers_de(usuarios["vendedor"])).status_code == 404
    assert client.patch(f"/api/v1/notificaciones/{n['id']}/leer", headers=h_admin).json()["leida"] is True
    assert client.patch("/api/v1/notificaciones/leer-todas", headers=h_admin).status_code == 204
    assert client.get("/api/v1/notificaciones", headers=headers_de(usuarios["vendedor"])).json() == {
        "no_leidas": 0, "resultados": []}
    assert client.get("/api/v1/notificaciones").status_code == 401
