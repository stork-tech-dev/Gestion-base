// Tests de la pantalla de cambio masivo del dólar (backend/app/static/js/dolar_masivo.js):
// el toast al aplicar cuenta solo los proveedores con `aplicado: true` (la API
// devuelve todos los elegidos, hayan cambiado o no). También cubre
// `window.dolares` de app.js (única definición del prefijo "US$ ").
// Mismos stubs mínimos que usuarios.test.mjs. Correr con: node --test backend/tests_js/
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const RUTA_APP = new URL('../app/static/js/app.js', import.meta.url);
const RUTA_MASIVO = new URL('../app/static/js/dolar_masivo.js', import.meta.url);

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
  vm.runInNewContext(readFileSync(RUTA_MASIVO, 'utf8'), contexto);
  return window;
}

test('aplicar: el toast cuenta solo los proveedores que cambiaron', async () => {
  const window = cargarComponente();
  const toasts = [];
  window.toast = (mensaje, tipo) => toasts.push({ mensaje, tipo });
  window.confirmar = () => Promise.resolve(true);
  const respuestas = [
    [{ proveedor_id: 1, aplicado: true }, { proveedor_id: 2, aplicado: false }, { proveedor_id: 3, aplicado: true }],
    [],  // recarga de /dolar/activos
  ];
  window.pedir = () => Promise.resolve(respuestas.shift());
  const c = window.dolarMasivo();
  c.vista = [{}, {}, {}];

  await c.aplicar();

  assert.equal(toasts[0].mensaje, 'Dólar actualizado en 2 proveedor(es).');
});

test('aplicar: si ninguno cambió, lo dice', () => {
  const c = cargarComponente().dolarMasivo();
  assert.equal(c.mensajeAplicados([{ aplicado: false }, { aplicado: false }]), 'Ningún proveedor cambió.');
});

test('dolares() antepone "US$ " al número formateado', () => {
  const window = cargarComponente();
  assert.equal(window.dolares('1234.5'), `US$ ${window.formatearDolar('1234.5')}`);
  assert.match(window.dolares('1000'), /^US\$ 1\.000$/);
});
