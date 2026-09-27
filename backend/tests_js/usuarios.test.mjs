// Tests de la lógica del formulario de usuarios (backend/app/static/js/usuarios.js),
// en particular alCambiarRol(): mientras cargan los accesos del rol nuevo no
// se puede guardar (se perderían accesos sin reconciliar), ni en el alta ni
// en la edición, y las respuestas viejas se ignoran.
// Se carga en un contexto vm compartido primero app.js (para usar el
// `ultimaRespuesta` real, el secuenciador que evita la carrera) y después
// usuarios.js, con los stubs mínimos que necesita app.js para cargar sin
// romper (sin red ni DOM real). `window.pedir` se stubea con promesas
// controladas a mano por el test (un "deferred" por pedido).
// Correr con: node --test backend/tests_js/
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const RUTA_APP = new URL('../app/static/js/app.js', import.meta.url);
const RUTA_USUARIOS = new URL('../app/static/js/usuarios.js', import.meta.url);

// Carga app.js y usuarios.js en el mismo contexto vm, con stubs mínimos:
// `document` con addEventListener y documentElement.classList.contains,
// `window.fetch`, `window.dispatchEvent`, `localStorage`, `matchMedia` y
// `setTimeout`/`clearTimeout` (app.js los usa al definirse o en listeners
// que acá nunca se disparan). `CustomEvent`/`Event` son globales del vm,
// no de `window`, porque app.js los usa sin prefijo.
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
  vm.runInNewContext(readFileSync(RUTA_USUARIOS, 'utf8'), contexto);
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
  return window.usuariosListado({
    esAdmin: false, usuarioActualId: null, rolesGestionables: [], rolesFiltro: [], puedeEditar: true,
  });
}

test('edición: alCambiarRol bloquea accesosCargados mientras carga y lo libera con la respuesta', async () => {
  const window = cargarComponente();
  const { pedir, pendientes } = pedirDiferido();
  window.pedir = pedir;
  const c = crearComponente(window);
  c.form = { id: 7, rol_id: 3 };
  c.marcados = [];
  c.accesosCargados = true;
  c._cargaInicialLista = true;  // editar() ya recibió los accesos del usuario  // como queda tras editar() con la carga ya resuelta

  const promesa = c.alCambiarRol();
  assert.equal(c.accesosCargados, false);  // bloqueado mientras no llegó la respuesta

  assert.equal(pendientes.length, 1);
  assert.match(pendientes[0].url, /rol_id=3/);
  pendientes[0].resolver([{ clave: 'stock.ver', heredado: false }]);
  await promesa;

  assert.equal(c.accesosCargados, true);
  assert.deepEqual(c.accesos, [{ clave: 'stock.ver', heredado: false }]);
});

test('dos cambios de rol seguidos: la respuesta vieja que llega después no pisa el estado', async () => {
  const window = cargarComponente();
  const { pedir, pendientes } = pedirDiferido();
  window.pedir = pedir;
  const c = crearComponente(window);
  c.form = { id: 7, rol_id: 3 };
  c.marcados = [];
  c.accesosCargados = true;
  c._cargaInicialLista = true;  // editar() ya recibió los accesos del usuario

  const promesaRol3 = c.alCambiarRol();  // elige el rol 3 primero...
  c.form.rol_id = 4;
  const promesaRol4 = c.alCambiarRol();  // ...y cambia de opinión antes de que responda

  assert.equal(pendientes.length, 2);
  const pedidoRol3 = pendientes.find((p) => /rol_id=3/.test(p.url));
  const pedidoRol4 = pendientes.find((p) => /rol_id=4/.test(p.url));

  // Responde primero el pedido del rol 4 (el vigente)...
  pedidoRol4.resolver([{ clave: 'stock.ver', heredado: false }]);
  await promesaRol4;
  // ...y DESPUÉS el del rol 3, que ya quedó viejo: no debe pisar nada.
  pedidoRol3.resolver([{ clave: 'ventas.ver', heredado: false }]);
  await promesaRol3;

  assert.equal(c.accesosCargados, true);
  assert.deepEqual(c.accesos, [{ clave: 'stock.ver', heredado: false }]);
});

