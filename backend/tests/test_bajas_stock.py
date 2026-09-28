import pytest
from sqlalchemy import select

from app.core.errores import DatoInvalido, NoEncontrado, ReglaDeNegocio
from app.models import Auditoria, MotivoBaja, TipoMovimientoStock
from app.schemas.categorias import CategoriaCrear
from app.schemas.productos import ProductoCrear
from app.schemas.proveedores import ProveedorCrear
from app.schemas.stock import MotivoBajaCrear, MotivoBajaEditar
from app.services import bajas_stock as servicio
from app.services import categorias as servicio_categorias
from app.services import productos as servicio_productos
from app.services import proveedores as servicio_proveedores
from app.services import stock as servicio_stock


@pytest.fixture
def base(db, crear_usuario):
    admin = crear_usuario("admin")
    ropa = servicio_categorias.crear_categoria(db, admin, CategoriaCrear(nombre="Ropa bajas"), None)
    hoja = servicio_categorias.crear_categoria(db, admin, CategoriaCrear(nombre="Remeras bajas", parent_id=ropa.id), None)
    prov = servicio_proveedores.crear_proveedor(db, admin, ProveedorCrear(nombre="Prov bajas", moneda="ars"), None)

    def alta(descripcion, **extra):
        datos = {"categoria_id": hoja.id, "proveedor_id": prov.id, "costo": "1000", "margen": "0",
                 "descripcion": descripcion}
        datos.update(extra)
        return servicio_productos.crear_producto(db, admin, ProductoCrear(**datos), None)

    return {"admin": admin, "ropa": ropa, "hoja": hoja, "prov": prov, "alta": alta,
            "motivo": db.scalar(select(MotivoBaja).limit(1))}


# --- Motivos de baja -------------------------------------------------------

def test_crear_motivo_normaliza_nombre(db, base):
    m = servicio.crear_motivo(db, base["admin"], MotivoBajaCrear(nombre="  Vencimiento   producto "), None)
    assert m.nombre == "Vencimiento producto" and m.activo is True


def test_motivo_duplicado_sin_mayusculas_ni_tildes(db, base):
    servicio.crear_motivo(db, base["admin"], MotivoBajaCrear(nombre="Promoción"), None)
    with pytest.raises(ReglaDeNegocio):
        servicio.crear_motivo(db, base["admin"], MotivoBajaCrear(nombre="PROMOCION"), None)


def test_editar_motivo_audita_con_estado_anterior(db, base):
    m = servicio.crear_motivo(db, base["admin"], MotivoBajaCrear(nombre="Devolución proveedor"), None)
    editado = servicio.editar_motivo(
        db, base["admin"], m, MotivoBajaEditar(nombre="Devolucion a proveedor", activo=False), None
    )
    assert editado.nombre == "Devolucion a proveedor" and editado.activo is False
    registro = db.scalar(select(Auditoria).where(Auditoria.accion == "motivo_baja.editar", Auditoria.entidad_id == m.id))
    assert registro.estado_anterior["nombre"] == "Devolución proveedor" and registro.estado_anterior["activo"] is True
    assert registro.estado_nuevo["nombre"] == "Devolucion a proveedor" and registro.estado_nuevo["activo"] is False


def test_editar_motivo_duplicado_deja_objeto_intacto(db, base):
    servicio.crear_motivo(db, base["admin"], MotivoBajaCrear(nombre="Ajuste manual"), None)
    otro = servicio.crear_motivo(db, base["admin"], MotivoBajaCrear(nombre="Otro motivo"), None)
    with pytest.raises(ReglaDeNegocio):
        servicio.editar_motivo(db, base["admin"], otro, MotivoBajaEditar(nombre="AJUSTE MANUAL", activo=False), None)
    assert otro.nombre == "Otro motivo" and otro.activo is True


def test_listar_motivos_filtra_por_activo(db, base):
    activo = servicio.crear_motivo(db, base["admin"], MotivoBajaCrear(nombre="Motivo activo test"), None)
    inactivo = servicio.crear_motivo(db, base["admin"], MotivoBajaCrear(nombre="Motivo inactivo test"), None)
    servicio.editar_motivo(db, base["admin"], inactivo, MotivoBajaEditar(nombre=inactivo.nombre, activo=False), None)
    ids = {m.id for m in servicio.listar_motivos(db, activo=True)}
    assert activo.id in ids and inactivo.id not in ids


def test_listar_motivos_filtra_por_nombre_sin_tildes(db, base):
    m = servicio.crear_motivo(db, base["admin"], MotivoBajaCrear(nombre="Promoción vencida"), None)
    encontrados = {x.id for x in servicio.listar_motivos(db, nombre="promocion")}
    assert m.id in encontrados


# --- Bajas de stock ---------------------------------------------------------

def test_registrar_baja_descuenta_stock_y_audita(db, base):
    p = base["alta"]("Remera baja")
    servicio_stock.registrar_ingreso(db, base["admin"], p.id, 10, None, None)
    m = servicio.registrar_baja(db, base["admin"], p.id, 2, base["motivo"].id, "Rotura de percha", None)
    assert (m.cantidad, m.stock_resultante, m.tipo) == (-2, 8, TipoMovimientoStock.BAJA)
    assert m.motivo_baja_id == base["motivo"].id
    assert p.stock == 8
    registro = db.scalar(select(Auditoria).where(Auditoria.accion == "stock.baja", Auditoria.entidad_id == p.id))
    assert registro.estado_anterior == {"stock": 10} and registro.estado_nuevo["stock"] == 8


def test_registrar_baja_motivo_inactivo(db, base):
    p = base["alta"]("Remera motivo inactivo")
    servicio_stock.registrar_ingreso(db, base["admin"], p.id, 5, None, None)
    motivo = servicio.crear_motivo(db, base["admin"], MotivoBajaCrear(nombre="Motivo desactivado"), None)
    servicio.editar_motivo(db, base["admin"], motivo, MotivoBajaEditar(nombre=motivo.nombre, activo=False), None)
    with pytest.raises(ReglaDeNegocio) as error:
        servicio.registrar_baja(db, base["admin"], p.id, 1, motivo.id, None, None)
    assert error.value.mensaje == "El motivo de baja no está activo."
    assert p.stock == 5


def test_registrar_baja_motivo_inexistente(db, base):
    p = base["alta"]("Remera motivo inexistente")
    servicio_stock.registrar_ingreso(db, base["admin"], p.id, 5, None, None)
    with pytest.raises(NoEncontrado):
        servicio.registrar_baja(db, base["admin"], p.id, 1, 999999, None, None)


def test_registrar_baja_cantidad_cero(db, base):
    p = base["alta"]("Remera cantidad cero")
    with pytest.raises(DatoInvalido):
        servicio.registrar_baja(db, base["admin"], p.id, 0, base["motivo"].id, None, None)


def test_registrar_baja_sin_stock_suficiente(db, base):
    p = base["alta"]("Remera sin stock para baja")
    servicio_stock.registrar_ingreso(db, base["admin"], p.id, 1, None, None)
    with pytest.raises(ReglaDeNegocio):
        servicio.registrar_baja(db, base["admin"], p.id, 2, base["motivo"].id, None, None)
    assert p.stock == 1
