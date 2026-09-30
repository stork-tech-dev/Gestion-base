# Mejoras de venta y productos — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cantidad editable en el carrito con tope de stock bloqueante, descuento general de la venta (% o total final), precio de venta manual que calcula el margen, redondeo visible y gestión de fotos al editar un producto.

**Architecture:** El modelo de ítems no cambia (una fila por unidad). El backend agrupa unidades en "líneas" (producto + descuento) para la respuesta y para el nuevo endpoint de cantidad; el descuento general es un monto en `ventas` que `_recalcular` reparte entre las unidades. El precio manual es una alternativa al margen en el alta/edición y en el preview. Las fotos se extraen a una macro + componente Alpine reutilizados por ficha y edición.

**Tech Stack:** FastAPI, SQLAlchemy 2, Alembic (SQL crudo como las migraciones existentes), PostgreSQL, Pydantic 2, Jinja2, Alpine.js 3, pytest, `node --test`.

**Spec:** `docs/superpowers/specs/2026-09-30-mejoras-venta-productos-design.md` (manda) + `CLAUDE.md` + `modulos/06_ventas.md` y `modulos/04_productos.md` como contexto.

## Global Constraints

- Código, textos y comentarios en español (voseo en la UI).
- **Git:** rama local `mejoras-venta-productos` (ya creada desde `dev`). UN commit por tarea con el mensaje que indica cada tarea + línea en blanco + EXACTAMENTE `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. NUNCA push, amend, reset, rebase, merge ni checkout. Nunca commitear `.env`, `uploads/`, `backups/`, `.superpowers/`, `docs/superpowers/`.
- **La base de desarrollo tiene datos de demo: NUNCA crear, modificar ni borrar datos en ella.** Excepción única: `alembic upgrade head` para aplicar la migración nueva (Task 2) — lo corre el entrypoint al reiniciar, o `docker compose exec -T backend alembic upgrade head`.
- Carpeta en iCloud: si git o lecturas se cuelgan, `find . -flags +dataless -type f -print0 | xargs -0 -n 20 -P 8 cat > /dev/null` y reintentar.
- Tests Python en el contenedor (`docker compose exec -T backend pytest -p no:warnings -q; echo exit=$?`: el resumen puede no imprimirse). JS: `node --check` y `node --test backend/tests_js/`.
- Services: nunca `commit`; `DatoInvalido` 400 / `NoEncontrado` 404 / `ReglaDeNegocio` 409; auditoría con `registrar_auditoria`. Routers hacen `db.commit()`.
- Dinero: siempre `Decimal`; redondeo con `core/utils.py::redondear`.
- `_recalcular` (services/ventas.py) sigue siendo el ÚNICO lugar donde se calculan los importes de una venta en curso.
- Pantallas: valores a Alpine solo con `|js` en atributos; sin `x-html` con datos de la API; escrituras con `pedir()`; mobile-first, áreas de toque de 44px (`min-h-toque`), tablas en `overflow-x-auto`; reusar macros de `templates/components/`.

---

### Task 1: Cantidad por línea y tope de stock bloqueante (backend)

**Revisión:** CON revisor (stock y dinero).

**Files:**
- Modify: `backend/app/services/ventas.py`, `backend/app/schemas/ventas.py`, `backend/app/api/v1/ventas.py`
- Test: `backend/tests/test_ventas.py`, `backend/tests/test_ventas_api.py` (y los tests existentes que armen ventas con productos sin stock)

**Interfaces:**
- Produces (Task 3 los usa): `VentaResponse.lineas: list[VentaLineaResponse]` con `item_id` (representante), `item_ids`, `producto_id`, `codigo`, `descripcion`, `foto_url`, `cantidad`, `precio_lista` (unitario), `precio_unitario` (unitario sin promo), `descuento_item`, `descuento_efectivo`, `motivo`, `porcentaje_modificado`, `precio_final` (suma de la línea), `unidades_en_promocion`, `stock` (stock actual del producto, `null` si es infinito). Endpoint `PUT /api/v1/ventas/{venta_id}/items/{item_id}/cantidad` body `{"cantidad": int}` → `VentaResponse`. `POST /{venta_id}/items` devuelve `VentaResponse` (ya no `{venta, aviso}`) y acepta `cantidad` opcional (default 1).
- Consumes: `services.ventas._recalcular`, `_venta_propia_en_curso`, `_item_de`.

- [ ] **Step 1: Tests (agregar a `backend/tests/test_ventas.py`)**

Usar la fixture `e` que ya existe en ese archivo (con `e.admin`, `e.vendedor`, `e.cat`, `e.p10`, …; leerla antes). Helper local para un producto con stock:

```python
def _con_stock(db, e, descripcion, stock, costo="1000"):
    producto = e.cat["alta"](descripcion, costo=costo)
    if stock:
        registrar_ingreso(db, e.admin, producto.id, stock, None, None)
    return producto


def test_agregar_con_cantidad_crea_una_unidad_por_fila_y_una_linea(db, e):
    vaso = _con_stock(db, e, "Vaso linea", 5)
    venta = servicio.iniciar_venta(db, e.vendedor, None)
    venta = servicio.agregar_item(db, e.vendedor, venta.id, producto_id=vaso.id, cantidad=3)
    assert len(venta.items) == 3
    lineas = servicio.lineas(venta)
    assert len(lineas) == 1 and len(lineas[0]) == 3


def test_escanear_otra_vez_suma_a_la_linea_sin_descuento(db, e):
    vaso = _con_stock(db, e, "Vaso escaneo", 5)
    venta = servicio.iniciar_venta(db, e.vendedor, None)
    servicio.agregar_item(db, e.vendedor, venta.id, producto_id=vaso.id)
    venta = servicio.agregar_item(db, e.vendedor, venta.id, codigo=vaso.codigo_con_verificador)
    assert [len(linea) for linea in servicio.lineas(venta)] == [2]


def test_no_se_supera_el_stock_al_agregar_ni_al_subir_la_cantidad(db, e):
    vaso = _con_stock(db, e, "Vaso tope", 3)
    venta = servicio.iniciar_venta(db, e.vendedor, None)
    with pytest.raises(ReglaDeNegocio, match="Solo quedan 3 unidades de 'Vaso tope'"):
        servicio.agregar_item(db, e.vendedor, venta.id, producto_id=vaso.id, cantidad=4)
    venta = servicio.agregar_item(db, e.vendedor, venta.id, producto_id=vaso.id, cantidad=2)
    with pytest.raises(ReglaDeNegocio, match="Solo quedan 3 unidades"):
        servicio.cambiar_cantidad(db, e.vendedor, venta.id, venta.items[0].id, 4)
    venta = servicio.cambiar_cantidad(db, e.vendedor, venta.id, venta.items[0].id, 3)
    assert len(venta.items) == 3
    with pytest.raises(ReglaDeNegocio, match="Solo quedan 3 unidades"):
        servicio.agregar_item(db, e.vendedor, venta.id, producto_id=vaso.id)


