from decimal import Decimal

import pytest
from sqlalchemy import select, text

from app.core.codigos import digito_verificador
from app.core.errores import DatoInvalido, NoEncontrado, ReglaDeNegocio, SinPermiso
from app.models import Auditoria, ConfiguracionSistema, EstadoProveedor, Producto
from app.schemas.categorias import CategoriaCrear
from app.schemas.productos import ProductoCrear, ProductoEditar
from app.schemas.proveedores import ProveedorCrear
from app.services import categorias as servicio_categorias
from app.services import productos as servicio
from app.services import proveedores as servicio_proveedores


@pytest.fixture
def admin(crear_usuario):
    return crear_usuario("admin")


@pytest.fixture
def config(db):
    """redondeo 100, margen_default 50, descuento_maximo 30 (valores fijos para los tests)."""
    fila = db.scalar(select(ConfiguracionSistema))
    fila.redondeo, fila.margen_default, fila.descuento_maximo = Decimal("100"), Decimal("50"), Decimal("30")
    db.flush()
    return fila


@pytest.fixture
def base(db, admin, config):
    ropa = servicio_categorias.crear_categoria(db, admin, CategoriaCrear(nombre="Ropa"), None)
    remeras = servicio_categorias.crear_categoria(db, admin, CategoriaCrear(nombre="Remeras", parent_id=ropa.id), None)
    pesos = servicio_proveedores.crear_proveedor(db, admin, ProveedorCrear(nombre="Prov pesos", moneda="ars"), None)
    dolares = servicio_proveedores.crear_proveedor(
        db, admin, ProveedorCrear(nombre="Prov dólares", moneda="usd", dolar_actual="1000"), None)
    return {"ropa": ropa, "hoja": remeras, "pesos": pesos, "dolares": dolares}


def _alta(db, autor, base, **extra):
    datos = {"categoria_id": base["hoja"].id, "proveedor_id": base["pesos"].id, "costo": "1000",
             "descripcion": "remera lisa roja"}
    datos.update(extra)
    return servicio.crear_producto(db, autor, ProductoCrear(**datos), None)


def _editar(db, autor, producto, **cambios):
    datos = {"categoria_id": producto.categoria_id, "costo": str(producto.costo), "margen": str(producto.margen),
             "descripcion": producto.descripcion}
    datos.update(cambios)
    return servicio.editar_producto(db, autor, producto, ProductoEditar(**datos), None)


def test_alta_genera_codigo_y_precio_en_pesos(db, admin, base):
    p = _alta(db, admin, base)
    assert len(p.sku) == 5 and p.verificador == digito_verificador(p.sku)
    assert p.descripcion == "Remera lisa roja"
    assert p.margen == Decimal("50.00")                      # margen_default
    assert p.precio_venta == Decimal("1500.00")              # 1000 × 1.5, ya múltiplo de 100
    assert db.scalar(select(Auditoria).where(Auditoria.accion == "producto.crear", Auditoria.entidad_id == p.id))


def test_skus_correlativos(db, admin, base):
    a = _alta(db, admin, base, descripcion="Uno")
    b = _alta(db, admin, base, descripcion="Dos")
    from app.core.codigos import decodificar_sku
    assert decodificar_sku(b.sku) == decodificar_sku(a.sku) + 1


def test_precio_en_dolares_con_ceil(db, admin, base):
    p = _alta(db, admin, base, proveedor_id=base["dolares"].id, costo="10.01", margen="10")
    # 10.01 × 1000 × 1.10 = 11011 → CEIL a 100 = 11100
    assert p.precio_venta == Decimal("11100.00")


def test_precio_preview(db, base):
    vista = servicio.precio_preview(db, base["dolares"].id, Decimal("10.01"), margen=Decimal("10"))
    assert vista == {"moneda": "usd", "dolar_proveedor": Decimal("1000.00"), "precio_venta": Decimal("11100.00"),
                     "margen": Decimal("10.00"), "redondeo": Decimal("100"), "redondeado": True}
    vista = servicio.precio_preview(db, base["pesos"].id, Decimal("1001"), margen=Decimal("0"))
    assert vista == {"moneda": "ars", "dolar_proveedor": None, "precio_venta": Decimal("1100.00"),
                     "margen": Decimal("0.00"), "redondeo": Decimal("100"), "redondeado": True}


