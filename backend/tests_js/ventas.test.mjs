// Tests del Resumen de Ventas (backend/app/static/js/ventas.js): las
// funciones puras de window.ventasLogica y los flujos delicados del
// componente (detalle secuenciado que descarta una venta que ya no es la
// abierta, anulación con motivo obligatorio). Mismos stubs mínimos que
// venta.test.mjs. Correr con: node --test backend/tests_js/
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const RUTA_APP = new URL('../app/static/js/app.js', import.meta.url);
const RUTA_VENTAS = new URL('../app/static/js/ventas.js', import.meta.url);

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
  vm.runInNewContext(readFileSync(RUTA_VENTAS, 'utf8'), contexto);
  window.toast = (mensaje, tipo) => toasts.push({ mensaje, tipo });
  return { window, toasts };
}

function crearPantalla(window, overrides = {}) {
  return window.ventasResumen({ puedeAnular: true, clienteIdInicial: null, hoyIso: '2026-09-28', ...overrides });
}

// Los objetos creados dentro del vm tienen otro prototipo: se comparan por JSON.
const plano = (x) => JSON.parse(JSON.stringify(x));

// ---------- ventasLogica ----------

const { window: W } = cargar();
const L = W.ventasLogica;

test('filtrosIniciales: fecha desde/hasta = hoy; cliente_id solo si vino de la ficha', () => {
  assert.deepEqual(plano(L.filtrosIniciales('2026-09-28')), {
    numero: '', codigo_cambio: '', estado: '', usuario_id: '',
    fecha_desde: '2026-09-28', fecha_hasta: '2026-09-28', cliente_id: null,
  });
  assert.equal(L.filtrosIniciales('2026-09-28', 7).cliente_id, 7);
});

test('queryDeFiltros: omite vacíos, código en mayúsculas, siempre pagina y tamano', () => {
  const filtros = {
    numero: '  v-1  ', codigo_cambio: 'ab3d', estado: '', usuario_id: '',
    fecha_desde: '2026-09-01', fecha_hasta: '', cliente_id: null,
  };
  assert.deepEqual(plano(L.queryDeFiltros(filtros, 2)), {
    pagina: 2, tamano: 10, numero: 'v-1', codigo_cambio: 'AB3D', fecha_desde: '2026-09-01',
  });
});

test('queryDeFiltros: estado, usuario_id y cliente_id viajan cuando están cargados', () => {
  const filtros = { numero: '', codigo_cambio: '', estado: 'confirmada', usuario_id: '3', fecha_desde: '', fecha_hasta: '', cliente_id: 9 };
  assert.deepEqual(plano(L.queryDeFiltros(filtros, 1)), { pagina: 1, tamano: 10, estado: 'confirmada', usuario_id: '3', cliente_id: '9' });
});

test('textoMedios: une los medios con " + "; vacío si no hay ninguno', () => {
  assert.equal(L.textoMedios({ medios: ['Efectivo', 'Tarjeta de débito'] }), 'Efectivo + Tarjeta de débito');
  assert.equal(L.textoMedios({ medios: [] }), '');
});

test('puedeAnular: solo confirmadas y con el permiso', () => {
  assert.equal(L.puedeAnular({ estado: 'confirmada' }, true), true);
  assert.equal(L.puedeAnular({ estado: 'confirmada' }, false), false);
  assert.equal(L.puedeAnular({ estado: 'anulada' }, true), false);
  assert.equal(L.puedeAnular({ estado: 'en_curso' }, true), false);
  assert.equal(L.puedeAnular(null, true), false);
});

// ---------- Componente: listado ----------

test('cargar: arma la URL desde los filtros y guarda filas y total', async () => {
  const { window } = cargar();
  const pedidos = [];
  window.pedir = async (url) => {
    pedidos.push(url);
    return { resultados: [{ id: 1 }], total: 1 };
  };
  const pantalla = crearPantalla(window);
  pantalla.filtros.numero = 'V-000001';
  await pantalla.cargar(1);
  assert.equal(pantalla.filas.length, 1);
  assert.equal(pantalla.total, 1);
  assert.ok(pedidos[0].includes('numero=V-000001'));
  assert.ok(pedidos[0].includes('pagina=1'));
});

test('quitarClienteChip: borra el chip y el filtro, y vuelve a buscar', async () => {
  const { window } = cargar();
  const pedidos = [];
  window.pedir = async (url) => { pedidos.push(url); return { resultados: [], total: 0 }; };
  const pantalla = crearPantalla(window, { clienteIdInicial: 5 });
  assert.equal(pantalla.filtros.cliente_id, 5);
  await pantalla.quitarClienteChip();
  assert.equal(pantalla.clienteChip, null);
  assert.equal(pantalla.filtros.cliente_id, null);
  assert.ok(pedidos.some((u) => !u.includes('cliente_id')));
});