def test_sin_stock_no_se_puede_agregar(db, e):
    gorro = _con_stock(db, e, "Gorro sin stock", 0)
    venta = servicio.iniciar_venta(db, e.vendedor, None)
    with pytest.raises(ReglaDeNegocio, match="No hay stock de 'Gorro sin stock'"):
        servicio.agregar_item(db, e.vendedor, venta.id, producto_id=gorro.id)


def test_stock_infinito_no_tiene_tope(db, e):
    servicio_infinito = e.cat["alta"]("Servicio de arreglo", costo="1000", stock_infinito=True)
    venta = servicio.iniciar_venta(db, e.vendedor, None)
    venta = servicio.agregar_item(db, e.vendedor, venta.id, producto_id=servicio_infinito.id, cantidad=50)
    assert len(venta.items) == 50


def test_bajar_la_cantidad_quita_las_ultimas_y_cero_quita_la_linea(db, e):
    vaso = _con_stock(db, e, "Vaso baja", 5)
    remera = _con_stock(db, e, "Remera baja", 5)
    venta = servicio.iniciar_venta(db, e.vendedor, None)
    venta = servicio.agregar_item(db, e.vendedor, venta.id, producto_id=vaso.id, cantidad=4)
    venta = servicio.agregar_item(db, e.vendedor, venta.id, producto_id=remera.id)
    primera = min(i.id for i in venta.items if i.producto_id == vaso.id)
    venta = servicio.cambiar_cantidad(db, e.vendedor, venta.id, primera, 1)
    assert sorted(i.id for i in venta.items if i.producto_id == vaso.id) == [primera]
    venta = servicio.cambiar_cantidad(db, e.vendedor, venta.id, primera, 0)
    assert [i.producto_id for i in venta.items] == [remera.id]


def test_la_cantidad_valida_el_rango(db, e):
    vaso = _con_stock(db, e, "Vaso rango", 5)
    venta = servicio.iniciar_venta(db, e.vendedor, None)
    venta = servicio.agregar_item(db, e.vendedor, venta.id, producto_id=vaso.id)
    for cantidad in (-1, 1000):
        with pytest.raises(DatoInvalido):
            servicio.cambiar_cantidad(db, e.vendedor, venta.id, venta.items[0].id, cantidad)


def test_subir_la_cantidad_copia_el_descuento_de_la_linea(db, e):
    vaso = _con_stock(db, e, "Vaso con descuento", 5)
    motivo = e.motivo   # si la fixture no tiene un motivo de descuento, crearlo con services.descuentos.crear_motivo
    venta = servicio.iniciar_venta(db, e.vendedor, None)
    venta = servicio.agregar_item(db, e.vendedor, venta.id, producto_id=vaso.id, cantidad=2)
    venta = servicio.aplicar_descuento_item(db, e.vendedor, venta.id, venta.items[0].id, motivo.id, 10, None)
    assert all(i.descuento_item == Decimal("10") for i in venta.items)       # toda la línea
    venta = servicio.cambiar_cantidad(db, e.vendedor, venta.id, venta.items[0].id, 3)
    assert len(venta.items) == 3 and all(i.descuento_item == Decimal("10") for i in venta.items)
    venta = servicio.agregar_item(db, e.vendedor, venta.id, producto_id=vaso.id)   # sin descuento: otra línea
    assert sorted(len(linea) for linea in servicio.lineas(venta)) == [1, 3]


def test_confirmar_verifica_el_stock_otra_vez(db, e):
    vaso = _con_stock(db, e, "Vaso confirmar", 2)
    venta = servicio.iniciar_venta(db, e.vendedor, None)
    venta = servicio.agregar_item(db, e.vendedor, venta.id, producto_id=vaso.id, cantidad=2)
    # Otro vendedor se lleva una unidad en el medio.
    registrar_baja_o_venta = __import__("app.services.stock", fromlist=["aplicar_movimiento"]).aplicar_movimiento
    from app.models import TipoMovimientoStock
    registrar_baja_o_venta(db, e.admin, tipo=TipoMovimientoStock.AJUSTE_AUDITORIA, producto_id=vaso.id, cantidad=-1)
    efectivo = db.scalar(select(MedioDePago).where(MedioDePago.es_efectivo.is_(True)))
    venta = servicio.registrar_pagos(db, e.vendedor, venta.id,
                                     [{"medio_de_pago_id": efectivo.id, "monto": venta.cobrable, "plan_cuotas_id": None}])
    with pytest.raises(ReglaDeNegocio, match="No hay stock suficiente de 'Vaso confirmar'"):
        servicio.confirmar_venta(db, e.vendedor, venta.id, venta.total, None)
```

(Ajustar mecánicamente a la fixture real: nombres de atributos de `e`, turno abierto —confirmar necesita uno—, imports de `select`, `MedioDePago`, `registrar_ingreso`, `DatoInvalido`. Si `aplicar_movimiento` con `AJUSTE_AUDITORIA` exige `auditoria_id`, usar en su lugar una baja con `services.bajas_stock.registrar_baja` y un motivo de baja del seed.)

Borrar o reescribir los tests que afirmaban la regla vieja: `test_agregar_sin_stock_avisa_y_agrega` y `test_aviso_cuenta_lo_ya_cargado` (tests/test_ventas.py) pasan a afirmar el 409; `test_agregar_item_sin_stock_da_200_con_aviso` (tests/test_ventas_api.py) pasa a `..._da_409`; la aserción `cuerpo["aviso"] is None` (test_ventas_api.py:88) se adapta a la nueva respuesta (`VentaResponse` directo). **Correr la suite completa**: todo test existente que venda productos sin stock (fixtures de ventas, caja, anulación, reportes) tiene que cargar stock antes (con `registrar_ingreso`); ajustar esos fixtures, sin cambiar lo que cada test verifica.

En `backend/tests/test_ventas_api.py`:

```python
def test_put_cantidad_y_lineas_en_la_respuesta(client, crear_usuario, headers_de, db):
    admin = crear_usuario("admin")
    producto = _producto_con_stock(db, admin, "Vaso API cantidad", cantidad=5)
    h = headers_de(crear_usuario("vendedor"))
    venta_id = client.post(URL, headers=h).json()["id"]
    r = client.post(f"{URL}/{venta_id}/items", json={"producto_id": producto.id, "cantidad": 2}, headers=h)
    assert r.status_code == 200
    linea = r.json()["lineas"][0]
    assert linea["cantidad"] == 2 and len(linea["item_ids"]) == 2 and linea["stock"] == 5
    assert linea["precio_final"] == str(Decimal(r.json()["items"][0]["precio_final"]) * 2)
    r = client.put(f"{URL}/{venta_id}/items/{linea['item_id']}/cantidad", json={"cantidad": 5}, headers=h)
    assert r.status_code == 200 and r.json()["lineas"][0]["cantidad"] == 5
    r = client.put(f"{URL}/{venta_id}/items/{linea['item_id']}/cantidad", json={"cantidad": 6}, headers=h)
    assert r.status_code == 409 and "Solo quedan 5 unidades" in r.json()["detail"]
    assert client.put(f"{URL}/{venta_id}/items/{linea['item_id']}/cantidad", json={"cantidad": 1000},
                      headers=h).status_code == 422
