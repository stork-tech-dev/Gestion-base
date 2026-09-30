"""Datos de demo para ver todas las pantallas con información (NO usar en producción).

Uso (desde la raíz del repo):
    docker compose exec backend python -m scripts.datos_demo

Todo pasa por los services (mismas reglas, stock y auditoría que el uso real).
Lo único que se toca a mano es la fecha de las ventas, para que haya historia
en los reportes: las de días anteriores quedan sin turno (así no inflan el
arqueo del turno de hoy). Si ya se cargó una vez (existe el usuario "lucas"),
no hace nada.
"""
import random
from datetime import datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.utils import ahora_db
from app.models import MedioDePago, MotivoBaja, Rol, Usuario
from app.schemas.categorias import CategoriaCrear
from app.schemas.clientes import ClienteCrear
from app.schemas.descuentos import MotivoDescuentoCrear
from app.schemas.medios_pago import PlanCuotasCrear
from app.schemas.productos import ProductoCrear
from app.schemas.promociones import PromocionCrear
from app.schemas.proveedores import ProveedorCrear
from app.schemas.usuarios import UsuarioCrear
from app.services import bajas_stock, categorias, clientes, descuentos, medios_pago, productos, promociones
from app.services import proveedores, stock, turnos, usuarios, ventas
from config import settings

PASSWORD = "Demo1234"
DIAS_DE_HISTORIA = 45
azar = random.Random(9)   # determinístico: dos corridas en bases vacías dan lo mismo


def _usuarios(db, admin) -> dict:
    roles = {r.nombre: r.id for r in db.scalars(select(Rol))}
    creados = {}
    for username, nombre, rol in (("sofia", "Sofía Gómez", "supervisor"), ("lucas", "Lucas Pérez", "vendedor"),
                                  ("martina", "Martina Díaz", "vendedor")):
        usuario = usuarios.crear_usuario(db, admin, UsuarioCrear(username=username, nombre=nombre, password=PASSWORD,
                                                                 rol_id=roles[rol]), None)
        usuario.ultimo_acceso = ahora_db()   # demo: entra sin el cambio de contraseña obligatorio
        creados[username] = usuario
    db.flush()
    return creados


def _catalogo(db, admin) -> dict:
    def categoria(nombre, padre=None):
        return categorias.crear_categoria(db, admin, CategoriaCrear(nombre=nombre, parent_id=padre.id if padre else None),
                                          None)

    ropa, calzado = categoria("Ropa"), categoria("Calzado")
    remeras, pantalones, buzos = categoria("Remeras", ropa), categoria("Pantalones", ropa), categoria("Buzos", ropa)
    zapatillas = categoria("Zapatillas", calzado)
    accesorios = categoria("Accesorios")

    textil = proveedores.crear_proveedor(db, admin, ProveedorCrear(nombre="Textil Andina", moneda="ars",
                                                                  provincia="Córdoba"), None)
    delta = proveedores.crear_proveedor(db, admin, ProveedorCrear(nombre="Importadora Delta", moneda="usd",
                                                                 dolar_actual="1050", pais="China"), None)

    def alta(descripcion, cat, proveedor, costo, margen, stock_inicial):
        return productos.crear_producto(db, admin, ProductoCrear(
            descripcion=descripcion, categoria_id=cat.id, proveedor_id=proveedor.id, costo=costo, margen=margen,
            stock_inicial=stock_inicial), None)

    lista = [
        alta("Remera lisa algodón blanca", remeras, textil, "6500", "80", 60),
        alta("Remera estampada negra", remeras, textil, "7800", "85", 45),
        alta("Jean clásico azul", pantalones, textil, "18000", "70", 30),
        alta("Jogger frisa gris", pantalones, textil, "14500", "75", 25),
        alta("Buzo canguro con capucha", buzos, textil, "21000", "70", 20),
        alta("Zapatillas running", zapatillas, delta, "28", "90", 18),
        alta("Zapatillas urbanas blancas", zapatillas, delta, "24", "95", 22),
        alta("Gorra trucker", accesorios, delta, "6", "100", 35),
        alta("Medias pack x3", accesorios, textil, "3200", "90", 80),
        alta("Mochila urbana", accesorios, delta, "19", "85", 12),
    ]
    return {"productos": lista, "categorias": {"remeras": remeras, "accesorios": accesorios}}


def _clientes(db, admin) -> list:
    datos = [
        ("Carla Ruiz", "30111222", None, "consumidor_final", "Villa Carlos Paz"),
        ("Diego Fernández", "28444555", None, "consumidor_final", "Córdoba"),
        ("Almacén Don Pepe", None, "20304050609", "monotributista", "Río Cuarto"),
        ("Laura Méndez", "35666777", None, "consumidor_final", "Córdoba"),
    ]
    return [clientes.crear_cliente(db, admin, ClienteCrear(nombre=n, dni=dni, cuit=cuit, condicion_iva=iva,
                                                           localidad=loc), None)
            for n, dni, cuit, iva, loc in datos]


def _configuracion_ventas(db, admin, cat) -> dict:
    credito = db.scalar(select(MedioDePago).where(MedioDePago.soporta_cuotas.is_(True)))
    planes = [medios_pago.crear_plan(db, admin, credito, PlanCuotasCrear(cuotas=c, recargo_cliente=r, costo_medio=m),
                                     None)
              for c, r, m in ((1, Decimal("0"), Decimal("3")), (3, Decimal("10"), Decimal("5")),
                              (6, Decimal("20"), Decimal("7")))]
    motivo = descuentos.crear_motivo(db, admin, MotivoDescuentoCrear(nombre="Cliente frecuente",
                                                                     porcentaje_sugerido=Decimal("10")), None)
    medias = cat["productos"][8]
    promociones.crear_promocion(db, admin, PromocionCrear(
        nombre="3x2 en medias", tipo="tres_x_dos",
        alcances=[{"tipo_alcance": "producto", "referencia_id": medias.id}]), None)
    medios = {m.nombre: m for m in db.scalars(select(MedioDePago))}
    return {"medios": medios, "credito": credito, "planes": planes, "motivo": motivo}


