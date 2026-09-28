/* Pantalla de venta (/ventas/nueva): buscador de productos, carrito,
   descuento por ítem, cliente, promoción, hasta 2 medios de pago y
   confirmación. TODA la aritmética la hace la API: el carrito es una venta
   `en_curso` persistida y esta pantalla solo muestra la última VentaResponse
   (`venta`) y manda acciones. Atajos: F2 buscar, F10 confirmar, ESC descartar
   (eventos globales de app.js). */
(function () {
  'use strict';

  const API = '/api/v1/ventas';
  const API_CLIENTES = '/api/v1/clientes';
  const ESPERA_BUSQUEDA_MS = 300;
  const LIMITE_PRODUCTOS = 8;
  const MAX_PAGOS = 2;
  // Inicio del 409 de confirmar cuando el total cambió (services/ventas.py).
  const PRECIOS_CAMBIARON = 'Los precios cambiaron';

  const filaPagoVacia = () => ({ medio_de_pago_id: '', monto: '', plan_cuotas_id: '' });

  // ---------- Lógica pura (testeada con node --test en tests_js/venta.test.mjs) ----------
  window.ventaLogica = {
    // Código de etiqueta o SKU: Enter lo agrega directo sin abrir el desplegable.
    esCodigo: (texto) => /^[A-Za-z]{2}[0-9]{3}[0-9A-Za-z]?$/.test(String(texto || '').trim()),
    // En el desplegable: sin stock y sin stock infinito → deshabilitado.
    puedeAgregar: (p) => p.stock_infinito || p.stock > 0,
    // Texto de la columna Descuento.
    textoDescuento: (item) => item.en_promocion ? 'Promo'
      : (Number(item.descuento_item) > 0 ? `${Number(item.descuento_item)}% · ${item.motivo?.nombre ?? ''}` : ''),
    puedeDescontar: (item, permiso) => permiso && !item.en_promocion,
    // Índice del desplegable con flechas (circular, -1 = ninguno).
    moverIndice: (actual, total, delta) => total === 0 ? -1 : (actual + delta + total) % total,
    // Pagos que se mandan al backend: el monto del primero solo importa si hay dos.
    pagosParaEnviar: (filas) => filas.filter((f) => f.medio_de_pago_id)
      .map((f) => ({ medio_de_pago_id: Number(f.medio_de_pago_id), monto: String(f.monto || '0.01'),
                     plan_cuotas_id: f.plan_cuotas_id ? Number(f.plan_cuotas_id) : null })),
    puedeConfirmar: (venta, hayTurno) => !!venta && venta.items.length > 0 && venta.pagos.length > 0 && hayTurno,
    // Solo el monto del primero de dos pagos lo tipea el usuario; el del único
    // pago y el del segundo los fija la API (lo cobrable / el resto).
    montoEditable: (indice, filas) => indice === 0 && filas.length === MAX_PAGOS,
    // Filas de pago a partir de la última respuesta: medio, plan y monto salen
    // de `venta.pagos`. Se conservan (a) una fila recién agregada con
    // "+ Otro medio" que todavía no tiene medio y (b) el monto tipeado en la
    // primera fila mientras la segunda no tiene medio (la API todavía tiene un
    // solo pago y lo pondría en el total). Siempre hay al menos una fila.
    filasDePagos: (venta, actuales = []) => {
      const filas = (venta ? venta.pagos : []).map((p) => ({
        medio_de_pago_id: String(p.medio.id), monto: String(p.monto), plan_cuotas_id: p.plan ? String(p.plan.id) : '',
      }));
      const hayFilaSinMedio = actuales.some((f) => !f.medio_de_pago_id);
      if (filas.length === 1 && actuales.length === MAX_PAGOS && hayFilaSinMedio
          && actuales[0].medio_de_pago_id === filas[0].medio_de_pago_id) {
        filas[0].monto = actuales[0].monto;
      }
      if (filas.length < MAX_PAGOS && hayFilaSinMedio) filas.push(filaPagoVacia());
      if (!filas.length) filas.push(filaPagoVacia());
      return filas;
    },
  };
  const L = window.ventaLogica;

  // ---------- Buscador remoto con desplegable (productos y clientes) ----------
  // `url(texto)` arma el pedido; cada buscador tiene su propio ultimaRespuesta.
  function buscadorRemoto(url) {
    return {
      texto: '',
      resultados: [],
      abierto: false,
      activo: -1,
      _espera: null,
      _ultima: window.ultimaRespuesta(),
      programar() {
        clearTimeout(this._espera);
        this._espera = setTimeout(() => this.buscar(), ESPERA_BUSQUEDA_MS);
      },
      async buscar() {
        clearTimeout(this._espera);
        const texto = this.texto.trim();
        if (!texto) { this.cerrar(); return; }
        try {
          const resultados = await this._ultima(window.pedir(url(texto)));
          if (resultados === undefined) return;  // llegó un pedido más nuevo
          this.resultados = resultados;
          this.activo = -1;
          this.abierto = true;
        } catch (e) {
          window.toast(e.message, 'error');
        }
      },
      mover(delta) {
        if (!this.abierto) return;
        this.activo = L.moverIndice(this.activo, this.resultados.length, delta);
      },
      cerrar() {
        clearTimeout(this._espera);
        this._ultima(Promise.resolve());  // descarta la búsqueda en vuelo
        this.abierto = false;
        this.resultados = [];
        this.activo = -1;
      },
      limpiar() {
        this.texto = '';
        this.cerrar();
      },
    };
  }

  window.ventaPantalla = function ({ puedeDescontar, puedeVerClientes, puedeCrearCliente, hayTurno, condicionesIva }) {
    return {
      puedeDescontar,
      puedeVerClientes,
      puedeCrearCliente,
      hayTurno,
      condicionesIva,
      venta: null,
      cargando: true,
      productos: buscadorRemoto((t) => `${API}/productos?${new URLSearchParams({ busqueda: t, limite: LIMITE_PRODUCTOS })}`),
      clientes: buscadorRemoto((t) => `${API_CLIENTES}/buscar?${new URLSearchParams({ q: t })}`),
      opcionesDescuento: { motivos: [], porcentajes: [], tope: null },
      promociones: [],
      promocionElegida: '',
      pagos: [filaPagoVacia()],
      opcionesPago: [[], []],
      confirmando: false,
      descartando: false,

      // Popover (modal) de descuento de un ítem.
      descuentoAbierto: false,
      descuento: { item: null, motivo_id: '', porcentaje: '' },
      // Alta rápida de cliente.
      clienteAbierto: false,
      clienteForm: window.clienteFormulario.vacio(),
      errores: {},
      guardandoCliente: false,
      // Venta confirmada.
      confirmadaAbierta: false,
      confirmada: null,

      _ultimaVenta: window.ultimaRespuesta(),
      _ultimasPromos: window.ultimaRespuesta(),
      _ultimasOpcionesPago: [window.ultimaRespuesta(), window.ultimaRespuesta()],
      _clavesOpcionesPago: [null, null],
      _iniciando: null,
      _enVuelo: new Set(),
      _pidiendoConfirmacion: false,

      async init() {
        this.$watch('confirmadaAbierta', (abierta) => { if (!abierta) this.enfocarBuscador(); });
        this.enfocarBuscador();
        this.cargarOpcionesDescuento();
        try {
          const venta = await this._ultimaVenta(window.pedir(`${API}/en-curso`));
          if (venta !== undefined) this.mostrar(venta);
        } catch (e) {
          window.toast(e.message, 'error');
        } finally {
          this.cargando = false;
        }
      },

      // ---------- Estado derivado (solo presentación) ----------
      get items() { return this.venta ? this.venta.items : []; },
      get hayModalAbierto() {
        return this.descuentoAbierto || this.clienteAbierto || this.confirmadaAbierta || this._pidiendoConfirmacion;
      },
      get puedeConfirmar() { return L.puedeConfirmar(this.venta, this.hayTurno) && !this.confirmando; },
      get puedeOtroMedio() {
        return !!this.venta && this.items.length > 0 && this.pagos.length < MAX_PAGOS && !!this.pagos[0].medio_de_pago_id;
      },
      // Importe con signo de pesos (formato es-AR de app.js).
      plata: (valor) => '$ ' + window.pesos(valor),
      textoDescuento: (item) => L.textoDescuento(item),
      puedeDescontarItem(item) { return L.puedeDescontar(item, this.puedeDescontar); },
      montoEditable(indice) { return L.montoEditable(indice, this.pagos); },
      planesDe(indice) {
        const fila = this.pagos[indice];
        const medio = (this.opcionesPago[indice] || []).find((m) => String(m.id) === fila.medio_de_pago_id);
        return medio ? medio.planes : [];
      },
      textoPlan: (plan) => `${plan.cuotas} cuotas` + (Number(plan.recargo_cliente) > 0
        ? ` (recargo ${Number(plan.recargo_cliente)}%)` : ' sin interés'),
      textoCondicionIva(valor) {
        const par = this.condicionesIva.find(([v]) => v === valor);
        return par ? par[1] : valor;
      },
      get motivoElegido() {
        return this.opcionesDescuento.motivos.find((m) => String(m.id) === String(this.descuento.motivo_id)) || null;
      },

      // ---------- Respuestas de la API ----------
      /** Muestra la última VentaResponse y recarga lo que depende de ella. */
      mostrar(venta) {
        this.venta = venta;
        this.pagos = L.filasDePagos(venta, this.pagos);
        this.promocionElegida = venta && venta.promocion ? String(venta.promocion.id) : '';
        if (venta && venta.items.length) {
          this.cargarPromociones();
          this.cargarOpcionesPago();
        } else {
          this.promociones = [];
        }
      },

      /** Acción que devuelve una VentaResponse (o {venta, aviso}): secuenciada
          (solo se muestra la del último pedido lanzado) y registrada para que
          confirmar espere a que terminen las escrituras en vuelo. */
      async accion(promesa) {
        this._enVuelo.add(promesa);
        try {
          const respuesta = await this._ultimaVenta(promesa);
          if (respuesta !== undefined) this.mostrar(respuesta);
          return true;
        } catch (e) {
          window.toast(e.message, 'error');
          return false;
        } finally {
          this._enVuelo.delete(promesa);
        }
      },

      /** Id de la venta en curso; la inicia si hace falta (un solo POST
          aunque se escaneen dos productos seguidos). */
      async asegurarVenta() {
        if (this.venta) return this.venta.id;
        if (!this._iniciando) {
          this._iniciando = window.pedir(API, { method: 'POST' })
            .then((venta) => { if (!this.venta) this.mostrar(venta); return venta.id; })
            .finally(() => { this._iniciando = null; });
        }
        return this._iniciando;
      },

      limpiar() {
        this._ultimaVenta(Promise.resolve());  // descarta respuestas en vuelo de la venta anterior
        this.venta = null;
        this.pagos = [filaPagoVacia()];
        this.opcionesPago = [[], []];
        this._clavesOpcionesPago = [null, null];
        this.promociones = [];
        this.promocionElegida = '';
        this.productos.limpiar();
        this.clientes.limpiar();
      },

      enfocarBuscador() {
        this.$nextTick(() => this.$refs.buscador && this.$refs.buscador.focus());
      },

      // F2: enfoca el buscador (salvo que haya un modal abierto encima).
      alBuscar() {
        if (!this.hayModalAbierto) this.enfocarBuscador();
      },

      /** ESC dentro de un buscador con el desplegable abierto: solo lo cierra
          (y no llega al atajo global, que descartaría la venta). */
      escapeEn(buscador, evento) {
        if (!buscador.abierto) return;
        evento.stopPropagation();
        buscador.cerrar();
      },

      // ---------- Productos ----------
      async alEnter() {
        const p = this.productos;
        if (p.abierto && p.activo >= 0) return this.agregarProducto(p.resultados[p.activo]);
        const texto = p.texto.trim();
        if (!texto) return;
        if (L.esCodigo(texto)) return this.agregarPorCodigo(texto);
        return p.buscar();
      },

      async agregarPorCodigo(codigo) {
        this.productos.limpiar();
        try {
          const producto = await window.pedir(`${API}/producto?${new URLSearchParams({ codigo })}`);
          await this._agregar(producto.id);
        } catch (e) {
          window.toast(e.message, 'error');
        }
      },

      async agregarProducto(producto) {
        if (!producto || !L.puedeAgregar(producto)) return;
        this.productos.limpiar();
        this.enfocarBuscador();
        await this._agregar(producto.id);
      },

      async _agregar(productoId) {
        let ventaId;
        try {
          ventaId = await this.asegurarVenta();
        } catch (e) {
          window.toast(e.message, 'error');
          return;
        }
        const pedido = window.pedir(`${API}/${ventaId}/items`, { method: 'POST', body: { producto_id: productoId } })
          .then((r) => { if (r.aviso) window.toast(r.aviso, 'error'); return r.venta; });
        await this.accion(pedido);
      },

      async quitarItem(item) {
        await this.accion(window.pedir(`${API}/${this.venta.id}/items/${item.id}`, { method: 'DELETE' }));
      },

      // ---------- Descuento por ítem ----------
      async cargarOpcionesDescuento() {
        if (!this.puedeDescontar) return;
        try {
          this.opcionesDescuento = await window.pedir(`${API}/opciones-descuento`);
        } catch (e) {
          window.toast(e.message, 'error');
        }
      },

      abrirDescuento(item) {
        this.descuento = {
          item,
          motivo_id: item.motivo ? String(item.motivo.id) : '',
          porcentaje: Number(item.descuento_item) > 0 ? String(Number(item.descuento_item)) : '',
        };
        this.descuentoAbierto = true;
      },

      async aplicarDescuento(quitar = false) {
        const motivo = quitar ? null : this.motivoElegido;
        if (!quitar && !motivo) { window.toast('Elegí un motivo.', 'error'); return; }
        const porcentaje = motivo && motivo.porcentaje_sugerido === null && this.descuento.porcentaje
          ? Number(this.descuento.porcentaje) : null;
        if (motivo && motivo.porcentaje_sugerido === null && porcentaje === null) {
          window.toast('Elegí el porcentaje de descuento.', 'error');
          return;
        }
        const ok = await this.accion(window.pedir(`${API}/${this.venta.id}/descuento`, {
          method: 'POST',
          body: { item_id: this.descuento.item.id, motivo_id: motivo ? motivo.id : null, porcentaje },
        }));
        if (ok) this.descuentoAbierto = false;
      },

      // ---------- Cliente ----------
      async elegirCliente(cliente) {
        this.clientes.limpiar();
        let ventaId;
        try {
          ventaId = await this.asegurarVenta();
        } catch (e) {
          window.toast(e.message, 'error');
          return;
        }
        await this.accion(window.pedir(`${API}/${ventaId}/cliente`, {
          method: 'POST', body: { cliente_id: cliente ? cliente.id : null },
        }));
      },

      alEnterCliente() {
        const c = this.clientes;
        if (c.abierto && c.activo >= 0) return this.elegirCliente(c.resultados[c.activo]);
        return c.buscar();
      },

      nuevoCliente() {
        this.clienteForm = window.clienteFormulario.vacio();
        this.errores = {};
        this.clienteAbierto = true;
      },

      async guardarCliente() {
        this.guardandoCliente = true;
        this.errores = {};
        try {
          const cliente = await window.pedir(API_CLIENTES, {
            method: 'POST', body: window.clienteFormulario.cuerpo(this.clienteForm),
          });
          window.toast('Cliente creado.');
          this.clienteAbierto = false;
          await this.elegirCliente(cliente);
        } catch (e) {
          this.errores = window.erroresDeCampos(e);
          window.toast(e.message, 'error');
        } finally {
          this.guardandoCliente = false;
        }
      },

      // ---------- Promoción ----------
      async cargarPromociones() {
        try {
          const promos = await this._ultimasPromos(window.pedir(`${API}/${this.venta.id}/promociones`));
          if (promos !== undefined) this.promociones = promos;
        } catch (e) {
          window.toast(e.message, 'error');
        }
      },

      async elegirPromocion() {
        const id = this.promocionElegida ? Number(this.promocionElegida) : null;
        const ok = await this.accion(window.pedir(`${API}/${this.venta.id}/promocion`, {
          method: 'POST', body: { promocion_id: id },
        }));
        // Rechazada: el select vuelve a mostrar la promoción que tiene la venta.
        if (!ok) this.promocionElegida = this.venta && this.venta.promocion ? String(this.venta.promocion.id) : '';
      },

      // ---------- Medios de pago ----------
      /** Medios activos con los planes que habilita el monto de cada fila
          (por defecto, lo cobrable). Solo se piden de nuevo si cambió el
          monto o algo que habilita cuotas sin interés (los motivos). */
      cargarOpcionesPago() {
        const venta = this.venta;
        const motivos = venta.items.map((i) => (i.motivo ? i.motivo.id : '')).join(',');
        this.pagos.forEach((fila, i) => {
          const monto = Number(fila.monto) > 0 ? String(fila.monto) : String(venta.cobrable);
          const clave = `${venta.id}|${monto}|${motivos}`;
          if (this._clavesOpcionesPago[i] === clave) return;
          this._clavesOpcionesPago[i] = clave;
          const params = Number(monto) > 0 ? `?${new URLSearchParams({ monto })}` : '';
          this._ultimasOpcionesPago[i](window.pedir(`${API}/${venta.id}/medios-de-pago${params}`))
            .then((opciones) => { if (opciones !== undefined) this.opcionesPago[i] = opciones; })
            .catch((e) => { this._clavesOpcionesPago[i] = null; window.toast(e.message, 'error'); });
        });
      },

      /** `campo`: 'medio' | 'plan' | 'monto'. Manda los pagos apenas cambian
          (decisión 1): así el total (recargos, promos por medio de pago) lo
          calcula siempre la API. */
      async cambioPago(indice, campo) {
        if (campo === 'medio') this.pagos[indice].plan_cuotas_id = '';
        const pagos = L.pagosParaEnviar(this.pagos);
        // El monto del primero solo cuenta con dos pagos cargados.
        if (campo === 'monto' && pagos.length < MAX_PAGOS) return;
        await this.accion(window.pedir(`${API}/${this.venta.id}/pagos`, { method: 'POST', body: { pagos } }));
      },

      otroMedio() {
        if (!this.puedeOtroMedio) return;
        this.pagos.push(filaPagoVacia());
        this._clavesOpcionesPago[1] = null;
        this.cargarOpcionesPago();
      },

      async quitarMedio(indice) {
        const quitada = this.pagos[indice];
        this.pagos.splice(indice, 1);
        this._clavesOpcionesPago = [null, null];
        if (!this.pagos.length) this.pagos.push(filaPagoVacia());
        if (!quitada.medio_de_pago_id) { this.cargarOpcionesPago(); return; }
        await this.accion(window.pedir(`${API}/${this.venta.id}/pagos`, {
          method: 'POST', body: { pagos: L.pagosParaEnviar(this.pagos) },
        }));
      },

      // ---------- Confirmar / descartar ----------
      async confirmarVenta() {
        if (this.hayModalAbierto || !this.puedeConfirmar) return;
        // F10 con el cursor en el monto del primer pago: el blur dispara su
        // `change` (y el POST /pagos) antes de esperar las escrituras en vuelo.
        const enFoco = document.activeElement;
        if (enFoco && typeof enFoco.blur === 'function') enFoco.blur();
        this.confirmando = true;
        try {
          // Primero terminan las escrituras en vuelo (p. ej. el cambio de un medio de pago).
          await Promise.allSettled([...this._enVuelo]);
          if (!L.puedeConfirmar(this.venta, this.hayTurno)) return;
          const venta = this.venta;
          const confirmada = await window.pedir(`${API}/${venta.id}/confirmar`, {
            method: 'POST', body: { total_esperado: String(venta.total) },
          });
          this.limpiar();
          this.confirmada = confirmada;
          this.confirmadaAbierta = true;
        } catch (e) {
          window.toast(e.message, 'error');
          if (e.status === 409 && e.message.startsWith(PRECIOS_CAMBIARON)) {
            await this.accion(window.pedir(`${API}/${this.venta.id}/recalcular`, { method: 'POST' }));
          }
        } finally {
          this.confirmando = false;
        }
      },

      alCancelar() {
        // ESC: si hay un modal abierto, no descarta (los modales se cierran solo con la X).
        if (this.hayModalAbierto || this.productos.abierto || this.clientes.abierto) return;
        this.descartar();
      },

      async descartar() {
        if (!this.venta || this.descartando || this.hayModalAbierto) return;
        this._pidiendoConfirmacion = true;
        const ok = await window.confirmar({
          titulo: `¿Descartar la venta ${this.venta.numero}?`,
          mensaje: 'Se quitan todos los productos, el cliente y los medios de pago cargados.',
          textoConfirmar: 'Descartar',
          peligro: true,
        });
        this._pidiendoConfirmacion = false;
        if (!ok || !this.venta) return;
        this.descartando = true;
        try {
          await Promise.allSettled([...this._enVuelo]);
          await window.pedir(`${API}/${this.venta.id}`, { method: 'DELETE' });
          this.limpiar();
          window.toast('Venta descartada.');
          this.enfocarBuscador();
        } catch (e) {
          window.toast(e.message, 'error');
        } finally {
          this.descartando = false;
        }
      },

      nuevaVenta() {
        this.confirmadaAbierta = false;
        this.confirmada = null;
        this.limpiar();
        this.enfocarBuscador();
      },
    };
  };
})();
