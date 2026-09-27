"""Proveedores: cada uno trabaja en pesos o en dólares. Baja siempre lógica."""
from decimal import Decimal, InvalidOperation

from sqlalchemy import func, select, text

from app.core.auditoria import registrar_auditoria, snapshot
from app.core.errores import DatoInvalido, NoEncontrado, ReglaDeNegocio, SinPermiso
from app.core.excel import celda_decimal, celda_entero, generar_plantilla, leer_tabla
from app.core.utils import ahora_db, filtro_texto, normalizar_texto, redondear, sin_tildes, sin_tildes_sql
from app.models import EstadoProveedor, Moneda, OrigenCambioDolar, Proveedor, ProveedorDolarHistorial, Usuario
from app.schemas.proveedores import ModalidadMasiva

ACCION_DE_ESTADO = {
    EstadoProveedor.ACTIVO: "proveedor.reactivar",
    EstadoProveedor.DESACTIVADO: "proveedor.desactivar",
    EstadoProveedor.INHABILITADO: "proveedor.inhabilitar",
}
ORIGEN_MASIVO = {ModalidadMasiva.VALOR: OrigenCambioDolar.MASIVO_VALOR, ModalidadMasiva.PORCENTAJE: OrigenCambioDolar.MASIVO_PORCENTAJE}
COLUMNAS_PLANTILLA_DOLAR = ["proveedor_id", "nombre", "dolar_nuevo"]
INSTRUCCIONES_DOLAR = [
    ["Instrucciones"],
    ["1. Cambiá solo la columna dolar_nuevo. Las filas que no modifiques se saltean."],
    ["2. No cambies los encabezados ni los proveedor_id."],
    ["3. Todo o nada: si una fila tiene un error, no se aplica ningún cambio y se informan todos los errores."],
    ["4. Solo figuran los proveedores activos que trabajan en dólares."],
]


def obtener_proveedor(db, proveedor_id: int) -> Proveedor:
    proveedor = db.get(Proveedor, proveedor_id)
    if proveedor is None:
        raise NoEncontrado("Proveedor no encontrado")
    return proveedor


def listar_proveedores(db, *, nombre=None, email=None, telefono=None, provincia=None, pais=None, estado=None,
                       moneda=None, dolar_desde: Decimal | None = None, dolar_hasta: Decimal | None = None) -> list[Proveedor]:
    """Tabla chica: sin paginación, orden alfabético."""
    condiciones = [
        filtro_texto(columna, valor)
        for columna, valor in (
            (Proveedor.nombre, nombre), (Proveedor.email, email), (Proveedor.telefono, telefono),
            (Proveedor.provincia, provincia), (Proveedor.pais, pais),
        )
        if valor
    ]
    if estado is not None:
        condiciones.append(Proveedor.estado == estado)
    if moneda is not None:
        condiciones.append(Proveedor.moneda == moneda)
    # Los filtros de dólar solo alcanzan a proveedores en dólares.
    if dolar_desde is not None:
        condiciones += [Proveedor.moneda == Moneda.USD, Proveedor.dolar_actual >= dolar_desde]
    if dolar_hasta is not None:
        condiciones += [Proveedor.moneda == Moneda.USD, Proveedor.dolar_actual <= dolar_hasta]
    return list(db.scalars(select(Proveedor).where(*condiciones).order_by(func.lower(Proveedor.nombre), Proveedor.id)).all())


def hay_proveedores_en_dolares(db) -> bool:
    """¿Hay al menos un proveedor ACTIVO en dólares? Si no, las pantallas ocultan el dólar."""
    consulta = select(Proveedor.id).where(Proveedor.moneda == Moneda.USD, Proveedor.estado == EstadoProveedor.ACTIVO).limit(1)
    return db.scalar(consulta) is not None


def contar_productos(db, proveedor_id: int, solo_activos: bool = False) -> int:
    """Productos del proveedor. La tabla llega en el módulo 04: hasta entonces, 0."""
    if not db.execute(text("SELECT to_regclass('public.productos') IS NOT NULL")).scalar_one():
        return 0
    sql = "SELECT count(*) FROM productos WHERE proveedor_id = :id"
    if solo_activos:
        sql += " AND activo"
    return db.execute(text(sql), {"id": proveedor_id}).scalar_one()