def test_precio_preview_con_precio_manual(db, base):
    # Precio manual: precio exacto (sin CEIL al redondeo) y margen derivado.
    vista = servicio.precio_preview(db, base["pesos"].id, Decimal("1000"), precio_venta=Decimal("1550"))
    assert vista == {"moneda": "ars", "dolar_proveedor": None, "precio_venta": Decimal("1550.00"),
                     "margen": Decimal("55.00"), "redondeo": Decimal("100"), "redondeado": False}


def test_alta_con_precio_venta_manual_en_pesos(db, admin, base):
    p = _alta(db, admin, base, costo="1000", precio_venta="1500")
    assert p.precio_venta == Decimal("1500.00")            # exacto, no múltiplo forzado de otra cosa
    assert p.margen == Decimal("50.00")


def test_alta_con_precio_venta_manual_en_dolares(db, admin, base):
    p = _alta(db, admin, base, proveedor_id=base["dolares"].id, costo="2", precio_venta="2500")
    assert p.precio_venta == Decimal("2500.00")
    assert p.margen == Decimal("25.00")                    # 2500 / (2*1000) - 1 = 25 %


def test_precio_venta_manual_menor_al_costo_o_margen_excesivo(db, admin, base):
    with pytest.raises(DatoInvalido) as error:
        _alta(db, admin, base, costo="1000", precio_venta="500")
    assert "no puede ser menor al costo" in error.value.mensaje
    with pytest.raises(DatoInvalido) as error:
        _alta(db, admin, base, costo="100", precio_venta="1200")   # margen 1100 % > 1000 %
    assert "1000" in error.value.mensaje


def test_precio_venta_apenas_por_debajo_del_costo_se_rechaza(db, admin, base):
    """Redondear el margen a 2 decimales ANTES de comparar convertía un
    margen apenas negativo (ej. -0.001 %) en "-0.00", que no es < 0: un
    precio apenas por debajo del costo se guardaba con margen 0. La
    comparación ahora es exacta, antes de redondear nada."""
    with pytest.raises(DatoInvalido) as error:
        _alta(db, admin, base, costo="1000", precio_venta="999.99")
    assert "no puede ser menor al costo" in error.value.mensaje


def test_precio_venta_igual_al_costo_se_acepta_con_margen_cero(db, admin, base):
    p = _alta(db, admin, base, costo="1000", precio_venta="1000")
    assert p.precio_venta == Decimal("1000.00") and p.margen == Decimal("0.00")


def test_edicion_con_precio_venta_manual_recalcula_margen(db, admin, base):
    p = _alta(db, admin, base, costo="1000", margen="0")            # precio 1000.00
    datos = ProductoEditar(categoria_id=p.categoria_id, descripcion=p.descripcion, costo="1000",
                           precio_venta="1300")
    editado = servicio.editar_producto(db, admin, p, datos, None)
    assert editado.precio_venta == Decimal("1300.00") and editado.margen == Decimal("30.00")


def test_edicion_con_margen_y_costo_nuevo_recalcula_con_la_formula(db, admin, base):
    p = _alta(db, admin, base, costo="1000", margen="0")
    editado = _editar(db, admin, p, costo="2000", margen="20")
    assert editado.precio_venta == Decimal("2400.00")               # 2000 × 1.20, formula + redondeo


def test_precio_manual_y_cambio_de_dolar_recalcula_con_margen_y_redondeo(db, admin, base):
    """Un precio cargado a mano queda EXACTO solo hasta el próximo recálculo:
    un cambio de dólar del proveedor (o de costo/margen en otra edición)
    vuelve a pasar por la fórmula con el margen derivado y el redondeo
    configurado, así que el precio exacto puede dejar de serlo."""
    p = _alta(db, admin, base, proveedor_id=base["dolares"].id, costo="2", precio_venta="2500")
    assert p.precio_venta == Decimal("2500.00") and p.margen == Decimal("25.00")
    servicio_proveedores.cambiar_dolar(db, admin, base["dolares"], Decimal("2000"), None)
    db.refresh(p)
    assert p.precio_venta == Decimal("5000.00")                     # CEIL(2 × 2000 × 1.25, 100) = 5000


def test_recalculo_por_cambio_de_dolar(db, admin, base):
    p = _alta(db, admin, base, proveedor_id=base["dolares"].id, costo="10", margen="0")
    otro = _alta(db, admin, base, descripcion="En pesos", costo="1000", margen="0")
    assert p.precio_venta == Decimal("10000.00")
    servicio_proveedores.cambiar_dolar(db, admin, base["dolares"], Decimal("1234"), None)
    db.refresh(p)
    assert p.precio_venta == Decimal("12400.00")             # 12340 → CEIL 100
    assert otro.precio_venta == Decimal("1000.00")
    assert servicio.recalcular_precios_de_proveedor(db, base["pesos"].id) == 0


