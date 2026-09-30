// Tests de la lógica del formulario de producto (backend/app/static/js/producto_form.js):
// las funciones puras de categorías (window.productoFormUtil) y, en el
// componente Alpine, que el preview de precio y la búsqueda de parecidos no
// se pisen con una respuesta vieja. Ambos van secuenciados con
// `ultimaRespuesta`; los parecidos, además, contra `_apertura` (reabrir con
// otro producto no vuelve a pedir similares por sí solo, así que el
// secuenciador solo no alcanza — ver el comentario en producto_form.js).
// Mismos stubs mínimos que usuarios.test.mjs/proveedores.test.mjs. `window.pedir`
// se stubea con promesas controladas a mano por el test (un "deferred" por
// pedido). Correr con: node --test backend/tests_js/
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const RUTA_APP = new URL('../app/static/js/app.js', import.meta.url);
const RUTA_PRODUCTO_FORM = new URL('../app/static/js/producto_form.js', import.meta.url);

// Ver el comentario equivalente en usuarios.test.mjs: mismos stubs mínimos.
function cargarComponente() {
  const document = {
    addEventListener: () => {},
    documentElement: { classList: { contains: () => false } },
  };
  const window = {
    document,
    addEventListener: () => {},
    dispatchEvent: () => {},
    localStorage: {},
    matchMedia: () => ({ matches: false, addEventListener: () => {} }),
    fetch: () => Promise.resolve({ status: 204 }),
  };
  const contexto = {
    window,
    document,
    CustomEvent: function CustomEvent(tipo, opciones) { this.type = tipo; this.detail = opciones && opciones.detail; },
    Event: function Event(tipo) { this.type = tipo; },
    URLSearchParams,
    setTimeout,
    clearTimeout,
  };
  vm.runInNewContext(readFileSync(RUTA_APP, 'utf8'), contexto);
  vm.runInNewContext(readFileSync(RUTA_PRODUCTO_FORM, 'utf8'), contexto);
  return window;
}

// Deferred por pedido: cada llamado a `pedir(url)` guarda su {url, resolver,
// rechazar} en `pendientes` y devuelve una promesa que el test resuelve o
// rechaza cuando quiere, en el orden que quiere (para simular respuestas
// que llegan desordenadas).
function pedirDiferido() {
  const pendientes = [];
  const pedir = (url) => new Promise((resolver, rechazar) => { pendientes.push({ url, resolver, rechazar }); });
  return { pedir, pendientes };
}

function crearComponente(window) {
  return window.productoForm({ esAdmin: true, nivelMaximo: 5, margenDefault: '40', descuentoMaximo: '30' });
}

// Árbol de 3 niveles: Ropa > Remeras > Lisas (hoja), y Calzado (raíz sin hijos).
const ARBOL = [
  {
    id: 1, nombre: 'Ropa', nivel: 1, parent_id: null, orden: 0,
    hijos: [
      {
        id: 2, nombre: 'Remeras', nivel: 2, parent_id: 1, orden: 0,
        hijos: [
          { id: 3, nombre: 'Lisas', nivel: 3, parent_id: 2, orden: 0, hijos: [] },
        ],
      },
    ],
  },
  { id: 4, nombre: 'Calzado', nivel: 1, parent_id: null, orden: 1, hijos: [] },
];

function producto({ id, categoriaId, moneda = 'ars' }) {
  return {
    id, sku: `SKU${id}`, verificador: '0', codigo_con_verificador: `SKU${id}0`, sku_proveedor: null,
    descripcion: `Producto ${id}`,
    categoria: { id: categoriaId, nombre: 'Lisas', camino: 'Ropa > Remeras > Lisas' },
    proveedor: { id: 9, nombre: 'Proveedor', moneda },
    moneda, costo: '100', margen: '40', precio_venta: '140', descuento_producto: '0',
    peso_gramos: null, temporada: 'atemporal', ubicacion_deposito: null, stock_infinito: false,
    activo: true, foto_url: null, fotos: [],
  };
}

