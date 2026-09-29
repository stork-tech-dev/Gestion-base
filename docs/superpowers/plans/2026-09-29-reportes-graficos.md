# Gráficos en reportes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un gráfico (línea o barras, una serie) arriba de la tabla en cada reporte de `/reportes/{clave}`, con Chart.js y los mismos datos de la API.

**Architecture:** Cada `DefinicionReporte` declara `grafico(filtros) -> Grafico` (qué columnas graficar); el motor lo incluye en la respuesta JSON; `reporte.js` arma los datos con una función pura (`datosGrafico`) y dibuja con Chart.js. Excel, PDF y endpoints no cambian.

**Tech Stack:** FastAPI, Pydantic 2, Jinja2, Alpine.js 3, Chart.js 4.4.4 (CDN jsdelivr, versión fija), pytest, `node --test`.

**Spec:** `docs/superpowers/specs/2026-09-29-reportes-graficos-design.md` (la tabla "Gráfico de cada reporte" manda) + `CLAUDE.md`.

## Global Constraints

- Código, textos y comentarios en español (voseo en la UI).
- **Git:** rama local `reportes-graficos` (ya creada desde `dev`). UN commit: `feat(reportes): gráfico de cada reporte arriba de la tabla` + línea en blanco + EXACTAMENTE `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. NUNCA push, amend, reset, rebase, merge ni checkout. Nunca commitear `.env`, `uploads/`, `backups/`, `.superpowers/`, `docs/superpowers/`.
- **NUNCA crear usuarios ni datos en la base de desarrollo** (la base ya tiene datos de demo: no tocarlos).
- Carpeta en iCloud: si git o lecturas se cuelgan, `find . -flags +dataless -type f -print0 | xargs -0 -n 20 -P 8 cat > /dev/null` y reintentar.
- Tests Python en el contenedor (`docker compose exec -T backend pytest -p no:warnings -q; echo exit=$?`: el resumen puede no imprimirse). JS: `node --check` y `node --test backend/tests_js/`.
- Una serie y un eje por gráfico (nunca doble eje). El objeto de Chart.js NO va en el estado reactivo de Alpine (el proxy rompe Chart.js): vive en una variable del closure.
- Pantallas: valores a Alpine solo con `|js` en atributos; sin `x-html`; mobile-first; sin scroll horizontal de la página.

---

### Task 1: Gráficos en reportes

**Revisión:** sin revisor por tarea (no toca dinero ni permisos); la cubre la revisión final.

**Files:**
- Modify: `backend/app/reports/motor.py` (`Grafico`, campo `grafico` en `DefinicionReporte`, `generar`)
- Modify: `backend/app/schemas/reportes.py` (`GraficoResponse`, `ReporteResponse.grafico`)
- Modify: `backend/app/services/reportes.py` (`consultar`)
- Modify: los seis `backend/app/reports/definiciones/*.py` (cada `DEFINICION` suma `grafico=`)
- Modify: `backend/app/templates/pages/reportes/reporte.html`, `backend/app/static/js/reporte.js`
- Modify: `docs/pendientes.md` (una línea; se commitea aparte, ver Step 8)
- Test: `backend/tests/test_reportes.py`, `backend/tests/test_reportes_ventas.py`, `backend/tests/test_paginas_reportes.py`, `backend/tests_js/reporte.test.mjs`

- [ ] **Step 1: Tests de backend**

En `backend/tests/test_reportes.py` (sumar a los imports lo que falte: `REPORTES` de `app.reports.definiciones`, `TipoColumna` de `app.schemas.reportes`):

```python
@pytest.mark.parametrize("clave", list(REPORTES))
def test_cada_reporte_declara_un_grafico_sobre_sus_columnas(clave):
    definicion = REPORTES[clave]
    for agrupar in definicion.agrupaciones or (None,):
        filtros = normalizar_filtros(definicion, FiltrosReporte(agrupar=agrupar), hoy=date(2026, 9, 29))
        tipos = {c.clave: c.tipo for c in definicion.columnas(filtros)}
        grafico = definicion.grafico(filtros)
        assert grafico.tipo in ("linea", "barras")
        assert grafico.etiquetas and set(grafico.etiquetas) <= set(tipos)
        assert tipos[grafico.valor] in (TipoColumna.ENTERO, TipoColumna.MONEDA, TipoColumna.PORCENTAJE)
        assert grafico.titulo
```

En `backend/tests/test_reportes_ventas.py` (usa la fixture `e` y `_pedir` que ya existen):

```python
def test_el_json_trae_el_grafico_segun_la_agrupacion(client, h, e):
    assert _pedir(client, h, "ventas-periodo")["grafico"] == {
        "tipo": "linea", "etiquetas": ["periodo"], "valor": "total", "titulo": "Total vendido por día"}
    assert _pedir(client, h, "rentabilidad", agrupar="proveedor")["grafico"] == {
        "tipo": "barras", "etiquetas": ["grupo"], "valor": "ganancia", "titulo": "Ganancia bruta por proveedor"}
    assert _pedir(client, h, "productos-vendidos", orden="importe")["grafico"] == {
        "tipo": "barras", "etiquetas": ["descripcion"], "valor": "importe", "titulo": "Importe vendido por producto"}
    assert _pedir(client, h, "medios-pago")["grafico"]["etiquetas"] == ["medio", "plan"]
```

En `backend/tests/test_paginas_reportes.py`:

```python
def test_la_pantalla_carga_chart_js_y_el_lienzo(crear_usuario, iniciar_sesion):
    html = iniciar_sesion(crear_usuario("admin")).get("/reportes/vendedores").text
    assert "chart.js@4.4.4/dist/chart.umd.min.js" in html
    assert 'x-ref="grafico"' in html
    assert html.index("chart.umd.min.js") < html.index("/static/js/reporte.js")
```

Run: `docker compose exec -T backend pytest -p no:warnings tests/test_reportes.py tests/test_reportes_ventas.py tests/test_paginas_reportes.py -q; echo exit=$?`
Expected: FAIL.

- [ ] **Step 2: Motor, schema y service**

`backend/app/reports/motor.py`, después de `Columna`:

```python
@dataclass(frozen=True)
class Grafico:
    """Qué dibujar arriba de la tabla (solo en pantalla): una serie y un eje.
    `etiquetas`: columnas que forman el nombre de cada punto o barra (la
    pantalla las une con " · "); `valor`: columna numérica a dibujar."""
    tipo: str                  # "linea" | "barras"
    etiquetas: tuple[str, ...]
    valor: str
    titulo: str
```

En `DefinicionReporte`, después de `agrupaciones`:

```python
    # Gráfico de la pantalla; puede depender de los filtros (línea por día, barras por categoría).
    grafico: Callable[[FiltrosReporte], Grafico] | None = None
```

En `generar`, sumar al dict (y al docstring la clave `grafico`):

```python
        "grafico": definicion.grafico(filtros) if definicion.grafico else None,
```

`backend/app/schemas/reportes.py` (sumar `Literal` a los imports de `typing`), antes de `ReporteResponse`:

```python
class GraficoResponse(BaseModel):
    tipo: Literal["linea", "barras"]
    etiquetas: list[str]             # claves de columna que nombran cada punto o barra
    valor: str                       # clave de la columna numérica
    titulo: str
```

y en `ReporteResponse`, después de `totales`:

```python
    grafico: GraficoResponse | None = None
```

`backend/app/services/reportes.py`, `consultar`:

```python
def consultar(db, clave: str, filtros) -> dict:
    resultado = motor.generar(db, obtener_reporte(clave), filtros)
    grafico = resultado["grafico"]
    return {**resultado, "columnas": [asdict(c) for c in resultado["columnas"]],
            "grafico": asdict(grafico) if grafico else None}
```

- [ ] **Step 3: El gráfico de cada definición**

En cada archivo, importar `Grafico` junto a `Columna, DefinicionReporte` desde `app.reports.motor`, agregar la función y pasarla como `grafico=` en `DEFINICION` (último argumento).

`ventas_periodo.py`:

```python
def _grafico(filtros) -> Grafico:
    return Grafico("linea", ("periodo",), "total", f"Total vendido por {'mes' if filtros.agrupar is Agrupar.MES else 'día'}")
```

`medios_pago.py`:

```python
def _grafico(_filtros) -> Grafico:
    return Grafico("barras", ("medio", "plan"), "total_cobrado", "Total cobrado por medio de pago")
```

`vendedores.py`:

```python
def _grafico(_filtros) -> Grafico:
    return Grafico("barras", ("vendedor",), "total", "Total vendido por vendedor")
```

`productos_vendidos.py`:

```python
def _grafico(filtros) -> Grafico:
    por_categoria = filtros.agrupar is Agrupar.CATEGORIA
    medida = "Unidades vendidas" if filtros.orden is Orden.UNIDADES else "Importe vendido"
    return Grafico("barras", ("categoria",) if por_categoria else ("descripcion",), filtros.orden.value,
                   f"{medida} por {'categoría' if por_categoria else 'producto'}")
```

`rentabilidad.py` (usa `TIPO_DEL_GRUPO` y `titulo_de_agrupacion`, ya importados ahí):

```python
def _grafico(filtros) -> Grafico:
    return Grafico("linea" if filtros.agrupar in TIPO_DEL_GRUPO else "barras", ("grupo",), "ganancia",
                   f"Ganancia bruta por {titulo_de_agrupacion(filtros.agrupar).lower()}")
```

`stock_valorizado.py`:

```python
def _grafico(filtros) -> Grafico:
    return Grafico("barras", ("grupo",), "valorizado_costo",
                   f"Valorizado a costo por {titulo_de_agrupacion(filtros.agrupar).lower()}")
```

Run los tests de backend del Step 1 → PASS.

- [ ] **Step 4: Tests JS (agregar a `backend/tests_js/reporte.test.mjs`)**

```js
test('datos del gráfico: barras con etiquetas compuestas, top 10 y números', () => {
  const columnas = [{ clave: 'medio', tipo: 'texto' }, { clave: 'plan', tipo: 'texto' },
                    { clave: 'total_cobrado', tipo: 'moneda' }];
  const filas = Array.from({ length: 12 }, (_, i) => ({ medio: 'Tarjeta', plan: `${i + 1} cuotas`, total_cobrado: `${1000 + i}.50` }));
  const g = L.datosGrafico({ tipo: 'barras', etiquetas: ['medio', 'plan'], valor: 'total_cobrado', titulo: 'Total' },
                           columnas, filas);
  assert.equal(g.etiquetas.length, 10);
  assert.equal(g.etiquetas[0], 'Tarjeta · 1 cuotas');
  assert.equal(g.valores[0], 1000.5);
  assert.equal(g.recortado, true);
  assert.equal(g.tipoValor, 'moneda');
  assert.equal(g.titulo, 'Total');
});

test('datos del gráfico: línea con todos los puntos y fechas formateadas', () => {
  const columnas = [{ clave: 'periodo', tipo: 'fecha' }, { clave: 'total', tipo: 'moneda' }];
  const filas = Array.from({ length: 15 }, (_, i) => ({ periodo: `2025-03-${String(i + 1).padStart(2, '0')}`, total: '10.00' }));
  const g = L.datosGrafico({ tipo: 'linea', etiquetas: ['periodo'], valor: 'total', titulo: 'T' }, columnas, filas);
  assert.equal(g.etiquetas.length, 15);
  assert.equal(g.etiquetas[0], '01/03/2025');
  assert.equal(g.recortado, false);
});

test('sin gráfico o sin filas no se dibuja nada', () => {
  const columnas = [{ clave: 'total', tipo: 'moneda' }];
  assert.equal(L.datosGrafico(null, columnas, [{ total: '1' }]), null);
  assert.equal(L.datosGrafico({ tipo: 'barras', etiquetas: ['total'], valor: 'total', titulo: 'T' }, columnas, []), null);
});
```

Run: `node --test backend/tests_js/` → FAIL (`datosGrafico` no existe).

- [ ] **Step 5: `backend/app/static/js/reporte.js`**

a) Constante nueva junto a las otras:

```js
  const MAX_BARRAS = 10;   // barras: el gráfico muestra las primeras N filas; la tabla, todas
```

b) En `window.reporteLogica`, después de `alineacion`:

```js
    // Datos del gráfico (una serie) a partir de la respuesta: barras = las
    // primeras MAX_BARRAS filas en el orden del reporte; línea = todas.
    // Las etiquetas usan el mismo formato que la tabla. null = no se dibuja.
    datosGrafico: (grafico, columnas, filas) => {
      if (!grafico || !filas.length) return null;
      const tipos = Object.fromEntries(columnas.map((c) => [c.clave, c.tipo]));
      const formatear = window.reporteLogica.formatear;
      const visibles = grafico.tipo === 'barras' ? filas.slice(0, MAX_BARRAS) : filas;
      return {
        tipo: grafico.tipo,
        titulo: grafico.titulo,
        tipoValor: tipos[grafico.valor],
        recortado: visibles.length < filas.length,
        etiquetas: visibles.map((fila) => grafico.etiquetas
          .map((clave) => formatear(fila[clave], tipos[clave])).filter(Boolean).join(' · ')),
        valores: visibles.map((fila) => Number(fila[grafico.valor]) || 0),
      };
    },
```

c) En `window.reporte`, antes del `return {`:

```js
    // Instancia de Chart.js FUERA del estado reactivo (el proxy de Alpine la rompe).
    let chart = null;
```

d) Estado nuevo del componente (junto a `totales`):

```js
      grafico: null,   // datosGrafico de la última respuesta (null = sin gráfico)
```

e) En `init()`, al final:

```js
        // Redibujar con los colores del tema al alternar claro/oscuro.
        if (typeof MutationObserver !== 'undefined') {
          new MutationObserver(() => this._dibujar())
            .observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
        }
```

f) En `buscar()`, después de `this.totales = respuesta.totales;`:

```js
          this.grafico = L.datosGrafico(respuesta.grafico, respuesta.columnas, respuesta.filas);
          this.$nextTick(() => this._dibujar());
```

g) Método nuevo (antes de la sección "Celdas"):

```js
      // Dibuja (o borra) el gráfico con el color primario del tema actual.
      _dibujar() {
        if (chart) { chart.destroy(); chart = null; }
        const lienzo = this.$refs.grafico;
        if (!this.grafico || !lienzo || typeof window.Chart === 'undefined') return;
        const estilo = getComputedStyle(document.documentElement);
        const color = (variable) => estilo.getPropertyValue(variable).trim();
        const g = this.grafico;
        const barras = g.tipo === 'barras';
        const formatear = (valor) => L.formatear(valor, g.tipoValor);
        const ejeValor = { beginAtZero: true, grid: { color: color('--color-border') },
                           ticks: { color: color('--color-text-muted'), callback: (valor) => formatear(valor) } };
        const ejeGrupo = { grid: { display: false }, ticks: { color: color('--color-text-muted') } };
        chart = new window.Chart(lienzo, {
          type: barras ? 'bar' : 'line',
          data: {
            labels: g.etiquetas,
            datasets: [{
              data: g.valores, backgroundColor: color('--color-primary'), borderColor: color('--color-primary'),
              borderWidth: 2, borderRadius: 4, maxBarThickness: 28, pointRadius: 3, pointHoverRadius: 5, tension: 0.2,
            }],
          },
          options: {
            indexAxis: barras ? 'y' : 'x',
            responsive: true,
            maintainAspectRatio: false,
            animation: false,
            plugins: { legend: { display: false }, tooltip: { callbacks: { label: (ctx) => formatear(ctx.raw) } } },
            scales: barras ? { x: ejeValor, y: ejeGrupo } : { x: ejeGrupo, y: ejeValor },
          },
        });
      },
```

h) Actualizar el comentario de cabecera del archivo: "…tabla con las columnas que devuelve la API, gráfico arriba (Chart.js) y fila de totales…".

- [ ] **Step 6: `backend/app/templates/pages/reportes/reporte.html`**

Antes de `<div class="tarjeta overflow-hidden p-0">` (la tabla):

```html
  {# Gráfico (Chart.js, solo en pantalla): una serie; en barras, las 10 primeras filas. #}
  <section x-show="grafico" x-cloak class="tarjeta mb-4 flex flex-col gap-3" aria-labelledby="reporte-grafico-titulo">
    <div class="flex flex-wrap items-baseline justify-between gap-2">
      <h2 id="reporte-grafico-titulo" class="text-lg font-semibold text-texto-header" x-text="grafico ? grafico.titulo : ''"></h2>
      <p x-show="grafico && grafico.recortado" class="text-sm text-texto-muted">Primeras 10 · la tabla muestra todas</p>
    </div>
    <div class="relative h-72 w-full">
      <canvas x-ref="grafico" role="img" :aria-label="grafico ? grafico.titulo : ''"></canvas>
    </div>
  </section>
```

Y el bloque de scripts, Chart.js ANTES de `reporte.js`:

```html
{% block scripts %}
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.min.js"></script>
<script src="{{ estatico('/js/reporte.js') }}"></script>
{% endblock %}
```

- [ ] **Step 7: Correr, verificar y commitear**

```bash
node --check backend/app/static/js/reporte.js
node --test backend/tests_js/
docker compose exec -T backend pytest -p no:warnings -q; echo exit=$?
```
Expected: todo en verde.

```bash
git add backend/app/reports backend/app/schemas/reportes.py backend/app/services/reportes.py \
  backend/app/templates/pages/reportes/reporte.html backend/app/static/js/reporte.js \
  backend/tests/test_reportes.py backend/tests/test_reportes_ventas.py backend/tests/test_paginas_reportes.py \
  backend/tests_js/reporte.test.mjs
git commit -m "feat(reportes): gráfico de cada reporte arriba de la tabla

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 8: Pendiente de CDN (sin commitear; lo commitea el controlador con los docs)**

En `docs/pendientes.md`, la viñeta "**Pin y SRI de los CDN** (Tailwind, htmx, Alpine)." pasa a "**Pin y SRI de los CDN** (Tailwind, htmx, Alpine, Chart.js en la pantalla de reportes)." Dejarlo sin commitear.

---

## Cierre (lo hace el controlador)

1. Revisión final con Opus.
2. Commit de docs (plan, spec, pendientes) y merge a `dev` cuando el usuario lo pida.
