import pytest

from app.core.permisos import (
    ACCIONES,
    LABEL_MODULO,
    LABEL_RECURSO,
    MODULO_DE_RECURSO,
    ROLES_SISTEMA,
    Modulo,
    Recurso,
    acceso_por_clave,
    acciones_aplicables,
    catalogo_accesos,
    clave_acceso,
    recursos_de_modulo,
    validar_destino,
)


def test_todo_modulo_y_recurso_tiene_label_y_modulo():
    assert set(LABEL_MODULO) == set(Modulo)
    assert set(LABEL_RECURSO) == set(Recurso)
    assert set(MODULO_DE_RECURSO) == set(Recurso)
    for recurso in Recurso:
        assert set(acciones_aplicables(MODULO_DE_RECURSO[recurso], recurso)) <= set(ACCIONES)


def test_roles_de_sistema():
    assert ROLES_SISTEMA == ("admin", "supervisor", "vendedor")


def test_acciones_aplicables_por_modulo_y_recurso():
    assert acciones_aplicables(Modulo.STOCK) == ACCIONES
    assert acciones_aplicables(Modulo.AUDITORIA) == ("ver",)
    assert acciones_aplicables(Modulo.REPORTES) == ("ver",)
    assert acciones_aplicables(Modulo.IMPORTACION) == ("crear",)
    assert acciones_aplicables(Modulo.VENTAS, Recurso.VENTA_ANULAR) == ("eliminar",)
    assert acciones_aplicables(Modulo.CONFIGURACION, Recurso.PROMOCIONES) == ("ver", "crear", "editar")


def test_recursos_de_modulo():
    assert recursos_de_modulo(Modulo.CAJA) == [Recurso.CAJA_ARQUEO, Recurso.CAJA_RETIRO]
    assert recursos_de_modulo(Modulo.CLIENTES) == []


def test_validar_destino():
    assert validar_destino("stock", "stock.baja") == (Modulo.STOCK, Recurso.STOCK_BAJA)
    assert validar_destino("stock", None) == (Modulo.STOCK, None)
    with pytest.raises(ValueError):
        validar_destino("inventado", None)
    with pytest.raises(ValueError):
        validar_destino("ventas", "stock.baja")  # el recurso no es del módulo


def test_catalogo_de_accesos():
    catalogo = catalogo_accesos()
    claves = [a.clave for a in catalogo]
    assert len(claves) == len(set(claves))
    assert catalogo[0].label == "Acceso a tablas y configuración"
    assert clave_acceso(Modulo.CONFIGURACION, None, "ver") == "configuracion::ver"
    masivo = acceso_por_clave("proveedores:dolar.cambio_masivo:editar")
    assert masivo.label == "Modificar: cambio masivo del dólar"
    assert masivo.modulo is Modulo.PROVEEDORES and masivo.recurso is Recurso.DOLAR_CAMBIO_MASIVO
    assert acceso_por_clave("stock:stock.baja:crear").label == "Registrar: bajas de stock"
    assert acceso_por_clave("ventas:venta.anular:eliminar").label == "Realizar: anulación de ventas"
    assert acceso_por_clave("no:existe:ver") is None
    # un casillero por cada (recurso, acción aplicable) + los 5 de módulo
    esperados = 5 + sum(len(acciones_aplicables(MODULO_DE_RECURSO[r], r)) for r in Recurso)
    assert len(catalogo) == esperados
