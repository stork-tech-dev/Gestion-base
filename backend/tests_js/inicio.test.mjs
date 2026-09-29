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