```

Run: `docker compose exec -T backend pytest -p no:warnings tests/test_ventas.py tests/test_ventas_api.py -q; echo exit=$?` → FAIL.

- [ ] **Step 2: Service (`backend/app/services/ventas.py`)**

Constante y helpers (junto a las constantes del módulo):

```python
CANTIDAD_MAXIMA = 999   # por pedido: tope de sanidad (el tope real es el stock)


def _clave_linea(item: VentaItem) -> tuple:
    """Unidades del mismo producto con el mismo descuento = una línea del carrito."""
    return (item.producto_id, item.descuento_item, item.motivo_descuento_id)


def lineas(venta: Venta) -> list[list[VentaItem]]:
    """Unidades agrupadas en líneas, en el orden de su primera unidad."""
    grupos: dict[tuple, list[VentaItem]] = {}
    for item in sorted(venta.items, key=lambda i: i.orden):
        grupos.setdefault(_clave_linea(item), []).append(item)
    return list(grupos.values())


def _validar_cantidad(cantidad: int, *, permite_cero: bool) -> None:
    minimo = 0 if permite_cero else 1
    if not isinstance(cantidad, int) or not minimo <= cantidad <= CANTIDAD_MAXIMA:
        raise DatoInvalido(f"La cantidad tiene que estar entre {minimo} y {CANTIDAD_MAXIMA}")


def _validar_stock(venta: Venta, producto, agregar: int) -> None:
    """Decisión del usuario: la venta nunca supera el stock (stock infinito: sin tope)."""
    if producto.stock_infinito:
        return
    cargadas = sum(1 for i in venta.items if i.producto_id == producto.id)
    if cargadas + agregar > producto.stock:
        if producto.stock <= 0:
            raise ReglaDeNegocio(f"No hay stock de '{producto.descripcion}'.")
        raise ReglaDeNegocio(f"Solo quedan {producto.stock} unidades de '{producto.descripcion}'.")


def _nueva_unidad(venta: Venta, producto, *, descuento=Decimal("0"), motivo=None, modificado=False) -> VentaItem:
    orden = max((i.orden for i in venta.items), default=0) + 1
    # Los precios los completa _recalcular; acá solo para no violar NOT NULL.
    item = VentaItem(
        producto_id=producto.id, producto=producto, orden=orden,
        precio_lista=producto.precio_venta, precio_unitario=producto.precio_venta,
        precio_final=producto.precio_venta, costo_unitario=producto.costo_en_pesos,
        descuento_item=descuento, motivo_descuento_id=motivo.id if motivo else None, motivo_descuento=motivo,
        porcentaje_modificado=modificado, en_promocion=False,
    )
    venta.items.append(item)
    return item
```

`agregar_item` pasa a:

```python
def agregar_item(db, autor, venta_id: int, *, codigo: str | None = None, producto_id: int | None = None,
                 cantidad: int = 1, ip=None) -> Venta:
    """Agrega `cantidad` unidades sin descuento (caen en la línea sin
    descuento del producto). 409 si superan el stock. Sin auditoría por ítem."""
    if (codigo is None) == (producto_id is None):
        raise DatoInvalido("Indicá el código o el producto (uno de los dos)")
    _validar_cantidad(cantidad, permite_cero=False)
    venta = _venta_propia_en_curso(db, autor, venta_id)
    producto = buscar_por_codigo(db, codigo) if codigo is not None else obtener_producto(db, producto_id)
    if not producto.activo:
        raise ReglaDeNegocio(f"'{producto.descripcion}' está inactivo")
    _validar_stock(venta, producto, cantidad)
    for _ in range(cantidad):
        _nueva_unidad(venta, producto)
    db.flush()   # los ítems necesitan id: promociones.simular indexa por item.id
    _carrito_cambio(venta)
    _recalcular(db, venta)
    return venta
```

Nuevo:

```python
def cambiar_cantidad(db, autor, venta_id: int, item_id: int, cantidad: int, ip=None) -> Venta:
    """Fija la cantidad de la línea del ítem: sube con el mismo descuento de la
    línea, baja quitando las últimas unidades, 0 quita la línea."""
    _validar_cantidad(cantidad, permite_cero=True)
    venta = _venta_propia_en_curso(db, autor, venta_id)
    item = _item_de(venta, item_id)
    linea = [i for i in venta.items if _clave_linea(i) == _clave_linea(item)]
    diferencia = cantidad - len(linea)
    if diferencia > 0:
        _validar_stock(venta, item.producto, diferencia)
        for _ in range(diferencia):
            _nueva_unidad(venta, item.producto, descuento=item.descuento_item, motivo=item.motivo_descuento,
                          modificado=item.porcentaje_modificado)
    else:
        for sobrante in sorted(linea, key=lambda i: i.orden, reverse=True)[:-diferencia]:
            venta.items.remove(sobrante)
    db.flush()
    _carrito_cambio(venta)
    _recalcular(db, venta)
    return venta
```

`_carrito_cambio(venta)` (helper nuevo) = lo que hoy hacen varias funciones al cambiar el carrito:

```python
def _carrito_cambio(venta: Venta) -> None:
    """Cambió el carrito: la promoción elegida a mano deja de valer (se elige
    la mejor de nuevo). La Task 2 suma acá el reset del descuento general."""
    venta.promocion_a_mano = False
```

Usarlo en `agregar_item`, `cambiar_cantidad`, `quitar_item`, `asociar_cliente` y `aplicar_descuento_item` en lugar del `venta.promocion_a_mano = False` suelto (misma conducta).

`aplicar_descuento_item` aplica a toda la línea:

```python
    venta = _venta_propia_en_curso(db, autor, venta_id)
    item = _item_de(venta, item_id)
    linea = [i for i in venta.items if _clave_linea(i) == _clave_linea(item)]
    if any(i.en_promocion for i in linea):
        raise ReglaDeNegocio("Este producto está en una promoción: no admite otro descuento")
    motivo, valor, modificado = None, Decimal("0"), False
    if motivo_id is not None:
        motivo, valor, modificado = resolver_porcentaje(db, motivo_id, porcentaje)
        validar_tope(db, item.producto.descuento_producto, valor, item.producto.descripcion)
    antes = {"item_ids": [i.id for i in linea], "descuento_item": item.descuento_item,
             "motivo_descuento_id": item.motivo_descuento_id}
    for unidad in linea:
        unidad.descuento_item = valor
        unidad.motivo_descuento_id = motivo.id if motivo else None
        unidad.motivo_descuento = motivo
        unidad.porcentaje_modificado = modificado
    _carrito_cambio(venta)
    _recalcular(db, venta)
    registrar_auditoria(db, accion="venta.descuento", entidad="venta", entidad_id=venta.id, usuario_id=autor.id,
                        estado_anterior=antes,
                        estado_nuevo={"item_ids": [i.id for i in linea], "descuento_item": valor,
                                      "motivo_descuento_id": motivo.id if motivo else None},
                        ip_origen=ip)
    return venta
