"""Tests de services/descuentos.py (sesión 06)."""
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.errores import DatoInvalido, NoEncontrado, ReglaDeNegocio
from app.models import Auditoria
from app.schemas.descuentos import MotivoDescuentoCrear, MotivoDescuentoEditar
from app.schemas.medios_pago import MedioDePagoCrear
from app.services import descuentos as servicio
from app.services import medios_pago as servicio_medios
from app.services.configuracion import obtener_configuracion


def test_aplicar_descuentos_encadenado_y_hacia_abajo():
    # 10000 × 0.9 × 0.85 = 7650 → múltiplo de 1000 hacia abajo = 7000
    assert servicio.aplicar_descuentos(Decimal("10000"), Decimal("10"), Decimal("15"), Decimal("1000")) == Decimal("7000")


def test_aplicar_descuentos_nunca_cero():
    assert servicio.aplicar_descuentos(Decimal("1000"), Decimal("0"), Decimal("50"), Decimal("1000")) == Decimal("500.00")


def test_tope_leido_de_configuracion(db):
    config = obtener_configuracion(db)
    config.tope_descuento_venta = Decimal("20")
    db.flush()
    assert servicio.porcentajes_validos(db) == [5, 10, 15, 20]
    with pytest.raises(DatoInvalido):
        servicio.validar_porcentaje(db, 25)


def test_tope_suma_directa(db):
    with pytest.raises(DatoInvalido, match="no puede superar el 50%"):
        servicio.validar_tope(db, Decimal("30"), Decimal("25"), "Remera")
    servicio.validar_tope(db, Decimal("30"), Decimal("20"), "Remera")   # 50 justo: OK


def test_porcentaje_no_multiplo_de_5(db):
    with pytest.raises(DatoInvalido):
        servicio.validar_porcentaje(db, 12)


def test_calcular_descuento_total_encadenado():
    # 1 - (0.9 * 0.85) = 0.235 → 23.5%
    assert servicio.calcular_descuento_total(Decimal("10"), Decimal("15")) == Decimal("23.50")


def test_resolver_porcentaje_usa_sugerido_y_marca_modificado(db, crear_usuario):
    admin = crear_usuario("admin")
    motivo = servicio.crear_motivo(
        db, admin, MotivoDescuentoCrear(nombre="Motivo sugerido", porcentaje_sugerido=Decimal("10")), None)

    _, valor, modificado = servicio.resolver_porcentaje(db, motivo.id, None)
    assert valor == Decimal("10")
    assert modificado is False

    _, valor, modificado = servicio.resolver_porcentaje(db, motivo.id, 20)
    assert valor == Decimal("20")
    assert modificado is True


def test_resolver_sin_sugerido_exige_porcentaje(db, crear_usuario):
    admin = crear_usuario("admin")
    motivo = servicio.crear_motivo(db, admin, MotivoDescuentoCrear(nombre="Motivo sin sugerido"), None)
    with pytest.raises(DatoInvalido, match="Elegí el porcentaje"):
        servicio.resolver_porcentaje(db, motivo.id, None)
    _, valor, modificado = servicio.resolver_porcentaje(db, motivo.id, 15)
    assert valor == Decimal("15")
    assert modificado is False


def test_motivo_inactivo_409(db, crear_usuario):
    admin = crear_usuario("admin")
    motivo = servicio.crear_motivo(
        db, admin, MotivoDescuentoCrear(nombre="Motivo a desactivar", porcentaje_sugerido=Decimal("10")), None)
    servicio.cambiar_estado_motivo(db, admin, motivo, False, None)
    with pytest.raises(ReglaDeNegocio, match="inactivo"):
        servicio.resolver_porcentaje(db, motivo.id, None)


