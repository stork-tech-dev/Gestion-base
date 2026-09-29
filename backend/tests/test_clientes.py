"""Tests de services/clientes.py (sesión 06)."""
import itertools
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.codigos import cuit_es_valido
from app.core.errores import DatoInvalido, NoEncontrado, ReglaDeNegocio
from app.core.utils import ahora_db
from app.models import Auditoria, CondicionIva, EstadoVenta, Venta
from app.schemas.clientes import ClienteCrear, ClienteEditar
from app.services import clientes as servicio

_numeros = itertools.count(1)


def _crear_venta(db, cliente, usuario, total, estado=EstadoVenta.CONFIRMADA):
    """Crea una venta a mano (Task 3/4 todavía no existen): CONFIRMADA exige
    codigo_cambio y confirmada_en por el CHECK de la tabla."""
    n = next(_numeros)
    venta = Venta(
        numero=f"V{n:010d}",
        cliente_id=cliente.id if cliente else None,
        usuario_id=usuario.id,
        estado=estado,
        total=Decimal(str(total)),
        codigo_cambio=f"C{n:07d}" if estado != EstadoVenta.EN_CURSO else None,
        confirmada_en=ahora_db() if estado != EstadoVenta.EN_CURSO else None,
    )
    db.add(venta)
    db.flush()
    return venta


# --- solo_digitos ------------------------------------------------------------

def test_solo_digitos_limpia_formato():
    assert servicio.solo_digitos("20-39059158-1") == "20390591581"
    assert servicio.solo_digitos("   ") is None
    assert servicio.solo_digitos("") is None
    assert servicio.solo_digitos(None) is None


# --- Alta y validaciones -------------------------------------------------------

def test_crear_cliente_normaliza_nombre(db, crear_usuario):
    admin = crear_usuario("admin")
    c = servicio.crear_cliente(db, admin, ClienteCrear(nombre="  Juan   Perez  "), None)
    assert c.nombre == "Juan Perez"
    assert c.activo is True
    assert c.condicion_iva == CondicionIva.CONSUMIDOR_FINAL


def test_dni_longitud_invalida(db, crear_usuario):
    admin = crear_usuario("admin")
    with pytest.raises(DatoInvalido):
        servicio.crear_cliente(db, admin, ClienteCrear(nombre="Cliente dni corto", dni="123"), None)


def test_dni_se_limpia_a_digitos(db, crear_usuario):
    admin = crear_usuario("admin")
    c = servicio.crear_cliente(db, admin, ClienteCrear(nombre="Cliente dni con guiones", dni="30-123-456"), None)
    assert c.dni == "30123456"


def test_cuit_verificador_invalido(db, crear_usuario):
    admin = crear_usuario("admin")
    # NOTA: el brief sugería 20390591581 como CUIT válido, pero
    # cuit_es_valido (dígito verificador módulo 11) lo rechaza: el válido
    # real con esos primeros 10 dígitos es 20390591587 (confirmado con la
    # propia función, tal como pide el brief).
    assert cuit_es_valido("20390591587") is True
    assert cuit_es_valido("20390591582") is False
    with pytest.raises(DatoInvalido, match="dígito verificador"):
        servicio.crear_cliente(db, admin, ClienteCrear(nombre="Cliente cuit invalido", cuit="20390591582"), None)
    c = servicio.crear_cliente(db, admin, ClienteCrear(nombre="Cliente cuit valido", cuit="20-39059158-7"), None)
    assert c.cuit == "20390591587"


def test_cuit_obligatorio_fuera_de_consumidor_final(db, crear_usuario):
    admin = crear_usuario("admin")
    with pytest.raises(DatoInvalido, match="consumidor final"):
        servicio.crear_cliente(
            db, admin,
            ClienteCrear(nombre="Responsable sin cuit", condicion_iva=CondicionIva.RESPONSABLE_INSCRIPTO),
            None,
        )
    c = servicio.crear_cliente(
        db, admin,
        ClienteCrear(nombre="Responsable con cuit", condicion_iva=CondicionIva.RESPONSABLE_INSCRIPTO,
                    cuit="20390591587"),
        None,
    )
    assert c.condicion_iva == CondicionIva.RESPONSABLE_INSCRIPTO


