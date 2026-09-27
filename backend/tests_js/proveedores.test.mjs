// Tests de la lógica del formulario de proveedores (backend/app/static/js/proveedores.js),
// en particular cargarHistorial(): el historial que llega tarde de un
// proveedor que ya no está en pantalla no debe pisar el del proveedor
// actual. Un secuenciador (`ultimaRespuesta`) solo no alcanza cuando el
// siguiente editar() no vuelve a pedir historial (proveedor en pesos), así
// que cargarHistorial() también compara `this.form.id` contra el id que
// tenía cuando arrancó el pedido.
// Se carga en un contexto vm compartido primero app.js (para usar el
// `ultimaRespuesta` real) y después proveedores.js, con los stubs mínimos
// que necesita app.js para cargar sin romper (sin red ni DOM real).
// `window.pedir` se stubea con promesas controladas a mano por el test (un
// "deferred" por pedido).
// Correr con: node --test backend/tests_js/
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const RUTA_APP = new URL('../app/static/js/app.js', import.meta.url);
const RUTA_PROVEEDORES = new URL('../app/static/js/proveedores.js', import.meta.url);

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
    setTimeout,
    clearTimeout,
  };
  vm.runInNewContext(readFileSync(RUTA_APP, 'utf8'), contexto);
  vm.runInNewContext(readFileSync(RUTA_PROVEEDORES, 'utf8'), contexto);
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
  return window.proveedoresListado({ usaDolar: true, puedeEditar: true, esAdmin: true });
}

test('editar A (usd) con el historial demorado y después B (ars): al llegar el de A, el historial queda vacío', async () => {
  const window = cargarComponente();
  const { pedir, pendientes } = pedirDiferido();
  window.pedir = pedir;
  const c = crearComponente(window);

  const promesaA = c.editar({ id: 1, nombre: 'A', moneda: 'usd', dolar_actual: '100' });
  assert.equal(pendientes.length, 1);
  const pedidoA = pendientes.find((p) => /\/1\/dolar\/historial$/.test(p.url));
  assert.ok(pedidoA);

  // B está en pesos: editar() no pide historial (no hay un segundo pedido
  // que "gane" la carrera del lado del secuenciador).
  await c.editar({ id: 2, nombre: 'B', moneda: 'ars' });
  assert.equal(pendientes.length, 1);
  assert.equal(c.form.id, 2);

  // Recién ahora llega, tarde, la respuesta de A.
  pedidoA.resolver([{ id: 10, valor_anterior: '90', valor_nuevo: '100' }]);
  await promesaA;

  assert.equal(c.form.id, 2);
  assert.equal(c.historial.length, 0);
});

test('editar A y después B (ambos usd): si B resuelve antes que A, el historial que queda es el de B', async () => {
  const window = cargarComponente();
  const { pedir, pendientes } = pedirDiferido();
  window.pedir = pedir;
  const c = crearComponente(window);

  const promesaA = c.editar({ id: 1, nombre: 'A', moneda: 'usd', dolar_actual: '100' });
  const promesaB = c.editar({ id: 2, nombre: 'B', moneda: 'usd', dolar_actual: '200' });

  assert.equal(pendientes.length, 2);
  const pedidoA = pendientes.find((p) => /\/1\/dolar\/historial$/.test(p.url));
  const pedidoB = pendientes.find((p) => /\/2\/dolar\/historial$/.test(p.url));

  // Responde primero B (el vigente)...
  pedidoB.resolver([{ id: 20, valor_anterior: '190', valor_nuevo: '200' }]);
  await promesaB;
  // ...y DESPUÉS A, que ya quedó viejo: no debe pisar el historial de B.
  pedidoA.resolver([{ id: 10, valor_anterior: '90', valor_nuevo: '100' }]);
  await promesaA;

  assert.equal(c.form.id, 2);
  assert.deepEqual(c.historial, [{ id: 20, valor_anterior: '190', valor_nuevo: '200' }]);
});