def test_recalculo_desborda_no_modifica_nada_y_localiza_el_producto(db, admin, base):
    """Dos pasadas: se calculan TODOS los precios antes de asignar ninguno. Si
    uno desborda el tope, el que ya se había calculado bien no debe quedar
    modificado en la sesión (se comprueba sin refresh: si se hubiera asignado
    dentro del mismo loop que calcula, quedaría con el precio nuevo en memoria
    aunque la operación general falle)."""
    bajo = _alta(db, admin, base, proveedor_id=base["dolares"].id, descripcion="Bajo el tope", costo="10", margen="0")
    alto = _alta(db, admin, base, proveedor_id=base["dolares"].id, descripcion="Supera el tope", costo="99000", margen="0")
    precio_bajo, precio_alto = bajo.precio_venta, alto.precio_venta
    with pytest.raises(ReglaDeNegocio) as error:
        servicio_proveedores.cambiar_dolar(db, admin, base["dolares"], Decimal("2000"), None)
    assert alto.sku in error.value.mensaje and "Prov dólares" in error.value.mensaje
    assert "máximo permitido" in error.value.mensaje
    assert bajo.precio_venta == precio_bajo and alto.precio_venta == precio_alto   # nada se tocó, sin refresh


def test_edicion_recalcula_y_audita(db, admin, base):
    p = _alta(db, admin, base, costo="1000", margen="0")
    _editar(db, admin, p, costo="2000", margen="10")
    assert p.precio_venta == Decimal("2200.00")
    registro = db.scalar(select(Auditoria).where(Auditoria.accion == "producto.editar", Auditoria.entidad_id == p.id))
    assert registro.estado_anterior["precio_venta"] == "1000.00" and registro.estado_nuevo["precio_venta"] == "2200.00"
    assert registro.estado_anterior["costo"] == "1000.00" and registro.estado_nuevo["margen"] == "10.00"


def test_sku_y_proveedor_no_se_editan(db, admin, base):
    p = _alta(db, admin, base)
    sku, verificador, proveedor_id = p.sku, p.verificador, p.proveedor_id
    _editar(db, admin, p, descripcion="Remera lisa bordó")
    assert (p.sku, p.verificador, p.proveedor_id) == (sku, verificador, proveedor_id)
    assert "proveedor_id" not in ProductoEditar.model_fields


def test_descripcion_duplicada(db, admin, base):
    p = _alta(db, admin, base, descripcion="Remera lisa roja")
    with pytest.raises(ReglaDeNegocio) as error:
        _alta(db, admin, base, descripcion="REMERA LISA ROJA")
    assert p.sku in error.value.mensaje and "otro color o talle" in error.value.mensaje
    servicio.cambiar_estado_producto(db, admin, p, False, None)
    with pytest.raises(ReglaDeNegocio) as error:
        _alta(db, admin, base, descripcion="remera lisa roja")
    assert "está inactivo y se puede volver a activar" in error.value.mensaje
    _alta(db, admin, base, descripcion="Remera lisa roja", proveedor_id=base["dolares"].id)   # otro proveedor: ok


def test_validaciones_del_alta(db, admin, base):
    with pytest.raises(ReglaDeNegocio) as error:
        _alta(db, admin, base, categoria_id=base["ropa"].id)            # no es hoja
    assert "último nivel" in error.value.mensaje
    with pytest.raises(NoEncontrado):
        _alta(db, admin, base, categoria_id=999999)
    with pytest.raises(NoEncontrado):
        _alta(db, admin, base, proveedor_id=999999)
    servicio_proveedores.cambiar_estado(db, admin, base["pesos"], EstadoProveedor.DESACTIVADO, False, None)
    with pytest.raises(ReglaDeNegocio) as error:
        _alta(db, admin, base)
    assert "proveedor" in error.value.mensaje.lower()


def test_descuento_maximo(db, admin, base):
    with pytest.raises(DatoInvalido) as error:
        _alta(db, admin, base, descuento_producto="30.01")
    assert "30" in error.value.mensaje
    assert _alta(db, admin, base, descuento_producto="30").descuento_producto == Decimal("30.00")


