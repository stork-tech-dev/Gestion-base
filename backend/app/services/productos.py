"""Productos: alta, edición, estado, precio de venta y recálculo en cascada.
Sin variantes: cada artículo vendible es un producto con su código y precio."""
from decimal import Decimal

from sqlalchemy import func, select, text

from app.core.auditoria import registrar_auditoria, snapshot
from app.core.codigos import codificar_sku, digito_verificador
from app.core.errores import DatoInvalido, NoEncontrado, ReglaDeNegocio, SinPermiso
from app.core.utils import capitalizar_inicial, normalizar_texto, redondear, redondear_hacia_arriba, sin_tildes, sin_tildes_sql
from app.models import Producto, Proveedor
from app.schemas.productos import ProductoDetalle, ProductoResponse
from app.services import categorias as servicio_categorias
from app.services.configuracion import obtener_configuracion
from app.services.proveedores import obtener_proveedor


def obtener_producto(db, producto_id: int) -> Producto:
    producto = db.get(Producto, producto_id)
    if producto is None:
        raise NoEncontrado("Producto no encontrado")
    return producto


def calcular_precio_venta(db, costo, margen, proveedor: Proveedor, redondeo: Decimal | None = None) -> Decimal:
    """ÚNICA definición del precio de venta (alta, edición, recálculo, preview e
    importación): CEIL(costo × dólar (o 1) × (1 + margen/100), redondeo).

    `redondeo=None` lee la configuración (un solo producto). Quien recalcula
    varios de una vez (`recalcular_precios_de_proveedor`) la lee una sola vez
    antes del loop y la pasa acá, en vez de una query por producto."""
    factor = proveedor.dolar_actual if proveedor.en_dolares else Decimal("1")
    bruto = Decimal(costo) * factor * (1 + Decimal(margen) / 100)
    precio = redondear_hacia_arriba(bruto, redondeo if redondeo is not None else obtener_configuracion(db).redondeo)
    if precio >= Decimal("100000000"):
        raise DatoInvalido("El precio de venta resultante es demasiado grande.")
    return precio


def precio_preview(db, proveedor_id: int, costo, margen) -> dict:
    proveedor = obtener_proveedor(db, proveedor_id)
    return {
        "moneda": proveedor.moneda.value,
        "dolar_proveedor": proveedor.dolar_actual if proveedor.en_dolares else None,
        "precio_venta": calcular_precio_venta(db, costo, margen, proveedor),
    }


def recalcular_precios_de_proveedor(db, proveedor_id: int) -> int:
    """Lo llama services.proveedores tras cada cambio REAL del dólar, después del
    flush del valor nuevo (sin commit). Proveedor en pesos: no hace nada. El
    cambio queda auditado en el registro dolar.cambio del proveedor.

    Dos pasadas: primero se calculan TODOS los precios nuevos sin tocar los
    productos; solo si ninguno desborda se asignan. Si se asignara dentro del
    mismo loop que calcula, un desborde a mitad de camino dejaría los
    productos anteriores ya modificados en la sesión (con el precio nuevo en
    memoria) aunque toda la operación termine fallando."""
    proveedor = db.get(Proveedor, proveedor_id)
    if proveedor is None or not proveedor.en_dolares:
        return 0
    productos = db.scalars(select(Producto).where(Producto.proveedor_id == proveedor_id)).all()
    redondeo = obtener_configuracion(db).redondeo
    nuevos_precios = []
    for producto in productos:
        try:
            nuevos_precios.append(calcular_precio_venta(db, producto.costo, producto.margen, proveedor, redondeo))
        except DatoInvalido:
            # Mensaje localizable (qué producto y de qué proveedor): lo ve el
            # cambio individual, el masivo y la importación por Excel.
            raise ReglaDeNegocio(
                f"Con ese dólar, el precio de venta de {producto.sku} ({proveedor.nombre}) "
                "superaría el máximo permitido."
            ) from None
    for producto, precio in zip(productos, nuevos_precios):
        producto.precio_venta = precio
    db.flush()
    return len(productos)


def _categoria_de_producto(db, categoria_id: int):
    categoria = servicio_categorias.obtener_categoria(db, categoria_id)
    if not servicio_categorias.es_hoja(db, categoria_id):
        raise ReglaDeNegocio("Elegí hasta el último nivel: la categoría del producto es la del final de la rama.")
    return categoria


def _descripcion_libre(db, descripcion: str, categoria_id: int, proveedor_id: int, excepto_id: int | None = None) -> str:
    limpia = capitalizar_inicial(descripcion)
    if not limpia:
        raise DatoInvalido("La descripción es obligatoria")
    condiciones = [
        func.lower(sin_tildes_sql(Producto.descripcion)) == sin_tildes(limpia).lower(),
        Producto.categoria_id == categoria_id,
        Producto.proveedor_id == proveedor_id,
    ]
    if excepto_id is not None:
        condiciones.append(Producto.id != excepto_id)
    existente = db.scalar(select(Producto).where(*condiciones))
    if existente is not None:
        inactivo = "" if existente.activo else ", que está inactivo y se puede volver a activar"
        raise ReglaDeNegocio(
            f"Ya existe un producto con esa descripción en este proveedor y categoría: {existente.sku}{inactivo}. "
            "Si es el mismo artículo en otro color o talle, cargalo como otro producto con una descripción que lo distinga."
        )
    return limpia


