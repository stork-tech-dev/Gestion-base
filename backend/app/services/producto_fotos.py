"""Fotos de productos en el volumen /uploads (sobreviven a un rebuild).
Hasta 5 por producto; una sola principal; formato por firma de bytes."""
from pathlib import Path
from uuid import uuid4

from sqlalchemy import func, select

from app.core.auditoria import registrar_auditoria
from app.core.errores import DatoInvalido, NoEncontrado, ReglaDeNegocio
from app.models import ProductoFoto
from config import settings

MAXIMO_FOTOS = 5
TAMANO_MAXIMO_FOTO = 5 * 1024 * 1024
URL_BASE = "/uploads/productos"


def _carpeta() -> Path:
    carpeta = Path(settings.UPLOADS_DIR) / "productos"
    carpeta.mkdir(parents=True, exist_ok=True)
    return carpeta


def formato_de_imagen(contenido: bytes) -> str | None:
    """Por firma de bytes, no por extensión ni Content-Type."""
    if contenido.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if contenido.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if len(contenido) >= 12 and contenido[:4] == b"RIFF" and contenido[8:12] == b"WEBP":
        return "webp"
    return None


def obtener_foto(db, foto_id: int) -> ProductoFoto:
    foto = db.get(ProductoFoto, foto_id)
    if foto is None:
        raise NoEncontrado("Foto no encontrada")
    return foto


def _auditar(db, autor, accion, foto, ip) -> None:
    registrar_auditoria(db, accion=accion, entidad="producto", entidad_id=foto.producto_id, usuario_id=autor.id,
                        estado_nuevo={"foto_id": foto.id, "url": foto.url, "es_principal": foto.es_principal},
                        ip_origen=ip)


def subir_foto(db, autor, producto, contenido: bytes, ip) -> ProductoFoto:
    if len(contenido) > TAMANO_MAXIMO_FOTO:
        raise ReglaDeNegocio("La foto supera los 5 MB.")
    formato = formato_de_imagen(contenido)
    if formato is None:
        raise DatoInvalido("La foto tiene que ser JPG, PNG o WEBP.")
    cantidad = db.scalar(select(func.count()).select_from(ProductoFoto).where(ProductoFoto.producto_id == producto.id))
    if cantidad >= MAXIMO_FOTOS:
        raise ReglaDeNegocio(f"Un producto puede tener hasta {MAXIMO_FOTOS} fotos.")
    orden = db.scalar(select(func.coalesce(func.max(ProductoFoto.orden) + 1, 0))
                      .where(ProductoFoto.producto_id == producto.id))
    nombre = f"{producto.sku}_{uuid4().hex[:12]}.{formato}"
    archivo = _carpeta() / nombre
    archivo.write_bytes(contenido)
    try:
        foto = ProductoFoto(producto_id=producto.id, url=f"{URL_BASE}/{nombre}", es_principal=cantidad == 0, orden=orden)
        db.add(foto)
        db.flush()
        db.refresh(foto)
        _auditar(db, autor, "producto.foto_subir", foto, ip)
    except Exception:
        archivo.unlink(missing_ok=True)       # sin fila no queda un archivo huérfano
        raise
    db.expire(producto, ["fotos"])
    return foto


def marcar_principal(db, autor, foto: ProductoFoto, ip) -> ProductoFoto:
    if foto.es_principal:
        return foto
    anterior = db.scalar(select(ProductoFoto).where(ProductoFoto.producto_id == foto.producto_id,
                                                    ProductoFoto.es_principal.is_(True)))
    if anterior is not None:
        anterior.es_principal = False
        db.flush()                            # el índice único parcial no admite dos principales a la vez
    foto.es_principal = True
    db.flush()
    _auditar(db, autor, "producto.foto_principal", foto, ip)
    return foto


def eliminar_foto(db, autor, foto: ProductoFoto, ip) -> None:
    era_principal, producto_id = foto.es_principal, foto.producto_id
    archivo = _carpeta() / foto.url.rsplit("/", 1)[1]
    _auditar(db, autor, "producto.foto_eliminar", foto, ip)
    db.delete(foto)
    db.flush()
    if era_principal:
        siguiente = db.scalar(select(ProductoFoto).where(ProductoFoto.producto_id == producto_id)
                              .order_by(ProductoFoto.created_at, ProductoFoto.id).limit(1))
        if siguiente is not None:
            siguiente.es_principal = True
            db.flush()
    # Último paso: el archivo no vuelve con un rollback.
    archivo.unlink(missing_ok=True)
