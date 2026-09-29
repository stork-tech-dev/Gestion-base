"""Notificaciones del usuario logueado (sesión 07). Marcarlas como leídas no
es una acción sensible: no se audita."""
from sqlalchemy import func, select, update

from app.core.errores import NoEncontrado
from app.models import Notificacion


def listar(db, usuario, limite: int = 20) -> tuple[list[Notificacion], int]:
    notificaciones = db.scalars(select(Notificacion).where(Notificacion.usuario_id == usuario.id)
                                .order_by(Notificacion.created_at.desc(), Notificacion.id.desc())
                                .limit(limite)).all()
    no_leidas = db.scalar(select(func.count()).select_from(Notificacion)
                          .where(Notificacion.usuario_id == usuario.id, Notificacion.leida.is_(False)))
    return list(notificaciones), no_leidas


def marcar_leida(db, usuario, notificacion_id: int) -> Notificacion:
    notificacion = db.get(Notificacion, notificacion_id)
    # La de otro usuario responde igual que una inexistente (no se revela).
    if notificacion is None or notificacion.usuario_id != usuario.id:
        raise NoEncontrado("Notificación no encontrada")
    notificacion.leida = True
    db.flush()
    return notificacion


def marcar_todas(db, usuario) -> None:
    db.execute(update(Notificacion).where(Notificacion.usuario_id == usuario.id, Notificacion.leida.is_(False))
               .values(leida=True).execution_options(synchronize_session="fetch"))
    db.flush()