```

`confirmar_venta`: en el loop de `aplicar_movimiento`, quitar `permitir_faltante=True` (el producto se bloquea y, si otro vendió en el medio, `aplicar_movimiento` levanta `ReglaDeNegocio("No hay stock suficiente de …")`; el router ya hace rollback). Actualizar el docstring del módulo/las funciones que hablen de "la venta puede dejar el stock en negativo".

- [ ] **Step 3: Schemas (`backend/app/schemas/ventas.py`)**

```python
class ItemAgregar(BaseModel):
    codigo: str | None = Field(default=None, min_length=1, max_length=30)
    producto_id: int | None = None
    cantidad: int = Field(default=1, ge=1, le=999)


class CantidadLinea(BaseModel):
    cantidad: int = Field(ge=0, le=999)   # 0 = quitar la línea
```

`VentaLineaResponse` (antes de `VentaResponse`):

```python
class VentaLineaResponse(BaseModel):
    """Unidades del mismo producto con el mismo descuento (lo que muestra el carrito)."""
    item_id: int                     # representante: cantidad, descuento y quitar se piden con este id
    item_ids: list[int]
    producto_id: int
    codigo: str
    descripcion: str
    foto_url: str | None
    cantidad: int
    precio_lista: Decimal            # unitario
    precio_unitario: Decimal         # unitario sin promo
    descuento_item: Decimal
    descuento_efectivo: Decimal
    motivo: Referencia | None
    porcentaje_modificado: bool
    precio_final: Decimal            # suma de la línea
    unidades_en_promocion: int
    stock: int | None                # stock actual del producto; None = infinito

    @classmethod
    def desde(cls, unidades) -> "VentaLineaResponse":
        primera = unidades[0]
        producto = primera.producto
        return cls(
            item_id=primera.id, item_ids=[i.id for i in unidades], producto_id=primera.producto_id,
            codigo=producto.codigo_con_verificador, descripcion=producto.descripcion,
            foto_url=producto.foto_principal_url, cantidad=len(unidades),
            precio_lista=primera.precio_lista, precio_unitario=primera.precio_unitario,
            descuento_item=primera.descuento_item,
            descuento_efectivo=calcular_descuento_total(producto.descuento_producto, primera.descuento_item),
            motivo=Referencia.de(primera.motivo_descuento), porcentaje_modificado=primera.porcentaje_modificado,
            precio_final=sum((i.precio_final for i in unidades), Decimal("0")),
            unidades_en_promocion=sum(1 for i in unidades if i.en_promocion),
            stock=None if producto.stock_infinito else producto.stock,
        )
```

`VentaResponse` suma `lineas: list[VentaLineaResponse]` (después de `items`); `VentaResponse.desde` recibe las líneas ya agrupadas: `lineas=[VentaLineaResponse.desde(u) for u in lineas_agrupadas]`. Para no importar el service desde el schema, `desde(cls, venta, caminos, lineas)` recibe las líneas y `services.ventas.a_respuesta` las pasa: `VentaResponse.desde(venta, caminos, lineas(venta))`. Borrar `AgregarItemResponse`.

- [ ] **Step 4: Router (`backend/app/api/v1/ventas.py`)**

```python
@router.post("/{venta_id}/items", response_model=VentaResponse)
def agregar_item(venta_id: int, datos: ItemAgregar, request: Request, db: Session = Depends(get_db),
                 autor: Usuario = Depends(puede_vender)):
    venta = servicio.agregar_item(db, autor, venta_id, codigo=datos.codigo, producto_id=datos.producto_id,
                                  cantidad=datos.cantidad, ip=ip_de_request(request))
    db.commit()
    return servicio.a_respuesta(db, venta)


@router.put("/{venta_id}/items/{item_id}/cantidad", response_model=VentaResponse)
def cambiar_cantidad(venta_id: int, item_id: int, datos: CantidadLinea, request: Request,
                     db: Session = Depends(get_db), autor: Usuario = Depends(puede_vender)):
    venta = servicio.cambiar_cantidad(db, autor, venta_id, item_id, datos.cantidad, ip=ip_de_request(request))
    db.commit()
    return servicio.a_respuesta(db, venta)
```

(Respetar el orden de rutas del archivo; `/items/{item_id}/cantidad` no choca con `DELETE /items/{item_id}`.)

- [ ] **Step 5: Correr y commitear**

Focalizados → PASS; suite completa → exit 0 (ajustando fixtures según Step 1). El frontend (`venta.js`) todavía lee `r.venta`/`r.aviso` de la respuesta de agregar: en ESTA tarea hacer el ajuste mínimo en `backend/app/static/js/venta.js::_agregar` para que la pantalla no se rompa (`.then((venta) => venta)` en vez de leer `r.venta`/`r.aviso`) y correr `node --test backend/tests_js/` (ajustar el test JS que dependa del aviso, si hay). El rediseño del carrito es la Task 3.

```bash
git add backend/app/services/ventas.py backend/app/schemas/ventas.py backend/app/api/v1/ventas.py \
  backend/app/static/js/venta.js backend/tests backend/tests_js
git commit -m "feat(ventas): cantidad por línea y tope de stock bloqueante

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Descuento general de la venta (backend)

**Revisión:** CON revisor (dinero).

**Files:**
- Create: `backend/migrations/versions/0008_descuento_general.py`
- Modify: `backend/app/models/ventas.py`, `backend/app/services/ventas.py`, `backend/app/schemas/ventas.py`, `backend/app/api/v1/ventas.py`
- Test: `backend/tests/test_ventas.py`, `backend/tests/test_ventas_api.py`

**Interfaces:**
- Consumes (Task 1): `_carrito_cambio(venta)`, `lineas`, `_recalcular`.
- Produces (Task 3): `VentaResponse.descuento_general: Decimal`; `POST /api/v1/ventas/{venta_id}/descuento-general` body `{"porcentaje": "10" | null, "total": "80.00" | null}` (ninguno = quitar) → `VentaResponse`; permiso `venta.descuento`.

- [ ] **Step 1: Migración y modelo**

`backend/migrations/versions/0008_descuento_general.py` (mismo estilo que `0007_caja.py`: `op.execute` con SQL):

```python
"""Descuento general de la venta (monto que se reparte entre las unidades)."""
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE ventas ADD COLUMN descuento_general NUMERIC(10,2) NOT NULL DEFAULT 0;
        ALTER TABLE ventas ADD CONSTRAINT ck_ventas_descuento_general CHECK (descuento_general >= 0);
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE ventas DROP COLUMN descuento_general;")
```

En `Venta` (models/ventas.py), junto a `descuento_total`:

