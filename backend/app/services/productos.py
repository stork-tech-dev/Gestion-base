"""Productos: alta, edición, estado, precio de venta y recálculo en cascada.
Sin variantes: cada artículo vendible es un producto con su código y precio."""
import re
from decimal import Decimal
from io import BytesIO

import barcode
from barcode.writer import SVGWriter
from sqlalchemy import func, or_, select, text

from app.core.auditoria import registrar_auditoria, snapshot
from app.core.codigos import codificar_sku, codigo_es_valido, digito_verificador
from app.core.errores import DatoInvalido, NoEncontrado, ReglaDeNegocio, SinPermiso
from app.core.permisos import Modulo
from app.core.seguridad import resolver_permiso
from app.core.utils import (
    capitalizar_inicial, filtro_texto, normalizar_texto, paginar, patron_ilike,
    redondear, redondear_hacia_arriba, sin_tildes, sin_tildes_sql,
)
from app.models import Producto, Proveedor, TemporadaProducto
from app.schemas.productos import ProductoDetalle, ProductoResponse
from app.services import categorias as servicio_categorias
from app.services.configuracion import obtener_configuracion
from app.services.proveedores import obtener_proveedor


def obtener_producto(db, producto_id: int) -> Producto:
    producto = db.get(Producto, producto_id)
    if producto is None:
        raise NoEncontrado("Producto no encontrado")
    return producto


def bloquear_producto(db, producto_id: int) -> Producto:
    """`SELECT ... FOR UPDATE` de la fila del producto POR ID (sin relaciones:
    categoria y proveedor van joined con LEFT OUTER JOIN y Postgres no permite
    bloquear ese lado del join) y relectura con `populate_existing`. Única
    definición del patrón de lock de un producto: la reusan `services.stock`
    (ingresos, mínimos, ajustes de auditoría) y `services.producto_fotos`
    (altas, bajas y cambio de principal de fotos)."""
    db.execute(select(Producto.id).where(Producto.id == producto_id).with_for_update())
    producto = db.get(Producto, producto_id, populate_existing=True)
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


MARGEN_MAXIMO = Decimal("1000")


def margen_desde_precio(costo, precio, proveedor: Proveedor) -> Decimal:
    """Margen % que lleva el costo (en pesos, con el dólar actual) al precio
    cargado a mano. El precio se respeta exacto (decisión del usuario)."""
    factor = proveedor.dolar_actual if proveedor.en_dolares else Decimal("1")
    costo_pesos = Decimal(costo) * factor
    precio_exacto = Decimal(precio)
    # Comparación EXACTA (sin redondear el margen primero): redondear a 2
    # decimales puede convertir un precio apenas por debajo del costo (margen
    # negativo, ej. -0.001 %) en "-0.00", que no es < 0 y dejaría pasar un
    # precio menor al costo con margen 0.
    if precio_exacto < costo_pesos:
        raise DatoInvalido(f"El precio de venta no puede ser menor al costo (${redondear(costo_pesos)}).")
    margen = redondear((precio_exacto / costo_pesos - 1) * 100)
    if margen > MARGEN_MAXIMO:
        raise DatoInvalido("El margen resultante supera el 1000 %.")
    return margen


