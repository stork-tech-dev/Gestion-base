# Tablero de inicio — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convertir `/` en un tablero con cuatro bloques (Caja, Ventas de hoy, Accesos rápidos, Stock bajo el mínimo), cada uno visible según el permiso de quien entra.

**Architecture:** Sin endpoint nuevo: `pages.py::inicio` decide con `resolver_permiso` qué bloques renderizar y arma los accesos rápidos; cada bloque es un componente Alpine (`static/js/inicio.js`) que pide a una API existente. `/stock` acepta `?solo_bajo_minimo=1` para el link "Ver todos".

**Tech Stack:** FastAPI + Jinja2, Alpine.js 3, Tailwind CDN, pytest, `node --test`.

**Spec:** `docs/superpowers/specs/2026-09-29-inicio-tablero-design.md` + `CLAUDE.md`.

## Global Constraints

- Código, textos y comentarios en español (voseo en la UI).
- **Git:** rama local `inicio-tablero` (ya creada desde `dev`). UN commit: `feat(inicio): tablero de inicio con caja, ventas de hoy, accesos y stock bajo el mínimo` + línea en blanco + EXACTAMENTE `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. NUNCA push, amend, reset, rebase, merge ni checkout. Nunca commitear `.env`, `uploads/`, `backups/`, `.superpowers/`, `docs/`.
- **NUNCA crear usuarios ni datos en la base de desarrollo:** verificar con tests y sus fixtures.
- Carpeta en iCloud: si git o lecturas se cuelgan, `find . -flags +dataless -type f -print0 | xargs -0 -n 20 -P 8 cat > /dev/null` y reintentar.
- Tests Python en el contenedor (`docker compose exec -T backend pytest -p no:warnings -q`; el resumen puede no imprimirse: verificar `echo $?`). JS: `node --check` y `node --test backend/tests_js/`.
- Pantallas: valores del servidor a Alpine solo con `|js` en atributos; sin `x-html`; `x-text` para todo dato de la API; mobile-first; áreas de toque de 44px (`min-h-toque`); reusar clases existentes (`tarjeta`, `tarjeta-enlace`, `boton`, `boton-primario`).
- El test existente `tests/test_pages.py::test_inicio_renderiza_layout_y_saludo` exige que "Auditoría" NO aparezca en el HTML de `/` y que siga "Bienvenido, Ana": no romperlo.

---

### Task 1: Tablero de inicio

**Revisión:** sin revisor por tarea (no toca dinero ni permisos nuevos); la cubre la revisión final.

**Files:**
- Modify: `backend/app/api/pages.py` (helper `_con_venta_en_curso`, `ACCESOS_INICIO`, rutas `/` y `/stock`)
- Modify: `backend/app/templates/pages/index.html`
- Modify: `backend/app/templates/pages/stock/listado.html` (x-data)
- Modify: `backend/app/static/js/stock.js` (parámetro `soloBajoMinimoInicial`)
- Create: `backend/app/static/js/inicio.js`
- Test: `backend/tests/test_paginas_inicio.py`, `backend/tests_js/inicio.test.mjs`

**Interfaces (existentes, no cambian):**
- `GET /api/v1/turnos/activo` → `TurnoResponse | null` con `id, estado, efectivo_apertura, fecha_apertura, es_de_dia_anterior, usuario_apertura_nombre, usuarios: [...]`.
- `GET /api/v1/reportes/ventas-periodo?desde=AAAA-MM-DD&hasta=AAAA-MM-DD` → `ReporteResponse`; se usa `totales` (`total`, `ventas`, `ticket_promedio`, `anuladas`, `anuladas_monto`).
- `GET /api/v1/stock/alertas?limite=5` → `list[StockResponse]` (`producto_id, codigo, descripcion, stock, stock_minimo, …`).
- `app.js`: `window.pedir(url)` (devuelve el JSON; `null` si la API devuelve null), `window.pesos`, `window.fechaHora`, `window.fecha`.

- [ ] **Step 1: Tests de página `backend/tests/test_paginas_inicio.py`**

```python
"""Tablero de inicio (/): cada bloque se renderiza solo con su permiso; los
datos los carga cada bloque desde su API (inicio.js)."""
from app.models import Rol
from app.services import ventas as servicio_ventas
from tests.fabricas import abrir_turno_de_test


