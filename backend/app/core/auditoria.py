"""Única vía de escritura de la auditoría (Principio 3).

registrar_auditoria hace add + flush y NUNCA commit: el registro viaja en la
misma transacción que la acción auditada.
"""
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
from uuid import UUID

from sqlalchemy import inspect

from app.core.utils import ahora_db, ip_de_request
from app.models.auditoria import Auditoria

CAMPOS_SENSIBLES = frozenset(
    {
        "password",
        "password_hash",
        "clave_especial",
        "clave_especial_hash",
        "pin",
        "pin_hash",
        "token",
        "access_token",
        "refresh_token",
    }
)


def _valor_json(valor):
    if isinstance(valor, Enum):
        return valor.value
    if isinstance(valor, Decimal):
        return str(valor)
    if isinstance(valor, (datetime, date, time)):
        return valor.isoformat()
    if isinstance(valor, UUID):
        return str(valor)
    if isinstance(valor, dict):
        return {str(k): _valor_json(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple, set)):
        return [_valor_json(v) for v in valor]
    return valor


def snapshot(obj, campos=None) -> dict | None:
    """Modelo SQLAlchemy o dict → dict JSON-safe sin campos sensibles."""
    if obj is None:
        return None
    if isinstance(obj, dict):
        datos = dict(obj)
    else:
        datos = {attr.key: getattr(obj, attr.key) for attr in inspect(obj).mapper.column_attrs}
    if campos is not None:
        datos = {k: datos[k] for k in campos if k in datos}
    return {k: _valor_json(v) for k, v in datos.items() if k not in CAMPOS_SENSIBLES}


def registrar_auditoria(
    db,
    *,
    accion: str,
    entidad: str,
    usuario_id: int | None = None,
    entidad_id: int | None = None,
    estado_anterior=None,
    estado_nuevo=None,
    ip_origen: str | None = None,
    request=None,
) -> Auditoria:
    if ip_origen is None and request is not None:
        ip_origen = ip_de_request(request)
    registro = Auditoria(
        usuario_id=usuario_id,
        accion=accion,
        entidad=entidad,
        entidad_id=entidad_id,
        estado_anterior=snapshot(estado_anterior),
        estado_nuevo=snapshot(estado_nuevo),
        ip_origen=ip_origen,
        timestamp=ahora_db(),
    )
    db.add(registro)
    db.flush()
    return registro
