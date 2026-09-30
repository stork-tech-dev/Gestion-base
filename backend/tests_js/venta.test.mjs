// Tests de la pantalla de venta (backend/app/static/js/venta.js): cada
// función pura de window.ventaLogica y los flujos delicados del componente
// (un solo POST /ventas aunque se escaneen dos productos seguidos, cualquier
// 409 de confirmar → recalcular). Mismos stubs mínimos que productos.test.mjs.
// Correr con: node --test backend/tests_js/
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const RUTA_APP = new URL('../app/static/js/app.js', import.meta.url);
const RUTA_CLIENTE_FORM = new URL('../app/static/js/cliente_form.js', import.meta.url);
const RUTA_VENTA = new URL('../app/static/js/venta.js', import.meta.url);

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
  vm.runInNewContext(readFileSync(RUTA_CLIENTE_FORM, 'utf8'), contexto);
  vm.runInNewContext(readFileSync(RUTA_VENTA, 'utf8'), contexto);
  window.toast = (mensaje, tipo) => toasts.push({ mensaje, tipo });
  return { window, toasts };
}

const { window: W } = cargar();
const L = W.ventaLogica;
// Los objetos creados dentro del vm tienen otro prototipo: se comparan por JSON.
const plano = (x) => JSON.parse(JSON.stringify(x));

// ---------- ventaLogica ----------

test('esCodigo: dos letras, tres dígitos y un verificador opcional', () => {
  assert.equal(L.esCodigo('AB123'), true);
  assert.equal(L.esCodigo('ab1234'), true);
  assert.equal(L.esCodigo('  AB123X  '), true);
  assert.equal(L.esCodigo('AB12'), false);
  assert.equal(L.esCodigo('AB1234X'), false);
  assert.equal(L.esCodigo('remera azul'), false);
  assert.equal(L.esCodigo(''), false);
  assert.equal(L.esCodigo(null), false);
});

test('puedeAgregar: con stock o stock infinito', () => {
  assert.equal(L.puedeAgregar({ stock: 3, stock_infinito: false }), true);
  assert.equal(L.puedeAgregar({ stock: 0, stock_infinito: true }), true);
  assert.equal(L.puedeAgregar({ stock: 0, stock_infinito: false }), false);
  assert.equal(L.puedeAgregar({ stock: -2, stock_infinito: false }), false);
});

test('cantidadValida: entero 0-999 o null', () => {
  assert.equal(L.cantidadValida('3'), 3);
  assert.equal(L.cantidadValida(''), null);
  assert.equal(L.cantidadValida('2.5'), null);
  assert.equal(L.cantidadValida('-1'), null);
  assert.equal(L.cantidadValida('1000'), null);
  assert.equal(L.cantidadValida('0'), 0);
});

test('puedeSumar: tope de stock (null = infinito)', () => {
  assert.equal(L.puedeSumar({ stock: 3, cantidad: 3 }), false);
  assert.equal(L.puedeSumar({ stock: 3, cantidad: 2 }), true);
  assert.equal(L.puedeSumar({ stock: null, cantidad: 999 }), true);
});

test('textoDescuentoLinea: Promo, Promo parcial, "X% · Motivo" o vacío', () => {
  assert.equal(L.textoDescuentoLinea({ unidades_en_promocion: 3, cantidad: 3, descuento_item: '0.00', motivo: null }),
    'Promo');
  assert.equal(L.textoDescuentoLinea({ unidades_en_promocion: 1, cantidad: 3, descuento_item: '0.00', motivo: null }),
    'Promo (1 de 3)');
  assert.equal(L.textoDescuentoLinea({ unidades_en_promocion: 0, cantidad: 2, descuento_item: '15.00',
    motivo: { id: 1, nombre: 'Fallado' } }), '15% · Fallado');
  assert.equal(L.textoDescuentoLinea({ unidades_en_promocion: 0, cantidad: 1, descuento_item: '0.00', motivo: null }),
    '');
});

test('puedeDescontarLinea: con permiso y fuera de promoción', () => {
  assert.equal(L.puedeDescontarLinea({ unidades_en_promocion: 0 }, true), true);
  assert.equal(L.puedeDescontarLinea({ unidades_en_promocion: 2 }, true), false);
  assert.equal(L.puedeDescontarLinea({ unidades_en_promocion: 0 }, false), false);
});

test('porcentajeDescuentoGeneral: % sobre el total antes de aplicarlo', () => {
  assert.equal(L.porcentajeDescuentoGeneral({ descuento_general: '3.00', cobrable: '80.00' }), 3.6);
  assert.equal(L.porcentajeDescuentoGeneral({ descuento_general: '0.00', cobrable: '80.00' }), 0);
  assert.equal(L.porcentajeDescuentoGeneral(null), 0);
});

test('cuerpoDescuentoGeneral: cuerpo de POST /descuento-general', () => {
  assert.deepEqual(plano(L.cuerpoDescuentoGeneral('total', '80')), { total: '80', porcentaje: null });
  assert.deepEqual(plano(L.cuerpoDescuentoGeneral('porcentaje', '10,5')), { porcentaje: '10.5', total: null });
  assert.equal(L.cuerpoDescuentoGeneral('total', ''), null);
  assert.equal(L.cuerpoDescuentoGeneral('total', '   '), null);
});

