// Tests del listado de productos (backend/app/static/js/productos.js) y de la
// cámara compartida (webcamCapture en app.js): ficha que no muestra el
// producto anterior, catálogos que cargan por separado, ventana de etiquetas
// abierta en el mismo click, leyenda de inactivos y cámara que se apaga.
// Mismos stubs mínimos que producto_form.test.mjs. Correr con: node --test backend/tests_js/
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const RUTA_APP = new URL('../app/static/js/app.js', import.meta.url);
const RUTA_PRODUCTOS = new URL('../app/static/js/productos.js', import.meta.url);

function cargarComponente({ fetch, open, navigator } = {}) {
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
    matchMedia: () => ({ matches: false, addEventListener: () => {} }),
    fetch: () => Promise.resolve({ status: 204 }),
    open: open || (() => null),
  };
  const revocadas = [];
  const temporizadores = [];
  const contexto = {
    window,
    document,
    CustomEvent: function CustomEvent(tipo, opciones) { this.type = tipo; this.detail = opciones && opciones.detail; },
    Event: function Event(tipo) { this.type = tipo; },
    URLSearchParams,
    URL: { createObjectURL: () => 'blob:etiquetas', revokeObjectURL: (u) => revocadas.push(u) },
    fetch: fetch || (() => Promise.reject(new Error('sin red'))),
    setTimeout: (fn, ms) => { temporizadores.push({ fn, ms }); return temporizadores.length; },
    clearTimeout: () => {},
    navigator: navigator || { mediaDevices: {} },
  };
  vm.runInNewContext(readFileSync(RUTA_APP, 'utf8'), contexto);
  vm.runInNewContext(readFileSync(RUTA_PRODUCTOS, 'utf8'), contexto);
  window.toast = (mensaje, tipo) => toasts.push({ mensaje, tipo });
  return { window, toasts, revocadas, temporizadores, contexto };
}

function pedirDiferido() {
  const pendientes = [];
  const pedir = (url) => new Promise((resolver, rechazar) => { pendientes.push({ url, resolver, rechazar }); });
  return { pedir, pendientes };
}

const TEMPORADAS = [['atemporal', 'Atemporal'], ['otoño_invierno', 'Otoño-Invierno']];

function crear(window) {
  return window.productosListado({ puedeEditar: true, temporadas: TEMPORADAS });
}

test('temporadas: llegan del servidor como [valor, texto] y alimentan filtro y ficha', () => {
  const { window } = cargarComponente();
  const c = crear(window);
  assert.deepEqual(c.temporadas.map((t) => [t.id, t.texto]), TEMPORADAS);
  assert.equal(c.temporadaTexto('otoño_invierno'), 'Otoño-Invierno');
});

test('catálogos: si falla el árbol, los proveedores igual cargan (y piden la ruta de productos)', async () => {
  const { window, toasts } = cargarComponente();
  const { pedir, pendientes } = pedirDiferido();
  window.pedir = pedir;
  const c = crear(window);
  c._cargarCatalogos();
  const arbol = pendientes.find((p) => p.url === '/api/v1/categorias/arbol');
  const proveedores = pendientes.find((p) => p.url === '/api/v1/productos/proveedores');
  assert.ok(arbol && proveedores);
  arbol.rechazar(new Error('falló el árbol'));
  proveedores.resolver([{ id: 1, nombre: 'Prov', moneda: 'ars', activo: false }]);
  await new Promise((r) => setImmediate(r));
  assert.equal(c.proveedores.length, 1);
  assert.deepEqual(toasts.map((t) => t.mensaje), ['falló el árbol']);
});

test('abrirFicha: no muestra el producto anterior mientras carga ni si falla', async () => {
  const { window } = cargarComponente();
  const { pedir, pendientes } = pedirDiferido();
  window.pedir = pedir;
  const c = crear(window);
  c.ficha = { id: 1, descripcion: 'Anterior' };
  const promesa = c.abrirFicha({ id: 2 });
  assert.equal(c.ficha, null);
  pendientes[0].rechazar(new Error('no se pudo'));
  await promesa;
  assert.equal(c.ficha, null);
});

test('etiquetas: ventana bloqueada → aviso y no se pide el PDF', async () => {
  let pedidos = 0;
  const { window, toasts } = cargarComponente({ open: () => null, fetch: () => { pedidos++; return Promise.reject(); } });
  const c = crear(window);
  c.ficha = { id: 7 };
  await c.imprimir('colita');
  assert.equal(pedidos, 0);
  assert.equal(toasts[0].mensaje, 'El navegador bloqueó la ventana; habilitá las ventanas emergentes.');
});