```python
    # Monto del descuento general (% o "total final" de la pantalla). Ya está
    # repartido en el precio_final de cada unidad: se guarda para poder
    # recalcular y para mostrarlo; no se vuelve a restar del total.
    descuento_general: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"))
```

Aplicar a la base de desarrollo: `docker compose exec -T backend alembic upgrade head` (la base de tests se recrea sola).

- [ ] **Step 2: Tests (agregar a `backend/tests/test_ventas.py`)**

```python
def _venta_de(db, e, *precios):
    """Venta en curso con una unidad por precio (productos con stock, margen 0 y redondeo del test)."""
    venta = servicio.iniciar_venta(db, e.vendedor, None)
    for n, costo in enumerate(precios):
        producto = e.cat["alta"](f"Desc general {n} {costo}", costo=costo, margen="0")
        registrar_ingreso(db, e.admin, producto.id, 5, None, None)
        venta = servicio.agregar_item(db, e.vendedor, venta.id, producto_id=producto.id)
    return venta


def test_descuento_por_total_final_reparte_al_centavo(db, e):
    venta = _venta_de(db, e, "3000", "5300")
    base = venta.cobrable
    objetivo = base - Decimal("300")
    venta = servicio.aplicar_descuento_general(db, e.vendedor, venta.id, total=objetivo, ip=None)
    assert venta.descuento_general == Decimal("300.00")
    assert venta.cobrable == objetivo
    assert sum(i.precio_final for i in venta.items) == objetivo
    assert venta.descuento_total == venta.subtotal - objetivo


def test_descuento_por_porcentaje(db, e):
    venta = _venta_de(db, e, "3000", "5000")
    base = venta.cobrable
    venta = servicio.aplicar_descuento_general(db, e.vendedor, venta.id, porcentaje=Decimal("10"), ip=None)
    assert venta.descuento_general == redondear(base * Decimal("0.10"))


def test_descuento_general_respeta_el_tope(db, e):
    venta = _venta_de(db, e, "10000")
    tope = servicio_descuentos.tope(db)
    with pytest.raises(DatoInvalido, match="no puede superar"):
        servicio.aplicar_descuento_general(db, e.vendedor, venta.id, porcentaje=tope + 1, ip=None)


def test_total_final_invalido(db, e):
    venta = _venta_de(db, e, "10000")
    for total in (venta.cobrable + 1, Decimal("0")):
        with pytest.raises(DatoInvalido):
            servicio.aplicar_descuento_general(db, e.vendedor, venta.id, total=total, ip=None)


def test_cambiar_el_carrito_borra_el_descuento_general(db, e):
    venta = _venta_de(db, e, "3000", "5000")
    venta = servicio.aplicar_descuento_general(db, e.vendedor, venta.id, porcentaje=Decimal("5"), ip=None)
    venta = servicio.cambiar_cantidad(db, e.vendedor, venta.id, venta.items[0].id, 2)
    assert venta.descuento_general == 0
    assert venta.cobrable == sum(i.precio_final for i in venta.items)


def test_quitar_el_descuento_general(db, e):
    venta = _venta_de(db, e, "3000")
    base = venta.cobrable
    venta = servicio.aplicar_descuento_general(db, e.vendedor, venta.id, porcentaje=Decimal("5"), ip=None)
    venta = servicio.aplicar_descuento_general(db, e.vendedor, venta.id, ip=None)
    assert venta.descuento_general == 0 and venta.cobrable == base


def test_descuento_general_se_audita_y_llega_confirmado(db, e):
    # Confirmar con descuento general: los precio_final guardados suman el total cobrado.
    ...  # armar venta, aplicar total final, registrar pagos por venta.cobrable, confirmar (con turno de la fixture);
         # verificar sum(precio_final) == venta.total - venta.recargo_total y un registro de auditoría
         # accion="venta.descuento_general" con estado_nuevo["descuento_general"] == "300.00".
```

(Completar el último test con el patrón de `_confirmada` de `tests/test_anulacion.py`. Si el redondeo configurado en la base de tests hace que los precios no sean los del costo, derivar los esperados de `venta.cobrable` como arriba, nunca de números fijos.)

En `backend/tests/test_ventas_api.py`: un test de `POST /descuento-general` con `{"total": ...}` → 200 y `descuento_general` en la respuesta; con porcentaje y total a la vez → 400; un vendedor sin `venta.descuento` → 403 (crear un rol sin ese recurso, como los tests de descuento existentes).

- [ ] **Step 3: Service**

`_carrito_cambio` suma el reset:

```python
def _carrito_cambio(venta: Venta) -> None:
    """Cambió el carrito: la promoción elegida a mano y el descuento general
    dejan de valer (se vuelven a elegir sobre el carrito nuevo)."""
    venta.promocion_a_mano = False
    venta.descuento_general = Decimal("0")
```

Llamarlo también en `elegir_promocion` (reset del descuento general; ahí `promocion_a_mano` se pone en True DESPUÉS, respetar ese orden).

Reparto (helper nuevo, usa `ROUND_DOWN` de `decimal`):

```python
CENTAVO = Decimal("0.01")


def _repartir_descuento_general(items, monto: Decimal) -> None:
    """Resta `monto` de los precio_final en proporción a cada uno, al centavo:
    primero la parte truncada y después los centavos que sobran, de a uno, a
    las unidades con mayor fracción descartada (Σ descuentos == monto exacto)."""
    base = sum((i.precio_final for i in items), Decimal("0"))
    if not monto or base <= 0:
        return
    partes = [(i, i.precio_final * monto / base) for i in items]
    truncadas = {i.id: parte.quantize(CENTAVO, rounding=ROUND_DOWN) for i, parte in partes}
    sobrante = int((monto - sum(truncadas.values())) / CENTAVO)
    candidatas = sorted((p for p in partes if p[0].precio_final > truncadas[p[0].id]),
                        key=lambda p: (p[1] - truncadas[p[0].id], -p[0].orden), reverse=True)
    for item, _ in candidatas[:sobrante]:
        truncadas[item.id] += CENTAVO
    for item in items:
        item.precio_final -= truncadas[item.id]
```

En `_recalcular`, después del paso 2 (promoción) y antes del paso 3 (totales):

```python
    # 2b. Descuento general: monto fijo repartido entre las unidades. Red de
    #     seguridad: si ya no entra (cambió una promo por medio de pago), se borra.
    base = sum((i.precio_final for i in venta.items), Decimal("0"))
    if venta.descuento_general and (venta.descuento_general >= base
                                    or venta.descuento_general > redondear(base * tope(db) / 100)):
        venta.descuento_general = Decimal("0")
    _repartir_descuento_general(venta.items, venta.descuento_general)
```

(`tope` de `services.descuentos`; importarlo junto a lo que ya se importa de ahí.)

Nueva función:

