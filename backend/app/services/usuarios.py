"""Usuarios: alta, edición, estado e historial. Admin gestiona a todos; el
resto de los que tienen permiso sobre Usuarios, solo a vendedores."""
from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select

from app.core.auditoria import registrar_auditoria, snapshot
from app.core.errores import DatoInvalido, NoEncontrado, ReglaDeNegocio, SinPermiso
from app.core.permisos import ROL_ADMIN, ROL_VENDEDOR
from app.core.utils import filtro_texto, normalizar_texto
from app.models import HistorialAcceso, ResultadoAcceso, Rol, Usuario
from app.services import auth

TAMANO_MAXIMO = 100


def obtener_usuario(db, usuario_id: int) -> Usuario:
    usuario = db.get(Usuario, usuario_id)
    if usuario is None:
        raise NoEncontrado("Usuario no encontrado")
    return usuario


def validar_puede_gestionar(autor: Usuario, rol_objetivo: Rol) -> None:
    if autor.es_admin:
        return
    if rol_objetivo.nombre != ROL_VENDEDOR:
        raise SinPermiso("Solo podés gestionar usuarios con rol vendedor")


def roles_asignables(db, autor: Usuario) -> list[Rol]:
    consulta = select(Rol).where(Rol.activo.is_(True), Rol.nombre != ROL_ADMIN).order_by(func.lower(Rol.nombre))
    if not autor.es_admin:
        consulta = consulta.where(Rol.nombre == ROL_VENDEDOR)
    return list(db.scalars(consulta).all())


def _rol_asignable(db, autor: Usuario, rol_id: int) -> Rol:
    rol = db.get(Rol, rol_id)
    if rol is None or not rol.activo:
        raise ReglaDeNegocio("El rol elegido no existe o está inactivo")
    if rol.nombre == ROL_ADMIN:
        raise ReglaDeNegocio("No se puede asignar el rol Admin")
    validar_puede_gestionar(autor, rol)
    return rol


def _paginar(pagina: int, tamano: int) -> tuple[int, int]:
    return max(1, pagina), max(1, min(tamano, TAMANO_MAXIMO))


def listar_usuarios(db, *, nombre=None, username=None, email=None, rol_id=None, activo=None,
                    pagina: int = 1, tamano: int = 10) -> tuple[list[Usuario], int]:
    condiciones = []
    if nombre:
        condiciones.append(filtro_texto(Usuario.nombre, nombre))
    if username:
        condiciones.append(filtro_texto(Usuario.username, username))
    if email:
        condiciones.append(filtro_texto(Usuario.email, email))
    if rol_id is not None:
        condiciones.append(Usuario.rol_id == rol_id)
    if activo is not None:
        condiciones.append(Usuario.activo.is_(activo))
    pagina, tamano = _paginar(pagina, tamano)
    total = db.scalar(select(func.count()).select_from(Usuario).where(*condiciones))
    usuarios = db.scalars(
        select(Usuario).where(*condiciones).order_by(func.lower(Usuario.nombre), Usuario.id)
        .offset((pagina - 1) * tamano).limit(tamano)
    ).all()
    return list(usuarios), total


def _validar_username_libre(db, username: str) -> str:
    username = username.strip().lower()
    if db.scalar(select(Usuario.id).where(Usuario.username == username)) is not None:
        raise ReglaDeNegocio(f"El usuario '{username}' ya existe")
    return username


def _validar_email_libre(db, email: str | None, excepto_id: int | None = None) -> str | None:
    if not email:
        return None
    email = email.strip().lower()
    condiciones = [func.lower(Usuario.email) == email]
    if excepto_id is not None:
        condiciones.append(Usuario.id != excepto_id)
    if db.scalar(select(Usuario.id).where(*condiciones)) is not None:
        raise ReglaDeNegocio("El email ya está cargado en otro usuario")
    return email


def _nombre_obligatorio(nombre: str | None) -> str:
    limpio = normalizar_texto(nombre)
    if not limpio:
        raise DatoInvalido("El nombre es obligatorio")
    return limpio


