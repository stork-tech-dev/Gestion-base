// Tests del componente de fotos de producto (backend/app/static/js/fotos_producto.js),
// reutilizado por la ficha y por el formulario de edición (Task 4). Mismos
// stubs mínimos que producto_form.test.mjs/productos.test.mjs. Correr con:
// node --test backend/tests_js/
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const RUTA_APP = new URL('../app/static/js/app.js', import.meta.url);
const RUTA_FOTOS = new URL('../app/static/js/fotos_producto.js', import.meta.url);

function cargarComponente() {
  const document = {
    addEventListener: () => {},
    documentElement: { classList: { contains: () => false } },
  };
  const toasts = [];
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
    FormData: function FormData() { this._campos = {}; this.append = (k, v) => { this._campos[k] = v; }; },
    URLSearchParams,
    setTimeout,
    clearTimeout,
  };
  vm.runInNewContext(readFileSync(RUTA_APP, 'utf8'), contexto);
  vm.runInNewContext(readFileSync(RUTA_FOTOS, 'utf8'), contexto);
  window.toast = (mensaje, tipo) => toasts.push({ mensaje, tipo });
  return { window, toasts };
}

function foto(id, esPrincipal = false) {
  return { id, url: `/uploads/productos/${id}.jpg`, es_principal: esPrincipal, orden: id };
}

function crear(window, { productoId = 1, fotos = [], alCambiar, vigilarProducto } = {}) {
  return window.fotosProducto({ productoId, fotos, alCambiar, vigilarProducto });
}

// Mismo stub que usan webcamCapture y otros componentes con `init()` en
// productos.test.mjs: `$watch` guarda {expresion, fn} en vez de observar de
// verdad (no hay Alpine real en este harness).
function conWatch(c) {
  const vigilancias = [];
  c.$watch = (expresion, fn) => vigilancias.push({ expresion, fn });
  c.init();
  return vigilancias;
}

test('puedeSubir: true con menos de 5 fotos, false con 5', () => {
  const { window } = cargarComponente();
  const c4 = crear(window, { fotos: [foto(1), foto(2), foto(3), foto(4)] });
  assert.equal(c4.puedeSubir, true);
  const c5 = crear(window, { fotos: [foto(1), foto(2), foto(3), foto(4), foto(5)] });
  assert.equal(c5.puedeSubir, false);
});

test('recargar: pide la ficha completa y se queda solo con las fotos', async () => {
  const { window } = cargarComponente();
  const llamadas = [];
  window.pedir = (url) => { llamadas.push(url); return Promise.resolve({ id: 7, fotos: [foto(1)] }); };
  const c = crear(window, { productoId: 7, fotos: [] });
  await c.recargar();
  assert.deepEqual(llamadas, ['/api/v1/productos/7']);
  assert.equal(c.fotos.length, 1);
});

test('subirFoto: sin archivo no llama a la API', async () => {
  const { window } = cargarComponente();
  let llamado = false;
  window.pedir = () => { llamado = true; return Promise.resolve({}); };
  const c = crear(window, { productoId: 1 });
  await c.subirFoto(null);
  assert.equal(llamado, false);
});

test('subirFoto: sube, avisa con un toast, recarga sus fotos y llama a alCambiar', async () => {
  const { window, toasts } = cargarComponente();
  const llamadas = [];
  let avisado = false;
  window.pedir = (url, opciones) => {
    llamadas.push({ url, method: opciones && opciones.method });
    if (url === '/api/v1/productos/1/fotos') return Promise.resolve({ id: 9, es_principal: true });
    return Promise.resolve({ id: 1, fotos: [foto(9, true)] });
  };
  const c = crear(window, { productoId: 1, fotos: [], alCambiar: () => { avisado = true; } });
  await c.subirFoto({ name: 'x.jpg' });
  assert.deepEqual(llamadas.map((l) => l.url), ['/api/v1/productos/1/fotos', '/api/v1/productos/1']);
  assert.equal(llamadas[0].method, 'POST');
  assert.equal(c.fotos.length, 1);
  assert.equal(avisado, true);
  assert.ok(toasts.some((t) => t.mensaje === 'Foto subida.'));
});

test('subirFoto: si falla, avisa por toast de error y no llama a alCambiar', async () => {
  const { window, toasts } = cargarComponente();
  window.pedir = () => Promise.reject(new Error('La foto supera los 5 MB.'));
  let avisado = false;
  const c = crear(window, { productoId: 1, alCambiar: () => { avisado = true; } });
  await c.subirFoto({ name: 'x.jpg' });
  assert.equal(avisado, false);
  assert.deepEqual(toasts, [{ mensaje: 'La foto supera los 5 MB.', tipo: 'error' }]);
});