test('limpiarFiltros: resetea los campos de la barra pero mantiene el chip de cliente', async () => {
  const { window } = cargar();
  window.pedir = async () => ({ resultados: [], total: 0 });
  const pantalla = crearPantalla(window, { clienteIdInicial: 5 });
  pantalla.filtros.numero = 'V-000001';
  pantalla.filtros.estado = 'confirmada';
  await pantalla.limpiarFiltros();
  assert.equal(pantalla.filtros.numero, '');
  assert.equal(pantalla.filtros.estado, '');
  assert.equal(pantalla.filtros.cliente_id, 5);
});

// ---------- Componente: detalle ----------

function pedirDiferido() {
  const pendientes = [];
  const pedir = (url) => new Promise((resolver) => { pendientes.push({ url, resolver }); });
  return { pedir, pendientes };
}

test('abrirDetalle: descarta la venta que ya no es la abierta (secuenciado por id)', async () => {
  const { window } = cargar();
  const { pedir, pendientes } = pedirDiferido();
  window.pedir = pedir;
  const pantalla = crearPantalla(window);

  const p1 = pantalla.abrirDetalle({ id: 1 });
  const p2 = pantalla.abrirDetalle({ id: 2 });   // se abrió otra venta antes de que llegue la primera

  const pedidoUno = pendientes.find((p) => p.url.endsWith('/ventas/1'));
  const pedidoDos = pendientes.find((p) => p.url.endsWith('/ventas/2'));
  assert.ok(pedidoUno && pedidoDos);

  pedidoUno.resolver({ id: 1, numero: 'V-000001' });
  await p1;
  assert.equal(pantalla.detalle, null);   // la de la venta 1 se descarta: ya no es la abierta

  pedidoDos.resolver({ id: 2, numero: 'V-000002' });
  await p2;
  assert.equal(pantalla.detalle.id, 2);
  assert.equal(pantalla.detalleId, 2);
});

function ventaConfirmada(id = 5) {
  return { id, numero: `V-00000${id}`, estado: 'confirmada', items: [], pagos: [] };
}

test('confirmarAnulacion: sin motivo no manda nada', async () => {
  const { window } = cargar();
  let llamadas = 0;
  window.pedir = async () => { llamadas++; return {}; };
  const pantalla = crearPantalla(window);
  pantalla.detalle = ventaConfirmada();
  pantalla.motivoAnulacion = '   ';
  await pantalla.confirmarAnulacion();
  assert.equal(llamadas, 0);
});

test('confirmarAnulacion: si no se confirma el diálogo, no anula', async () => {
  const { window } = cargar();
  window.confirmar = () => Promise.resolve(false);
  let llamadas = 0;
  window.pedir = async () => { llamadas++; return {}; };
  const pantalla = crearPantalla(window);
  pantalla.detalle = ventaConfirmada();
  pantalla.motivoAnulacion = 'No corresponde el descuento aplicado';
  await pantalla.confirmarAnulacion();
  assert.equal(llamadas, 0);
});

test('confirmarAnulacion: éxito manda el motivo, recarga el detalle y la fila, y avisa', async () => {
  const { window, toasts } = cargar();
  window.confirmar = () => Promise.resolve(true);
  const pedidos = [];
  const anulada = { ...ventaConfirmada(), estado: 'anulada', anulada_en: '2026-09-28T10:00:00', motivo_anulacion: 'Error de carga' };
  window.pedir = async (url, op = {}) => {
    pedidos.push({ url, op });
    if (url.endsWith('/ventas/5/anular')) {
      assert.equal(op.method, 'POST');
      assert.deepEqual(plano(op.body), { motivo: 'Error de carga' });
      return anulada;
    }
    if (url.endsWith('/ventas/5')) return anulada;
    if (url.startsWith('/api/v1/ventas?')) return { resultados: [], total: 0 };
    throw new Error(`url inesperada: ${url}`);
  };
  const pantalla = crearPantalla(window);
  pantalla.detalle = ventaConfirmada();
  pantalla.detalleId = 5;
  pantalla.motivoAnulacion = 'Error de carga';
  pantalla.anulando = true;
  await pantalla.confirmarAnulacion();
  assert.equal(pantalla.anulando, false);
  assert.equal(pantalla.detalle.estado, 'anulada');
  assert.equal(pantalla.anulandoEnCurso, false);
  assert.equal(toasts.at(-1).mensaje, 'Venta anulada.');
  assert.ok(pedidos.some((p) => p.url.endsWith('/ventas/5/anular')));
});

test('puedeAnularVenta: refleja el permiso y el estado de la venta abierta', () => {
  const { window } = cargar();
  const pantalla = crearPantalla(window, { puedeAnular: false });
  pantalla.detalle = ventaConfirmada();
  assert.equal(pantalla.puedeAnularVenta(), false);
  pantalla.puedeAnular = true;
  assert.equal(pantalla.puedeAnularVenta(), true);
  pantalla.detalle = { ...ventaConfirmada(), estado: 'anulada' };
  assert.equal(pantalla.puedeAnularVenta(), false);
});