def test_stock_infinito_solo_admin(db, admin, base, crear_usuario):
    supervisor = crear_usuario("supervisor")
    with pytest.raises(SinPermiso) as error:
        _alta(db, supervisor, base, stock_infinito=True)
    assert error.value.mensaje == "El stock infinito lo define el Admin"
    p = _alta(db, admin, base, stock_infinito=True)
    _editar(db, supervisor, p, descripcion="Remera editada", stock_infinito=True)   # no cambia: se permite
    with pytest.raises(SinPermiso):
        _editar(db, supervisor, p, stock_infinito=False)
    _editar(db, supervisor, p, descripcion="Remera sin el campo")          # omitido: no cambia
    assert p.stock_infinito and p.descripcion == "Remera sin el campo"


def test_edicion_valida_antes_de_modificar(db, admin, base):
    _alta(db, admin, base, descripcion="Existente")
    p = _alta(db, admin, base, descripcion="Otra", costo="1000", margen="0")
    with pytest.raises(ReglaDeNegocio):
        _editar(db, admin, p, descripcion="existente", costo="5000")
    assert p.costo == Decimal("1000.00") and p.descripcion == "Otra" and p.precio_venta == Decimal("1000.00")


def test_estado(db, admin, base):
    p = _alta(db, admin, base)
    servicio.cambiar_estado_producto(db, admin, p, False, None)
    servicio.cambiar_estado_producto(db, admin, p, False, None)      # sin cambio: no audita
    servicio.cambiar_estado_producto(db, admin, p, True, None)
    acciones = db.scalars(select(Auditoria.accion).where(Auditoria.entidad == "producto", Auditoria.entidad_id == p.id)
                          .order_by(Auditoria.id)).all()
    assert acciones == ["producto.crear", "producto.desactivar", "producto.activar"]


def test_respuesta(db, admin, base):
    p = _alta(db, admin, base, proveedor_id=base["dolares"].id, costo="10")
    (r,) = servicio.a_respuesta(db, [p])
    assert r.codigo_con_verificador == p.sku + p.verificador and r.moneda == "usd"
    assert r.categoria.camino == "Ropa > Remeras" and r.proveedor.nombre == "Prov dólares"
    assert r.foto_url is None
    assert servicio.a_detalle(db, p).fotos == []


def test_alta_y_edicion_bloquean_al_proveedor(db, admin, base, monkeypatch):
    """Carrera dólar ↔ producto: alta y edición leen el proveedor con
    FOR UPDATE (el mismo lock que toma el cambio de dólar) antes de calcular."""
    llamadas = []
    original = servicio.obtener_proveedor

    def espia(db, proveedor_id, bloquear=False):
        llamadas.append((proveedor_id, bloquear))
        return original(db, proveedor_id, bloquear=bloquear)

    monkeypatch.setattr(servicio, "obtener_proveedor", espia)
    p = _alta(db, admin, base, proveedor_id=base["dolares"].id, costo="10", margen="0")
    _editar(db, admin, p, costo="20")
    assert llamadas == [(base["dolares"].id, True), (base["dolares"].id, True)]


def test_edicion_usa_el_dolar_vigente(db, admin, base):
    """Si el dólar cambió (por otra vía) desde que se cargó el proveedor en la
    sesión, la edición calcula con el valor releído de la base."""
    p = _alta(db, admin, base, proveedor_id=base["dolares"].id, costo="10", margen="0")
    db.execute(text("UPDATE proveedores SET dolar_actual = 2000 WHERE id = :id"), {"id": base["dolares"].id})
    assert base["dolares"].dolar_actual == Decimal("1000")                # en memoria, viejo
    assert _editar(db, admin, p, costo="11").precio_venta == Decimal("22000")


def test_editar_proveedor_bloquea_antes_de_contar_productos(db, admin, monkeypatch):
    from app.schemas.proveedores import ProveedorEditar

    orden = []
    original_obtener = servicio_proveedores.obtener_proveedor
    original_contar = servicio_proveedores.contar_productos
    monkeypatch.setattr(servicio_proveedores, "obtener_proveedor",
                        lambda db, pid, bloquear=False: (orden.append(("obtener", bloquear)),
                                                         original_obtener(db, pid, bloquear))[1])
    monkeypatch.setattr(servicio_proveedores, "contar_productos",
                        lambda db, pid, solo_activos=False: (orden.append(("contar", None)),
                                                             original_contar(db, pid, solo_activos))[1])
    prov = servicio_proveedores.crear_proveedor(db, admin, ProveedorCrear(nombre="Prov moneda", moneda="ars"), None)
    servicio_proveedores.editar_proveedor(db, admin, prov, ProveedorEditar(nombre="Prov moneda", moneda="usd",
                                                                           dolar_actual="1000"), None)
    assert orden == [("obtener", True), ("contar", None)]