test('capturarFoto: captura con la cámara, la detiene y sube el blob', async () => {
  const { window } = cargarComponente();
  const llamadas = [];
  window.pedir = (url, opciones) => {
    llamadas.push(url);
    if (url === '/api/v1/productos/1/fotos') return Promise.resolve({ id: 9 });
    return Promise.resolve({ id: 1, fotos: [] });
  };
  const camara = {
    detenida: false,
    capturar: () => Promise.resolve('blob-de-la-foto'),
    detener() { this.detenida = true; },
  };
  const c = crear(window, { productoId: 1 });
  await c.capturarFoto(camara);
  assert.equal(camara.detenida, true);
  assert.ok(llamadas.includes('/api/v1/productos/1/fotos'));
});

test('marcarPrincipal: patchea la foto y recarga', async () => {
  const { window } = cargarComponente();
  const llamadas = [];
  window.pedir = (url, opciones) => {
    llamadas.push({ url, method: opciones && opciones.method });
    return url.includes('/principal') ? Promise.resolve({}) : Promise.resolve({ id: 1, fotos: [foto(2, true)] });
  };
  const c = crear(window, { productoId: 1, fotos: [foto(2, false)] });
  await c.marcarPrincipal(foto(2));
  assert.equal(llamadas[0].url, '/api/v1/productos/fotos/2/principal');
  assert.equal(llamadas[0].method, 'PATCH');
  assert.equal(c.fotos[0].es_principal, true);
});

test('borrarFoto: sin confirmar no llama a la API', async () => {
  const { window } = cargarComponente();
  let llamado = false;
  window.pedir = () => { llamado = true; return Promise.resolve({}); };
  window.confirmar = () => Promise.resolve(false);
  const c = crear(window, { productoId: 1, fotos: [foto(2)] });
  await c.borrarFoto(foto(2));
  assert.equal(llamado, false);
  assert.equal(c.fotos.length, 1);
});

test('borrarFoto: confirmando, borra, avisa y recarga', async () => {
  const { window, toasts } = cargarComponente();
  const llamadas = [];
  window.confirmar = () => Promise.resolve(true);
  window.pedir = (url, opciones) => {
    llamadas.push({ url, method: opciones && opciones.method });
    return url === '/api/v1/productos/fotos/2' ? Promise.resolve(null) : Promise.resolve({ id: 1, fotos: [] });
  };
  let avisado = false;
  const c = crear(window, { productoId: 1, fotos: [foto(2)], alCambiar: () => { avisado = true; } });
  await c.borrarFoto(foto(2));
  assert.equal(llamadas[0].url, '/api/v1/productos/fotos/2');
  assert.equal(llamadas[0].method, 'DELETE');
  assert.equal(c.fotos.length, 0);
  assert.equal(avisado, true);
  assert.ok(toasts.some((t) => t.mensaje === 'Foto borrada.'));
});

// ---------- vigilarProducto: resincroniza si el x-if padre no remonta ----------

test('vigilarProducto: sin pasarlo, no registra ningún $watch', () => {
  const { window } = cargarComponente();
  const c = crear(window, { productoId: 1 });
  assert.equal(conWatch(c).length, 0);
});

test('vigilarProducto: al cambiar el id del padre (ej. form.id de A a B sin remontar), resincroniza y recarga', async () => {
  const { window } = cargarComponente();
  const llamadas = [];
  window.pedir = (url) => { llamadas.push(url); return Promise.resolve({ id: 2, fotos: [foto(1)] }); };
  const c = crear(window, { productoId: 1, fotos: [foto(9)], vigilarProducto: 'form.id' });
  const vigilancias = conWatch(c);
  assert.equal(vigilancias.length, 1);
  assert.equal(vigilancias[0].expresion, 'form.id');

  await vigilancias[0].fn(2);

  assert.equal(c.productoId, 2);                      // ya no apunta al producto A
  assert.deepEqual(llamadas, ['/api/v1/productos/2']);
  assert.equal(c.fotos.length, 1);
});

test('vigilarProducto: un cambio a null o al mismo id no hace nada (evita recargas de más)', async () => {
  const { window } = cargarComponente();
  let llamado = false;
  window.pedir = () => { llamado = true; return Promise.resolve({ id: 1, fotos: [] }); };
  const c = crear(window, { productoId: 1, vigilarProducto: 'form.id' });
  const vigilancias = conWatch(c);

  await vigilancias[0].fn(null);   // se cerró el formulario (alta: form.id vuelve a null)
  await vigilancias[0].fn(1);      // "cambió" al mismo producto que ya tenía

  assert.equal(llamado, false);
  assert.equal(c.productoId, 1);
});

test('sin alCambiar: los cambios no explotan aunque nadie escuche', async () => {
  const { window } = cargarComponente();
  window.confirmar = () => Promise.resolve(true);
  window.pedir = (url) => (url === '/api/v1/productos/fotos/2' ? Promise.resolve(null) : Promise.resolve({ id: 1, fotos: [] }));
  const c = crear(window, { productoId: 1, fotos: [foto(2)] });
  await assert.doesNotReject(c.borrarFoto(foto(2)));
});