def test_dni_unico_nombra_al_otro_cliente(db, crear_usuario):
    admin = crear_usuario("admin")
    original = servicio.crear_cliente(db, admin, ClienteCrear(nombre="Cliente original", dni="30123456"), None)
    with pytest.raises(ReglaDeNegocio) as error:
        servicio.crear_cliente(db, admin, ClienteCrear(nombre="Cliente repetido", dni="30123456"), None)
    assert "30123456" in error.value.mensaje
    assert original.nombre in error.value.mensaje


def test_cuit_unico_nombra_al_otro_cliente(db, crear_usuario):
    admin = crear_usuario("admin")
    original = servicio.crear_cliente(db, admin, ClienteCrear(nombre="Cliente cuit original", cuit="20390591587"), None)
    with pytest.raises(ReglaDeNegocio) as error:
        servicio.crear_cliente(db, admin, ClienteCrear(nombre="Cliente cuit repetido", cuit="20390591587"), None)
    assert "20390591587" in error.value.mensaje
    assert original.nombre in error.value.mensaje


def test_editar_excluye_el_propio_id(db, crear_usuario):
    admin = crear_usuario("admin")
    c = servicio.crear_cliente(db, admin, ClienteCrear(nombre="Cliente editable", dni="30111222"), None)
    editado = servicio.editar_cliente(db, admin, c, ClienteEditar(nombre="Cliente editado", dni="30111222"), None)
    assert editado.nombre == "Cliente editado"
    assert editado.dni == "30111222"


def test_editar_cliente_dni_duplicado_de_otro(db, crear_usuario):
    admin = crear_usuario("admin")
    a = servicio.crear_cliente(db, admin, ClienteCrear(nombre="Cliente A", dni="30000001"), None)
    b = servicio.crear_cliente(db, admin, ClienteCrear(nombre="Cliente B", dni="30000002"), None)
    with pytest.raises(ReglaDeNegocio):
        servicio.editar_cliente(db, admin, b, ClienteEditar(nombre="Cliente B", dni="30000001"), None)
    assert a.dni == "30000001"


def test_obtener_cliente_inexistente(db):
    with pytest.raises(NoEncontrado):
        servicio.obtener_cliente(db, 999999)


# --- Auditoría -----------------------------------------------------------------

def test_editar_cliente_audita_con_estado_anterior(db, crear_usuario):
    admin = crear_usuario("admin")
    c = servicio.crear_cliente(db, admin, ClienteCrear(nombre="Cliente auditado"), None)
    servicio.editar_cliente(db, admin, c, ClienteEditar(nombre="Cliente auditado editado"), None)
    registro = db.scalar(select(Auditoria).where(Auditoria.accion == "cliente.editar", Auditoria.entidad_id == c.id))
    assert registro.estado_anterior["nombre"] == "Cliente auditado"
    assert registro.estado_nuevo["nombre"] == "Cliente auditado editado"


def test_crear_cliente_audita(db, crear_usuario):
    admin = crear_usuario("admin")
    c = servicio.crear_cliente(db, admin, ClienteCrear(nombre="Cliente creado auditado"), None)
    registro = db.scalar(select(Auditoria).where(Auditoria.accion == "cliente.crear", Auditoria.entidad_id == c.id))
    assert registro is not None


def test_cambiar_estado_audita_activar_y_desactivar(db, crear_usuario):
    admin = crear_usuario("admin")
    c = servicio.crear_cliente(db, admin, ClienteCrear(nombre="Cliente estado"), None)

    servicio.cambiar_estado(db, admin, c, False, None)
    assert c.activo is False
    registro = db.scalar(
        select(Auditoria).where(Auditoria.accion == "cliente.desactivar", Auditoria.entidad_id == c.id))
    assert registro is not None

    servicio.cambiar_estado(db, admin, c, True, None)
    assert c.activo is True
    registro = db.scalar(
        select(Auditoria).where(Auditoria.accion == "cliente.activar", Auditoria.entidad_id == c.id))
    assert registro is not None