def _validar_descuento(db, descuento: Decimal) -> None:
    maximo = obtener_configuracion(db).descuento_maximo
    if descuento > maximo:
        raise DatoInvalido(f"El descuento del producto no puede superar el {maximo.normalize():f}%.")


def _validar_stock_infinito(autor, actual: bool, nuevo: bool) -> None:
    if nuevo != actual and not autor.es_admin:
        raise SinPermiso("El stock infinito lo define el Admin")


def _siguiente_sku(db) -> str:
    return codificar_sku(db.execute(text("SELECT nextval('productos_sku_seq')")).scalar_one())


def _asignar_opcionales(producto: Producto, datos) -> None:
    producto.sku_proveedor = normalizar_texto(datos.sku_proveedor)
    producto.descuento_producto = redondear(datos.descuento_producto)
    producto.peso_gramos = redondear(datos.peso_gramos) if datos.peso_gramos is not None else None
    producto.temporada = datos.temporada
    producto.ubicacion_deposito = normalizar_texto(datos.ubicacion_deposito)


def crear_producto(db, autor, datos, ip) -> Producto:
    categoria = _categoria_de_producto(db, datos.categoria_id)
    proveedor = obtener_proveedor(db, datos.proveedor_id)
    if not proveedor.activo:
        raise ReglaDeNegocio("El proveedor no está activo: no se le pueden cargar productos.")
    descripcion = _descripcion_libre(db, datos.descripcion, categoria.id, proveedor.id)
    _validar_descuento(db, datos.descuento_producto)
    _validar_stock_infinito(autor, False, datos.stock_infinito)
    margen = redondear(datos.margen if datos.margen is not None else obtener_configuracion(db).margen_default)
    costo = redondear(datos.costo)
    precio = calcular_precio_venta(db, costo, margen, proveedor)
    sku = _siguiente_sku(db)
    producto = Producto(sku=sku, verificador=digito_verificador(sku), descripcion=descripcion,
                        categoria_id=categoria.id, proveedor_id=proveedor.id, costo=costo, margen=margen,
                        precio_venta=precio, stock_infinito=datos.stock_infinito, activo=True)
    _asignar_opcionales(producto, datos)
    db.add(producto)
    db.flush()
    db.refresh(producto)
    registrar_auditoria(db, accion="producto.crear", entidad="producto", entidad_id=producto.id,
                        usuario_id=autor.id, estado_nuevo=producto, ip_origen=ip)
    return producto


def editar_producto(db, autor, producto: Producto, datos, ip) -> Producto:
    # Primero se valida todo; recién después se modifica el producto.
    categoria_id = producto.categoria_id
    if datos.categoria_id != producto.categoria_id:
        categoria_id = _categoria_de_producto(db, datos.categoria_id).id
    descripcion = _descripcion_libre(db, datos.descripcion, categoria_id, producto.proveedor_id, excepto_id=producto.id)
    _validar_descuento(db, datos.descuento_producto)
    stock_infinito = producto.stock_infinito if datos.stock_infinito is None else datos.stock_infinito
    _validar_stock_infinito(autor, producto.stock_infinito, stock_infinito)
    costo, margen = redondear(datos.costo), redondear(datos.margen)
    precio = producto.precio_venta
    if costo != producto.costo or margen != producto.margen:
        precio = calcular_precio_venta(db, costo, margen, producto.proveedor)

    antes = snapshot(producto)
    producto.categoria_id = categoria_id
    producto.descripcion = descripcion
    producto.costo, producto.margen, producto.precio_venta = costo, margen, precio
    producto.stock_infinito = stock_infinito
    _asignar_opcionales(producto, datos)
    db.flush()
    db.refresh(producto)
    registrar_auditoria(db, accion="producto.editar", entidad="producto", entidad_id=producto.id,
                        usuario_id=autor.id, estado_anterior=antes, estado_nuevo=producto, ip_origen=ip)
    return producto


def cambiar_estado_producto(db, autor, producto: Producto, activo: bool, ip) -> Producto:
    if producto.activo is activo:
        return producto
    antes = snapshot(producto)
    producto.activo = activo
    db.flush()
    registrar_auditoria(db, accion="producto.activar" if activo else "producto.desactivar", entidad="producto",
                        entidad_id=producto.id, usuario_id=autor.id, estado_anterior=antes,
                        estado_nuevo=producto, ip_origen=ip)
    return producto


def a_respuesta(db, productos) -> list[ProductoResponse]:
    rutas = servicio_categorias.caminos(db)
    return [ProductoResponse.desde(p, rutas[p.categoria_id]) for p in productos]


def a_detalle(db, producto: Producto) -> ProductoDetalle:
    return ProductoDetalle.desde(producto, servicio_categorias.caminos(db)[producto.categoria_id])
