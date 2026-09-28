"""Categorías de productos, en árbol (hasta NIVEL_MAXIMO niveles)."""
from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.permisos import Modulo
from app.core.seguridad import requiere_permiso
from app.core.utils import ip_de_request
from app.models import NIVEL_MAXIMO, Usuario
from app.schemas.categorias import CategoriaCrear, CategoriaEditar, CategoriaMover, CategoriaNodo, CategoriaResponse
from app.services import categorias as servicio

router = APIRouter(prefix="/categorias", tags=["categorias"])

puede_ver = requiere_permiso(Modulo.PRODUCTOS, "ver")
puede_crear = requiere_permiso(Modulo.PRODUCTOS, "crear")
puede_editar = requiere_permiso(Modulo.PRODUCTOS, "editar")
puede_eliminar = requiere_permiso(Modulo.PRODUCTOS, "eliminar")


@router.get("", response_model=list[CategoriaResponse])
def listar(nombre: str | None = None, nivel: int | None = Query(None, ge=1, le=NIVEL_MAXIMO),
           parent_id: int | None = None, db: Session = Depends(get_db), _: Usuario = Depends(puede_ver)):
    return servicio.listar_categorias(db, nombre=nombre, nivel=nivel, parent_id=parent_id)


@router.get("/arbol", response_model=list[CategoriaNodo])
def arbol(db: Session = Depends(get_db), _: Usuario = Depends(puede_ver)):
    return servicio.arbol(db)


@router.get("/{categoria_id}", response_model=CategoriaResponse)
def ficha(categoria_id: int, db: Session = Depends(get_db), _: Usuario = Depends(puede_ver)):
    return servicio.obtener_categoria(db, categoria_id)


@router.post("", response_model=CategoriaResponse, status_code=201)
def crear(datos: CategoriaCrear, request: Request, db: Session = Depends(get_db), autor: Usuario = Depends(puede_crear)):
    categoria = servicio.crear_categoria(db, autor, datos, ip_de_request(request))
    db.commit()
    return categoria


@router.put("/{categoria_id}", response_model=CategoriaResponse)
def editar(categoria_id: int, datos: CategoriaEditar, request: Request, db: Session = Depends(get_db),
           autor: Usuario = Depends(puede_editar)):
    categoria = servicio.editar_categoria(db, autor, servicio.obtener_categoria(db, categoria_id), datos,
                                          ip_de_request(request))
    db.commit()
    return categoria


@router.patch("/{categoria_id}/mover", response_model=CategoriaResponse)
def mover(categoria_id: int, datos: CategoriaMover, request: Request, db: Session = Depends(get_db),
          autor: Usuario = Depends(puede_editar)):
    categoria = servicio.mover_categoria(db, autor, servicio.obtener_categoria(db, categoria_id), datos.parent_id,
                                         ip_de_request(request))
    db.commit()
    return categoria


@router.delete("/{categoria_id}", status_code=204)
def eliminar(categoria_id: int, request: Request, db: Session = Depends(get_db), autor: Usuario = Depends(puede_eliminar)):
    servicio.eliminar_categoria(db, autor, servicio.obtener_categoria(db, categoria_id), ip_de_request(request))
    db.commit()
    return Response(status_code=204)
