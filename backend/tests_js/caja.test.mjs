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

test('aCentavos acepta la forma con separador de miles es-AR', () => {
  const L = cargar().window.cajaLogica;
  assert.equal(L.aCentavos('10.000'), 1000000);
  assert.equal(L.aCentavos('1.500'), 150000);
  assert.equal(L.aCentavos('1.500,50'), 150050);
  assert.equal(L.aCentavos('10.50'), 1050);
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
  // Las líneas informativas NO viajan en items_declarados: el backend ya las
  // completa con el esperado (services/arqueo.py, decisión 10).
  assert.deepEqual(plano(L.payloadArqueo(items, { 'm:1': '100', 'g:Clover/Payway': '49,90' })), {
    items_declarados: [
      { medio_de_pago_id: 1, grupo_terminal: null, monto_declarado: '100.00' },
      { medio_de_pago_id: null, grupo_terminal: 'Clover/Payway', monto_declarado: '49.90' },
    ],
    total_declarado: '149.90',
  });
});

test('diferencia en centavos', () => {
  const L = cargar().window.cajaLogica;
  assert.equal(L.diferencia('90', '100.00'), -1000);
  assert.equal(L.diferencia('', '100.00'), null);
});

test('cerrarTurnoPantalla: si el esperado falla, queda en error y no se puede cerrar', async () => {
  // cargar() deja `fetch` (global, el que usa window.pedir) rechazando siempre.
  const { window } = cargar();
  const pantalla = window.cerrarTurnoPantalla({ turnoId: 1 });
  await pantalla.init();
  assert.equal(pantalla.cargando, false);
  assert.equal(pantalla.error, true);
  assert.equal(pantalla.puedeCerrar, false);
});

test('cerrarTurnoPantalla: con el esperado cargado, puedeCerrar depende de lo declarado', async () => {
  const { window } = cargar();
  window.pedir = async () => ({
    items: [{ medio_de_pago_id: 1, grupo_terminal: null, medio_nombre: 'Efectivo', monto_esperado: '100.00',
             es_informativo: false, es_efectivo: true }],
    efectivo_apertura: '0.00',
    total_esperado: '100.00',
  });
  const pantalla = window.cerrarTurnoPantalla({ turnoId: 1 });
  await pantalla.init();
  assert.equal(pantalla.error, false);
  assert.equal(pantalla.puedeCerrar, false);
  pantalla.declarados['m:1'] = '100';
  assert.equal(pantalla.puedeCerrar, true);
});

test('cargarTurnos manda el filtro de estado a la API cuando está seteado', async () => {
  const { window } = cargar();
  let urlUsada = null;
  window.pedir = async (url) => { urlUsada = url; return { resultados: [], total: 0 }; };
  const pantalla = window.cajaPantalla({ usuarioId: 1, puedeRetirar: false, puedeArquear: false });
  pantalla.filtros.estado = 'abierto';
  await pantalla.cargarTurnos(1);
  assert.ok(urlUsada.includes('estado=abierto'), urlUsada);
});

test('limpiarFiltrosTurnos resetea también el estado', async () => {
  const { window } = cargar();
  window.pedir = async () => ({ resultados: [], total: 0 });
  const pantalla = window.cajaPantalla({ usuarioId: 1, puedeRetirar: false, puedeArquear: false });
  pantalla.filtros = { desde: '2026-01-01', hasta: '2026-01-31', estado: 'cerrado' };
  await pantalla.limpiarFiltrosTurnos();
  assert.deepEqual(plano(pantalla.filtros), { desde: '', hasta: '', estado: '' });
});

test('verArqueo guarda la fecha de APERTURA del turno (la de la fila), no arqueo.created_at', async () => {
  const { window } = cargar();
  window.pedir = async () => ({ id: 5, turno_id: 9, created_at: '2026-02-02T00:00:00', items: [] });
  const pantalla = window.cajaPantalla({ usuarioId: 1, puedeRetirar: false, puedeArquear: false });
  await pantalla.verArqueo({ id: 9, fecha_apertura: '2026-01-15T20:00:00' });
  assert.equal(pantalla.arqueoFechaApertura, '2026-01-15T20:00:00');
});