def precio_preview(db, proveedor_id: int, costo, margen=None, precio_venta=None) -> dict:
    """Con `precio_venta`: precio exacto y margen derivado (sin redondeo). Con
    `margen`: precio por la fórmula (CEIL al redondeo configurado). El
    llamador (router) exige exactamente uno de los dos."""
    proveedor = obtener_proveedor(db, proveedor_id)
    redondeo = obtener_configuracion(db).redondeo
    if precio_venta is not None:
        precio = redondear(precio_venta)
        margen_final = margen_desde_precio(costo, precio, proveedor)
    else:
        margen_final = redondear(margen)
        precio = calcular_precio_venta(db, costo, margen_final, proveedor, redondeo)
    return {
        "moneda": proveedor.moneda.value,
        "dolar_proveedor": proveedor.dolar_actual if proveedor.en_dolares else None,
        "precio_venta": precio,
        "margen": margen_final,
        "redondeo": redondeo,
        "redondeado": precio_venta is None,
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
    # Lock compartido del árbol: las altas de productos no se esperan entre sí,
    # pero sí esperan a que termine una subcategoría nueva (o un movimiento)
    # sobre esta categoría, así nunca queda un producto en una que no es hoja.
    servicio_categorias.bloquear_arbol(db, compartido=True)
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
    # Bloqueado (FOR UPDATE + relectura): un cambio de dólar simultáneo espera
    # a que este alta termine, o este alta lee el dólar ya cambiado. Sin el
    # lock, el recálculo del dólar no ve este producto (todavía sin commit) y
    # el alta queda con el precio del dólar viejo.
    proveedor = obtener_proveedor(db, datos.proveedor_id, bloquear=True)
    if not proveedor.activo:
        raise ReglaDeNegocio("El proveedor no está activo: no se le pueden cargar productos.")
    descripcion = _descripcion_libre(db, datos.descripcion, categoria.id, proveedor.id)
    _validar_descuento(db, datos.descuento_producto)
    _validar_stock_infinito(autor, False, datos.stock_infinito)
    # Cargar stock inicial es, en los hechos, un ingreso de stock: exige el
    # mismo permiso que services.stock.registrar_ingreso. Se valida ANTES de
    # crear nada (ni el producto ni el movimiento).
    if datos.stock_inicial and not datos.stock_infinito and not resolver_permiso(db, autor.id, Modulo.STOCK, "crear"):
        raise SinPermiso("Cargar stock inicial requiere permiso de ingreso de stock")
    costo = redondear(datos.costo)
    if datos.precio_venta is not None:
        precio = redondear(datos.precio_venta)
        margen = margen_desde_precio(costo, precio, proveedor)
    else:
        margen = redondear(datos.margen if datos.margen is not None else obtener_configuracion(db).margen_default)
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
    if datos.stock_inicial and not producto.stock_infinito:
        # Import local: stock importa de productos (condiciones_codigo), así que
        # a nivel de módulo quedaría un ciclo. El producto ya está flusheado
        # (con id), así que aplicar_movimiento lo bloquea y lo ve sin problema
        # dentro de esta misma transacción.
        from app.services.stock import registrar_ingreso
        registrar_ingreso(db, autor, producto.id, datos.stock_inicial, "Stock inicial", ip)
        db.refresh(producto)
    return producto


def editar_producto(db, autor, producto: Producto, datos, ip) -> Producto:
    # Mismo lock que en el alta (ver crear_producto), tomado ANTES de leer
    # nada: después se relee el producto por si un cambio de dólar que
    # terminó mientras se esperaba el lock le recalculó el precio.
    if datos.categoria_id != producto.categoria_id:
        # Mismo orden de locks que el alta (árbol → proveedor): si no, un alta,
        # esta edición y una escritura de categorías pueden quedar esperando
        # hasta que Postgres detecte el deadlock (deadlock_timeout).
        servicio_categorias.bloquear_arbol(db, compartido=True)
    proveedor = obtener_proveedor(db, producto.proveedor_id, bloquear=True)
    db.refresh(producto)
    # Primero se valida todo; recién después se modifica el producto.
    categoria_id = producto.categoria_id
    if datos.categoria_id != producto.categoria_id:
        categoria_id = _categoria_de_producto(db, datos.categoria_id).id
    descripcion = _descripcion_libre(db, datos.descripcion, categoria_id, producto.proveedor_id, excepto_id=producto.id)
    _validar_descuento(db, datos.descuento_producto)
    stock_infinito = producto.stock_infinito if datos.stock_infinito is None else datos.stock_infinito
    _validar_stock_infinito(autor, producto.stock_infinito, stock_infinito)
    costo = redondear(datos.costo)
    if datos.precio_venta is not None:
        precio = redondear(datos.precio_venta)
        margen = margen_desde_precio(costo, precio, proveedor)
    else:
        margen = redondear(datos.margen)
        precio = producto.precio_venta
        if costo != producto.costo or margen != producto.margen:
            precio = calcular_precio_venta(db, costo, margen, proveedor)

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


TAMANO_MAXIMO = 100
MINIMO_SIMILARES = 10
_OPCIONES_BARCODE = {"module_width": 0.2, "module_height": 4.0, "write_text": False, "quiet_zone": 1.0}
_MEDIDA = re.compile(r'(\d+(?:\.\d+)?)mm')


def _sku_de_codigo(texto: str | None) -> str | None:
    """ÚNICA lectura de lo que se tipea o escanea como código: si es una
    etiqueta (SKU + verificador válido, 6 caracteres), el SKU (los primeros 5);
    si no, el texto tal cual (limpio y en mayúsculas). None si viene vacío."""
    limpio = (texto or "").strip().upper()
    if not limpio:
        return None
    return limpio[:5] if len(limpio) == 6 and codigo_es_valido(limpio) else limpio


def condiciones_codigo(texto: str):
    """ÚNICA definición de "buscar por código" (la reusan stock y ventas): ILIKE
    parcial sobre el SKU y, si el texto es SKU + verificador válido, también el
    match EXACTO del SKU sin el verificador."""
    limpio = (texto or "").strip().upper()
    condicion = Producto.sku.ilike(patron_ilike(limpio), escape="\\")
    sku = _sku_de_codigo(limpio)
    if sku is not None and sku != limpio:
        condicion = or_(condicion, Producto.sku == sku)
    return condicion


def buscar_por_codigo(db, codigo: str) -> Producto:
    """Etiqueta con verificador válido o el SKU solo; un verificador incorrecto no resuelve."""
    sku = _sku_de_codigo(codigo)
    producto = db.scalar(select(Producto).where(Producto.sku == sku)) if sku and len(sku) == 5 else None
    if producto is None:
        raise NoEncontrado("No hay ningún producto con ese código")
    return producto


def listar_productos(db, *, busqueda: str | None = None, categoria_id: int | None = None,
                     proveedor_id: int | None = None, temporada: TemporadaProducto | None = None,
                     activo: bool | None = None, precio_desde: Decimal | None = None,
                     precio_hasta: Decimal | None = None, stock_cero: bool = False,
                     pagina: int = 1, tamano: int = 10) -> tuple[list[Producto], int]:
    condiciones = []
    if busqueda and busqueda.strip():
        condiciones.append(or_(condiciones_codigo(busqueda), filtro_texto(Producto.sku_proveedor, busqueda),
                               filtro_texto(Producto.descripcion, busqueda)))
    if categoria_id is not None:
        condiciones.append(Producto.categoria_id.in_(servicio_categorias.rama_de_ids(db, categoria_id)))
    if proveedor_id is not None:
        condiciones.append(Producto.proveedor_id == proveedor_id)
    if temporada is not None:
        condiciones.append(Producto.temporada == temporada)
    if activo is not None:
        condiciones.append(Producto.activo.is_(activo))
    if precio_desde is not None:
        condiciones.append(Producto.precio_venta >= precio_desde)
    if precio_hasta is not None:
        condiciones.append(Producto.precio_venta <= precio_hasta)
    if stock_cero:
        condiciones.append(Producto.stock <= 0)
        condiciones.append(Producto.stock_infinito.is_(False))
    pagina, tamano = paginar(pagina, tamano, TAMANO_MAXIMO)
    total = db.scalar(select(func.count()).select_from(Producto).where(*condiciones))
    productos = db.scalars(
        select(Producto).where(*condiciones).order_by(func.lower(Producto.descripcion), Producto.sku)
        .offset((pagina - 1) * tamano).limit(tamano)
    ).unique().all()
    return list(productos), total


def buscar_similares(db, descripcion: str, categoria_id: int | None = None, proveedor_id: int | None = None,
                     limite: int = 8) -> list[dict]:
    """Parecidos al tipear la descripción (incluye inactivos): desde 10 caracteres,
    con TODAS las palabras de 3+ letras, en la rama de categoría y el proveedor."""
    limpia = normalizar_texto(descripcion) or ""
    if len(limpia) < MINIMO_SIMILARES:
        return []
    palabras = [p for p in limpia.split() if len(p) >= 3]
    if not palabras:
        return []
    condiciones = [filtro_texto(Producto.descripcion, p) for p in palabras]
    if categoria_id is not None:
        condiciones.append(Producto.categoria_id.in_(servicio_categorias.rama_de_ids(db, categoria_id)))
    if proveedor_id is not None:
        condiciones.append(Producto.proveedor_id == proveedor_id)
    filas = db.execute(
        select(Producto.id, Producto.sku, Producto.descripcion, Producto.activo).where(*condiciones)
        .order_by(func.lower(Producto.descripcion), Producto.sku).limit(limite)
    ).all()
    return [{"id": f.id, "sku": f.sku, "descripcion": f.descripcion, "activo": f.activo} for f in filas]


def svg_code128(texto: str, ancho_mm=None, alto_mm=None) -> str:
    """Code128 en SVG escalable: python-barcode usa unidades "mm" en cada
    atributo (no escala); se pasan a números con un viewBox en mm. Con ancho y
    alto, el SVG se fuerza a ese tamaño (preserveAspectRatio none)."""
    salida = BytesIO()
    barcode.get("code128", texto, writer=SVGWriter()).write(salida, _OPCIONES_BARCODE)
    svg = salida.getvalue().decode()
    svg = svg[svg.index("<svg"):]                                   # sin <?xml ...> ni DOCTYPE
    raiz = svg[:svg.index(">") + 1]
    ancho = _MEDIDA.search(re.search(r'width="([^"]+)"', raiz).group(1)).group(1)
    alto = _MEDIDA.search(re.search(r'height="([^"]+)"', raiz).group(1)).group(1)
    cuerpo = _MEDIDA.sub(r"\1", svg[len(raiz):])
    final_ancho = f"{ancho_mm}mm" if ancho_mm else f"{ancho}mm"
    final_alto = f"{alto_mm}mm" if alto_mm else f"{alto}mm"
    ajuste = ' preserveAspectRatio="none"' if ancho_mm and alto_mm else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" version="1.1" viewBox="0 0 {ancho} {alto}" '
            f'width="{final_ancho}" height="{final_alto}"{ajuste}>{cuerpo}')


def barcode_svg(db, producto_id: int) -> str:
    return svg_code128(obtener_producto(db, producto_id).codigo_con_verificador)


# Medidas del código de barras impreso en la etiqueta (única definición).
ETIQUETA_BARCODE_MM = (16, 4.5)


def barcode_svg_de_producto_para_etiqueta(producto: Producto) -> str:
    ancho, alto = ETIQUETA_BARCODE_MM
    return svg_code128(producto.codigo_con_verificador, ancho_mm=ancho, alto_mm=alto)


def barcode_svg_para_etiqueta(db, producto_id: int) -> str:
    return barcode_svg_de_producto_para_etiqueta(obtener_producto(db, producto_id))