# --- Listado y búsqueda ---------------------------------------------------------

def test_listar_clientes_filtra_por_localidad(db, crear_usuario):
    admin = crear_usuario("admin")
    c = servicio.crear_cliente(db, admin, ClienteCrear(nombre="Cliente cordoba", localidad="Córdoba"), None)
    resultados, total = servicio.listar_clientes(db, localidad="cordoba")
    assert c.id in {x.id for x in resultados}
    assert total >= 1


def test_buscar_por_nombre_sin_tildes(db, crear_usuario):
    admin = crear_usuario("admin")
    c = servicio.crear_cliente(db, admin, ClienteCrear(nombre="José María Ñáñez"), None)
    encontrados = {x.id for x in servicio.buscar(db, "jose maria nanez")}
    assert c.id in encontrados


def test_buscar_por_prefijo_de_dni(db, crear_usuario):
    admin = crear_usuario("admin")
    c = servicio.crear_cliente(db, admin, ClienteCrear(nombre="Cliente dni buscar", dni="30999888"), None)
    encontrados = {x.id for x in servicio.buscar(db, "309998")}
    assert c.id in encontrados


def test_buscar_por_prefijo_de_cuit(db, crear_usuario):
    admin = crear_usuario("admin")
    c = servicio.crear_cliente(db, admin, ClienteCrear(nombre="Cliente cuit buscar", cuit="20390591587"), None)
    encontrados = {x.id for x in servicio.buscar(db, "2039059")}
    assert c.id in encontrados


def test_buscar_excluye_inactivos(db, crear_usuario):
    admin = crear_usuario("admin")
    c = servicio.crear_cliente(db, admin, ClienteCrear(nombre="Cliente inactivo buscar"), None)
    servicio.cambiar_estado(db, admin, c, False, None)
    encontrados = {x.id for x in servicio.buscar(db, "Cliente inactivo buscar")}
    assert c.id not in encontrados


# --- Ficha -----------------------------------------------------------------

def test_ficha_cuenta_solo_confirmadas(db, crear_usuario):
    admin = crear_usuario("admin")
    cliente = servicio.crear_cliente(db, admin, ClienteCrear(nombre="Cliente ficha"), None)
    otro = servicio.crear_cliente(db, admin, ClienteCrear(nombre="Cliente ficha otro"), None)

    _crear_venta(db, cliente, admin, "1000")
    _crear_venta(db, cliente, admin, "2000")
    _crear_venta(db, cliente, admin, "500", estado=EstadoVenta.EN_CURSO)
    anulada = _crear_venta(db, cliente, admin, "300")
    anulada.estado = EstadoVenta.ANULADA
    anulada.anulada_en = ahora_db()
    anulada.anulada_por_id = admin.id
    anulada.motivo_anulacion = "Cancelada en test"
    db.flush()
    _crear_venta(db, otro, admin, "999")

    resultado = servicio.ficha(db, cliente.id)
    assert resultado["compras_cantidad"] == 2
    assert resultado["compras_total"] == Decimal("3000")
    assert resultado["promociones"] == []
    assert resultado["cliente"].id == cliente.id


def test_ficha_sin_compras(db, crear_usuario):
    admin = crear_usuario("admin")
    cliente = servicio.crear_cliente(db, admin, ClienteCrear(nombre="Cliente ficha vacia"), None)
    resultado = servicio.ficha(db, cliente.id)
    assert resultado["compras_cantidad"] == 0
    assert resultado["compras_total"] == Decimal("0")


def test_ficha_cliente_inexistente(db):
    with pytest.raises(NoEncontrado):
        servicio.ficha(db, 999999)