def validar_dolar(valor) -> Decimal:
    """Convierte y valida el valor del dólar de un proveedor. Cualquier entrada
    inválida (None, texto no numérico, NaN/infinito, cero o negativo) da
    DatoInvalido en lugar de dejar escapar la excepción de `Decimal` —
    la Task 5 (cambio masivo y Excel) reusa esta función con datos de afuera."""
    try:
        numero = Decimal(valor)
    except (InvalidOperation, TypeError, ValueError):
        raise DatoInvalido("El valor del dólar debe ser mayor a cero.") from None
    if not numero.is_finite() or numero <= 0:
        raise DatoInvalido("El valor del dólar debe ser mayor a cero.")
    return redondear(numero)


def _nombre_libre(db, nombre: str, excepto_id: int | None = None) -> str:
    limpio = normalizar_texto(nombre)
    if not limpio:
        raise DatoInvalido("El nombre es obligatorio")
    condiciones = [func.lower(sin_tildes_sql(Proveedor.nombre)) == sin_tildes(limpio).lower()]
    if excepto_id is not None:
        condiciones.append(Proveedor.id != excepto_id)
    existente = db.scalar(select(Proveedor).where(*condiciones))
    if existente is not None:
        raise ReglaDeNegocio(f"Ya existe un proveedor llamado '{existente.nombre}'")
    return limpio


def _asignar_datos(proveedor: Proveedor, datos) -> None:
    proveedor.pais = normalizar_texto(datos.pais)
    proveedor.provincia = normalizar_texto(datos.provincia)
    proveedor.telefono = normalizar_texto(datos.telefono)
    proveedor.email = datos.email.lower() if datos.email else None
    proveedor.notas = (datos.notas or "").strip() or None


def crear_proveedor(db, autor, datos, ip) -> Proveedor:
    proveedor = Proveedor(
        nombre=_nombre_libre(db, datos.nombre),
        moneda=datos.moneda,
        # En pesos el dólar se ignora; en dólares es obligatorio y > 0.
        dolar_actual=validar_dolar(datos.dolar_actual) if datos.moneda is Moneda.USD else None,
        estado=EstadoProveedor.ACTIVO,
    )
    _asignar_datos(proveedor, datos)
    db.add(proveedor)
    db.flush()
    db.refresh(proveedor)
    registrar_auditoria(db, accion="proveedor.crear", entidad="proveedor", entidad_id=proveedor.id,
                        usuario_id=autor.id, estado_nuevo=proveedor, ip_origen=ip)
    return proveedor


def editar_proveedor(db, autor, proveedor: Proveedor, datos, ip) -> Proveedor:
    """No toca el dólar (tiene su propio endpoint). Cambiar la moneda solo sin productos.

    Primero se valida todo (nombre libre, productos cargados, dólar nuevo) y
    se guarda en variables locales; recién si todo pasa se muta `proveedor`.
    Si alguna validación falla, el objeto de la sesión queda intacto (si no,
    una falla a mitad de camino dejaría la moneda cambiada sin que la
    operación se haya confirmado)."""
    antes = snapshot(proveedor)
    nombre_nuevo = _nombre_libre(db, datos.nombre, excepto_id=proveedor.id)
    cambia_moneda = datos.moneda is not proveedor.moneda
    if cambia_moneda:
        if contar_productos(db, proveedor.id):
            raise ReglaDeNegocio("No se puede cambiar la moneda de un proveedor con productos cargados.")
        dolar_nuevo = validar_dolar(datos.dolar_actual) if datos.moneda is Moneda.USD else None
    proveedor.nombre = nombre_nuevo
    if cambia_moneda:
        proveedor.moneda = datos.moneda
        proveedor.dolar_actual = dolar_nuevo
    _asignar_datos(proveedor, datos)
    db.flush()
    db.refresh(proveedor)
    registrar_auditoria(db, accion="proveedor.editar", entidad="proveedor", entidad_id=proveedor.id,
                        usuario_id=autor.id, estado_anterior=antes, estado_nuevo=proveedor, ip_origen=ip)
    return proveedor