def _html(iniciar_sesion, usuario):
    r = iniciar_sesion(usuario).get("/")
    assert r.status_code == 200
    return r.text


def test_admin_ve_los_tres_bloques_y_los_accesos(crear_usuario, iniciar_sesion):
    html = _html(iniciar_sesion, crear_usuario("admin", nombre="Ana"))
    assert "Bienvenido, Ana" in html and "/static/js/inicio.js" in html
    assert 'id="inicio-caja"' in html and 'id="inicio-ventas"' in html and 'id="inicio-stock"' in html
    for url in ("/ventas/nueva", "/productos", "/gestion-de-stock", "/caja"):
        assert f'href="{url}"' in html
    assert 'href="/stock?solo_bajo_minimo=1"' in html
    assert 'href="/reportes/ventas-periodo"' in html


def test_vendedor_no_ve_ventas_de_hoy(crear_usuario, iniciar_sesion):
    # El vendedor no tiene REPORTES ver (seed.sql): la tarjeta ni se renderiza.
    html = _html(iniciar_sesion, crear_usuario("vendedor"))
    assert 'id="inicio-caja"' in html and 'id="inicio-stock"' in html
    assert 'id="inicio-ventas"' not in html
    assert 'href="/ventas/nueva"' in html


def test_rol_sin_permisos_solo_ve_el_saludo(db, crear_usuario, iniciar_sesion):
    rol = Rol(nombre="sin permisos inicio", es_sistema=False)
    db.add(rol)
    db.flush()
    html = _html(iniciar_sesion, crear_usuario(rol, nombre="Beto"))
    assert "Bienvenido, Beto" in html
    assert 'id="inicio-caja"' not in html and 'id="inicio-ventas"' not in html and 'id="inicio-stock"' not in html
    assert 'aria-label="Accesos rápidos"' not in html


def test_acceso_continuar_venta_si_hay_una_en_curso(db, crear_usuario, iniciar_sesion):
    vendedor = crear_usuario("vendedor")
    abrir_turno_de_test(db, crear_usuario("admin"))
    venta = servicio_ventas.iniciar_venta(db, vendedor, None)
    html = _html(iniciar_sesion, vendedor)
    assert f"Continuar venta {venta.numero}" in html


def test_stock_con_filtro_bajo_minimo_desde_el_link(crear_usuario, iniciar_sesion):
    cliente = iniciar_sesion(crear_usuario("admin"))
    assert "soloBajoMinimoInicial: true" in cliente.get("/stock?solo_bajo_minimo=1").text
    assert "soloBajoMinimoInicial: false" in cliente.get("/stock").text
```

Run: `docker compose exec -T backend pytest -p no:warnings tests/test_paginas_inicio.py -q`
Expected: FAIL.

Nota: si `iniciar_venta` exige otra firma, mirarla en `app/services/ventas.py` (los tests de `tests/test_anulacion.py` la usan como `servicio.iniciar_venta(db, autor, None)` con un turno abierto).

- [ ] **Step 2: `backend/app/api/pages.py`**

a) Después de `SECCIONES_VENTAS` (definido junto a `SECCION_NUEVA_VENTA`), agregar el helper y reemplazar la lógica equivalente de `ventas_hub`:

```python
def _con_venta_en_curso(secciones: list[dict], en_curso) -> list[dict]:
    """"Nueva venta" pasa a "Continuar venta V-…" si el usuario tiene una en
    curso. Devuelve copias: las constantes las comparten sidebar y páginas."""
    if en_curso is None:
        return secciones
    return [{**s, "nombre": f"Continuar venta {en_curso.numero}"} if s["url"] == SECCION_NUEVA_VENTA["url"] else s
            for s in secciones]
```

`ventas_hub` queda:

```python
    secciones = _con_venta_en_curso(menu_visible(SECCIONES_VENTAS, usuario, db),
                                    servicio_ventas.venta_en_curso(db, usuario))
    return _pagina(request, "pages/ventas/hub.html", _contexto_ventas(request, db, usuario, secciones=secciones))