```python
def aplicar_descuento_general(db, autor, venta_id: int, *, porcentaje: Decimal | None = None,
                              total: Decimal | None = None, ip=None) -> Venta:
    """Descuento sobre toda la venta, por % o por total final (ninguno = quitar).
    El permiso `venta.descuento` lo chequea el router. Sin motivo (decisión del usuario)."""
    if porcentaje is not None and total is not None:
        raise DatoInvalido("Indicá el porcentaje o el total final, no los dos")
    venta = _venta_propia_en_curso(db, autor, venta_id)
    anterior = venta.descuento_general
    venta.descuento_general = Decimal("0")
    _recalcular(db, venta)
    base = venta.cobrable
    if porcentaje is not None:
        monto = redondear(base * Decimal(porcentaje) / 100)
    elif total is not None:
        total = redondear(total)
        if total <= 0:
            raise DatoInvalido("El total final tiene que ser mayor a 0")
        if total > base:
            raise DatoInvalido("El total final no puede ser mayor al total actual")
        monto = base - total
    else:
        monto = Decimal("0")
    limite = tope(db)
    if monto >= base and monto > 0:
        raise DatoInvalido("El descuento no puede cubrir todo el total")
    if monto > redondear(base * limite / 100):
        raise DatoInvalido(f"El descuento general no puede superar el {int(limite)}% del total")
    venta.descuento_general = monto
    _recalcular(db, venta)
    registrar_auditoria(db, accion="venta.descuento_general", entidad="venta", entidad_id=venta.id,
                        usuario_id=autor.id, estado_anterior={"descuento_general": anterior},
                        estado_nuevo={"descuento_general": monto, "porcentaje": porcentaje, "total": total},
                        ip_origen=ip)
    return venta
```

- [ ] **Step 4: Schema y router**

```python
class DescuentoGeneral(BaseModel):
    """Uno de los dos (o ninguno = quitar el descuento general)."""
    porcentaje: Decimal | None = Field(default=None, gt=0, le=100, decimal_places=2)
    total: Decimal | None = Field(default=None, gt=0, le=MONTO_MAXIMO, decimal_places=2)
```

`VentaResponse` suma `descuento_general: Decimal` (asignado en `desde`).

```python
@router.post("/{venta_id}/descuento-general", response_model=VentaResponse)
def aplicar_descuento_general(venta_id: int, datos: DescuentoGeneral, request: Request,
                              db: Session = Depends(get_db), autor: Usuario = Depends(puede_vender),
                              _descuento: Usuario = Depends(puede_descontar)):
    venta = servicio.aplicar_descuento_general(db, autor, venta_id, porcentaje=datos.porcentaje, total=datos.total,
                                               ip=ip_de_request(request))
    db.commit()
    return servicio.a_respuesta(db, venta)
```

- [ ] **Step 5: Correr y commitear**

Focalizados → PASS; suite completa → exit 0.

```bash
git add backend/migrations/versions/0008_descuento_general.py backend/app/models/ventas.py \
  backend/app/services/ventas.py backend/app/schemas/ventas.py backend/app/api/v1/ventas.py backend/tests
git commit -m "feat(ventas): descuento general de la venta por porcentaje o total final

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Pantalla de venta — carrito por líneas y descuento general

**Revisión:** sin revisor por tarea (la cubre la revisión final).

**Files:**
- Modify: `backend/app/templates/pages/ventas/nueva.html`, `backend/app/static/js/venta.js`
- Test: `backend/tests_js/venta.test.mjs`, `backend/tests/test_paginas_ventas.py`

**Interfaces:** consume `venta.lineas`, `venta.descuento_general`, `PUT /items/{item_id}/cantidad`, `POST /descuento-general` (Tasks 1 y 2).

- [ ] **Step 1: Lógica pura en `window.ventaLogica` (con tests en `tests_js/venta.test.mjs`)**

```js
    // Cantidad tipeada en una línea → entero válido o null (vacío, decimal,
    // negativo, > 999: se ignora y la fila vuelve a la cantidad de la API).
    cantidadValida: (valor) => {
      const texto = String(valor ?? '').trim();
      if (!/^\d+$/.test(texto)) return null;
      const n = Number(texto);
      return n <= 999 ? n : null;
    },
    // El + de una línea: deshabilitado si ya se llegó al stock (null = infinito).
    puedeSumar: (linea) => linea.stock === null || linea.cantidad < linea.stock,
    // Columna Descuento de una línea.
    textoDescuentoLinea: (linea) => {
      if (linea.unidades_en_promocion) return linea.unidades_en_promocion === linea.cantidad
        ? 'Promo' : `Promo (${linea.unidades_en_promocion} de ${linea.cantidad})`;
      return Number(linea.descuento_item) > 0 ? `${Number(linea.descuento_item)}% · ${linea.motivo?.nombre ?? ''}` : '';
    },
    puedeDescontarLinea: (linea, permiso) => permiso && !linea.unidades_en_promocion,
    // % que representa el descuento general sobre el total antes de aplicarlo (1 decimal, para mostrar).
    porcentajeDescuentoGeneral: (venta) => {
      const monto = Number(venta?.descuento_general || 0);
      const base = Number(venta?.cobrable || 0) + monto;
      return monto > 0 && base > 0 ? Math.round((monto / base) * 1000) / 10 : 0;
    },
    // Cuerpo de POST /descuento-general según el modo elegido ('porcentaje' | 'total').
    cuerpoDescuentoGeneral: (modo, valor) => {
      const texto = String(valor ?? '').trim().replace(',', '.');
      if (!texto) return null;
      return modo === 'total' ? { total: texto, porcentaje: null } : { porcentaje: texto, total: null };
    },
```

Tests JS (en el archivo existente, con su `cargar()`): `cantidadValida` ('3'→3, ''→null, '2.5'→null, '-1'→null, '1000'→null, '0'→0); `puedeSumar` (stock 3 cantidad 3 → false; stock null → true); `textoDescuentoLinea` (promo total, promo parcial "Promo (1 de 3)", descuento con motivo, vacío); `porcentajeDescuentoGeneral` ({descuento_general:'3.00', cobrable:'80.00'} → 3.6); `cuerpoDescuentoGeneral` ('total','80' → {total:'80',porcentaje:null}; 'porcentaje','10,5' → porcentaje '10.5'; vacío → null). Ajustar/borrar los tests de `textoDescuento`/`puedeDescontar` por ítem si esas funciones se reemplazan.

- [ ] **Step 2: Carrito por líneas (`nueva.html` + `venta.js`)**

- La tabla itera `venta.lineas` (`x-for="linea in lineas" :key="linea.item_id"`; getter `lineas` análogo a `items`). Columnas: foto, código, descripción, **Cantidad**, precio unitario (tachado el de lista si difiere, como hoy), descuento (`textoDescuentoLinea`), final (`plata(linea.precio_final)`, suma de la línea), acciones.
- Celda Cantidad: `[−]` `<input type="number" inputmode="numeric" min="0" max="999" step="1" class="campo w-16 text-center">` `[+]`, en una fila `inline-flex items-center gap-1`; botones `btn-accion min-h-toque` con `aria-label` "Restar uno" / "Sumar uno"; el input con `aria-label` "Cantidad de <descripción>" (`:aria-label`). El input NO usa `x-model`: `:value="linea.cantidad"` y `@change="cambiarCantidad(linea, $event.target)"` (también Enter vía `@keydown.enter.prevent="$event.target.blur()"`). `+` deshabilitado con `!ventaLogica.puedeSumar(linea)` y `title` "Sin más stock" en ese caso.
- Métodos del componente:

```js
      async cambiarCantidad(linea, campo) {
        const cantidad = L.cantidadValida(campo.value);
        if (cantidad === null || cantidad === linea.cantidad) { campo.value = linea.cantidad; return; }
        const ok = await this._fijarCantidad(linea, cantidad);
        if (!ok) campo.value = linea.cantidad;   // rechazada (ej. stock): vuelve a la de la API
      },
      sumar(linea, delta) { return this._fijarCantidad(linea, linea.cantidad + delta); },
      quitarLinea(linea) { return this._fijarCantidad(linea, 0); },
      _fijarCantidad(linea, cantidad) {
        return this.accion(window.pedir(`${API}/${this.venta.id}/items/${linea.item_id}/cantidad`,
                                        { method: 'PUT', body: { cantidad } }));
      },
