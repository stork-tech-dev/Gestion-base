// Tests de window.notificaciones (backend/app/static/js/app.js): leer() y
// leerTodas() atrapan el error del pedido y avisan con un toast (nunca dejan
// una promesa rechazada sin manejar). Mismos stubs mínimos que caja.test.mjs.
// Correr con: node --test backend/tests_js/
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const RUTA_APP = new URL('../app/static/js/app.js', import.meta.url);

function cargar({ fetchImpl } = {}) {
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
    // Por defecto rechaza siempre (mismo criterio que caja.test.mjs): así se
    // ejercita el camino de error de leer()/leerTodas() sin mocks extra.
    fetch: fetchImpl || (() => Promise.reject(new Error('sin red'))),
    setTimeout: () => 0,
    clearTimeout: () => {},
  };
  vm.runInNewContext(readFileSync(RUTA_APP, 'utf8'), contexto);
  window.toast = (mensaje, tipo) => toasts.push({ mensaje, tipo });
  return { window, toasts };
}

test('leer atrapa el error del pedido y muestra un toast de error', async () => {
  const { window, toasts } = cargar();
  const n = window.notificaciones();
  await n.leer({ id: 1, leida: false });
  assert.equal(toasts.length, 1);
  assert.equal(toasts[0].tipo, 'error');
});

test('leerTodas atrapa el error del pedido y muestra un toast de error', async () => {
  const { window, toasts } = cargar();
  const n = window.notificaciones();
  n.lista = [{ id: 1, leida: false }];
  await n.leerTodas();
  assert.equal(toasts.length, 1);
  assert.equal(toasts[0].tipo, 'error');
});

test('leer marca como leída y descuenta el contador si el pedido funciona', async () => {
  const { window, toasts } = cargar({ fetchImpl: () => Promise.resolve({ status: 204 }) });
  const n = window.notificaciones();
  n.noLeidas = 1;
  const notif = { id: 1, leida: false };
  await n.leer(notif);
  assert.equal(notif.leida, true);
  assert.equal(n.noLeidas, 0);
  assert.equal(toasts.length, 0);
});
