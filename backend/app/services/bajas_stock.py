"""Motivos de baja (catálogo) y registro de bajas de stock. `registrar_baja`
nunca toca `productos.stock` por su cuenta: valida el motivo y delega el
cambio de stock a `services.stock.aplicar_movimiento` (Principio de producto:
"el stock solo cambia vía services.stock.aplicar_movimiento")."""
from sqlalchemy import func, select

from app.core.auditoria import registrar_auditoria, snapshot
from app.core.errores import DatoInvalido, NoEncontrado, ReglaDeNegocio
from app.core.utils import filtro_texto, normalizar_texto, sin_tildes, sin_tildes_sql
from app.models import MotivoBaja, MovimientoStock, TipoMovimientoStock
from app.services.stock import aplicar_movimiento


def obtener_motivo(db, motivo_id: int) -> MotivoBaja:
    motivo = db.get(MotivoBaja, motivo_id)
    if motivo is None:
        raise NoEncontrado("Motivo de baja no encontrado")
    return motivo


def listar_motivos(db, *, nombre: str | None = None, activo: bool | None = None) -> list[MotivoBaja]:
    condiciones = []
    if nombre:
        condiciones.append(filtro_texto(MotivoBaja.nombre, nombre))
    if activo is not None:
        condiciones.append(MotivoBaja.activo.is_(activo))
    return list(db.scalars(select(MotivoBaja).where(*condiciones).order_by(func.lower(MotivoBaja.nombre))).all())


def _nombre_libre(db, nombre: str, excepto_id: int | None = None) -> str:
    limpio = normalizar_texto(nombre)
    if not limpio:
        raise DatoInvalido("El nombre es obligatorio")
    condiciones = [func.lower(sin_tildes_sql(MotivoBaja.nombre)) == sin_tildes(limpio).lower()]
    if excepto_id is not None:
        condiciones.append(MotivoBaja.id != excepto_id)
    existente = db.scalar(select(MotivoBaja).where(*condiciones))
    if existente is not None:
        raise ReglaDeNegocio(f"Ya existe el motivo '{existente.nombre}'")
    return limpio


def crear_motivo(db, autor, datos, ip) -> MotivoBaja:
    motivo = MotivoBaja(nombre=_nombre_libre(db, datos.nombre), activo=True)
    db.add(motivo)
    db.flush()
    db.refresh(motivo)
    registrar_auditoria(db, accion="motivo_baja.crear", entidad="motivo_baja", entidad_id=motivo.id,
                        usuario_id=autor.id, estado_nuevo=motivo, ip_origen=ip)
    return motivo


def editar_motivo(db, autor, motivo: MotivoBaja, datos, ip) -> MotivoBaja:
    """Valida todo (nombre libre) ANTES de mutar `motivo`: si el nombre está
    duplicado, el objeto queda intacto (ni nombre ni activo cambian)."""
    antes = snapshot(motivo)
    nombre = _nombre_libre(db, datos.nombre, excepto_id=motivo.id)
    motivo.nombre = nombre
    motivo.activo = datos.activo
    db.flush()
    registrar_auditoria(db, accion="motivo_baja.editar", entidad="motivo_baja", entidad_id=motivo.id,
                        usuario_id=autor.id, estado_anterior=antes, estado_nuevo=motivo, ip_origen=ip)
    return motivo


def registrar_baja(db, autor, producto_id: int, cantidad: int, motivo_baja_id: int, notas: str | None,
                    ip: str | None) -> MovimientoStock:
    if not isinstance(cantidad, int) or cantidad <= 0:
        raise DatoInvalido("La cantidad debe ser un número entero mayor a 0.")
    # El motivo se obtiene y valida ANTES de tocar el stock: una baja con un
    # motivo inactivo o inexistente no debe llegar a aplicar_movimiento.
    motivo = obtener_motivo(db, motivo_baja_id)
    if not motivo.activo:
        raise ReglaDeNegocio("El motivo de baja no está activo.")
    return aplicar_movimiento(db, autor, tipo=TipoMovimientoStock.BAJA, producto_id=producto_id, cantidad=-cantidad,
                              motivo_baja_id=motivo.id, notas=notas, ip_origen=ip)
