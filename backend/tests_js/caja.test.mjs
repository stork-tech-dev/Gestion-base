// Tests de la lógica pura de Caja (backend/app/static/js/caja.js):
// window.cajaLogica. Mismos stubs mínimos que ventas.test.mjs. Correr con:
// node --test backend/tests_js/
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const RUTA_APP = new URL('../app/static/js/app.js', import.meta.url);
const RUTA_CAJA = new URL('../app/static/js/caja.js', import.meta.url);

function cargar() {
  const document = {
    addEventListener: () => {},
    documentElement: { classList: { contains: () => false } },
    createElement: () => ({}),
  };
  const toasts = [];
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
  vm.runInNewContext(readFileSync(RUTA_CAJA, 'utf8'), contexto);
  window.toast = (mensaje, tipo) => toasts.push({ mensaje, tipo });
  return { window, toasts };
}

// Los objetos creados dentro del vm tienen otro prototipo: se comparan por JSON.
const plano = (x) => JSON.parse(JSON.stringify(x));

test('aCentavos acepta coma o punto decimal y rechaza basura', () => {
  const L = cargar().window.cajaLogica;
  assert.equal(L.aCentavos('1.500,50'), 150050);
  assert.equal(L.aCentavos('1500.5'), 150050);
  assert.equal(L.aCentavos('$ 1500'), 150000);
  assert.equal(L.aCentavos(''), null);
  assert.equal(L.aCentavos('12a'), null);
});

test('totalDeclarado ignora informativos y es null si falta una línea', () => {
  const L = cargar().window.cajaLogica;
  const items = [
    { medio_de_pago_id: 1, grupo_terminal: null, monto_esperado: '100.00', es_informativo: false },
    { medio_de_pago_id: null, grupo_terminal: 'Clover/Payway', monto_esperado: '50.00', es_informativo: false },
    { medio_de_pago_id: 4, grupo_terminal: null, monto_esperado: '30.00', es_informativo: true },
  ];
  assert.equal(L.totalDeclarado(items, { 'm:1': '100', 'g:Clover/Payway': '49,90' }), 14990);
  assert.equal(L.totalDeclarado(items, { 'm:1': '100' }), null);
  assert.deepEqual(plano(L.payloadArqueo(items, { 'm:1': '100', 'g:Clover/Payway': '49,90' })), {
    items_declarados: [
      { medio_de_pago_id: 1, grupo_terminal: null, monto_declarado: '100.00' },
      { medio_de_pago_id: null, grupo_terminal: 'Clover/Payway', monto_declarado: '49.90' },
      { medio_de_pago_id: 4, grupo_terminal: null, monto_declarado: '30.00' },
    ],
    total_declarado: '149.90',
  });
});

test('diferencia en centavos', () => {
  const L = cargar().window.cajaLogica;
  assert.equal(L.diferencia('90', '100.00'), -1000);
  assert.equal(L.diferencia('', '100.00'), null);
});
