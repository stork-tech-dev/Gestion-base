"""Proveedores: cada uno trabaja en pesos o en dólares. Baja siempre lógica."""
from decimal import Decimal

from sqlalchemy import func, select, text

from app.core.auditoria import registrar_auditoria, snapshot
from app.core.errores import DatoInvalido, NoEncontrado, ReglaDeNegocio, SinPermiso
from app.core.utils import filtro_texto, normalizar_texto, redondear, sin_tildes, sin_tildes_sql
from app.models import EstadoProveedor, Moneda, Proveedor

ACCION_DE_ESTADO = {
    EstadoProveedor.ACTIVO: "proveedor.reactivar",
    EstadoProveedor.DESACTIVADO: "proveedor.desactivar",
    EstadoProveedor.INHABILITADO: "proveedor.inhabilitar",
}


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
    if valor is None or Decimal(valor) <= 0:
        raise DatoInvalido("El valor del dólar debe ser mayor a cero.")
    return redondear(valor)


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
    """No toca el dólar (tiene su propio endpoint). Cambiar la moneda solo sin productos."""
    antes = snapshot(proveedor)
    if datos.moneda is not proveedor.moneda:
        if contar_productos(db, proveedor.id):
            raise ReglaDeNegocio("No se puede cambiar la moneda de un proveedor con productos cargados.")
        proveedor.dolar_actual = validar_dolar(datos.dolar_actual) if datos.moneda is Moneda.USD else None
        proveedor.moneda = datos.moneda
    proveedor.nombre = _nombre_libre(db, datos.nombre, excepto_id=proveedor.id)
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