def _una_venta(db, vendedor, catalogo, config, clientes_):
    venta = ventas.iniciar_venta(db, vendedor, None)
    for producto in azar.sample(catalogo["productos"], azar.randint(1, 3)):
        for _ in range(azar.choice((1, 1, 1, 2, 3))):
            # El tope de stock bloquea: se controla acá para no pedirle a
            # agregar_item más de lo que queda.
            cargadas = sum(1 for i in venta.items if i.producto_id == producto.id)
            if producto.stock - cargadas > 0:
                venta = ventas.agregar_item(db, vendedor, venta.id, producto_id=producto.id)
    if not venta.items:
        ventas.descartar_venta(db, vendedor, venta.id, None)
        return None
    if azar.random() < 0.3:
        ventas.asociar_cliente(db, vendedor, venta.id, azar.choice(clientes_).id)
    if azar.random() < 0.2:
        item = next((i for i in venta.items if not i.en_promocion), None)
        if item is not None:
            venta = ventas.aplicar_descuento_item(db, vendedor, venta.id, item.id, config["motivo"].id,
                                                  Decimal("10"), None)
    sorteo = azar.random()
    if sorteo < 0.45:
        pagos = [{"medio_de_pago_id": config["medios"]["Efectivo"].id, "monto": venta.cobrable, "plan_cuotas_id": None}]
    elif sorteo < 0.65:
        pagos = [{"medio_de_pago_id": config["medios"]["Débito"].id, "monto": venta.cobrable, "plan_cuotas_id": None}]
    elif sorteo < 0.75:
        pagos = [{"medio_de_pago_id": config["medios"]["Transferencia"].id, "monto": venta.cobrable,
                  "plan_cuotas_id": None}]
    else:
        plan = azar.choice(config["planes"])
        pagos = [{"medio_de_pago_id": config["credito"].id, "monto": venta.cobrable, "plan_cuotas_id": plan.id}]
    venta = ventas.registrar_pagos(db, vendedor, venta.id, pagos)
    return ventas.confirmar_venta(db, vendedor, venta.id, venta.total, None)


def _ventas(db, admin, equipo, catalogo, config, clientes_) -> None:
    vendedores = [equipo["lucas"], equipo["martina"], equipo["sofia"]]
    hoy = ahora_db().date()
    confirmadas = []
    # Historia: 45 días hacia atrás (quedan sin turno para no inflar el arqueo de hoy).
    for dias_atras in range(DIAS_DE_HISTORIA, 0, -1):
        for _ in range(azar.choice((0, 1, 1, 2, 2, 3))):
            venta = _una_venta(db, azar.choice(vendedores), catalogo, config, clientes_)
            if venta is None:
                continue
            venta.confirmada_en = datetime.combine(hoy - timedelta(days=dias_atras),
                                                   time(azar.randint(10, 19), azar.randint(0, 59)))
            venta.turno_id = None
            confirmadas.append(venta)
    # Hoy: en el turno abierto.
    for _ in range(6):
        venta = _una_venta(db, azar.choice(vendedores), catalogo, config, clientes_)
        if venta is not None:
            confirmadas.append(venta)
    db.flush()
    # Dos anuladas (una de hoy y una de la semana pasada): el supervisor anula.
    ventas.anular_venta(db, equipo["sofia"], confirmadas[-1].id, "Cliente se arrepintió", None)
    ventas.anular_venta(db, equipo["sofia"], confirmadas[-10].id, "Error de carga", None)


def _stock_final(db, admin, catalogo) -> None:
    lista = catalogo["productos"]
    # Tres productos quedan bajo el mínimo (alertas y "Stock bajo el mínimo" del inicio).
    for producto in (lista[4], lista[5], lista[9]):
        stock.definir_minimo(db, admin, producto.id, producto.stock + 5, None)
    for producto in lista[:4]:
        stock.definir_minimo(db, admin, producto.id, 5, None)
    rotura = db.scalar(select(MotivoBaja).where(MotivoBaja.nombre == "Rotura"))
    bajas_stock.registrar_baja(db, admin, lista[1].id, 1, rotura.id, "Se descosió en el probador", None)
    stock.registrar_ingreso(db, admin, lista[8].id, 24, "Reposición semanal", None)


def main() -> None:
    if settings.APP_ENV == "production":
        raise SystemExit("Abortado: no se cargan datos de demo en producción.")
    db = SessionLocal()
    try:
        if db.scalar(select(Usuario).where(Usuario.username == "lucas")) is not None:
            print("Los datos de demo ya estaban cargados (existe el usuario 'lucas'). No se hizo nada.")
            return
        admin = db.scalar(select(Usuario).where(Usuario.username == "admin"))
        equipo = _usuarios(db, admin)
        catalogo = _catalogo(db, admin)
        clientes_ = _clientes(db, admin)
        config = _configuracion_ventas(db, admin, catalogo)
        turnos.abrir_turno(db, admin, Decimal("20000"), "Turno de demo", None)
        _ventas(db, admin, equipo, catalogo, config, clientes_)
        turnos.registrar_retiro(db, equipo["sofia"], Decimal("5000"), "Pago a proveedor de limpieza", None)
        _stock_final(db, admin, catalogo)
        db.commit()
        print(f"Listo. Usuarios de demo (contraseña {PASSWORD}): sofia (supervisor), lucas y martina (vendedores).")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
