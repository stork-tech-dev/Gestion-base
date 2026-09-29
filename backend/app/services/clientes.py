"""Clientes de ventas (sesión 06): alta/edición/baja, listado, búsqueda
rápida (combobox del punto de venta) y ficha (compras confirmadas + promociones
exclusivas). `cuit` y `condicion_iva` no entran en ningún cálculo hoy: quedan
cargados para la futura facturación electrónica."""
import re
from decimal import Decimal

from sqlalchemy import func, or_, select

from app.core.auditoria import registrar_auditoria, snapshot
from app.core.codigos import cuit_es_valido
from app.core.errores import DatoInvalido, NoEncontrado, ReglaDeNegocio
from app.core.utils import filtro_texto, normalizar_texto, paginar
from app.models import Cliente, CondicionIva, EstadoVenta, Venta
from app.services.promociones import promociones_de_cliente

TAMANO_MAXIMO = 100
LIMITE_BUSQUEDA_MAXIMO = 20


def solo_digitos(texto: str | None) -> str | None:
    """Deja solo los dígitos de `texto` (saca guiones, espacios, puntos);
    vacío o None → None. Definición única para DNI y CUIT (Principio 2:
    la usan tanto el alta/edición como los filtros de búsqueda)."""
    if texto is None:
        return None
    limpio = re.sub(r"\D", "", texto)
    return limpio or None


def obtener_cliente(db, cliente_id: int) -> Cliente:
    cliente = db.get(Cliente, cliente_id)
    if cliente is None:
        raise NoEncontrado("Cliente no encontrado")
    return cliente


def _condicion_busqueda(texto: str):
    """OR de nombre (ILIKE sin tildes) + prefijo de DNI/CUIT si el texto trae
    dígitos. Única definición: la reusan listar_clientes y buscar."""
    condiciones = [filtro_texto(Cliente.nombre, texto)]
    digitos = solo_digitos(texto)
    if digitos:
        condiciones.append(Cliente.dni.like(f"{digitos}%"))
        condiciones.append(Cliente.cuit.like(f"{digitos}%"))
    return or_(*condiciones)


def listar_clientes(db, *, busqueda: str | None = None, localidad: str | None = None,
                    condicion_iva: CondicionIva | None = None, activo: bool | None = None,
                    pagina: int = 1, tamano: int = 10) -> tuple[list[Cliente], int]:
    condiciones = []
    if busqueda and busqueda.strip():
        condiciones.append(_condicion_busqueda(busqueda))
    if localidad:
        condiciones.append(filtro_texto(Cliente.localidad, localidad))
    if condicion_iva is not None:
        condiciones.append(Cliente.condicion_iva == condicion_iva)
    if activo is not None:
        condiciones.append(Cliente.activo.is_(activo))
    pagina, tamano = paginar(pagina, tamano, TAMANO_MAXIMO)
    total = db.scalar(select(func.count()).select_from(Cliente).where(*condiciones))
    clientes = db.scalars(
        select(Cliente).where(*condiciones).order_by(func.lower(Cliente.nombre), Cliente.id)
        .offset((pagina - 1) * tamano).limit(tamano)
    ).all()
    return list(clientes), total


def buscar(db, texto: str, limite: int = 10) -> list[Cliente]:
    """Buscador rápido (combobox del punto de venta): solo clientes activos."""
    if not texto or not texto.strip():
        return []
    limite = max(1, min(limite, LIMITE_BUSQUEDA_MAXIMO))
    return list(db.scalars(
        select(Cliente).where(Cliente.activo.is_(True), _condicion_busqueda(texto))
        .order_by(func.lower(Cliente.nombre), Cliente.id).limit(limite)
    ).all())


