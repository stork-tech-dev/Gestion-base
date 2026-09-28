"""Tests de services/medios_pago.py (sesión 06)."""
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.errores import DatoInvalido, NoEncontrado, ReglaDeNegocio
from app.models import Auditoria
from app.schemas.medios_pago import MedioDePagoCrear, MedioDePagoEditar, PlanCuotasCrear
from app.services import medios_pago as servicio


def test_medio_efectivo_devuelve_el_sembrado(db):
    efectivo = servicio.medio_efectivo(db)
    assert efectivo.es_efectivo is True
    assert efectivo.nombre == "Efectivo"


def test_un_solo_efectivo(db, crear_usuario):
    admin = crear_usuario("admin")
    with pytest.raises(ReglaDeNegocio, match="efectivo"):
        servicio.crear_medio(db, admin, MedioDePagoCrear(nombre="Otro efectivo", es_efectivo=True), None)


def test_efectivo_sin_cuotas(db, crear_usuario):
    admin = crear_usuario("admin")
    with pytest.raises(DatoInvalido, match="cuotas"):
        servicio.crear_medio(
            db, admin, MedioDePagoCrear(nombre="Efectivo raro", es_efectivo=True, soporta_cuotas=True), None)


def test_efectivo_no_se_desactiva(db, crear_usuario):
    admin = crear_usuario("admin")
    efectivo = servicio.medio_efectivo(db)
    with pytest.raises(ReglaDeNegocio, match="caja"):
        servicio.cambiar_estado_medio(db, admin, efectivo, False, None)


def test_desactivar_soporta_cuotas_con_planes_activos(db, crear_usuario):
    admin = crear_usuario("admin")
    medio = servicio.crear_medio(db, admin, MedioDePagoCrear(nombre="Tarjeta test", soporta_cuotas=True), None)
    servicio.crear_plan(db, admin, medio, PlanCuotasCrear(cuotas=3, recargo_cliente=Decimal("10")), None)
    with pytest.raises(ReglaDeNegocio, match="planes"):
        servicio.editar_medio(db, admin, medio, MedioDePagoEditar(nombre="Tarjeta test", soporta_cuotas=False), None)


def test_plan_en_medio_sin_cuotas(db, crear_usuario):
    admin = crear_usuario("admin")
    medio = servicio.crear_medio(db, admin, MedioDePagoCrear(nombre="Transferencia test"), None)
    with pytest.raises(ReglaDeNegocio, match="cuotas"):
        servicio.crear_plan(db, admin, medio, PlanCuotasCrear(cuotas=3, recargo_cliente=Decimal("0")), None)


def test_plan_duplicado(db, crear_usuario):
    admin = crear_usuario("admin")
    medio = servicio.crear_medio(db, admin, MedioDePagoCrear(nombre="Tarjeta duplicado", soporta_cuotas=True), None)
    servicio.crear_plan(db, admin, medio, PlanCuotasCrear(cuotas=6, recargo_cliente=Decimal("15")), None)
    with pytest.raises(ReglaDeNegocio, match="Ya existe un plan"):
        servicio.crear_plan(db, admin, medio, PlanCuotasCrear(cuotas=6, recargo_cliente=Decimal("15")), None)


def test_planes_disponibles_con_minimo_y_habilita_sin_interes(db, crear_usuario):
    admin = crear_usuario("admin")
    medio = servicio.crear_medio(db, admin, MedioDePagoCrear(nombre="Tarjeta planes", soporta_cuotas=True), None)
    sin_interes = servicio.crear_plan(
        db, admin, medio,
        PlanCuotasCrear(cuotas=3, recargo_cliente=Decimal("0"), monto_minimo=Decimal("5000")), None)
    con_interes = servicio.crear_plan(
        db, admin, medio,
        PlanCuotasCrear(cuotas=6, recargo_cliente=Decimal("15"), monto_minimo=Decimal("5000")), None)

    # Bajo el mínimo, sin habilitar el sin interés: ninguno entra.
    assert servicio.planes_disponibles(medio, Decimal("1000"), False) == []

    # Bajo el mínimo, habilitando el sin interés: entra el sin interés, NO el que tiene interés.
    disponibles = servicio.planes_disponibles(medio, Decimal("1000"), True)
    ids = {p.id for p in disponibles}
    assert sin_interes.id in ids
    assert con_interes.id not in ids

    # Sobre el mínimo: entran los dos, se pida o no habilitar el sin interés.
    disponibles = servicio.planes_disponibles(medio, Decimal("6000"), False)
    ids = {p.id for p in disponibles}
    assert sin_interes.id in ids
    assert con_interes.id in ids


def test_planes_disponibles_medio_sin_cuotas():
    from app.models import MedioDePago
    medio = MedioDePago(nombre="Sin cuotas", soporta_cuotas=False)
    medio.planes = []
    assert servicio.planes_disponibles(medio, Decimal("100000"), True) == []


def test_calcular_recargo(db, crear_usuario):
    admin = crear_usuario("admin")
    medio = servicio.crear_medio(db, admin, MedioDePagoCrear(nombre="Tarjeta recargo", soporta_cuotas=True), None)
    plan = servicio.crear_plan(db, admin, medio, PlanCuotasCrear(cuotas=3, recargo_cliente=Decimal("15")), None)
    assert servicio.calcular_recargo(Decimal("10000"), plan) == Decimal("1500.00")
    assert servicio.calcular_recargo(Decimal("10000"), None) == Decimal("0")


def test_medio_nombre_duplicado_sin_tildes(db, crear_usuario):
    admin = crear_usuario("admin")
    servicio.crear_medio(db, admin, MedioDePagoCrear(nombre="Débito test"), None)
    with pytest.raises(ReglaDeNegocio):
        servicio.crear_medio(db, admin, MedioDePagoCrear(nombre="DEBITO TEST"), None)


def test_medio_inexistente(db):
    with pytest.raises(NoEncontrado):
        servicio.obtener_medio(db, 999999)


def test_crear_medio_audita(db, crear_usuario):
    admin = crear_usuario("admin")
    medio = servicio.crear_medio(db, admin, MedioDePagoCrear(nombre="Medio auditado"), None)
    registro = db.scalar(
        select(Auditoria).where(Auditoria.accion == "medio_de_pago.crear", Auditoria.entidad_id == medio.id))
    assert registro is not None


def test_crear_plan_audita(db, crear_usuario):
    admin = crear_usuario("admin")
    medio = servicio.crear_medio(db, admin, MedioDePagoCrear(nombre="Tarjeta auditada", soporta_cuotas=True), None)
    plan = servicio.crear_plan(db, admin, medio, PlanCuotasCrear(cuotas=12, recargo_cliente=Decimal("20")), None)
    registro = db.scalar(
        select(Auditoria).where(Auditoria.accion == "plan_cuotas.crear", Auditoria.entidad_id == plan.id))
    assert registro is not None
