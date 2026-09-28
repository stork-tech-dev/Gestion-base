"""Fotos de productos en el volumen /uploads (sobreviven a un rebuild).
Hasta 5 por producto; una sola principal; formato por firma de bytes."""
from pathlib import Path
from uuid import uuid4

from sqlalchemy import func, select

from app.core.auditoria import registrar_auditoria, snapshot
from app.core.errores import DatoInvalido, NoEncontrado, ReglaDeNegocio
from app.models import Producto, ProductoFoto
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


def _auditar(db, autor, accion, producto_id, ip, *, estado_anterior=None, estado_nuevo=None) -> None:
    """Las tres acciones sobre fotos se auditan como acciones del PRODUCTO
    (la foto en sí no es la entidad que le importa a quien lee la auditoría)."""
    registrar_auditoria(db, accion=accion, entidad="producto", entidad_id=producto_id, usuario_id=autor.id,
                        estado_anterior=estado_anterior, estado_nuevo=estado_nuevo, ip_origen=ip)


def _bloquear_producto(db, producto_id: int) -> None:
    """SELECT ... FOR UPDATE de la fila del producto: serializa las altas,
    bajas y cambios de principal sobre las fotos de un mismo producto (si no,
    dos subidas simultáneas pueden contar 4 fotos cada una y terminar en 6)."""
    db.execute(select(Producto.id).where(Producto.id == producto_id).with_for_update())


def _bloquear_y_releer(db, foto: ProductoFoto) -> ProductoFoto:
    """Lock del producto y relectura de la foto DESPUÉS del lock: mientras se
    esperaba, otra transacción pudo borrarla o cambiar la principal."""
    _bloquear_producto(db, foto.producto_id)
    releida = db.get(ProductoFoto, foto.id, populate_existing=True)
    if releida is None:
        raise NoEncontrado("Foto no encontrada")
    return releida


def subir_foto(db, autor, producto, contenido: bytes, ip) -> ProductoFoto:
    if len(contenido) > TAMANO_MAXIMO_FOTO:
        raise ReglaDeNegocio("La foto supera los 5 MB.")
    formato = formato_de_imagen(contenido)
    if formato is None:
        raise DatoInvalido("La foto tiene que ser JPG, PNG o WEBP.")
    _bloquear_producto(db, producto.id)
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
        _auditar(db, autor, "producto.foto_subir", producto.id, ip,
                estado_nuevo={"foto_id": foto.id, "url": foto.url, "es_principal": foto.es_principal})
    except Exception:
        archivo.unlink(missing_ok=True)       # sin fila no queda un archivo huérfano
        raise
    db.expire(producto, ["fotos"])
    return foto


def marcar_principal(db, autor, foto: ProductoFoto, ip) -> ProductoFoto:
    foto = _bloquear_y_releer(db, foto)
    if foto.es_principal:
        return foto
    # populate_existing: si la fila ya estaba en la sesión, sus atributos se
    # releen (con valores viejos en memoria, el UPDATE podría no emitirse).
    anterior = db.scalar(select(ProductoFoto).where(ProductoFoto.producto_id == foto.producto_id,
                                                    ProductoFoto.es_principal.is_(True))
                         .execution_options(populate_existing=True))
    anterior_id = anterior.id if anterior is not None else None
    if anterior is not None:
        anterior.es_principal = False
        db.flush()                            # el índice único parcial no admite dos principales a la vez
    foto.es_principal = True
    db.flush()
    db.expire(db.get(Producto, foto.producto_id), ["fotos"])
    _auditar(db, autor, "producto.foto_principal", foto.producto_id, ip,
            estado_anterior={"foto_principal_id": anterior_id}, estado_nuevo={"foto_principal_id": foto.id})
    return foto


def eliminar_foto(db, autor, foto: ProductoFoto, ip) -> None:
    foto = _bloquear_y_releer(db, foto)
    era_principal, producto_id = foto.es_principal, foto.producto_id
    archivo = _carpeta() / foto.url.rsplit("/", 1)[1]
    antes = snapshot(foto)                    # tomado ANTES del delete: después ya no se puede leer
    db.delete(foto)
    db.flush()
    if era_principal:
        siguiente = db.scalar(select(ProductoFoto).where(ProductoFoto.producto_id == producto_id)
                              .order_by(ProductoFoto.created_at, ProductoFoto.id).limit(1)
                              .execution_options(populate_existing=True))   # ver marcar_principal
        if siguiente is not None:
            siguiente.es_principal = True
            db.flush()
    db.expire(db.get(Producto, producto_id), ["fotos"])
    _auditar(db, autor, "producto.foto_eliminar", producto_id, ip, estado_anterior=antes)
    # Último paso: el archivo no vuelve con un rollback.
    archivo.unlink(missing_ok=True)