def crear_usuario(db, autor: Usuario, datos, ip) -> Usuario:
    rol = _rol_asignable(db, autor, datos.rol_id)
    usuario = Usuario(
        username=_validar_username_libre(db, datos.username),
        nombre=_nombre_obligatorio(datos.nombre),
        password_hash=auth.hash_password(datos.password),
        rol_id=rol.id,
        email=_validar_email_libre(db, datos.email),
        fecha_nacimiento=datos.fecha_nacimiento,
        celular=datos.celular,
        activo=True,
        ultimo_acceso=None,  # obliga a cambiar la contraseña en el primer ingreso
    )
    db.add(usuario)
    db.flush()
    db.refresh(usuario)
    registrar_auditoria(db, accion="usuario.crear", entidad="usuario", entidad_id=usuario.id,
                        usuario_id=autor.id, estado_nuevo=usuario, ip_origen=ip)
    return usuario


def editar_usuario(db, autor: Usuario, usuario: Usuario, datos, ip) -> Usuario:
    validar_puede_gestionar(autor, usuario.rol)
    antes = snapshot(usuario)
    enviados = datos.model_fields_set
    if "rol_id" in enviados and datos.rol_id is not None and datos.rol_id != usuario.rol_id:
        if usuario.es_admin:
            raise ReglaDeNegocio("No se puede cambiar el rol del Admin")
        usuario.rol_id = _rol_asignable(db, autor, datos.rol_id).id
    if "nombre" in enviados:
        usuario.nombre = _nombre_obligatorio(datos.nombre)
    if "email" in enviados:
        usuario.email = _validar_email_libre(db, datos.email, excepto_id=usuario.id)
    for campo in ("fecha_nacimiento", "celular"):
        if campo in enviados:
            setattr(usuario, campo, getattr(datos, campo))
    db.flush()
    if "password" in enviados and datos.password:
        auth.cambiar_password(db, usuario, datos.password, autor_id=autor.id, ip=ip, debe_cambiarla=True)
    db.refresh(usuario)
    registrar_auditoria(db, accion="usuario.editar", entidad="usuario", entidad_id=usuario.id,
                        usuario_id=autor.id, estado_anterior=antes, estado_nuevo=usuario, ip_origen=ip)
    return usuario


def cambiar_estado_usuario(db, autor: Usuario, usuario: Usuario, activo: bool, ip) -> Usuario:
    validar_puede_gestionar(autor, usuario.rol)
    if not activo:
        if usuario.id == autor.id:
            raise ReglaDeNegocio("No podés desactivarte a vos mismo")
        if usuario.es_admin:
            raise ReglaDeNegocio("El Admin no se puede desactivar")
    antes = snapshot(usuario)
    usuario.activo = activo
    db.flush()
    if not activo:
        auth.revocar_sesiones_de_usuario(db, usuario.id)
    registrar_auditoria(db, accion="usuario.activar" if activo else "usuario.desactivar", entidad="usuario",
                        entidad_id=usuario.id, usuario_id=autor.id, estado_anterior=antes, estado_nuevo=usuario, ip_origen=ip)
    return usuario


def historial_de_usuario(db, usuario_id: int, *, desde: date | None = None, hasta: date | None = None,
                         resultado: ResultadoAcceso | None = None, pagina: int = 1,
                         tamano: int = 10) -> tuple[list[HistorialAcceso], int]:
    condiciones = [HistorialAcceso.usuario_id == usuario_id]
    if desde:
        condiciones.append(HistorialAcceso.timestamp >= datetime.combine(desde, time.min))
    if hasta:
        condiciones.append(HistorialAcceso.timestamp < datetime.combine(hasta + timedelta(days=1), time.min))
    if resultado is not None:
        condiciones.append(HistorialAcceso.resultado == resultado)
    pagina, tamano = _paginar(pagina, tamano)
    total = db.scalar(select(func.count()).select_from(HistorialAcceso).where(*condiciones))
    filas = db.scalars(
        select(HistorialAcceso).where(*condiciones)
        .order_by(HistorialAcceso.timestamp.desc(), HistorialAcceso.id.desc())
        .offset((pagina - 1) * tamano).limit(tamano)
    ).all()
    return list(filas), total
