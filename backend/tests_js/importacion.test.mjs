// Tests de la pantalla de importación (backend/app/static/js/importacion.js).
// Correr con: node --test backend/tests_js/
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const RUTA_APP = new URL('../app/static/js/app.js', import.meta.url);
const RUTA = new URL('../app/static/js/importacion.js', import.meta.url);

function cargar(respuestas = [], confirmar = true) {
  const document = { addEventListener: () => {}, documentElement: { classList: { contains: () => false } } };
  const toasts = [];
  const window = {
    document, addEventListener: () => {}, dispatchEvent: () => {}, localStorage: {},
    matchMedia: () => ({ matches: false, addEventListener: () => {} }),
    fetch: () => Promise.resolve({ status: 204 }),
  };
  const contexto = {
    window, document, FormData: class { append() {} },
    CustomEvent: function CustomEvent(tipo, opciones) { this.type = tipo; this.detail = opciones && opciones.detail; },
    Event: function Event(tipo) { this.type = tipo; }, setTimeout, clearTimeout,
  };
  vm.runInNewContext(readFileSync(RUTA_APP, 'utf8'), contexto);
  vm.runInNewContext(readFileSync(RUTA, 'utf8'), contexto);
  const pedidos = [];
  window.pedir = async (url) => { pedidos.push(url); return respuestas.shift(); };
  window.toast = (mensaje, tipo = 'exito') => toasts.push({ mensaje, tipo });
  window.confirmar = async () => confirmar;
  return { window, pedidos, toasts };
}

const TIPOS = [{ valor: 'proveedores', etiqueta: 'Proveedores', listado: '/proveedores' },
               { valor: 'clientes', etiqueta: 'Clientes', listado: '/clientes' }];
const OK = { tipo: 'proveedores', filas_leidas: 3, filas_validas: 3, creados: 0, categorias_nuevas: [], errores: [], aplicado: false };

test('textos del resumen, la confirmación y el éxito', () => {
  const { window } = cargar();
  const t = window.importacionTextos;
  assert.equal(t.resumen(OK), '3 filas leídas · 3 listas para importar');
  assert.equal(t.confirmacion(OK, 'Proveedores'), 'Se van a crear 3 proveedores. Esta acción no se deshace desde el sistema.');
  assert.equal(t.exito({ ...OK, creados: 3 }, 'Clientes'), 'Listo: se crearon 3 clientes.');
});

test('importar se habilita solo con 0 errores y el mismo archivo validado', async () => {
  const { window } = cargar([OK]);
  const c = window.importacion(TIPOS);
  const archivo = { name: 'a.xlsx' };
  c.elegirArchivo(archivo);
  assert.equal(c.puedeImportar, false);
  await c.validar();
  assert.equal(c.puedeImportar, true);
  c.elegirArchivo({ name: 'b.xlsx' });           // cambió el archivo
  assert.equal(c.puedeImportar, false);
});

test('con errores no se puede importar y la tabla pagina de a 10', async () => {
  const errores = Array.from({ length: 12 }, (_, i) => ({ fila: i + 2, columna: 'nombre', error: 'x' }));
  const { window } = cargar([{ ...OK, filas_validas: 0, errores }]);
  const c = window.importacion(TIPOS);
  c.elegirArchivo({ name: 'a.xlsx' });
  await c.validar();
  assert.equal(c.puedeImportar, false);
  assert.equal(c.erroresPagina.length, 10);
  c.pagina = 2;
  assert.equal(c.erroresPagina.length, 2);
});

test('importar usa el tipo elegido y avisa con toast', async () => {
  const { window, pedidos, toasts } = cargar([{ ...OK, tipo: 'clientes' }, { ...OK, tipo: 'clientes', creados: 3, aplicado: true }]);
  const c = window.importacion(TIPOS);
  c.elegirTipo(TIPOS[1]);
  c.elegirArchivo({ name: 'a.xlsx' });
  await c.validar();
  await c.importar();
  assert.deepEqual(pedidos, ['/api/v1/importacion/clientes/validar', '/api/v1/importacion/clientes/importar']);
  assert.equal(toasts.at(-1).mensaje, 'Listo: se crearon 3 clientes.');
  assert.equal(c.importado.creados, 3);
  assert.equal(c.puedeImportar, false);
});

test('cambiar de pestaña limpia el archivo y el resultado', async () => {
  const { window } = cargar([OK]);
  const c = window.importacion(TIPOS);
  c.elegirArchivo({ name: 'a.xlsx' });
  await c.validar();
  c.elegirTipo(TIPOS[1]);
  assert.equal(c.archivo, null);
  assert.equal(c.resultado, null);
});

const tick = () => new Promise((r) => setImmediate(r));

// Pedido que queda pendiente hasta que el test lo resuelva.
function pendiente(window) {
  let resolver;
  window.pedir = () => new Promise((r) => { resolver = r; });
  return (valor) => resolver(valor);
}

test('ocupado indica qué acción está en curso', async () => {
  const { window } = cargar();
  const c = window.importacion(TIPOS);
  c.elegirArchivo({ name: 'a.xlsx' });
  let resolver = pendiente(window);
  const validando = c.validar();
  assert.equal(c.ocupado, 'validar');
  resolver(OK);
  await validando;
  assert.equal(c.ocupado, null);
  assert.equal(c.puedeImportar, true);
  resolver = pendiente(window);
  const importando = c.importar();
  await tick();                                    // pasa el confirmar()
  assert.equal(c.ocupado, 'importar');
  assert.equal(c.puedeImportar, false);
  resolver({ ...OK, creados: 3, aplicado: true });
  await importando;
  assert.equal(c.ocupado, null);
});

test('si cambian de pestaña durante el pedido, la respuesta se ignora', async () => {
  const { window, toasts } = cargar([OK]);
  const c = window.importacion(TIPOS);
  c.elegirArchivo({ name: 'a.xlsx' });
  await c.validar();
  const resolver = pendiente(window);
  const importando = c.importar();
  await tick();
  c.elegirTipo(TIPOS[1]);
  resolver({ ...OK, filas_validas: 0, errores: [{ fila: 2, columna: 'nombre', error: 'x' }] });
  await importando;
  assert.equal(c.tipo, TIPOS[1]);
  assert.equal(c.resultado, null);                 // los errores del tipo viejo no aparecen en la pestaña nueva
  assert.equal(c.importado, null);
  assert.equal(toasts.length, 0);
  assert.equal(c.ocupado, null);
});

test('si importar devuelve errores vuelve a la primera página', async () => {
  const errores = Array.from({ length: 12 }, (_, i) => ({ fila: i + 2, columna: 'nombre', error: 'x' }));
  const { window } = cargar([OK, { ...OK, filas_validas: 0, errores }]);
  const c = window.importacion(TIPOS);
  c.elegirArchivo({ name: 'a.xlsx' });
  await c.validar();
  c.pagina = 2;
  await c.importar();
  assert.equal(c.pagina, 1);
  assert.equal(c.erroresPagina.length, 10);
});