test('si falla la carga de accesos, queda bloqueado y avisa que vuelva a elegir el rol', async () => {
  const window = cargarComponente();
  const { pedir, pendientes } = pedirDiferido();
  window.pedir = pedir;
  const toasts = [];
  window.toast = (mensaje, tipo) => toasts.push({ mensaje, tipo });
  const c = crearComponente(window);
  c.form = { id: 7, rol_id: 3 };
  c.marcados = [];
  c.accesosCargados = true;
  c._cargaInicialLista = true;  // editar() ya recibió los accesos del usuario

  const promesa = c.alCambiarRol();
  pendientes[0].rechazar(new Error('Sin conexión'));
  await promesa;

  assert.equal(c.accesosCargados, false);
  assert.equal(toasts.length, 1);
  assert.equal(toasts[0].tipo, 'error');
  assert.match(toasts[0].mensaje, /Volvé a elegir el rol\./);
});

test('alta sin rol elegido: no hay accesos que perder y no se llama a la API', async () => {
  const window = cargarComponente();
  const { pedir, pendientes } = pedirDiferido();
  window.pedir = pedir;
  const c = crearComponente(window);
  c.form = { id: null, rol_id: null };
  c.marcados = ['stock.ver'];
  c.accesosCargados = false;

  await c.alCambiarRol();

  assert.equal(c.accesosCargados, true);
  // c.accesos es un array del contexto vm, con su propio Array.prototype:
  // deepEqual con un [] de este realm falla porque el prototipo no es el
  // mismo objeto, no por estar vacío (los arrays no vacíos de otro realm sí
  // comparan bien más arriba porque ahí no importa el prototipo).
  assert.equal(c.accesos.length, 0);
  assert.equal(pendientes.length, 0);
});

test('alta CON rol elegido: accesosCargados queda false mientras carga', () => {
  const window = cargarComponente();
  const { pedir, pendientes } = pedirDiferido();
  window.pedir = pedir;
  const c = crearComponente(window);
  c.form = { id: null, rol_id: 3 };
  c.marcados = [];
  c.accesosCargados = true;  // como queda tras nuevo()

  c.alCambiarRol();

  assert.equal(c.accesosCargados, false);
  assert.equal(pendientes.length, 1);
  assert.match(pendientes[0].url, /rol_id=3/);
});

test('edición: un cambio de rol durante la carga inicial se ignora y los overrides del usuario se cargan', async () => {
  const window = cargarComponente();
  const { pedir, pendientes } = pedirDiferido();
  window.pedir = pedir;
  const c = crearComponente(window);

  const promesaEditar = c.editar({ id: 7, username: 'ana', nombre: 'Ana', rol_id: 3 });
  assert.equal(c.accesosCargados, false);

  // El combobox está deshabilitado; si igual llega un cambio de rol, se ignora.
  c.form.rol_id = 4;
  await c.alCambiarRol();
  assert.equal(pendientes.length, 1);  // no se pidió nada para el rol 4
  assert.equal(c.form.rol_id, 3);      // vuelve al rol original

  // Llega el GET de editar(): no se descarta y carga los overrides propios.
  pendientes[0].resolver([
    { clave: 'ventas.ver', override: true, heredado: false },
    { clave: 'stock.ver', override: false, heredado: true },
  ]);
  await promesaEditar;

  assert.equal(c.accesosCargados, true);
  assert.equal(c.accesos.length, 2);
  assert.deepEqual([...c.marcados], ['ventas.ver']);
  assert.deepEqual([...c.marcadosOriginales], ['ventas.ver']);

  // Terminada la carga inicial, el cambio de rol vuelve a funcionar.
  c.form.rol_id = 4;
  const promesaRol = c.alCambiarRol();
  assert.equal(pendientes.length, 2);
  assert.match(pendientes[1].url, /rol_id=4/);
  pendientes[1].resolver([{ clave: 'stock.ver', heredado: false }]);
  await promesaRol;
  assert.equal(c.accesosCargados, true);
  assert.deepEqual([...c.marcados], ['ventas.ver']);
});