```

  `−` con cantidad 1 quita la línea (misma llamada con 0). "Quitar" de acciones → `quitarLinea(linea)`. "Descuento" → `abrirDescuento(linea)` (el modal usa `linea.item_id`, `linea.descripcion`, `linea.motivo`, `linea.descuento_item`; en `aplicarDescuento` mandar `item_id: this.descuento.linea.item_id`). Visible con `puedeDescontarLinea`.
- `_agregar` ya devuelve la `VentaResponse` (Task 1): sin aviso.
- `puedeConfirmar`/`puedeOtroMedio` siguen usando `items` (unidades): sin cambios.
- Mobile: la tabla sigue en `overflow-x-auto`; la celda de cantidad con `whitespace-nowrap`.

- [ ] **Step 3: Descuento general (sección nueva del resumen, después de "Promoción")**

Visible con `x-show="items.length && puedeDescontar"`. Contenido:
- Título "Descuento general".
- Si `Number(venta.descuento_general) > 0`: texto `'− ' + plata(venta.descuento_general) + ' (' + pct + ' %)'` (pct con `porcentajeDescuentoGeneral`, formateado con coma) y botón "Quitar" (`quitarDescuentoGeneral()`).
- Formulario en fila (`flex flex-wrap gap-2`): select `descuentoGeneral.modo` con opciones "Total final ($)" (`total`, por defecto) y "Porcentaje (%)" (`porcentaje`); input `descuentoGeneral.valor` (`type="number" min="0" step="0.01" inputmode="decimal"`, placeholder según el modo: "Ej. 80" / "Ej. 10"); botón "Aplicar" (`aplicarDescuentoGeneral()`, `boton boton-secundario min-h-toque`). Cada control con su `<label>` (visible o `sr-only`).

```js
      descuentoGeneral: { modo: 'total', valor: '' },
      async aplicarDescuentoGeneral() {
        const cuerpo = L.cuerpoDescuentoGeneral(this.descuentoGeneral.modo, this.descuentoGeneral.valor);
        if (!cuerpo) { window.toast('Escribí el total final o el porcentaje.', 'error'); return; }
        const ok = await this.accion(window.pedir(`${API}/${this.venta.id}/descuento-general`, { method: 'POST', body: cuerpo }));
        if (ok) this.descuentoGeneral.valor = '';
      },
      quitarDescuentoGeneral() {
        return this.accion(window.pedir(`${API}/${this.venta.id}/descuento-general`,
                                        { method: 'POST', body: { porcentaje: null, total: null } }));
      },
```

En los totales, entre "Descuentos y promociones" y "Recargo", una fila informativa `x-show="venta && Number(venta.descuento_general) > 0"`: "de los cuales, descuento general" / `'− ' + plata(venta.descuento_general)` (text-sm text-texto-muted): el descuento general YA está dentro de `descuento_total`, no se resta dos veces.

Cuando el carrito cambia, la API borra el descuento general: la pantalla lo refleja sola (muestra la respuesta).

- [ ] **Step 4: Test de página y verificación**

En `backend/tests/test_paginas_ventas.py`: la pantalla `/ventas/nueva` de un usuario con `venta.descuento` contiene "Descuento general" y 'aria-label="Sumar uno"'; uno sin el recurso no ve "Descuento general" (seguir el patrón de los tests existentes de esa página; si la sección se oculta con `x-show` y no con Jinja, gatearla con `{% if puede_descontar %}` para que el test sea posible).

```bash
node --check backend/app/static/js/venta.js
node --test backend/tests_js/
docker compose exec -T backend pytest -p no:warnings -q; echo exit=$?
git add backend/app/templates/pages/ventas/nueva.html backend/app/static/js/venta.js \
  backend/tests_js/venta.test.mjs backend/tests/test_paginas_ventas.py
git commit -m "feat(ventas): carrito por líneas con cantidad y descuento general en la pantalla de venta

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Productos — precio manual, redondeo visible y fotos al editar

**Revisión:** CON revisor (cálculo de precios).

**Files:**
- Modify: `backend/app/services/productos.py`, `backend/app/schemas/productos.py`, `backend/app/api/v1/productos.py`
- Modify: `backend/app/templates/components/producto_form.html`, `backend/app/static/js/producto_form.js`, `backend/app/templates/pages/productos/_modal_ficha.html`, `backend/app/static/js/productos.js`, `backend/app/templates/pages/productos/listado.html` (script nuevo)
- Create: `backend/app/templates/components/fotos_producto.html`, `backend/app/static/js/fotos_producto.js`
- Test: `backend/tests/test_productos.py`, `backend/tests/test_productos_api.py`, `backend/tests_js/producto_form.test.mjs`, `backend/tests/test_paginas_productos.py`

- [ ] **Step 1: Tests de backend**

En `backend/tests/test_productos.py` (con sus fixtures; leerlas):
- Alta con `precio_venta="1500"`, costo 1000 en pesos → `precio_venta == 1500.00` exacto (aunque el redondeo configurado sea otro) y `margen == 50.00`.
- Alta con proveedor en dólares (dólar 1000), costo 2, `precio_venta=2500` → margen 25.00.
- Precio menor al costo → `DatoInvalido` ("no puede ser menor al costo"); margen resultante > 1000 → `DatoInvalido`.
- `margen` y `precio_venta` a la vez → 422 (schema) en el test de API.
- Edición con `precio_venta` → precio exacto y margen recalculado; edición con `margen` y costo nuevo → recalcula con la fórmula (como hoy).
- Un precio manual y después un cambio de dólar del proveedor → el precio se recalcula con el margen guardado y el redondeo (documenta la regla; usar `recalcular_precios_de_proveedor` o el service de cambio de dólar).