test('nivelesDeCategoria: ids desde la raíz hasta una hoja de nivel 3; null da []', () => {
  const window = cargarComponente();
  // rutaDeIds (app.js) construye el resultado con spread DENTRO del contexto
  // vm: el array que devuelve tiene el Array.prototype de ESE realm, no el de
  // este archivo. Se envuelve en un spread propio antes de comparar (mismo
  // motivo que "[...c.marcados]" en usuarios.test.mjs).
  assert.deepEqual([...window.productoFormUtil.nivelesDeCategoria(ARBOL, 3)], [1, 2, 3]);
  assert.deepEqual([...window.productoFormUtil.nivelesDeCategoria(ARBOL, null)], []);
});

test('opcionesDeNivel: nivel 0 son las raíces; nivel 1 con la raíz elegida son sus hijos', () => {
  const window = cargarComponente();
  const raices = window.productoFormUtil.opcionesDeNivel(ARBOL, [], 0);
  assert.deepEqual(raices.map((n) => n.id), [1, 4]);

  const hijosDeRopa = window.productoFormUtil.opcionesDeNivel(ARBOL, [1], 1);
  assert.deepEqual(hijosDeRopa.map((n) => n.id), [2]);
});

test('esHoja: true en una hoja, false en un nodo con hijos', () => {
  const window = cargarComponente();
  assert.equal(window.productoFormUtil.esHoja(ARBOL, 3), true);   // Lisas, sin hijos
  assert.equal(window.productoFormUtil.esHoja(ARBOL, 1), false);  // Ropa, tiene hijos
  assert.equal(window.productoFormUtil.esHoja(ARBOL, 4), true);   // Calzado, raíz sin hijos
});

test('stockEntero: trunca y no baja de 0', () => {
  const window = cargarComponente();
  assert.equal(window.productoFormUtil.stockEntero(5.9), 5);
  assert.equal(window.productoFormUtil.stockEntero(-3), 0);
  assert.equal(window.productoFormUtil.stockEntero('7'), 7);
  assert.equal(window.productoFormUtil.stockEntero('no-es-numero'), 0);
});

test('preview: dos cambios de costo seguidos, la respuesta vieja no pisa la del último', async () => {
  const window = cargarComponente();
  const { pedir, pendientes } = pedirDiferido();
  window.pedir = pedir;
  const c = crearComponente(window);
  c.proveedores = [{ id: 9, nombre: 'Proveedor', moneda: 'usd' }];
  c.form.proveedor_id = 9;

  c.form.costo = '100';
  const promesaUno = c.pedirPreview();
  c.form.costo = '200';
  const promesaDos = c.pedirPreview();

  assert.equal(pendientes.length, 2);
  const pedidoUno = pendientes.find((p) => /costo=100/.test(p.url));
  const pedidoDos = pendientes.find((p) => /costo=200/.test(p.url));
  assert.ok(pedidoUno && pedidoDos);

  // Responde primero el del costo 200 (el vigente)...
  pedidoDos.resolver({ moneda: 'usd', dolar_proveedor: '1000', precio_venta: '280000' });
  await promesaDos;
  // ...y DESPUÉS el del costo 100, que ya quedó viejo: no debe pisar el precio.
  pedidoUno.resolver({ moneda: 'usd', dolar_proveedor: '1000', precio_venta: '140000' });
  await promesaUno;

  assert.equal(c.precioPreview, '280000');
});

test('preview: sin proveedor, costo o margen válidos no hay pedido y el precio queda en null', async () => {
  const window = cargarComponente();
  const { pedir, pendientes } = pedirDiferido();
  window.pedir = pedir;
  const c = crearComponente(window);
  c.precioPreview = '999';

  c.form.proveedor_id = null;
  c.form.costo = '100';
  c.form.margen = '40';
  await c.pedirPreview();

  assert.equal(pendientes.length, 0);
  assert.equal(c.precioPreview, null);
});

