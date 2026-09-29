"""Descuentos de ventas: tope de configuración, fórmula única de precio con
descuentos y motivos de descuento. `aplicar_descuentos` es la ÚNICA fórmula de
precio con descuentos (Principio 2): la reusa services.ventas para cada ítem."""
from decimal import Decimal

from sqlalchemy import func, select

from app.core.auditoria import registrar_auditoria, snapshot
from app.core.errores import DatoInvalido, NoEncontrado, ReglaDeNegocio
from app.core.utils import filtro_texto, nombre_libre, normalizar_texto, redondear, redondear_hacia_abajo
from app.models import MedioDePago, MotivoDescuento
from app.services.configuracion import obtener_configuracion

PASO_PORCENTAJE = 5

# Múltiplo al que se redondea HACIA ABAJO un precio con descuento. Decisión del
# usuario (revisión final del módulo 06): NO se usa el `redondeo` configurado
# (sembrado en 1000), que es para los precios de lista. Con esa regla un 5% de
# descuento sobre $2000 cobraba $1000 (un 50% real). Con $10, un 5% sobre $2000
# cobra $1900. Los precios de lista siguen redondeando HACIA ARRIBA al
# `redondeo` configurado (services.productos.calcular_precio_venta).
REDONDEO_DESCUENTO = Decimal("10")


def tope(db) -> Decimal:
    """Tope de descuento por producto (producto + venta, suma directa). ÚNICA lectura."""
    return obtener_configuracion(db).tope_descuento_venta


def porcentajes_validos(db) -> list[int]:
    return list(range(PASO_PORCENTAJE, int(tope(db)) + 1, PASO_PORCENTAJE))


def validar_porcentaje(db, porcentaje) -> Decimal:
    valor = Decimal(str(porcentaje))
    if valor != valor.to_integral_value() or int(valor) not in porcentajes_validos(db):
        raise DatoInvalido(f"El descuento tiene que ser de 5 en 5, hasta el {int(tope(db))}%")
    return valor


def validar_tope(db, desc_producto: Decimal, desc_venta: Decimal, descripcion: str) -> None:
    limite = tope(db)
    if desc_producto + desc_venta > limite:
        raise DatoInvalido(f"El descuento total no puede superar el {int(limite)}% por producto: "
                           f"'{descripcion}' ya tiene {desc_producto}% de descuento propio")


def calcular_descuento_total(desc_producto: Decimal, desc_venta: Decimal) -> Decimal:
    """Descuento efectivo encadenado, para mostrar: 1 − (1−dp)(1−dv), en %."""
    factor = (1 - desc_producto / 100) * (1 - desc_venta / 100)
    return redondear((1 - factor) * 100)


def aplicar_descuentos(precio_lista: Decimal, desc_producto: Decimal, desc_venta: Decimal) -> Decimal:
    """ÚNICA fórmula de precio con descuentos: encadenados y redondeados HACIA
    ABAJO al múltiplo de REDONDEO_DESCUENTO. Nunca 0: si el redondeo lo haría
    0, queda el bruto a centavos (y como mínimo $0,01)."""
    bruto = precio_lista * (1 - desc_producto / 100) * (1 - desc_venta / 100)
    final = redondear_hacia_abajo(bruto, REDONDEO_DESCUENTO)
    if final <= 0:
        final = max(redondear(bruto), Decimal("0.01"))
    return final


def obtener_motivo(db, motivo_id: int) -> MotivoDescuento:
    motivo = db.get(MotivoDescuento, motivo_id)
    if motivo is None:
        raise NoEncontrado("Motivo de descuento no encontrado")
    return motivo


def listar_motivos(db, *, nombre: str | None = None, habilita_cuotas_sin_interes: bool | None = None,
                   activo: bool | None = None) -> list[MotivoDescuento]:
    condiciones = []
    if nombre:
        condiciones.append(filtro_texto(MotivoDescuento.nombre, nombre))
    if habilita_cuotas_sin_interes is not None:
        condiciones.append(MotivoDescuento.habilita_cuotas_sin_interes.is_(habilita_cuotas_sin_interes))
    if activo is not None:
        condiciones.append(MotivoDescuento.activo.is_(activo))
    return list(db.scalars(
        select(MotivoDescuento).where(*condiciones).order_by(func.lower(MotivoDescuento.nombre))
    ).all())


def resolver_porcentaje(db, motivo_id: int, porcentaje) -> tuple[MotivoDescuento, Decimal, bool]:
    """Resuelve qué porcentaje aplica un motivo de descuento al confirmar una
    venta. No valida vigencia (fecha_inicio/fecha_fin) ni medios habilitados:
    el spec dice que esos datos se guardan y se muestran, pero no se validan
    hoy (queda para una sesión futura)."""
    motivo = obtener_motivo(db, motivo_id)
    if not motivo.activo:
        raise ReglaDeNegocio(f"El motivo '{motivo.nombre}' está inactivo")
    if porcentaje is None:
        if motivo.porcentaje_sugerido is None:
            raise DatoInvalido("Elegí el porcentaje de descuento")
        porcentaje = motivo.porcentaje_sugerido
    valor = validar_porcentaje(db, porcentaje)
    modificado = motivo.porcentaje_sugerido is not None and valor != motivo.porcentaje_sugerido
    return motivo, valor, modificado