def test_motivo_sincroniza_medios_y_audita(db, crear_usuario):
    admin = crear_usuario("admin")
    medio_a = servicio_medios.crear_medio(db, admin, MedioDePagoCrear(nombre="Medio motivo a"), None)
    medio_b = servicio_medios.crear_medio(db, admin, MedioDePagoCrear(nombre="Medio motivo b"), None)

    motivo = servicio.crear_motivo(
        db, admin, MotivoDescuentoCrear(nombre="Motivo con medios", medio_de_pago_ids=[medio_a.id]), None)
    assert {m.id for m in motivo.medios} == {medio_a.id}
    registro = db.scalar(
        select(Auditoria).where(Auditoria.accion == "motivo_descuento.crear", Auditoria.entidad_id == motivo.id))
    assert registro.estado_nuevo["medio_de_pago_ids"] == [medio_a.id]

    servicio.editar_motivo(
        db, admin, motivo, MotivoDescuentoEditar(nombre="Motivo con medios", medio_de_pago_ids=[medio_b.id]), None)
    assert {m.id for m in motivo.medios} == {medio_b.id}
    registro = db.scalar(
        select(Auditoria).where(Auditoria.accion == "motivo_descuento.editar", Auditoria.entidad_id == motivo.id))
    assert registro.estado_anterior["medio_de_pago_ids"] == [medio_a.id]
    assert registro.estado_nuevo["medio_de_pago_ids"] == [medio_b.id]


def test_motivo_medio_inexistente_404(db, crear_usuario):
    admin = crear_usuario("admin")
    with pytest.raises(NoEncontrado):
        servicio.crear_motivo(
            db, admin, MotivoDescuentoCrear(nombre="Motivo medio raro", medio_de_pago_ids=[999999]), None)


def test_motivo_nombre_duplicado_sin_tildes(db, crear_usuario):
    admin = crear_usuario("admin")
    servicio.crear_motivo(db, admin, MotivoDescuentoCrear(nombre="Promoción motivo"), None)
    with pytest.raises(ReglaDeNegocio):
        servicio.crear_motivo(db, admin, MotivoDescuentoCrear(nombre="PROMOCION MOTIVO"), None)


def test_motivo_fechas_incoherentes(db, crear_usuario):
    admin = crear_usuario("admin")
    with pytest.raises(DatoInvalido):
        servicio.crear_motivo(
            db, admin,
            MotivoDescuentoCrear(nombre="Motivo fechas", fecha_inicio=date(2026, 2, 1), fecha_fin=date(2026, 1, 1)),
            None,
        )


def test_motivo_porcentaje_sugerido_invalido(db, crear_usuario):
    admin = crear_usuario("admin")
    with pytest.raises(DatoInvalido):
        servicio.crear_motivo(
            db, admin, MotivoDescuentoCrear(nombre="Motivo sugerido invalido", porcentaje_sugerido=Decimal("12")),
            None,
        )


def test_cambiar_estado_motivo_audita(db, crear_usuario):
    admin = crear_usuario("admin")
    motivo = servicio.crear_motivo(db, admin, MotivoDescuentoCrear(nombre="Motivo estado"), None)
    servicio.cambiar_estado_motivo(db, admin, motivo, False, None)
    assert motivo.activo is False
    registro = db.scalar(
        select(Auditoria).where(Auditoria.accion == "motivo_descuento.desactivar", Auditoria.entidad_id == motivo.id))
    assert registro is not None


def test_listar_motivos_filtra_por_activo(db, crear_usuario):
    admin = crear_usuario("admin")
    activo = servicio.crear_motivo(db, admin, MotivoDescuentoCrear(nombre="Motivo listado activo"), None)
    inactivo = servicio.crear_motivo(db, admin, MotivoDescuentoCrear(nombre="Motivo listado inactivo"), None)
    servicio.cambiar_estado_motivo(db, admin, inactivo, False, None)
    ids = {m.id for m in servicio.listar_motivos(db, activo=True)}
    assert activo.id in ids
    assert inactivo.id not in ids


def test_obtener_motivo_inexistente(db):
    with pytest.raises(NoEncontrado):
        servicio.obtener_motivo(db, 999999)