test('similares: al abrir otro producto no se pisan los parecidos con una respuesta vieja', async () => {
  const window = cargarComponente();
  const { pedir, pendientes } = pedirDiferido();
  window.pedir = pedir;
  const c = crearComponente(window);

  // Abre el producto A (edición): dispara el GET de /categorias/arbol.
  const promesaAbrirA = c.abrir(producto({ id: 1, categoriaId: 3 }));
  const pedidoArbolA = pendientes[pendientes.length - 1];
  pedidoArbolA.resolver(ARBOL);
  await promesaAbrirA;

  // El usuario escribe una descripción larga: se buscan parecidos de A.
  c.form.descripcion = 'Remera de algodon lisa';
  const promesaSimilaresA = c.buscarSimilares();
  const pedidoSimilaresA = pendientes[pendientes.length - 1];
  assert.match(pedidoSimilaresA.url, /\/similares\?/);

  // Antes de que respondan los parecidos, se abre el producto B (otro _apertura).
  const promesaAbrirB = c.abrir(producto({ id: 2, categoriaId: 3 }));
  const pedidoArbolB = pendientes[pendientes.length - 1];
  assert.equal(c.similares.length, 0);  // abrir() ya vació la lista
  pedidoArbolB.resolver(ARBOL);
  await promesaAbrirB;

  // Recién ahora llega, tarde, la respuesta de los parecidos de A.
  pedidoSimilaresA.resolver([{ id: 5, sku: 'SKU5', descripcion: 'Remera de algodon lisa vieja', activo: true }]);
  await promesaSimilaresA;

  assert.equal(c.similares.length, 0);  // no la pisó
});

test('similares: menos de 10 caracteres no pide nada y vacía la lista', async () => {
  const window = cargarComponente();
  const { pedir, pendientes } = pedirDiferido();
  window.pedir = pedir;
  const c = crearComponente(window);
  c.similares = [{ id: 1, sku: 'X', descripcion: 'algo', activo: true }];

  c.form.descripcion = 'corta';
  await c.buscarSimilares();

  assert.equal(pendientes.length, 0);
  assert.equal(c.similares.length, 0);
});

test('alta: árbol y proveedores activos por separado; si fallan los proveedores, el árbol igual carga', async () => {
  const window = cargarComponente();
  const { pedir, pendientes } = pedirDiferido();
  window.pedir = pedir;
  window.toast = () => {};
  const c = crearComponente(window);
  const abriendo = c.abrir(null);
  const arbol = pendientes.find((p) => p.url === '/api/v1/categorias/arbol');
  const proveedores = pendientes.find((p) => p.url === '/api/v1/productos/proveedores?solo_activos=true');
  assert.ok(arbol && proveedores);
  proveedores.rechazar(new Error('sin permiso'));
  arbol.resolver(ARBOL);
  await abriendo;
  assert.equal(c.arbol.length, 2);
  assert.equal(c.proveedores.length, 0);
});

test('edición: muestra el precio guardado y, en dólares, el dólar vigente (sin pisar el precio)', async () => {
  const window = cargarComponente();
  const { pedir, pendientes } = pedirDiferido();
  window.pedir = pedir;
  const c = crearComponente(window);
  const abriendo = c.abrir(producto({ id: 1, categoriaId: 3, moneda: 'usd' }));
  assert.equal(c.precioPreview, '140');
  const preview = pendientes.find((p) => /precio-preview\?/.test(p.url));
  assert.ok(preview && /proveedor_id=9/.test(preview.url));
  pendientes.find((p) => p.url === '/api/v1/categorias/arbol').resolver(ARBOL);
  preview.resolver({ moneda: 'usd', dolar_proveedor: '1000', precio_venta: '999999' });
  await abriendo;
  assert.equal(c.dolarProveedor, '1000');
  assert.equal(c.precioPreview, '140');
  assert.deepEqual([...c.elegidos], [1, 2, 3]);
});

