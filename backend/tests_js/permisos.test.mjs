// Tests de la lógica del árbol de permisos (backend/app/static/js/permisos.js).
// Sin Alpine ni red: se carga el archivo en un contexto vm con un `window`
// falso y se llama a los métodos del componente directamente.
// Correr con: node --test backend/tests_js/
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const RUTA = new URL('../app/static/js/permisos.js', import.meta.url);
const ACCIONES = ['ver', 'crear', 'editar', 'eliminar'];

function cargarComponente(modo) {
  const window = {
    pedir: async () => ({ modulos: [] }),
    toast: () => {},
    confirmar: async () => true,
    addEventListener: () => {},
  };
  vm.runInNewContext(readFileSync(RUTA, 'utf8'), { window });
  return window.arbolPermisos({ urlDatos: '/datos', urlGuardar: '/guardar', modo, editable: true });
}

// Nodo con todas las acciones aplicables; `extra` pisa campos.
function nodo(modulo, recurso, extra = {}) {
  const base = { modulo, recurso, label: recurso || modulo };
  for (const a of ACCIONES) base[`puede_${a}`] = false;
  return { ...base, ...extra };
}

function nodoUsuario(modulo, recurso, extra = {}) {
  const base = {};
  for (const a of ACCIONES) {
    base[`heredado_${a}`] = false;
    base[`override_${a}`] = false;
    base[`otorgable_${a}`] = true;
  }
  return nodo(modulo, recurso, { ...base, ...extra });
}

const filaDe = (entradas, recurso) => entradas.find((e) => e.modulo === 'stock' && e.recurso === recurso);

test('modo rol: el general marcado cubre al recurso y desmarcarlo lo libera', () => {
  const c = cargarComponente('rol');
  const general = nodo('stock', null);
  const baja = nodo('stock', 'baja');
  general.recursos = [baja];
  c.modulos = [general];

  c.alternar(general, 'crear');
  assert.equal(general.puede_crear, true);
  assert.equal(c.bloqueado(baja, 'crear'), true);
  assert.equal(filaDe(c.entradas(), 'baja').puede_crear, false);

  c.alternar(general, 'crear');
  assert.equal(baja.puede_crear, false);
  assert.equal(c.bloqueado(baja, 'crear'), false);
});

test('modo usuario: desmarcar el general quita el override heredado por cascada de la API', () => {
  const c = cargarComponente('usuario');
  const general = nodoUsuario('stock', null, { override_crear: true });
  const baja = nodoUsuario('stock', 'baja', { heredado_crear: true, override_crear: true });
  general.recursos = [baja];
  c.modulos = [general];

  c.alternar(general, 'crear');
  assert.equal(general.override_crear, false);
  assert.equal(baja.override_crear, false);
  const recursosConCrear = c.entradas().filter((e) => e.recurso !== null && e.puede_crear);
  assert.equal(recursosConCrear.length, 0);
});

test('modo usuario: marcar el general no otorga override a un recurso no otorgable', () => {
  const c = cargarComponente('usuario');
  const general = nodoUsuario('stock', null);
  const baja = nodoUsuario('stock', 'baja', { otorgable_crear: false });
  general.recursos = [baja];
  c.modulos = [general];

  c.alternar(general, 'crear');
  assert.equal(general.override_crear, true);
  assert.equal(baja.override_crear, false);
});