```

b) Después de `PAGINA_CERRAR_TURNO` (o de la sección de reportes, antes de `MENU_SIDEBAR`), los accesos rápidos:

```python
# Accesos rápidos del inicio: mismas constantes (y permisos) que sidebar y hubs.
ACCESOS_INICIO: list[dict] = [
    {**SECCION_NUEVA_VENTA, "icono": "ventas"},
    PAGINA_PRODUCTOS,
    PAGINA_STOCK_HUB,
    PAGINA_CAJA,
]
```

c) Ruta `/`:

```python
@router.get("/")
def inicio(request: Request, db: Session = Depends(get_db), usuario: Usuario = Depends(requiere_sesion)):
    """Tablero: cada bloque se renderiza solo si el usuario puede pedir su API
    (misma barrera, así nunca hay 403) y carga sus datos por su cuenta (inicio.js)."""
    accesos = _con_venta_en_curso(menu_visible(ACCESOS_INICIO, usuario, db),
                                  servicio_ventas.venta_en_curso(db, usuario))
    return _pagina(request, "pages/index.html", contexto_base(
        request, db, "/", usuario,
        accesos=accesos,
        ver_caja=resolver_permiso(db, usuario.id, Modulo.CAJA, "ver"),
        puede_cerrar_turno=resolver_permiso(db, usuario.id, Modulo.CAJA, "crear", Recurso.CAJA_ARQUEO),
        ver_ventas_hoy=resolver_permiso(db, usuario.id, Modulo.REPORTES, "ver"),
        ver_stock=resolver_permiso(db, usuario.id, Modulo.STOCK, "ver"),
        hoy_iso=ahora_db().date().isoformat(),
    ))
```

Nota: `ACCESOS_INICIO` usa `PAGINA_PRODUCTOS`, `PAGINA_STOCK_HUB` y `PAGINA_CAJA`, que deben estar definidas antes (están arriba de `MENU_SIDEBAR`); ubicar la constante donde todas ya existan.

d) Ruta `/stock`: aceptar el filtro inicial (un link, no un filtro que persista):

```python
@router.get("/stock")
def stock(request: Request, solo_bajo_minimo: bool = False, db: Session = Depends(get_db),
          usuario: Usuario = Depends(requiere_pagina(SECCION_STOCK, actual="/gestion-de-stock"))):
    # `solo_bajo_minimo` llega del link "Ver todos" del inicio: tilda el filtro al entrar.
    return _pagina(request, "pages/stock/listado.html",
                   _contexto_stock(request, db, usuario, solo_bajo_minimo_inicial=solo_bajo_minimo))
