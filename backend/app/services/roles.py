"""Roles: los de sistema (admin/supervisor/vendedor) no se borran ni renombran."""
from sqlalchemy import func, select

from app.core.auditoria import registrar_auditoria, snapshot
from app.core.errores import DatoInvalido, NoEncontrado, ReglaDeNegocio
from app.core.utils import filtro_texto, normalizar_texto
from app.models import Rol, Usuario
from app.services.permisos import crear_permisos_vacios


def obtener_rol(db, rol_id: int) -> Rol:
    rol = db.get(Rol, rol_id)
    if rol is None:
        raise NoEncontrado("Rol no encontrado")
    return rol


def cantidad_usuarios(db, rol_id: int, solo_activos: bool = False) -> int:
    condiciones = [Usuario.rol_id == rol_id]
    if solo_activos:
        condiciones.append(Usuario.activo.is_(True))
    return db.scalar(select(func.count()).select_from(Usuario).where(*condiciones))


def listar_roles(db, *, nombre: str | None = None, activo: bool | None = None,
                 es_sistema: bool | None = None) -> list[tuple[Rol, int]]:
    cantidad = (
        select(func.count(Usuario.id)).where(Usuario.rol_id == Rol.id).correlate(Rol).scalar_subquery()
    )
    consulta = select(Rol, cantidad).order_by(Rol.es_sistema.desc(), func.lower(Rol.nombre))
    if nombre:
        consulta = consulta.where(filtro_texto(Rol.nombre, nombre))
    if activo is not None:
        consulta = consulta.where(Rol.activo.is_(activo))
    if es_sistema is not None:
        consulta = consulta.where(Rol.es_sistema.is_(es_sistema))
    return [(rol, total) for rol, total in db.execute(consulta).all()]


def _validar_nombre_libre(db, nombre: str, excepto_id: int | None = None) -> str:
    limpio = normalizar_texto(nombre)
    if not limpio:
        raise DatoInvalido("El nombre del rol es obligatorio")
    condiciones = [func.lower(Rol.nombre) == limpio.lower()]
    if excepto_id is not None:
        condiciones.append(Rol.id != excepto_id)
    if db.scalar(select(Rol.id).where(*condiciones)) is not None:
        raise ReglaDeNegocio(f"Ya existe un rol llamado '{limpio}'")
    return limpio


def crear_rol(db, autor, nombre: str, descripcion: str | None, ip) -> Rol:
    rol = Rol(nombre=_validar_nombre_libre(db, nombre), descripcion=normalizar_texto(descripcion), es_sistema=False, activo=True)
    db.add(rol)
    db.flush()
    crear_permisos_vacios(db, rol)
    registrar_auditoria(db, accion="rol.crear", entidad="rol", entidad_id=rol.id, usuario_id=autor.id, estado_nuevo=rol, ip_origen=ip)
    return rol


def editar_rol(db, autor, rol: Rol, nombre: str, descripcion: str | None, ip) -> Rol:
    antes = snapshot(rol)
    nombre_limpio = normalizar_texto(nombre)
    if rol.es_sistema and nombre_limpio != rol.nombre:
        raise ReglaDeNegocio("Los roles del sistema no se renombran")
    if not rol.es_sistema:
        rol.nombre = _validar_nombre_libre(db, nombre, excepto_id=rol.id)
    rol.descripcion = normalizar_texto(descripcion)
    db.flush()
    registrar_auditoria(db, accion="rol.editar", entidad="rol", entidad_id=rol.id, usuario_id=autor.id,
                        estado_anterior=antes, estado_nuevo=rol, ip_origen=ip)
    return rol


def cambiar_estado_rol(db, autor, rol: Rol, activo: bool, ip) -> Rol:
    if not activo:
        activos = cantidad_usuarios(db, rol.id, solo_activos=True)
        if activos:
            raise ReglaDeNegocio(
                f"El rol tiene {activos} usuario(s) activo(s): desactivarlos o reasignarlos antes de desactivar el rol."
            )
    antes = snapshot(rol)
    rol.activo = activo
    db.flush()
    registrar_auditoria(db, accion="rol.activar" if activo else "rol.desactivar", entidad="rol", entidad_id=rol.id,
                        usuario_id=autor.id, estado_anterior=antes, estado_nuevo=rol, ip_origen=ip)
    return rol


def eliminar_rol(db, autor, rol: Rol, ip) -> None:
    if rol.es_sistema:
        raise ReglaDeNegocio("Los roles del sistema no se eliminan")
    if cantidad_usuarios(db, rol.id):
        raise ReglaDeNegocio("El rol tiene usuarios asociados: reasignarlos antes de eliminarlo")
    antes = snapshot(rol)
    db.delete(rol)
    db.flush()
    registrar_auditoria(db, accion="rol.eliminar", entidad="rol", entidad_id=antes["id"], usuario_id=autor.id,
                        estado_anterior=antes, ip_origen=ip)