test('edición en pesos: sin pedido de dólar', async () => {
  const window = cargarComponente();
  const { pedir, pendientes } = pedirDiferido();
  window.pedir = pedir;
  const c = crearComponente(window);
  const abriendo = c.abrir(producto({ id: 1, categoriaId: 3 }));
  assert.equal(pendientes.length, 1);
  pendientes[0].resolver(ARBOL);
  await abriendo;
  assert.equal(c.dolarProveedor, null);
});

test('duplicadoExacto: en la edición el propio producto no cuenta', () => {
  const window = cargarComponente();
  const c = crearComponente(window);
  c.form.id = 1;
  c.form.descripcion = 'Remera lisa';
  c.similares = [{ id: 1, sku: 'SKU1', descripcion: 'Remera lisa', activo: true }];
  assert.equal(c.duplicadoExacto, null);
  c.similares.push({ id: 2, sku: 'SKU2', descripcion: 'remera lisa', activo: false });
  assert.equal(c.duplicadoExacto.id, 2);
});

// ---------- Stock inicial (módulo 05, Task 10) ----------

test('cuerpo: el alta manda stock_inicial truncado (Math.trunc, ≥0); la edición no lo manda', () => {
  const window = cargarComponente();
  const c = crearComponente(window);
  c.arbol = ARBOL;
  c.elegidos = [1, 2, 3];  // Ropa > Remeras > Lisas (hoja): categoriaId válido
  c.form.proveedor_id = 9;
  c.form.descripcion = 'Producto nuevo';
  c.form.costo = '100';
  c.form.margen = '40';

  c.form.stock_inicial = '7.9';
  const cuerpoAlta = c.cuerpo();
  assert.equal(cuerpoAlta.stock_inicial, 7);
  assert.equal(cuerpoAlta.proveedor_id, 9);

  // Edición: ni stock_inicial ni proveedor_id (no se editan).
  c.form.id = 1;
  const cuerpoEdicion = c.cuerpo();
  assert.equal('stock_inicial' in cuerpoEdicion, false);
  assert.equal('proveedor_id' in cuerpoEdicion, false);
});

// ---------- Margen ↔ precio de venta manual (Task 4) ----------

// window.productoFormLogica.* corre DENTRO del contexto vm: los objetos que
// devuelve tienen el Object.prototype de ESE realm, no el de este archivo.
// Se envuelven en un spread propio antes de comparar (mismo motivo que el
// spread de arrays documentado arriba, en el test de nivelesDeCategoria).
test('paramsPreview: manda margen en modo margen, precio_venta en modo precio (nunca los dos)', () => {
  const window = cargarComponente();
  const form = { proveedor_id: 9, costo: '100', margen: '40', precio_venta: '140' };
  assert.deepEqual({ ...window.productoFormLogica.paramsPreview(form, 'margen') }, { proveedor_id: 9, costo: '100', margen: '40' });
  assert.deepEqual({ ...window.productoFormLogica.paramsPreview(form, 'precio') }, { proveedor_id: 9, costo: '100', precio_venta: '140' });
});

test('cuerpoPrecio: manda el campo del modo vigente y el otro en null', () => {
  const window = cargarComponente();
  const form = { margen: '40', precio_venta: '140' };
  assert.deepEqual({ ...window.productoFormLogica.cuerpoPrecio(form, 'margen') }, { margen: '40', precio_venta: null });
  assert.deepEqual({ ...window.productoFormLogica.cuerpoPrecio(form, 'precio') }, { margen: null, precio_venta: '140' });
  assert.deepEqual({ ...window.productoFormLogica.cuerpoPrecio({ margen: '', precio_venta: '' }, 'margen') },
                   { margen: null, precio_venta: null });
});