def _validar_dni_cuit(db, dni, cuit, condicion_iva: CondicionIva,
                      excepto_id: int | None = None) -> tuple[str | None, str | None]:
    """Limpia DNI/CUIT a dígitos, valida formato y unicidad (excluyendo el
    propio id al editar). Se valida TODO antes de que el llamador mute nada."""
    dni_limpio = solo_digitos(dni)
    if dni_limpio is not None and len(dni_limpio) not in (7, 8):
        raise DatoInvalido("El DNI debe tener 7 u 8 dígitos")
    cuit_limpio = solo_digitos(cuit)
    if cuit_limpio is not None and (len(cuit_limpio) != 11 or not cuit_es_valido(cuit_limpio)):
        raise DatoInvalido("El CUIT no es válido: revisá el dígito verificador")
    if condicion_iva != CondicionIva.CONSUMIDOR_FINAL and cuit_limpio is None:
        raise DatoInvalido("El CUIT es obligatorio si no es consumidor final")
    if dni_limpio is not None:
        condiciones = [Cliente.dni == dni_limpio]
        if excepto_id is not None:
            condiciones.append(Cliente.id != excepto_id)
        otro = db.scalar(select(Cliente).where(*condiciones))
        if otro is not None:
            raise ReglaDeNegocio(f"El DNI {dni_limpio} ya está cargado en el cliente '{otro.nombre}'")
    if cuit_limpio is not None:
        condiciones = [Cliente.cuit == cuit_limpio]
        if excepto_id is not None:
            condiciones.append(Cliente.id != excepto_id)
        otro = db.scalar(select(Cliente).where(*condiciones))
        if otro is not None:
            raise ReglaDeNegocio(f"El CUIT {cuit_limpio} ya está cargado en el cliente '{otro.nombre}'")
    return dni_limpio, cuit_limpio


def _nombre_valido(nombre: str) -> str:
    limpio = normalizar_texto(nombre)
    if not limpio:
        raise DatoInvalido("El nombre es obligatorio")
    return limpio


def _asignar_datos(cliente: Cliente, datos, dni: str | None, cuit: str | None) -> None:
    cliente.nombre = _nombre_valido(datos.nombre)
    cliente.dni = dni
    cliente.cuit = cuit
    cliente.condicion_iva = datos.condicion_iva
    cliente.domicilio = normalizar_texto(datos.domicilio)
    cliente.codigo_postal = normalizar_texto(datos.codigo_postal)
    cliente.localidad = normalizar_texto(datos.localidad)
    cliente.telefono = normalizar_texto(datos.telefono)
    cliente.email = datos.email.lower() if datos.email else None


def crear_cliente(db, autor, datos, ip) -> Cliente:
    # _asignar_datos valida el nombre como su primer paso (antes de tocar
    # nada más); acá solo hace falta validar DNI/CUIT antes de construir el objeto.
    dni, cuit = _validar_dni_cuit(db, datos.dni, datos.cuit, datos.condicion_iva)
    cliente = Cliente(activo=True)
    _asignar_datos(cliente, datos, dni, cuit)
    db.add(cliente)
    db.flush()
    db.refresh(cliente)
    registrar_auditoria(db, accion="cliente.crear", entidad="cliente", entidad_id=cliente.id,
                        usuario_id=autor.id, estado_nuevo=cliente, ip_origen=ip)
    return cliente


def editar_cliente(db, autor, cliente: Cliente, datos, ip) -> Cliente:
    dni, cuit = _validar_dni_cuit(db, datos.dni, datos.cuit, datos.condicion_iva, excepto_id=cliente.id)
    antes = snapshot(cliente)
    _asignar_datos(cliente, datos, dni, cuit)
    db.flush()
    registrar_auditoria(db, accion="cliente.editar", entidad="cliente", entidad_id=cliente.id,
                        usuario_id=autor.id, estado_anterior=antes, estado_nuevo=cliente, ip_origen=ip)
    return cliente


def cambiar_estado(db, autor, cliente: Cliente, activo: bool, ip) -> Cliente:
    if cliente.activo is activo:
        return cliente
    antes = snapshot(cliente)
    cliente.activo = activo
    db.flush()
    registrar_auditoria(db, accion="cliente.activar" if activo else "cliente.desactivar", entidad="cliente",
                        entidad_id=cliente.id, usuario_id=autor.id, estado_anterior=antes,
                        estado_nuevo=cliente, ip_origen=ip)
    return cliente


def ficha(db, cliente_id: int) -> dict:
    """Cliente + resumen de compras (ventas CONFIRMADA, no anuladas) +
    promociones exclusivas (services.promociones.promociones_de_cliente)."""
    cliente = obtener_cliente(db, cliente_id)
    compras_cantidad, compras_total = db.execute(
        select(func.count(Venta.id), func.coalesce(func.sum(Venta.total), 0))
        .where(Venta.cliente_id == cliente_id, Venta.estado == EstadoVenta.CONFIRMADA)
    ).one()
    promociones = promociones_de_cliente(db, cliente_id)
    return {
        "cliente": cliente,
        "promociones": promociones,
        "compras_cantidad": compras_cantidad,
        "compras_total": Decimal(str(compras_total)),
    }
