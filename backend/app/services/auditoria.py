"""Consulta de la auditoría (solo lectura). El endpoint llega en la sesión 02."""
from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select

from app.core.utils import filtro_texto
from app.models.auditoria import Auditoria

TAMANO_MAXIMO_AUDITORIA = 200


def listar_auditoria(
    db,
    *,
    usuario_id: int | None = None,
    accion: str | None = None,
    entidad: str | None = None,
    entidad_id: int | None = None,
    desde: date | None = None,
    hasta: date | None = None,
    pagina: int = 1,
    tamano: int = 50,
) -> tuple[list[Auditoria], int]:
    condiciones = []
    if usuario_id is not None:
        condiciones.append(Auditoria.usuario_id == usuario_id)
    if accion:
        condiciones.append(filtro_texto(Auditoria.accion, accion))
    if entidad:
        condiciones.append(filtro_texto(Auditoria.entidad, entidad))
    if entidad_id is not None:
        condiciones.append(Auditoria.entidad_id == entidad_id)
    if desde:
        condiciones.append(Auditoria.timestamp >= datetime.combine(desde, time.min))
    if hasta:  # inclusivo: todo el día "hasta"
        condiciones.append(Auditoria.timestamp < datetime.combine(hasta + timedelta(days=1), time.min))

    tamano = max(1, min(tamano, TAMANO_MAXIMO_AUDITORIA))
    pagina = max(1, pagina)

    total = db.scalar(select(func.count()).select_from(Auditoria).where(*condiciones))
    registros = db.scalars(
        select(Auditoria)
        .where(*condiciones)
        .order_by(Auditoria.timestamp.desc(), Auditoria.id.desc())
        .offset((pagina - 1) * tamano)
        .limit(tamano)
    ).all()
    return list(registros), total
