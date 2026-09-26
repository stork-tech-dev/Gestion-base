"""Roles y su árbol de permisos (solo Admin)."""
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.seguridad import requiere_admin
from app.core.utils import ip_de_request
from app.models import Usuario
from app.schemas.permisos import ActualizarPermisos, ArbolPermisos
from app.schemas.roles import RolCrear, RolEditar, RolEstado, RolResponse
from app.services import permisos, roles

router = APIRouter(prefix="/roles", tags=["roles"])


def _respuesta(db, rol) -> RolResponse:
    return RolResponse.desde(rol, roles.cantidad_usuarios(db, rol.id))


@router.get("", response_model=list[RolResponse])
def listar(nombre: str | None = None, activo: bool | None = None, es_sistema: bool | None = None,
           db: Session = Depends(get_db), _: Usuario = Depends(requiere_admin)):
    return [RolResponse.desde(rol, total) for rol, total in roles.listar_roles(db, nombre=nombre, activo=activo, es_sistema=es_sistema)]


@router.post("", response_model=RolResponse, status_code=201)
def crear(datos: RolCrear, request: Request, db: Session = Depends(get_db), autor: Usuario = Depends(requiere_admin)):
    rol = roles.crear_rol(db, autor, datos.nombre, datos.descripcion, ip_de_request(request))
    db.commit()
    return _respuesta(db, rol)


@router.put("/{rol_id}", response_model=RolResponse)
def editar(rol_id: int, datos: RolEditar, request: Request, db: Session = Depends(get_db),
           autor: Usuario = Depends(requiere_admin)):
    rol = roles.editar_rol(db, autor, roles.obtener_rol(db, rol_id), datos.nombre, datos.descripcion, ip_de_request(request))
    db.commit()
    return _respuesta(db, rol)


@router.patch("/{rol_id}/estado", response_model=RolResponse)
def cambiar_estado(rol_id: int, datos: RolEstado, request: Request, db: Session = Depends(get_db),
                   autor: Usuario = Depends(requiere_admin)):
    rol = roles.cambiar_estado_rol(db, autor, roles.obtener_rol(db, rol_id), datos.activo, ip_de_request(request))
    db.commit()
    return _respuesta(db, rol)


@router.delete("/{rol_id}", status_code=204)
def eliminar(rol_id: int, request: Request, db: Session = Depends(get_db), autor: Usuario = Depends(requiere_admin)):
    roles.eliminar_rol(db, autor, roles.obtener_rol(db, rol_id), ip_de_request(request))
    db.commit()
    return Response(status_code=204)


@router.get("/{rol_id}/permisos", response_model=ArbolPermisos)
def ver_permisos(rol_id: int, db: Session = Depends(get_db), _: Usuario = Depends(requiere_admin)):
    return permisos.arbol_de_rol(db, roles.obtener_rol(db, rol_id))


@router.put("/{rol_id}/permisos", response_model=ArbolPermisos)
def guardar_permisos(rol_id: int, datos: ActualizarPermisos, request: Request, db: Session = Depends(get_db),
                     autor: Usuario = Depends(requiere_admin)):
    rol = roles.obtener_rol(db, rol_id)
    permisos.actualizar_permisos_rol(db, autor, rol, datos.permisos, ip_de_request(request))
    db.commit()
    return permisos.arbol_de_rol(db, rol)