def _nombre_libre(db, nombre: str, excepto_id: int | None = None) -> str:
    return nombre_libre(db, MotivoDescuento, nombre, excepto_id=excepto_id,
                        mensaje_duplicado=lambda m: f"Ya existe el motivo '{m.nombre}'")


def _validar_fechas(fecha_inicio, fecha_fin) -> None:
    if fecha_inicio is not None and fecha_fin is not None and fecha_inicio > fecha_fin:
        raise DatoInvalido("La fecha de inicio no puede ser posterior a la fecha de fin")


def _medios_de(db, medio_de_pago_ids: list[int]) -> list[MedioDePago]:
    """Medios de pago habilitados para un motivo (vacío = todos). Valida que
    todos los ids existan; el schema ya garantiza que no vengan repetidos."""
    if not medio_de_pago_ids:
        return []
    medios = list(db.scalars(select(MedioDePago).where(MedioDePago.id.in_(medio_de_pago_ids))).all())
    por_id = {m.id: m for m in medios}
    faltantes = [i for i in medio_de_pago_ids if i not in por_id]
    if faltantes:
        raise NoEncontrado(f"No existe el medio de pago {faltantes[0]}")
    return [por_id[i] for i in medio_de_pago_ids]


def _sincronizar_medios(motivo: MotivoDescuento, medios: list[MedioDePago]) -> None:
    motivo.medios = medios


def _snapshot_motivo(motivo: MotivoDescuento) -> dict:
    """snapshot() de columnas + medio_de_pago_ids (relación, no columna): la
    auditoría de motivos de descuento tiene que mostrar qué medios quedaron
    habilitados en cada alta/edición/cambio de estado."""
    datos = snapshot(motivo)
    datos["medio_de_pago_ids"] = [m.id for m in motivo.medios]
    return datos


def crear_motivo(db, autor, datos, ip) -> MotivoDescuento:
    nombre = _nombre_libre(db, datos.nombre)
    if datos.porcentaje_sugerido is not None:
        validar_porcentaje(db, datos.porcentaje_sugerido)
    _validar_fechas(datos.fecha_inicio, datos.fecha_fin)
    medios = _medios_de(db, datos.medio_de_pago_ids)
    motivo = MotivoDescuento(
        nombre=nombre, nota=normalizar_texto(datos.nota), porcentaje_sugerido=datos.porcentaje_sugerido,
        habilita_cuotas_sin_interes=datos.habilita_cuotas_sin_interes, activo=True,
        fecha_inicio=datos.fecha_inicio, fecha_fin=datos.fecha_fin,
    )
    _sincronizar_medios(motivo, medios)
    db.add(motivo)
    db.flush()
    db.refresh(motivo)
    registrar_auditoria(db, accion="motivo_descuento.crear", entidad="motivo_descuento", entidad_id=motivo.id,
                        usuario_id=autor.id, estado_nuevo=_snapshot_motivo(motivo), ip_origen=ip)
    return motivo


def editar_motivo(db, autor, motivo: MotivoDescuento, datos, ip) -> MotivoDescuento:
    nombre = _nombre_libre(db, datos.nombre, excepto_id=motivo.id)
    if datos.porcentaje_sugerido is not None:
        validar_porcentaje(db, datos.porcentaje_sugerido)
    _validar_fechas(datos.fecha_inicio, datos.fecha_fin)
    medios = _medios_de(db, datos.medio_de_pago_ids)
    antes = _snapshot_motivo(motivo)
    motivo.nombre = nombre
    motivo.nota = normalizar_texto(datos.nota)
    motivo.porcentaje_sugerido = datos.porcentaje_sugerido
    motivo.habilita_cuotas_sin_interes = datos.habilita_cuotas_sin_interes
    motivo.fecha_inicio = datos.fecha_inicio
    motivo.fecha_fin = datos.fecha_fin
    _sincronizar_medios(motivo, medios)
    db.flush()
    registrar_auditoria(db, accion="motivo_descuento.editar", entidad="motivo_descuento", entidad_id=motivo.id,
                        usuario_id=autor.id, estado_anterior=antes, estado_nuevo=_snapshot_motivo(motivo), ip_origen=ip)
    return motivo


def cambiar_estado_motivo(db, autor, motivo: MotivoDescuento, activo: bool, ip) -> MotivoDescuento:
    if motivo.activo is activo:
        return motivo
    antes = _snapshot_motivo(motivo)
    motivo.activo = activo
    db.flush()
    registrar_auditoria(db, accion="motivo_descuento.activar" if activo else "motivo_descuento.desactivar",
                        entidad="motivo_descuento", entidad_id=motivo.id, usuario_id=autor.id,
                        estado_anterior=antes, estado_nuevo=_snapshot_motivo(motivo), ip_origen=ip)
    return motivo