test('textoRedondeo: vacío sin redondeo configurado o con precio manual; si no, el monto formateado', () => {
  const window = cargarComponente();
  const { textoRedondeo } = window.productoFormLogica;
  assert.equal(textoRedondeo('1000.00', true), 'Redondeado hacia arriba a múltiplos de $ 1.000');
  assert.equal(textoRedondeo('1000.00', false), '');   // precio manual: no pasó por la fórmula
  assert.equal(textoRedondeo('0', true), '');           // sin redondeo configurado
  assert.equal(textoRedondeo(null, true), '');
});

test('alEditarMargen/alEditarPrecio: fijan el modo vigente antes de pedir el preview', () => {
  const window = cargarComponente();
  const { pedir, pendientes } = pedirDiferido();
  window.pedir = pedir;
  const c = crearComponente(window);
  c.form.proveedor_id = 9;
  c.form.costo = '100';
  c.form.margen = '40';
  c.form.precio_venta = '150';

  c.alEditarPrecio();
  assert.equal(c.modoPrecio, 'precio');
  assert.match(pendientes[pendientes.length - 1].url, /precio_venta=150/);

  c.alEditarMargen();
  assert.equal(c.modoPrecio, 'margen');
  assert.match(pendientes[pendientes.length - 1].url, /margen=40/);
});

test('pedirPreview en modo precio: la respuesta llena form.margen y no pisa el precio cargado', async () => {
  const window = cargarComponente();
  const { pedir, pendientes } = pedirDiferido();
  window.pedir = pedir;
  const c = crearComponente(window);
  c.form.proveedor_id = 9;
  c.form.costo = '100';
  c.modoPrecio = 'precio';
  c.form.precio_venta = '150';

  const promesa = c.pedirPreview();
  assert.equal(pendientes.length, 1);
  assert.match(pendientes[0].url, /precio_venta=150/);
  assert.doesNotMatch(pendientes[0].url, /[?&]margen=/);
  pendientes[0].resolver({ moneda: 'ars', dolar_proveedor: null, precio_venta: '150', margen: '50.00', redondeo: '0', redondeado: false });
  await promesa;

  assert.equal(c.form.margen, '50.00');
  assert.equal(c.form.precio_venta, '150');   // no se pisa a sí mismo
  assert.equal(c.redondeado, false);
  assert.equal(c.redondeoTexto, '');          // precio manual: sin leyenda
});

test('cambiar el costo respeta el modo vigente (precio): repregunta con precio_venta, no con margen', () => {
  const window = cargarComponente();
  const { pedir, pendientes } = pedirDiferido();
  window.pedir = pedir;
  const c = crearComponente(window);
  c.form.proveedor_id = 9;
  c.form.precio_venta = '150';
  c.modoPrecio = 'precio';   // el usuario ya había tocado el precio

  c.form.costo = '100';
  c.pedirPreview();          // disparado por @input.debounce.300ms del costo
  assert.equal(pendientes.length, 1);
  assert.match(pendientes[0].url, /precio_venta=150/);
});

test('redondeoTexto: con margen y redondeo > 0 muestra la leyenda con el múltiplo', async () => {
  const window = cargarComponente();
  const { pedir, pendientes } = pedirDiferido();
  window.pedir = pedir;
  const c = crearComponente(window);
  c.form.proveedor_id = 9;
  c.form.costo = '100';
  c.form.margen = '40';

  const promesa = c.pedirPreview();
  pendientes[0].resolver({ moneda: 'ars', dolar_proveedor: null, precio_venta: '140', margen: '40.00', redondeo: '100.00', redondeado: true });
  await promesa;

  assert.equal(c.redondeoTexto, 'Redondeado hacia arriba a múltiplos de $ 100');
});

test('cuerpo: stock_inicial negativo o inválido en el alta queda en 0', () => {
  const window = cargarComponente();
  const c = crearComponente(window);
  c.arbol = ARBOL;
  c.elegidos = [1, 2, 3];
  c.form.proveedor_id = 9;

  c.form.stock_inicial = '-5';
  assert.equal(c.cuerpo().stock_inicial, 0);

  c.form.stock_inicial = 'no-es-numero';
  assert.equal(c.cuerpo().stock_inicial, 0);
});
