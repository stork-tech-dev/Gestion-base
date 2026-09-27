from pathlib import Path

import pytest
from sqlalchemy import select

from config import settings
from app.core.errores import DatoInvalido, ReglaDeNegocio
from app.models import Auditoria
from app.schemas.categorias import CategoriaCrear
from app.schemas.productos import ProductoCrear
from app.schemas.proveedores import ProveedorCrear
from app.services import categorias as servicio_categorias
from app.services import producto_fotos as servicio
from app.services import productos as servicio_productos
from app.services import proveedores as servicio_proveedores

JPG = b"\xff\xd8\xff\xe0" + b"0" * 100
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 100
WEBP = b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"0" * 100


@pytest.fixture
def producto(db, crear_usuario):
    admin = crear_usuario("admin")
    hoja = servicio_categorias.crear_categoria(db, admin, CategoriaCrear(nombre="Fotos"), None)
    prov = servicio_proveedores.crear_proveedor(db, admin, ProveedorCrear(nombre="Prov fotos", moneda="ars"), None)
    p = servicio_productos.crear_producto(db, admin, ProductoCrear(
        categoria_id=hoja.id, proveedor_id=prov.id, costo="10", descripcion="Con fotos"), None)
    return admin, p


def _archivo(foto) -> Path:
    return Path(settings.UPLOADS_DIR) / "productos" / foto.url.rsplit("/", 1)[1]


@pytest.mark.parametrize("contenido, formato", [(JPG, "jpg"), (PNG, "png"), (WEBP, "webp"), (b"GIF89a", None),
                                                 (b"", None), (b"RIFF\x00\x00\x00\x00AVI ", None)])
def test_formato_por_firma(contenido, formato):
    assert servicio.formato_de_imagen(contenido) == formato


def test_subir_guarda_archivo_y_marca_principal(db, producto):
    admin, p = producto
    foto = servicio.subir_foto(db, admin, p, JPG, None)
    assert foto.url.startswith(f"/uploads/productos/{p.sku}_") and foto.url.endswith(".jpg")
    assert len(foto.url.rsplit("_", 1)[1].split(".")[0]) == 12
    assert _archivo(foto).read_bytes() == JPG
    assert foto.es_principal
    segunda = servicio.subir_foto(db, admin, p, PNG, None)
    assert not segunda.es_principal and segunda.orden > foto.orden
    assert db.scalar(select(Auditoria).where(Auditoria.accion == "producto.foto_subir", Auditoria.entidad_id == p.id))


def test_tope_de_cinco_fotos(db, producto):
    admin, p = producto
    for _ in range(5):
        servicio.subir_foto(db, admin, p, JPG, None)
    with pytest.raises(ReglaDeNegocio) as error:
        servicio.subir_foto(db, admin, p, JPG, None)
    assert "5 fotos" in error.value.mensaje


def test_formato_y_tamano_invalidos(db, producto):
    admin, p = producto
    with pytest.raises(DatoInvalido):
        servicio.subir_foto(db, admin, p, b"GIF89a" + b"0" * 10, None)
    with pytest.raises(ReglaDeNegocio):
        servicio.subir_foto(db, admin, p, JPG + b"0" * (5 * 1024 * 1024), None)


def test_marcar_principal_desmarca_la_anterior(db, producto):
    admin, p = producto
    a = servicio.subir_foto(db, admin, p, JPG, None)
    b = servicio.subir_foto(db, admin, p, JPG, None)
    servicio.marcar_principal(db, admin, b, None)
    db.refresh(a)
    assert b.es_principal and not a.es_principal
    auditoria = db.scalar(select(Auditoria).where(Auditoria.accion == "producto.foto_principal", Auditoria.entidad_id == p.id))
    assert auditoria is not None
    assert auditoria.estado_anterior == {"foto_principal_id": a.id}
    assert auditoria.estado_nuevo == {"foto_principal_id": b.id}


def test_eliminar_principal_promueve_la_mas_antigua(db, producto):
    admin, p = producto
    a = servicio.subir_foto(db, admin, p, JPG, None)
    b = servicio.subir_foto(db, admin, p, JPG, None)
    c = servicio.subir_foto(db, admin, p, JPG, None)
    archivo = _archivo(a)
    servicio.eliminar_foto(db, admin, a, None)
    db.refresh(b)
    db.refresh(c)
    assert b.es_principal and not c.es_principal
    assert not archivo.exists()
    auditoria = db.scalar(select(Auditoria).where(Auditoria.accion == "producto.foto_eliminar", Auditoria.entidad_id == p.id))
    assert auditoria is not None
    assert auditoria.estado_nuevo is None
    assert auditoria.estado_anterior["id"] == a.id
    assert auditoria.estado_anterior["es_principal"] is True


def test_eliminar_foto_expira_la_coleccion_del_producto(db, producto):
    """La colección `producto.fotos` puede estar cargada en la sesión desde
    antes de borrar (selectin la trae al acceder p.ej. foto_principal_url):
    después de eliminar_foto no debe seguir mostrando la foto borrada."""
    admin, p = producto
    a = servicio.subir_foto(db, admin, p, JPG, None)
    b = servicio.subir_foto(db, admin, p, JPG, None)
    assert len(p.fotos) == 2  # fuerza la carga de la colección ANTES de borrar
    servicio.eliminar_foto(db, admin, a, None)
    assert [foto.id for foto in p.fotos] == [b.id]