test('moverIndice: circular y -1 sin resultados', () => {
  assert.equal(L.moverIndice(-1, 3, 1), 0);
  assert.equal(L.moverIndice(2, 3, 1), 0);
  assert.equal(L.moverIndice(0, 3, -1), 2);
  assert.equal(L.moverIndice(-1, 3, -1), 1);
  assert.equal(L.moverIndice(0, 0, 1), -1);
});

test('pagosParaEnviar: descarta filas sin medio y convierte tipos', () => {
  const pagos = L.pagosParaEnviar([
    { medio_de_pago_id: '3', monto: '5000', plan_cuotas_id: '7' },
    { medio_de_pago_id: '', monto: '', plan_cuotas_id: '' },
    { medio_de_pago_id: '1', monto: '', plan_cuotas_id: '' },
  ]);
  assert.deepEqual(plano(pagos), [
    { medio_de_pago_id: 3, monto: '5000', plan_cuotas_id: 7 },
    { medio_de_pago_id: 1, monto: '0.01', plan_cuotas_id: null },
  ]);
});

test('puedeConfirmar: venta con ítems, pagos y turno', () => {
  const venta = { items: [{ id: 1 }], pagos: [{ id: 1 }] };
  assert.equal(L.puedeConfirmar(venta, true), true);
  assert.equal(L.puedeConfirmar(venta, false), false);
  assert.equal(L.puedeConfirmar({ items: [], pagos: [{ id: 1 }] }, true), false);
  assert.equal(L.puedeConfirmar({ items: [{ id: 1 }], pagos: [] }, true), false);
  assert.equal(L.puedeConfirmar(null, true), false);
});

test('recalcularTrasConfirmar: cualquier 409, y nada más', () => {
  const error = (status, mensaje) => Object.assign(new Error(mensaje), { status });
  assert.equal(L.recalcularTrasConfirmar(error(409, 'Los precios cambiaron mientras cargabas la venta')), true);
  assert.equal(L.recalcularTrasConfirmar(error(409, 'Cargá los medios de pago para cubrir el total')), true);
  assert.equal(L.recalcularTrasConfirmar(error(400, 'Dato inválido')), false);
  assert.equal(L.recalcularTrasConfirmar(error(undefined, 'sin red')), false);
  assert.equal(L.recalcularTrasConfirmar(null), false);
});

test('montoEditable: solo el primero de dos pagos', () => {
  const dos = [{}, {}];
  assert.equal(L.montoEditable(0, dos), true);
  assert.equal(L.montoEditable(1, dos), false);
  assert.equal(L.montoEditable(0, [{}]), false);
});

const pago = (medio, monto, plan = null) => ({
  medio: { id: medio, nombre: 'M' }, monto, plan: plan ? { id: plan, cuotas: 3, recargo_cliente: '10.00' } : null,
});

test('filasDePagos: sale de venta.pagos y siempre hay una fila', () => {
  assert.deepEqual(plano(L.filasDePagos(null, [])), [{ medio_de_pago_id: '', monto: '', plan_cuotas_id: '' }]);
  assert.deepEqual(plano(L.filasDePagos({ pagos: [pago(1, '8000.00'), pago(2, '2000.00', 5)] }, [])), [
    { medio_de_pago_id: '1', monto: '8000.00', plan_cuotas_id: '' },
    { medio_de_pago_id: '2', monto: '2000.00', plan_cuotas_id: '5' },
  ]);
});

test('filasDePagos: conserva la fila de "+ Otro medio" y el monto tipeado del primero', () => {
  const actuales = [
    { medio_de_pago_id: '1', monto: '3000', plan_cuotas_id: '' },
    { medio_de_pago_id: '', monto: '', plan_cuotas_id: '' },
  ];
  // La API tiene un solo pago (con todo lo cobrable): lo tipeado no se pisa.
  assert.deepEqual(plano(L.filasDePagos({ pagos: [pago(1, '10000.00')] }, actuales)), [
    { medio_de_pago_id: '1', monto: '3000', plan_cuotas_id: '' },
    { medio_de_pago_id: '', monto: '', plan_cuotas_id: '' },
  ]);
  // Una sola fila: el monto es el de la API.
  assert.deepEqual(plano(L.filasDePagos({ pagos: [pago(1, '10000.00')] }, [actuales[0]])), [
    { medio_de_pago_id: '1', monto: '10000.00', plan_cuotas_id: '' },
  ]);
  // La API borró los pagos (ya no cubrían el total): queda una fila vacía.
  assert.deepEqual(plano(L.filasDePagos({ pagos: [] }, actuales)), [
    { medio_de_pago_id: '', monto: '', plan_cuotas_id: '' },
  ]);
});

// ---------- Componente ----------

function ventaVacia(id = 9) {
  return { id, numero: 'V-000009', items: [], pagos: [], cobrable: '0.00', total: '0.00', promocion: null, cliente: null };
}