```

- [ ] **Step 3: `stock/listado.html` y `stock.js`**

En `backend/app/templates/pages/stock/listado.html`, el `x-data` suma el parámetro:

```html
<div x-data="stockListado({ puedeIngresar: {{ puede_ingresar|js }}, puedeMinimos: {{ puede_minimos|js }}, puedeBaja: {{ puede_baja|js }}, soloBajoMinimoInicial: {{ solo_bajo_minimo_inicial|default(false)|js }} })">
```

En `backend/app/static/js/stock.js`:

```js
  window.stockListado = function ({ puedeIngresar, puedeMinimos, puedeBaja, soloBajoMinimoInicial = false }) {
```

y el estado inicial de los filtros:

```js
      filtros: { ...filtrosVacios(), solo_bajo_minimo: !!soloBajoMinimoInicial },
```

(`limpiarFiltros()` sigue volviendo a `filtrosVacios()`: el filtro del link no persiste.)

- [ ] **Step 4: `backend/app/templates/pages/index.html`**

```html
{% extends "base.html" %}
{% from "components/icons.html" import icono %}
{% block contenido %}
<h1 class="text-2xl font-black text-welcome">Bienvenido{% if usuario_actual %}, {{ usuario_actual.nombre.split()[0] }}{% endif %}</h1>

{# Tablero de inicio: cada bloque se renderiza solo con su permiso (pages.py)
   y carga sus datos por su cuenta (static/js/inicio.js). #}
{% if accesos %}
<nav aria-label="Accesos rápidos" class="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
  {% for a in accesos %}
  <a href="{{ a.url }}" class="tarjeta tarjeta-enlace flex min-h-toque flex-col items-center justify-center gap-2 text-center font-semibold text-texto-header">
    {{ icono(a.icono, "w-6 h-6 text-primary") }}<span>{{ a.nombre }}</span>
  </a>
  {% endfor %}
</nav>
{% endif %}

<div class="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-2">
  {% if ver_caja %}
  <section class="tarjeta flex flex-col gap-3" aria-labelledby="inicio-caja" x-data="inicioCaja()">
    <div class="flex items-center justify-between gap-2">
      <h2 id="inicio-caja" class="text-lg font-semibold text-texto-header">Caja</h2>
      <a href="/caja" class="text-sm font-medium text-primary hover:underline">Ir a Caja</a>
    </div>
    <p x-show="cargando" class="text-sm text-texto-muted">Cargando…</p>
    <p x-show="error" x-cloak class="text-sm text-danger">No se pudo cargar.</p>
    <template x-if="!cargando && !error && estado === 'sin_turno'">
      <div class="flex flex-col gap-3">
        <p class="text-texto-muted">No hay un turno abierto.</p>
        <a href="/caja" class="boton boton-primario min-h-toque self-start">Iniciar turno</a>
      </div>
    </template>
    <template x-if="!cargando && estado === 'dia_anterior'">
      <p class="rounded-input bg-danger/10 p-3 text-sm text-danger">
        Hay un turno del <span x-text="fecha(turno.fecha_apertura)"></span> sin cerrar: no se puede vender hasta cerrarlo.
        {% if puede_cerrar_turno %}<a :href="`/caja/cerrar/${turno.id}`" class="font-semibold underline">Cerrar turno</a>{% endif %}
      </p>
    </template>
    <template x-if="!cargando && estado === 'abierto'">
      <dl class="grid grid-cols-2 gap-3 text-sm">
        <div><dt class="text-texto-muted">Abierto</dt><dd class="font-medium text-texto-header" x-text="fechaHora(turno.fecha_apertura)"></dd></div>
        <div><dt class="text-texto-muted">Por</dt><dd class="font-medium text-texto-header" x-text="turno.usuario_apertura_nombre"></dd></div>
        <div><dt class="text-texto-muted">Efectivo inicial</dt><dd class="font-medium text-texto-header" x-text="'$ ' + pesos(turno.efectivo_apertura)"></dd></div>
        <div><dt class="text-texto-muted">En el turno</dt><dd class="font-medium text-texto-header" x-text="turno.usuarios.length"></dd></div>
      </dl>
    </template>
  </section>
  {% endif %}

  {% if ver_ventas_hoy %}
  <section class="tarjeta flex flex-col gap-3" aria-labelledby="inicio-ventas" x-data="inicioVentasHoy({ hoyIso: {{ hoy_iso|js }} })">
    <div class="flex items-center justify-between gap-2">
      <h2 id="inicio-ventas" class="text-lg font-semibold text-texto-header">Ventas de hoy</h2>
      <a href="/reportes/ventas-periodo" class="text-sm font-medium text-primary hover:underline">Ver reporte</a>
    </div>
    <p x-show="cargando" class="text-sm text-texto-muted">Cargando…</p>
    <p x-show="error" x-cloak class="text-sm text-danger">No se pudo cargar.</p>
    <template x-if="!cargando && totales">
      <dl class="grid grid-cols-2 gap-3">
        <div><dt class="text-sm text-texto-muted">Total vendido</dt><dd class="text-xl font-bold text-texto-header" x-text="'$ ' + pesos(totales.total)"></dd></div>
        <div><dt class="text-sm text-texto-muted">Ventas</dt><dd class="text-xl font-bold text-texto-header" x-text="totales.ventas"></dd></div>
        <div><dt class="text-sm text-texto-muted">Ticket promedio</dt><dd class="text-xl font-bold text-texto-header" x-text="'$ ' + pesos(totales.ticket_promedio)"></dd></div>
        <div><dt class="text-sm text-texto-muted">Anuladas</dt><dd class="text-xl font-bold text-texto-header" x-text="textoAnuladas(totales)"></dd></div>
      </dl>
    </template>
  </section>
  {% endif %}

  {% if ver_stock %}
  <section class="tarjeta flex flex-col gap-3" aria-labelledby="inicio-stock" x-data="inicioStock()">
    <div class="flex items-center justify-between gap-2">
      <h2 id="inicio-stock" class="text-lg font-semibold text-texto-header">Stock bajo el mínimo</h2>
      <a href="/stock?solo_bajo_minimo=1" class="text-sm font-medium text-primary hover:underline">Ver todos</a>
    </div>
    <p x-show="cargando" class="text-sm text-texto-muted">Cargando…</p>
    <p x-show="error" x-cloak class="text-sm text-danger">No se pudo cargar.</p>
    <p x-show="!cargando && !error && !productos.length" x-cloak class="text-sm text-texto-muted">Todo el stock está por encima del mínimo.</p>
    <ul x-show="productos.length" x-cloak class="flex flex-col divide-y divide-borde">
      <template x-for="p in productos" :key="p.producto_id">
        <li class="flex items-center justify-between gap-3 py-2 text-sm">
          <span class="min-w-0 truncate"><span class="font-mono text-texto-muted" x-text="p.codigo"></span> <span x-text="p.descripcion"></span></span>
          <span class="shrink-0 font-semibold text-danger" x-text="p.stock + ' / mín. ' + p.stock_minimo"></span>
        </li>
      </template>
    </ul>
  </section>
  {% endif %}
</div>
{% endblock %}
{% block scripts %}<script src="{{ estatico('/js/inicio.js') }}"></script>{% endblock %}
```

(Verificar que `base.html` tenga `{% block scripts %}` —lo usan las otras páginas— y que los íconos `ventas`, `productos`, `stock`, `caja` existan en `components/icons.html`: existen.)

- [ ] **Step 5: Tests JS `backend/tests_js/inicio.test.mjs`**

```js
// Tests del tablero de inicio (backend/app/static/js/inicio.js): lógica pura
// y carga independiente de cada bloque. Mismos stubs mínimos que
// ventas.test.mjs. Correr con: node --test backend/tests_js/
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const RUTA_APP = new URL('../app/static/js/app.js', import.meta.url);
const RUTA_INICIO = new URL('../app/static/js/inicio.js', import.meta.url);

function cargar() {
  const document = {
    addEventListener: () => {},
    documentElement: { classList: { contains: () => false } },
    createElement: () => ({}),
  };
  const window = {
    document,
    addEventListener: () => {},
    dispatchEvent: () => {},
    localStorage: {},
    fetch: () => Promise.resolve({ status: 204 }),
  };
  const contexto = {
    window,
    document,
    CustomEvent: function CustomEvent(tipo, opciones) { this.type = tipo; this.detail = opciones && opciones.detail; },
    Event: function Event(tipo) { this.type = tipo; },
    URLSearchParams,
    fetch: () => Promise.reject(new Error('sin red')),
    setTimeout: () => 0,
    clearTimeout: () => {},
  };
  vm.runInNewContext(readFileSync(RUTA_APP, 'utf8'), contexto);
  vm.runInNewContext(readFileSync(RUTA_INICIO, 'utf8'), contexto);
  return window;
}

test('estado de la caja: sin turno, abierto hoy o de un día anterior', () => {
  const L = cargar().inicioLogica;
  assert.equal(L.estadoCaja(null), 'sin_turno');
  assert.equal(L.estadoCaja({ es_de_dia_anterior: false }), 'abierto');
  assert.equal(L.estadoCaja({ es_de_dia_anterior: true }), 'dia_anterior');
});

test('anuladas: "Ninguna" o cantidad y monto', () => {
  const L = cargar().inicioLogica;
  assert.equal(L.textoAnuladas({ anuladas: 0, anuladas_monto: '0.00' }), 'Ninguna');
  assert.equal(L.textoAnuladas({ anuladas: 2, anuladas_monto: '3500.00' }), '2 · $ 3.500');
});

test('ventas de hoy pide el reporte con desde y hasta = hoy y toma los totales', async () => {
  const window = cargar();
  const pedidos = [];
  window.pedir = async (url) => { pedidos.push(url); return { totales: { total: '100.00', ventas: 1 } }; };
  const bloque = window.inicioVentasHoy({ hoyIso: '2026-09-29' });
  await bloque.init();
  assert.deepEqual(pedidos, ['/api/v1/reportes/ventas-periodo?desde=2026-09-29&hasta=2026-09-29']);
  assert.equal(bloque.totales.total, '100.00');
  assert.equal(bloque.cargando, false);
  assert.equal(bloque.error, false);
});

test('un bloque que falla marca error sin tirar excepción', async () => {
  const window = cargar();
  window.pedir = async () => { throw new Error('500'); };
  const bloque = window.inicioStock();
  await bloque.init();
  assert.equal(bloque.error, true);
  assert.equal(bloque.cargando, false);
  assert.equal(bloque.productos.length, 0);
});

test('caja y stock piden sus APIs existentes', async () => {
  const window = cargar();
  const pedidos = [];
  window.pedir = async (url) => { pedidos.push(url); return url.includes('turnos') ? null : [{ producto_id: 1 }]; };
  const caja = window.inicioCaja();
  const stock = window.inicioStock();
  await caja.init();
  await stock.init();
  assert.deepEqual(pedidos, ['/api/v1/turnos/activo', '/api/v1/stock/alertas?limite=5']);
  assert.equal(caja.turno, null);
  assert.equal(caja.estado, 'sin_turno');
  assert.equal(stock.productos.length, 1);
});
```

Run: `node --test backend/tests_js/`
Expected: FAIL (no existe `inicio.js`).

- [ ] **Step 6: `backend/app/static/js/inicio.js`**

```js
/* Tablero de inicio (/): un componente Alpine por bloque. Cada uno pide su
   API existente por su cuenta (si uno falla, los demás se ven igual) y solo
   se renderiza si el usuario tiene el permiso de esa API (pages.py). */
(function () {
  'use strict';

  const ALERTAS_STOCK = 5;

  // ---------- Lógica pura (testeada con node --test en tests_js/inicio.test.mjs) ----------
  window.inicioLogica = {
    // Qué muestra la tarjeta de Caja según GET /api/v1/turnos/activo.
    estadoCaja: (turno) => {
      if (!turno) return 'sin_turno';
      return turno.es_de_dia_anterior ? 'dia_anterior' : 'abierto';
    },
    // Anuladas de hoy: "Ninguna" o "2 · $ 3.500".
    textoAnuladas: (totales) => (Number(totales.anuladas)
      ? `${totales.anuladas} · $ ${window.pesos(totales.anuladas_monto)}`
      : 'Ninguna'),
  };
  const L = window.inicioLogica;

  // Estado y carga comunes a todos los bloques. Sin toast: un error se
  // muestra adentro de su tarjeta ("No se pudo cargar.").
  function bloque(url, alCargar) {
    return {
      cargando: true,
      error: false,
      async init() {
        try {
          alCargar.call(this, await window.pedir(url));
        } catch (e) {
          this.error = true;
        } finally {
          this.cargando = false;
        }
      },
    };
  }

  window.inicioCaja = () => ({
    turno: null,
    get estado() { return L.estadoCaja(this.turno); },
    ...bloque('/api/v1/turnos/activo', function (turno) { this.turno = turno; }),
  });

  window.inicioVentasHoy = ({ hoyIso }) => ({
    totales: null,
    textoAnuladas: L.textoAnuladas,
    ...bloque(`/api/v1/reportes/ventas-periodo?${new URLSearchParams({ desde: hoyIso, hasta: hoyIso })}`,
      function (reporte) { this.totales = reporte.totales; }),
  });

  window.inicioStock = () => ({
    productos: [],
    ...bloque(`/api/v1/stock/alertas?limite=${ALERTAS_STOCK}`, function (lista) { this.productos = lista; }),
  });
})();
```

Nota sobre el spread: `{ get estado() {...}, ...bloque(...) }` copia `init`, `cargando` y `error` como propiedades propias; el getter queda definido en el literal (no se pisa porque `bloque` no tiene `estado`). Alpine llama a `init()` con `this` = el componente reactivo.

- [ ] **Step 7: Correr, verificar y commitear**

```bash
node --check backend/app/static/js/inicio.js && node --check backend/app/static/js/stock.js
node --test backend/tests_js/
docker compose exec -T backend pytest -p no:warnings tests/test_paginas_inicio.py tests/test_pages.py tests/test_paginas_stock.py tests/test_paginas_ventas.py -q; echo exit=$?
docker compose exec -T backend pytest -p no:warnings -q; echo exit=$?
```
Expected: todo en verde (exit=0).

```bash
git add backend/app/api/pages.py backend/app/templates/pages/index.html backend/app/templates/pages/stock/listado.html \
  backend/app/static/js/stock.js backend/app/static/js/inicio.js backend/tests/test_paginas_inicio.py backend/tests_js/inicio.test.mjs
git commit -m "feat(inicio): tablero de inicio con caja, ventas de hoy, accesos y stock bajo el mínimo

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Cierre (lo hace el controlador)

1. Revisión final completa con Opus sobre `git diff dev...inicio-tablero`.
2. Una sola tanda de correcciones si hace falta.
3. Commit de docs (este plan + spec) y merge a `dev` cuando el usuario lo pida.
