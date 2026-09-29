"""Esquemas de caja: turnos, retiros y arqueos (sesión 07). Datos crudos."""
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models import EstadoTurno

MONTO_MAXIMO = Decimal("99999999.99")


class TurnoAbrir(BaseModel):
    efectivo_apertura: Decimal = Field(ge=0, le=MONTO_MAXIMO, decimal_places=2)
    notas: str | None = Field(None, max_length=1000)


class RetiroCrear(BaseModel):
    monto: Decimal = Field(gt=0, le=MONTO_MAXIMO, decimal_places=2)
    motivo: str = Field(min_length=1, max_length=255)


class ParticipanteResponse(BaseModel):
    id: int
    nombre: str
    ingreso: datetime


class TurnoResponse(BaseModel):
    id: int
    estado: EstadoTurno
    efectivo_apertura: Decimal
    fecha_apertura: datetime
    fecha_cierre: datetime | None
    notas: str | None
    es_de_dia_anterior: bool
    usuario_apertura_nombre: str
    usuario_cierre_nombre: str | None
    usuarios: list[ParticipanteResponse]
    diferencia_arqueo: Decimal | None

    @classmethod
    def desde(cls, turno, es_de_dia_anterior: bool) -> "TurnoResponse":
        return cls(
            id=turno.id, estado=turno.estado, efectivo_apertura=turno.efectivo_apertura,
            fecha_apertura=turno.fecha_apertura, fecha_cierre=turno.fecha_cierre, notas=turno.notas,
            es_de_dia_anterior=es_de_dia_anterior,
            usuario_apertura_nombre=turno.usuario_apertura.nombre,
            usuario_cierre_nombre=turno.usuario_cierre.nombre if turno.usuario_cierre else None,
            usuarios=[ParticipanteResponse(id=p.usuario_id, nombre=p.usuario.nombre, ingreso=p.ingreso)
                      for p in turno.participantes],
            diferencia_arqueo=turno.arqueo.diferencia if turno.arqueo else None,
        )


class RetiroResponse(BaseModel):
    id: int
    turno_id: int
    monto: Decimal
    motivo: str
    usuario_id: int
    usuario_nombre: str
    timestamp: datetime

    @classmethod
    def desde(cls, retiro) -> "RetiroResponse":
        return cls(id=retiro.id, turno_id=retiro.turno_id, monto=retiro.monto, motivo=retiro.motivo,
                   usuario_id=retiro.usuario_id, usuario_nombre=retiro.usuario.nombre, timestamp=retiro.timestamp)


class ArqueoLinea(BaseModel):
    medio_de_pago_id: int | None
    medio_nombre: str
    grupo_terminal: str | None
    monto_esperado: Decimal
    es_informativo: bool
    es_efectivo: bool


class ArqueoEsperadoResponse(BaseModel):
    turno_id: int
    items: list[ArqueoLinea]
    efectivo_apertura: Decimal
    total_esperado: Decimal


class ItemDeclarado(BaseModel):
    medio_de_pago_id: int | None = None
    grupo_terminal: str | None = Field(None, max_length=60)
    monto_declarado: Decimal = Field(ge=0, le=MONTO_MAXIMO, decimal_places=2)


class ArqueoRegistrar(BaseModel):
    items_declarados: list[ItemDeclarado] = Field(max_length=100)
    total_declarado: Decimal = Field(ge=0, le=MONTO_MAXIMO, decimal_places=2)


class ArqueoItemResponse(BaseModel):
    medio_de_pago_id: int | None
    grupo_terminal: str | None
    medio_nombre: str
    monto_esperado: Decimal
    monto_declarado: Decimal
    diferencia: Decimal
    es_informativo: bool


class ArqueoResponse(BaseModel):
    id: int
    turno_id: int
    usuario_nombre: str
    total_esperado: Decimal
    total_declarado: Decimal
    diferencia: Decimal
    notificacion_enviada: bool
    created_at: datetime
    items: list[ArqueoItemResponse]

    @classmethod
    def desde(cls, arqueo) -> "ArqueoResponse":
        return cls(
            id=arqueo.id, turno_id=arqueo.turno_id, usuario_nombre=arqueo.usuario.nombre,
            total_esperado=arqueo.total_esperado, total_declarado=arqueo.total_declarado,
            diferencia=arqueo.diferencia, notificacion_enviada=arqueo.notificacion_enviada,
            created_at=arqueo.created_at,
            items=[ArqueoItemResponse(medio_de_pago_id=i.medio_de_pago_id, grupo_terminal=i.grupo_terminal,
                                      medio_nombre=i.nombre, monto_esperado=i.monto_esperado,
                                      monto_declarado=i.monto_declarado, diferencia=i.diferencia,
                                      es_informativo=i.es_informativo) for i in arqueo.items],
        )