function crearPantalla(window) {
  const pantalla = window.ventaPantalla({
    puedeDescontar: true, puedeVerClientes: true, puedeCrearCliente: true, hayTurno: true, condicionesIva: [],
  });
  pantalla.$nextTick = (fn) => fn();
  pantalla.$refs = {};
  return pantalla;
}

test('asegurarVenta: dos escaneos seguidos hacen un solo POST /ventas', async () => {
  const { window } = cargar();
  const pedidos = [];
  let resolverInicio;
  window.pedir = (url, op = {}) => {
    pedidos.push(`${op.method || 'GET'} ${url}`);
    return new Promise((r) => { resolverInicio = r; });
  };
  const pantalla = crearPantalla(window);
  const a = pantalla.asegurarVenta();
  const b = pantalla.asegurarVenta();
  resolverInicio(ventaVacia());
  assert.equal(await a, 9);
  assert.equal(await b, 9);
  assert.deepEqual(pedidos, ['POST /api/v1/ventas']);
});

test('confirmar: 409 de precios cambiados → toast y recalcular', async () => {
  const { window, toasts } = cargar();
  const pedidos = [];
  const venta = { ...ventaVacia(), items: [{ id: 1, motivo: null }], pagos: [pago(1, '1000.00')], cobrable: '1000.00', total: '1000.00' };
  const recalculada = { ...venta, total: '1200.00', cobrable: '1200.00', pagos: [pago(1, '1200.00')] };
  window.pedir = async (url, op = {}) => {
    pedidos.push(`${op.method || 'GET'} ${url}`);
    if (url.endsWith('/confirmar')) {
      assert.deepEqual(plano(op.body), { total_esperado: '1000.00' });
      const error = new Error('Los precios cambiaron mientras cargabas la venta: revisá el total y volvé a confirmar.');
      error.status = 409;
      throw error;
    }
    if (url.endsWith('/recalcular')) return recalculada;
    return [];
  };
  const pantalla = crearPantalla(window);
  pantalla.mostrar(venta);
  await pantalla.confirmarVenta();
  assert.ok(pedidos.includes('POST /api/v1/ventas/9/recalcular'));
  assert.equal(pantalla.venta.total, '1200.00');
  assert.equal(toasts[0].tipo, 'error');
  assert.equal(pantalla.confirmadaAbierta, false);
});

test('confirmar: 409 que no es de precios (pagos borrados) → toast con el mensaje y recalcular', async () => {
  const { window, toasts } = cargar();
  const pedidos = [];
  const venta = { ...ventaVacia(), items: [{ id: 1, motivo: null }], pagos: [pago(1, '1000.00', 5)], cobrable: '1000.00', total: '1100.00' };
  // El recálculo persistió el borrado de los pagos (el plan dejó de valer).
  const recalculada = { ...venta, total: '1000.00', pagos: [] };
  window.pedir = async (url, op = {}) => {
    pedidos.push(`${op.method || 'GET'} ${url}`);
    if (url.endsWith('/confirmar')) {
      const error = new Error('Cargá los medios de pago para cubrir el total');
      error.status = 409;
      throw error;
    }
    if (url.endsWith('/recalcular')) return recalculada;
    return [];
  };
  const pantalla = crearPantalla(window);
  pantalla.mostrar(venta);
  await pantalla.confirmarVenta();
  assert.ok(pedidos.includes('POST /api/v1/ventas/9/recalcular'));
  assert.deepEqual(plano(pantalla.venta.pagos), []);
  assert.deepEqual(plano(pantalla.pagos), [{ medio_de_pago_id: '', monto: '', plan_cuotas_id: '' }]);
  assert.equal(toasts[0].mensaje, 'Cargá los medios de pago para cubrir el total');
  assert.equal(toasts[0].tipo, 'error');
  assert.equal(pantalla.confirmadaAbierta, false);
});

test('confirmar: éxito limpia la pantalla y abre el modal con el código', async () => {
  const { window } = cargar();
  const venta = { ...ventaVacia(), items: [{ id: 1, motivo: null }], pagos: [pago(1, '1000.00')], cobrable: '1000.00', total: '1000.00' };
  window.pedir = async (url) => (url.endsWith('/confirmar') ? { ...venta, estado: 'confirmada', codigo_cambio: 'K7P2QX' } : []);
  const pantalla = crearPantalla(window);
  pantalla.mostrar(venta);
  await pantalla.confirmarVenta();
  assert.equal(pantalla.venta, null);
  assert.equal(pantalla.confirmadaAbierta, true);
  assert.equal(pantalla.confirmada.codigo_cambio, 'K7P2QX');
});

test('ESC con un modal abierto no descarta la venta', () => {
  const { window } = cargar();
  let confirmaciones = 0;
  window.confirmar = () => { confirmaciones++; return Promise.resolve(false); };
  const pantalla = crearPantalla(window);
  pantalla.venta = ventaVacia();
  pantalla.descuentoAbierto = true;
  pantalla.alCancelar();
  assert.equal(confirmaciones, 0);
  pantalla.descuentoAbierto = false;
  pantalla.alCancelar();
  assert.equal(confirmaciones, 1);
});