test('etiquetas: la ventana se abre ANTES del fetch y después recibe la URL del PDF (revocada a los 60 s)', async () => {
  const eventos = [];
  const ventana = { location: null, close: () => eventos.push('close') };
  const { window, revocadas, temporizadores } = cargarComponente({
    open: () => { eventos.push('open'); return ventana; },
    fetch: () => { eventos.push('fetch'); return Promise.resolve({ ok: true, blob: () => Promise.resolve('pdf') }); },
  });
  const c = crear(window);
  c.ficha = { id: 7 };
  await c.imprimir('rectangular');
  assert.deepEqual(eventos, ['open', 'fetch']);
  assert.equal(ventana.location, 'blob:etiquetas');
  const revocar = temporizadores.find((t) => t.ms === 60000);
  assert.ok(revocar);
  revocar.fn();
  assert.deepEqual(revocadas, ['blob:etiquetas']);
  assert.equal(c.imprimiendo, false);
});

test('etiquetas: si el pedido falla se cierra la ventana y se avisa', async () => {
  const ventana = { location: null, cerrada: false, close() { this.cerrada = true; } };
  const { window, toasts } = cargarComponente({
    open: () => ventana,
    fetch: () => Promise.resolve({ ok: false, status: 409, json: () => Promise.resolve({ detail: 'Demasiadas' }) }),
  });
  const c = crear(window);
  c.ficha = { id: 7 };
  await c.imprimir('rectangular');
  assert.equal(ventana.cerrada, true);
  assert.equal(toasts[0].tipo, 'error');
});

test('leyenda de inactivos: solo con el switch en Activos, una búsqueda y cero resultados', () => {
  const { window } = cargarComponente();
  const c = crear(window);
  c.total = 0;
  assert.equal(c.sugerirInactivos, false);                  // sin búsqueda
  c.filtros.busqueda = 'remera';
  assert.equal(c.sugerirInactivos, true);
  c.cargando = true;
  assert.equal(c.sugerirInactivos, false);                  // mientras carga
  c.cargando = false;
  c.filtros.activos = false;
  assert.equal(c.sugerirInactivos, false);                  // ya está en Inactivos
  c.filtros.activos = true;
  c.total = 3;
  assert.equal(c.sugerirInactivos, false);
});

// ---------- webcamCapture (app.js) ----------

function pista() {
  const t = { detenida: false, stop() { t.detenida = true; } };
  return t;
}

function camara(window, vigilar) {
  const c = window.webcamCapture(vigilar ? { vigilar } : undefined);
  c.$refs = { video: {} };
  const vigilancias = [];
  c.$watch = (expresion, fn) => vigilancias.push({ expresion, fn });
  c.init();
  return { c, vigilancias };
}

test('webcamCapture: si se detiene mientras el navegador pide permiso, el stream no queda abierto', async () => {
  let resolver;
  const track = pista();
  const { window } = cargarComponente({
    navigator: { mediaDevices: { getUserMedia: () => new Promise((r) => { resolver = r; }) } },
  });
  const { c } = camara(window);
  const iniciando = c.iniciar();
  c.detener();                                            // se cerró el modal
  resolver({ getTracks: () => [track] });
  await iniciando;
  assert.equal(track.detenida, true);
  assert.equal(c.activa, false);
  assert.equal(c.stream, null);
});

test('webcamCapture: `vigilar` apaga la cámara cuando cambia la expresión, y destroy también', async () => {
  let track = pista();
  const { window } = cargarComponente({
    navigator: { mediaDevices: { getUserMedia: () => Promise.resolve({ getTracks: () => [track] }) } },
  });
  const { c, vigilancias } = camara(window, 'fichaAbierta && ficha ? ficha.id : null');
  assert.equal(vigilancias[0].expresion, 'fichaAbierta && ficha ? ficha.id : null');
  await c.iniciar();
  assert.equal(c.activa, true);
  vigilancias[0].fn(null);                                // se cerró la ficha
  assert.equal(track.detenida, true);
  assert.equal(c.activa, false);

  track = pista();
  await c.iniciar();
  c.destroy();                                            // salió del DOM (x-if)
  assert.equal(track.detenida, true);
});

test('webcamCapture: sin `vigilar` no registra ningún $watch', () => {
  const { window } = cargarComponente();
  assert.equal(camara(window).vigilancias.length, 0);
});
