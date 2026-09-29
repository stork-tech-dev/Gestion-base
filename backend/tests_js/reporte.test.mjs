// Tests de la pantalla genérica de reportes (backend/app/static/js/reporte.js):
// funciones puras de window.reporteLogica. Mismos stubs mínimos que
// ventas.test.mjs. Correr con: node --test backend/tests_js/
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const RUTA_APP = new URL('../app/static/js/app.js', import.meta.url);
const RUTA_REPORTE = new URL('../app/static/js/reporte.js', import.meta.url);

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
  vm.runInNewContext(readFileSync(RUTA_REPORTE, 'utf8'), contexto);
  return window.reporteLogica;
}

const L = cargar();
const PRODUCTOS = ['desde', 'hasta', 'agrupar', 'nivel', 'orden', 'limite', 'proveedor_id', 'categoria_id'];

test('filtros iniciales: mes actual, primera agrupación y valores por defecto', () => {
  const f = L.filtrosIniciales({ admitidos: PRODUCTOS, agrupaciones: ['producto', 'categoria'],
                                 hoyIso: '2026-09-29', inicioMesIso: '2026-09-01' });
  assert.deepEqual({ ...f }, { desde: '2026-09-01', hasta: '2026-09-29', agrupar: 'producto', nivel: '1',
                               orden: 'unidades', limite: '50', proveedor_id: null, categoria_id: null });
});

test('filtros iniciales sin fechas (stock valorizado)', () => {
  const f = L.filtrosIniciales({ admitidos: ['agrupar', 'nivel'], agrupaciones: ['categoria', 'proveedor'],
                                 hoyIso: '2026-09-29', inicioMesIso: '2026-09-01' });
  assert.deepEqual({ ...f }, { agrupar: 'categoria', nivel: '1' });
});

test('query: omite vacíos y no admitidos; el nivel solo al agrupar por categoría', () => {
  const q = L.queryDeFiltros(
    { desde: '2026-09-01', hasta: '', agrupar: 'producto', nivel: '2', proveedor_id: 7, usuario_id: 3, categoria_id: null },
    ['desde', 'hasta', 'agrupar', 'nivel', 'proveedor_id', 'categoria_id']);
  assert.deepEqual({ ...q }, { desde: '2026-09-01', agrupar: 'producto', proveedor_id: '7' });
  assert.equal(L.queryDeFiltros({ agrupar: 'categoria', nivel: '2' }, ['agrupar', 'nivel']).nivel, '2');
});

test('formato de cada tipo de columna', () => {
  assert.equal(L.formatear('1234.50', 'moneda'), '$ 1.234,50');
  assert.equal(L.formatear(1234, 'entero'), '1.234');
  assert.equal(L.formatear('47.92', 'porcentaje'), '47,9 %');
  assert.equal(L.formatear('2025-03-01', 'fecha'), '01/03/2025');
  assert.equal(L.formatear('2025-03-01', 'mes'), '03/2025');
  assert.equal(L.formatear('Rep R > Rep S', 'texto'), 'Rep R > Rep S');
  assert.equal(L.formatear(null, 'moneda'), '');
});

test('alineación: solo los números a la derecha', () => {
  assert.match(L.alineacion('moneda'), /text-right/);
  assert.match(L.alineacion('porcentaje'), /text-right/);
  assert.equal(L.alineacion('texto'), '');
  assert.equal(L.alineacion('fecha'), '');
});
