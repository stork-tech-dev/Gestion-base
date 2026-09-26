"""Usuarios. Las rutas fijas van antes de /{usuario_id}; toda gestión sobre un
usuario pasa por validar_puede_gestionar."""
from datetime import date

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.permisos import Modulo
from app.core.seguridad import requiere_permiso
from app.core.utils import ip_de_request
from app.models import ResultadoAcceso, Usuario
from app.schemas.comunes import RespuestaPaginada
from app.schemas.permisos import AccesoResponse, ActualizarAccesos, ActualizarPermisos, ArbolPermisos
from app.schemas.usuarios import (
    HistorialAccesoResponse,
    RolAsignable,
    UsuarioCrear,
    UsuarioEditar,
    UsuarioEstado,
    UsuarioResponse,
)
from app.services import permisos, roles, usuarios
from app.services.usuarios import TAMANO_MAXIMO

router = APIRouter(prefix="/usuarios", tags=["usuarios"])

puede_ver = requiere_permiso(Modulo.USUARIOS, "ver")
puede_crear = requiere_permiso(Modulo.USUARIOS, "crear")
puede_editar = requiere_permiso(Modulo.USUARIOS, "editar")


@router.get("", response_model=RespuestaPaginada[UsuarioResponse])
def listar(nombre: str | None = None, username: str | None = None, email: str | None = None,
           rol_id: int | None = None, activo: bool | None = None, pagina: int = Query(1, ge=1),
           tamano: int = Query(10, ge=1, le=TAMANO_MAXIMO), db: Session = Depends(get_db),
           _: Usuario = Depends(puede_ver)):
    items, total = usuarios.listar_usuarios(db, nombre=nombre, username=username, email=email, rol_id=rol_id,
                                            activo=activo, pagina=pagina, tamano=tamano)
    return RespuestaPaginada(total=total, pagina=pagina, tamano=tamano,
                             resultados=[UsuarioResponse.desde(u) for u in items])


@router.get("/roles-asignables", response_model=list[RolAsignable])
def roles_asignables(db: Session = Depends(get_db), autor: Usuario = Depends(puede_ver)):
    return usuarios.roles_asignables(db, autor)


@router.get("/accesos", response_model=list[AccesoResponse])
def accesos_de_rol(rol_id: int, db: Session = Depends(get_db), _: Usuario = Depends(puede_ver)):
    return permisos.accesos_de_rol(db, roles.obtener_rol(db, rol_id))


@router.get("/{usuario_id}", response_model=UsuarioResponse)
def detalle(usuario_id: int, db: Session = Depends(get_db), _: Usuario = Depends(puede_ver)):
    return UsuarioResponse.desde(usuarios.obtener_usuario(db, usuario_id))


@router.post("", response_model=UsuarioResponse, status_code=201)
def crear(datos: UsuarioCrear, request: Request, db: Session = Depends(get_db), autor: Usuario = Depends(puede_crear)):
    usuario = usuarios.crear_usuario(db, autor, datos, ip_de_request(request))
    db.commit()
    return UsuarioResponse.desde(usuario)


@router.put("/{usuario_id}", response_model=UsuarioResponse)
def editar(usuario_id: int, datos: UsuarioEditar, request: Request, db: Session = Depends(get_db),
           autor: Usuario = Depends(puede_editar)):
    usuario = usuarios.editar_usuario(db, autor, usuarios.obtener_usuario(db, usuario_id), datos, ip_de_request(request))
    db.commit()
    return UsuarioResponse.desde(usuario)


@router.patch("/{usuario_id}/estado", response_model=UsuarioResponse)
def cambiar_estado(usuario_id: int, datos: UsuarioEstado, request: Request, db: Session = Depends(get_db),
                   autor: Usuario = Depends(puede_editar)):
    usuario = usuarios.cambiar_estado_usuario(db, autor, usuarios.obtener_usuario(db, usuario_id), datos.activo,
                                              ip_de_request(request))
    db.commit()
    return UsuarioResponse.desde(usuario)


@router.get("/{usuario_id}/accesos", response_model=list[AccesoResponse])
def accesos(usuario_id: int, db: Session = Depends(get_db), _: Usuario = Depends(puede_ver)):
    return permisos.accesos_de_usuario(db, usuarios.obtener_usuario(db, usuario_id))


@router.put("/{usuario_id}/accesos", response_model=list[AccesoResponse])
def guardar_accesos(usuario_id: int, datos: ActualizarAccesos, request: Request, db: Session = Depends(get_db),
                    autor: Usuario = Depends(puede_editar)):
    usuario = usuarios.obtener_usuario(db, usuario_id)
    usuarios.validar_puede_gestionar(autor, usuario.rol)
    permisos.actualizar_accesos_usuario(db, autor, usuario, datos.accesos, ip_de_request(request))
    db.commit()
    return permisos.accesos_de_usuario(db, usuario)


@router.get("/{usuario_id}/permisos", response_model=ArbolPermisos)
def ver_permisos(usuario_id: int, db: Session = Depends(get_db), _: Usuario = Depends(puede_ver)):
    return permisos.arbol_de_usuario(db, usuarios.obtener_usuario(db, usuario_id))


@router.put("/{usuario_id}/permisos", response_model=ArbolPermisos)
def guardar_permisos(usuario_id: int, datos: ActualizarPermisos, request: Request, db: Session = Depends(get_db),
                     autor: Usuario = Depends(puede_editar)):
    usuario = usuarios.obtener_usuario(db, usuario_id)
    usuarios.validar_puede_gestionar(autor, usuario.rol)
    permisos.actualizar_permisos_usuario(db, autor, usuario, datos.permisos, ip_de_request(request))
    db.commit()
    return permisos.arbol_de_usuario(db, usuario)


@router.get("/{usuario_id}/historial", response_model=RespuestaPaginada[HistorialAccesoResponse])
def historial(usuario_id: int, desde: date | None = None, hasta: date | None = None,
              resultado: ResultadoAcceso | None = None, pagina: int = Query(1, ge=1),
              tamano: int = Query(10, ge=1, le=TAMANO_MAXIMO), db: Session = Depends(get_db),
              _: Usuario = Depends(puede_ver)):
    usuarios.obtener_usuario(db, usuario_id)
    filas, total = usuarios.historial_de_usuario(db, usuario_id, desde=desde, hasta=hasta, resultado=resultado,
                                                 pagina=pagina, tamano=tamano)
    return RespuestaPaginada(total=total, pagina=pagina, tamano=tamano,
                             resultados=[HistorialAccesoResponse.model_validate(f) for f in filas])