En `backend/tests/test_productos_api.py`:
- `GET /productos/precio-preview?proveedor_id=..&costo=1000&margen=50` → incluye `margen: "50.00"`, `redondeo`, `redondeado: true`.
- `…&costo=1000&precio_venta=1500` → `precio_venta: "1500.00"`, `margen: "50.00"`, `redondeado: false`.
- Sin margen ni precio, o con los dos → 422.

- [ ] **Step 2: Backend**

Service:

```python
MARGEN_MAXIMO = Decimal("1000")


def margen_desde_precio(costo, precio, proveedor: Proveedor) -> Decimal:
    """Margen % que lleva el costo (en pesos, con el dólar actual) al precio
    cargado a mano. El precio se respeta exacto (decisión del usuario)."""
    factor = proveedor.dolar_actual if proveedor.en_dolares else Decimal("1")
    costo_pesos = Decimal(costo) * factor
    margen = redondear((Decimal(precio) / costo_pesos - 1) * 100)
    if margen < 0:
        raise DatoInvalido(f"El precio de venta no puede ser menor al costo (${redondear(costo_pesos)}).")
    if margen > MARGEN_MAXIMO:
        raise DatoInvalido("El margen resultante supera el 1000 %.")
    return margen
```

- `crear_producto`: si `datos.precio_venta is not None` → `precio = redondear(datos.precio_venta)`, `margen = margen_desde_precio(costo, precio, proveedor)`; si no, como hoy.
- `editar_producto`: si `datos.precio_venta is not None` → precio exacto y margen calculado; si no, `margen = redondear(datos.margen)` y la lógica actual (recalcula si cambió costo o margen).
- `precio_preview(db, proveedor_id, costo, margen=None, precio_venta=None)` devuelve además `margen`, `redondeo` (de la configuración) y `redondeado` (False con precio manual).

Schemas: `ProductoCrear.precio_venta: Decimal | None = Field(default=None, gt=0, lt=Decimal("100000000"), decimal_places=2)` + `model_validator(mode="after")` que rechace margen y precio a la vez; `ProductoEditar.margen` pasa a `Decimal | None = None`, suma `precio_venta` igual, y el validador exige EXACTAMENTE uno de los dos. `PrecioPreview` suma `margen: Decimal`, `redondeo: Decimal`, `redondeado: bool`.

Router `precio-preview`: `margen: Decimal | None = Query(None, ge=0, le=1000)`, `precio_venta: Decimal | None = Query(None, gt=0, lt=PRECIO_MAXIMO)`; 422 (`HTTPException` no: levantar `NoProcesable` de `core/errores.py`) si no viene exactamente uno.

- [ ] **Step 3: Formulario (margen ↔ precio + redondeo)**

`producto_form.html`: el bloque "Precio de venta" pasa a ser un input editable (`id="pf-precio"`, `type="number" min="0.01" step="0.01" inputmode="decimal"`, `x-model="form.precio_venta"`, `@input.debounce.300ms="alEditarPrecio()"`), y el de margen llama `alEditarMargen()`. Debajo del precio: `<p class="text-sm text-texto-muted" x-show="redondeoTexto" x-text="redondeoTexto"></p>`; y la línea del dólar como hoy.

`producto_form.js`:
- Estado `modoPrecio: 'margen' | 'precio'` (el último campo que tocó el usuario; `'margen'` al abrir), `form.precio_venta` (alta: vacío; edición: el precio guardado), `redondeo` y `redondeado` de la última preview.
- `alEditarMargen()` → `modoPrecio = 'margen'` y preview con `margen` → escribe `form.precio_venta` con el precio devuelto.
- `alEditarPrecio()` → `modoPrecio = 'precio'` y preview con `precio_venta` → escribe `form.margen` con el margen devuelto.
- Cambiar el costo → preview según `modoPrecio` (con precio manual, recalcula el margen; con margen, recalcula el precio).
- Guardar: manda `margen` (y `precio_venta: null`) si `modoPrecio === 'margen'`, o `precio_venta` (y `margen: null`) si es `'precio'`.
- Lógica pura testeable (en un objeto exportado como hacen los otros JS con tests, p. ej. `window.productoFormLogica`): `paramsPreview(form, modo)` y `cuerpoPrecio(form, modo)` y `textoRedondeo(redondeo, redondeado)` → `'Redondeado hacia arriba a múltiplos de $ 1.000'` o `''` (sin redondeo o precio manual). Tests en `tests_js/producto_form.test.mjs`.

- [ ] **Step 4: Fotos reutilizables**

- `static/js/fotos_producto.js`: `window.fotosProducto = function ({ productoId, fotos, alCambiar })` — componente con `fotos` (lista), `puedeSubir` (`fotos.length < 5`) y los métodos que hoy viven en la ficha de `productos.js`: `subirFoto(archivo)`, `capturarFoto(camara)`, `marcarPrincipal(f)`, `borrarFoto(f)` (con `window.confirmar`), más `recargar()` (GET `/api/v1/productos/{id}` → `fotos`) y `alCambiar()` opcional al terminar cada cambio (la ficha lo usa para refrescar el listado). MOVER esos métodos (no copiarlos): `productos.js` deja de tenerlos.
- `components/fotos_producto.html`: macro `fotos_producto(producto_id_expr, fotos_expr, puede_editar_expr, vigilar_expr, al_cambiar="")` con el markup que hoy está en `_modal_ficha.html` (grilla de miniaturas, "Principal", "Marcar principal", "Borrar", "Subir foto", "Tomar foto" con `webcamCapture`), dentro de un `x-data="fotosProducto({...})"` propio. Los textos y clases actuales se conservan.
- `_modal_ficha.html` usa la macro (mismo resultado visual).
- `producto_form.html`: en modo edición (`x-if="form.id"`), una sección "Fotos" con la macro y la aclaración "Las fotos se guardan al instante." (solo si `puede_editar`).
- `listado.html` carga `fotos_producto.js` antes de `productos.js`.

- [ ] **Step 5: Tests de página, verificación y commit**

En `backend/tests/test_paginas_productos.py`: `/productos` incluye `/static/js/fotos_producto.js` y el id `pf-precio`.

```bash
node --check backend/app/static/js/producto_form.js backend/app/static/js/fotos_producto.js backend/app/static/js/productos.js
node --test backend/tests_js/
docker compose exec -T backend pytest -p no:warnings -q; echo exit=$?
git add backend/app/services/productos.py backend/app/schemas/productos.py backend/app/api/v1/productos.py \
  backend/app/templates backend/app/static/js backend/tests backend/tests_js
git commit -m "feat(productos): precio de venta manual, redondeo visible y fotos al editar

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Cierre (lo hace el controlador)

1. Revisión final completa con Opus.
2. Una tanda de correcciones; docs (plan, spec, pendientes) en un commit aparte.
3. Actualizar `backend/scripts/datos_demo.py` si algo del flujo de venta cambió su uso (agregar_item ya no devuelve tupla).
4. Merge a `dev` cuando el usuario lo pida.