def cambiar_estado(db, autor, proveedor: Proveedor, nuevo: EstadoProveedor, confirmar_con_productos: bool, ip) -> Proveedor:
    if nuevo is proveedor.estado:
        return proveedor
    if proveedor.estado is EstadoProveedor.INHABILITADO and not autor.es_admin:
        raise SinPermiso("Reactivar un proveedor inhabilitado requiere Admin")
    if nuevo is not EstadoProveedor.ACTIVO and not confirmar_con_productos:
        activos = contar_productos(db, proveedor.id, solo_activos=True)
        if activos:
            raise ReglaDeNegocio(
                f"El proveedor tiene {activos} producto(s) activo(s). Reasignarlos o confirmar la baja explícitamente."
            )
    antes = snapshot(proveedor)
    proveedor.estado = nuevo
    db.flush()
    registrar_auditoria(db, accion=ACCION_DE_ESTADO[nuevo], entidad="proveedor", entidad_id=proveedor.id,
                        usuario_id=autor.id, estado_anterior=antes, estado_nuevo=proveedor, ip_origen=ip)
    return proveedor


def _recalcular_precios(db, proveedor_id: int) -> None:
    """Recalcula el precio de venta de los productos del proveedor (módulo 04).
    Import local para no acoplar módulos; sin el módulo de productos, no hace nada."""
    try:
        from app.services.productos import recalcular_precios_de_proveedor
    except ImportError:
        return
    recalcular_precios_de_proveedor(db, proveedor_id)


def _aplicar_cambio_dolar(db, autor, proveedor: Proveedor, valor, origen: OrigenCambioDolar, ip) -> bool:
    """Núcleo ÚNICO de todo cambio de dólar (individual, masivo y Excel).
    Devuelve False si el valor no cambia (no genera historial, auditoría ni recálculo)."""
    if proveedor.moneda is not Moneda.USD:
        raise ReglaDeNegocio("El proveedor trabaja en pesos: no tiene valor de dólar.")
    nuevo = validar_dolar(valor)
    if nuevo == proveedor.dolar_actual:
        return False
    antes = snapshot(proveedor, campos=["dolar_actual"])
    db.add(ProveedorDolarHistorial(
        proveedor_id=proveedor.id, valor_anterior=proveedor.dolar_actual, valor_nuevo=nuevo,
        usuario_id=autor.id, origen=origen, timestamp=ahora_db(),
    ))
    proveedor.dolar_actual = nuevo
    db.flush()
    registrar_auditoria(db, accion="dolar.cambio", entidad="proveedor", entidad_id=proveedor.id, usuario_id=autor.id,
                        estado_anterior=antes, estado_nuevo={"dolar_actual": nuevo, "origen": origen.value}, ip_origen=ip)
    _recalcular_precios(db, proveedor.id)
    return True


def cambiar_dolar(db, autor, proveedor: Proveedor, valor, ip) -> Proveedor:
    _aplicar_cambio_dolar(db, autor, proveedor, valor, OrigenCambioDolar.MANUAL, ip)
    return proveedor


def historial_dolar(db, proveedor_id: int) -> list[dict]:
    filas = db.execute(
        select(ProveedorDolarHistorial, Usuario.nombre)
        .join(Usuario, Usuario.id == ProveedorDolarHistorial.usuario_id)
        .where(ProveedorDolarHistorial.proveedor_id == proveedor_id)
        .order_by(ProveedorDolarHistorial.timestamp.desc(), ProveedorDolarHistorial.id.desc())
    ).all()
    return [
        {"id": h.id, "valor_anterior": h.valor_anterior, "valor_nuevo": h.valor_nuevo, "origen": h.origen,
         "timestamp": h.timestamp, "usuario_id": h.usuario_id, "usuario_nombre": nombre}
        for h, nombre in filas
    ]


def _proveedores_para_masivo(db, proveedor_ids) -> list[Proveedor]:
    """Solo activos en dólares; los ids en pesos o inactivos se ignoran."""
    consulta = select(Proveedor).where(Proveedor.moneda == Moneda.USD, Proveedor.estado == EstadoProveedor.ACTIVO)
    if proveedor_ids is not None:
        consulta = consulta.where(Proveedor.id.in_(proveedor_ids))
    proveedores = list(db.scalars(consulta.order_by(func.lower(Proveedor.nombre), Proveedor.id)).all())
    if not proveedores:
        raise ReglaDeNegocio("No hay proveedores activos en dólares para actualizar.")
    return proveedores


def _valor_masivo(proveedor: Proveedor, modalidad: ModalidadMasiva, valor: Decimal) -> Decimal:
    if modalidad is ModalidadMasiva.VALOR:
        return validar_dolar(valor)
    if valor <= Decimal("-100"):
        raise DatoInvalido("El porcentaje debe ser mayor a -100.")
    return validar_dolar(proveedor.dolar_actual * (1 + Decimal(valor) / 100))


def preview_masivo(db, proveedor_ids, modalidad: ModalidadMasiva, valor: Decimal) -> list[dict]:
    return [
        {"proveedor_id": p.id, "nombre": p.nombre, "valor_actual": p.dolar_actual,
         "valor_nuevo": _valor_masivo(p, modalidad, valor)}
        for p in _proveedores_para_masivo(db, proveedor_ids)
    ]


def aplicar_masivo(db, autor, proveedor_ids, modalidad: ModalidadMasiva, valor: Decimal, ip) -> list[dict]:
    vista = preview_masivo(db, proveedor_ids, modalidad, valor)  # valida todo antes de escribir
    for fila in vista:
        _aplicar_cambio_dolar(db, autor, db.get(Proveedor, fila["proveedor_id"]), fila["valor_nuevo"],
                              ORIGEN_MASIVO[modalidad], ip)
    return vista


def generar_plantilla_dolar(db) -> bytes:
    proveedores = db.scalars(
        select(Proveedor).where(Proveedor.moneda == Moneda.USD, Proveedor.estado == EstadoProveedor.ACTIVO)
        .order_by(func.lower(Proveedor.nombre), Proveedor.id)
    ).all()
    filas = [[p.id, p.nombre, p.dolar_actual] for p in proveedores]
    return generar_plantilla("Dolar", COLUMNAS_PLANTILLA_DOLAR, INSTRUCCIONES_DOLAR, filas)


def _validar_fila_dolar(db, fila: dict, vistos: set) -> tuple[Proveedor, Decimal] | str:
    """(proveedor, valor) si la fila es válida; si no, el mensaje de error."""
    try:
        proveedor_id = celda_entero(fila["proveedor_id"])
    except ValueError:
        proveedor_id = None
    if proveedor_id is None:
        return "proveedor_id vacío o inválido"
    if proveedor_id in vistos:
        return "proveedor_id repetido en el archivo"
    vistos.add(proveedor_id)
    proveedor = db.get(Proveedor, proveedor_id)
    if proveedor is None:
        return "El proveedor no existe"
    if proveedor.estado is not EstadoProveedor.ACTIVO:
        return "El proveedor no está activo"
    if proveedor.moneda is not Moneda.USD:
        return "El proveedor trabaja en pesos"
    try:
        valor = celda_decimal(fila["dolar_nuevo"])
    except ValueError:
        valor = None
    if valor is None or valor <= 0:
        return "dolar_nuevo vacío, inválido o menor o igual a cero"
    return proveedor, valor


def importar_dolar(db, autor, contenido: bytes, ip) -> dict:
    """Todo o nada: primero valida TODAS las filas; si alguna falla, no aplica
    ninguna y devuelve la lista de errores."""
    filas = leer_tabla(contenido, ["proveedor_id", "dolar_nuevo"], ["nombre"])
    errores, validas, vistos = [], [], set()
    for numero, fila in filas:
        resultado = _validar_fila_dolar(db, fila, vistos)
        if isinstance(resultado, str):
            errores.append({"fila": numero, "error": resultado})
        else:
            validas.append(resultado)
    if errores:
        return {"aplicados": 0, "sin_cambios": 0, "errores": errores}
    aplicados = sum(
        1 for proveedor, valor in validas
        if _aplicar_cambio_dolar(db, autor, proveedor, valor, OrigenCambioDolar.IMPORTACION_EXCEL, ip)
    )
    return {"aplicados": aplicados, "sin_cambios": len(validas) - aplicados, "errores": []}
