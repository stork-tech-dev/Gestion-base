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

  const filaPagoVacia = () => ({ medio_de_pago_id: '', monto: '', plan_cuotas_id: '' });

  // ---------- Lógica pura (testeada con node --test en tests_js/venta.test.mjs) ----------
  window.ventaLogica = {
    // Código de etiqueta o SKU: Enter lo agrega directo sin abrir el desplegable.
    esCodigo: (texto) => /^[A-Za-z]{2}[0-9]{3}[0-9A-Za-z]?$/.test(String(texto || '').trim()),
    // En el desplegable: sin stock y sin stock infinito → deshabilitado.
    puedeAgregar: (p) => p.stock_infinito || p.stock > 0,
    // Cantidad tipeada en una línea → entero válido o null (vacío, decimal,
    // negativo, > 999: se ignora y la fila vuelve a la cantidad de la API).
    cantidadValida: (valor) => {
      const texto = String(valor ?? '').trim();
      if (!/^\d+$/.test(texto)) return null;
      const n = Number(texto);
      return n <= 999 ? n : null;
    },
    // El + de una línea: deshabilitado si ya se llegó al stock del PRODUCTO
    // (no de esta línea sola: un producto puede estar repartido en varias
    // líneas, una con descuento y otra sin él). null = infinito.
    puedeSumar: (linea, venta) => {
      if (linea.stock === null) return true;
      const cargadas = ((venta && venta.items) || []).filter((i) => i.producto_id === linea.producto_id).length;
      return cargadas < linea.stock;
    },
    // Mientras haya un PUT de cantidad en vuelo para esta línea: deshabilita
    // −/+/input así dos clics seguidos no mandan la misma cantidad de base dos veces.
    lineaOcupada: (ocupadas, itemId) => ocupadas.has(itemId),
    // Columna Descuento de una línea.
    textoDescuentoLinea: (linea) => {
      if (linea.unidades_en_promocion) return linea.unidades_en_promocion === linea.cantidad
        ? 'Promo' : `Promo (${linea.unidades_en_promocion} de ${linea.cantidad})`;
      return Number(linea.descuento_item) > 0 ? `${Number(linea.descuento_item)}% · ${linea.motivo?.nombre ?? ''}` : '';
    },
    puedeDescontarLinea: (linea, permiso) => permiso && !linea.unidades_en_promocion,
    // % que representa el descuento general sobre el total antes de aplicarlo (1 decimal, para mostrar).
    porcentajeDescuentoGeneral: (venta) => {
      const monto = Number(venta?.descuento_general || 0);
      const base = Number(venta?.cobrable || 0) + monto;
      return monto > 0 && base > 0 ? Math.round((monto / base) * 1000) / 10 : 0;
    },
    // Cuerpo de POST /descuento-general según el modo elegido ('porcentaje' | 'total').
    cuerpoDescuentoGeneral: (modo, valor) => {
      const texto = String(valor ?? '').trim().replace(',', '.');
      if (!texto) return null;
      return modo === 'total' ? { total: texto, porcentaje: null } : { porcentaje: texto, total: null };
    },
    // El backend borra el descuento general en silencio cuando cambia el
    // carrito (_carrito_cambio) o cuando deja de entrar (red de seguridad de
    // _recalcular): de > 0 a 0 sin que el usuario lo haya pedido él mismo.
    descuentoGeneralSeBorro: (anterior, actual) =>
      !!anterior && Number(anterior.descuento_general || 0) > 0 && Number(actual?.descuento_general || 0) === 0,
    // Índice del desplegable con flechas (circular, -1 = ninguno).
    moverIndice: (actual, total, delta) => total === 0 ? -1 : (actual + delta + total) % total,
    // Pagos que se mandan al backend: el monto del primero solo importa si hay dos.
    pagosParaEnviar: (filas) => filas.filter((f) => f.medio_de_pago_id)
      .map((f) => ({ medio_de_pago_id: Number(f.medio_de_pago_id), monto: String(f.monto || '0.01'),
                     plan_cuotas_id: f.plan_cuotas_id ? Number(f.plan_cuotas_id) : null })),
    puedeConfirmar: (venta, hayTurno) => !!venta && venta.items.length > 0 && venta.pagos.length > 0 && hayTurno,
    // CUALQUIER 409 de confirmar (no solo "Los precios cambiaron") pide
    // POST /recalcular: confirmar recalcula sin commitear y puede haber borrado
    // los pagos (plan que dejó de valer, medio desactivado, resto ≤ 0). El
    // recálculo lo persiste y la pantalla vuelve a mostrar lo que hay en la base.
    recalcularTrasConfirmar: (error) => !!error && error.status === 409,
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
      descuentoGeneral: { modo: 'total', valor: '' },

      // Popover (modal) de descuento de una línea.
      descuentoAbierto: false,
      descuento: { linea: null, motivo_id: '', porcentaje: '' },
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
      _lineasOcupadas: new Set(),
      _descuentoGeneralAMano: false,
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
      // Carrito que muestra la tabla: unidades agrupadas por producto + descuento (Task 3).
      get lineas() { return this.venta ? this.venta.lineas : []; },
      get hayModalAbierto() {
        return this.descuentoAbierto || this.clienteAbierto || this.confirmadaAbierta || this._pidiendoConfirmacion;
      },
      get puedeConfirmar() { return L.puedeConfirmar(this.venta, this.hayTurno) && !this.confirmando; },
      get puedeOtroMedio() {
        return !!this.venta && this.items.length > 0 && this.pagos.length < MAX_PAGOS && !!this.pagos[0].medio_de_pago_id;
      },
      // Importe con signo de pesos (formato es-AR de app.js).
      plata: (valor) => '$ ' + window.pesos(valor),
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
        const anterior = this.venta;
        this.venta = venta;
        this.pagos = L.filasDePagos(venta, this.pagos);
        this.promocionElegida = venta && venta.promocion ? String(venta.promocion.id) : '';
        if (venta && venta.items.length) {
          this.cargarPromociones();
          this.cargarOpcionesPago();
        } else {
          this.promociones = [];
        }
        // Aviso solo si el borrado NO lo pidió el propio usuario (aplicar uno
        // nuevo o "Quitar"): esas dos acciones prenden _descuentoGeneralAMano.
        if (!this._descuentoGeneralAMano && L.descuentoGeneralSeBorro(anterior, venta)) {
          window.toast('Se quitó el descuento general porque cambió la venta.');
        }
      },

      /** Acción que devuelve una VentaResponse: secuenciada (solo se muestra
          la del último pedido lanzado) y registrada para que confirmar espere
          a que terminen las escrituras en vuelo (y no confirme si alguna
          falló: ver `_ejecutarAccion`). */
      accion(promesa) {
        // `_enVuelo` guarda la promesa de ESTA función (nunca rechaza: ya
        // atrapó su propio error), no la de `promesa`: así confirmar puede
        // distinguir "en vuelo" de "en vuelo y ya falló" con un solo
        // allSettled (ver confirmarVenta).
        const tarea = this._ejecutarAccion(promesa);
        this._enVuelo.add(tarea);
        return tarea.finally(() => this._enVuelo.delete(tarea));
      },
      async _ejecutarAccion(promesa) {
        try {
          const respuesta = await this._ultimaVenta(promesa);
          if (respuesta !== undefined) this.mostrar(respuesta);
          return true;
        } catch (e) {
          window.toast(e.message, 'error');
          return false;
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
        this.descuentoGeneral = { modo: 'total', valor: '' };
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
        const pedido = window.pedir(`${API}/${ventaId}/items`, { method: 'POST', body: { producto_id: productoId } });
        await this.accion(pedido);
      },

      // ---------- Cantidad por línea (Task 3) ----------
      lineaOcupada(linea) { return L.lineaOcupada(this._lineasOcupadas, linea.item_id); },
      async cambiarCantidad(linea, campo) {
        const cantidad = L.cantidadValida(campo.value);
        if (cantidad === null || cantidad === linea.cantidad) { campo.value = linea.cantidad; return; }
        const ok = await this._fijarCantidad(linea, cantidad);
        if (!ok) campo.value = linea.cantidad;   // rechazada (ej. stock): vuelve a la de la API
      },
      sumar(linea, delta) { return this._fijarCantidad(linea, linea.cantidad + delta); },
      quitarLinea(linea) { return this._fijarCantidad(linea, 0); },
      async _fijarCantidad(linea, cantidad) {
        // Mientras esta línea tenga un PUT en vuelo, −/+/input quedan
        // deshabilitados (template): dos clics antes de que vuelva la
        // respuesta no mandan la misma cantidad de base dos veces.
        this._lineasOcupadas.add(linea.item_id);
        try {
          return await this.accion(window.pedir(`${API}/${this.venta.id}/items/${linea.item_id}/cantidad`,
                                                { method: 'PUT', body: { cantidad } }));
        } finally {
          this._lineasOcupadas.delete(linea.item_id);
        }
      },

      // ---------- Descuento por línea ----------
      async cargarOpcionesDescuento() {
        if (!this.puedeDescontar) return;
        try {
          this.opcionesDescuento = await window.pedir(`${API}/opciones-descuento`);
        } catch (e) {
          window.toast(e.message, 'error');
        }
      },

      abrirDescuento(linea) {
        this.descuento = {
          linea,
          motivo_id: linea.motivo ? String(linea.motivo.id) : '',
          porcentaje: Number(linea.descuento_item) > 0 ? String(Number(linea.descuento_item)) : '',
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
          body: { item_id: this.descuento.linea.item_id, motivo_id: motivo ? motivo.id : null, porcentaje },
        }));
        if (ok) this.descuentoAbierto = false;
      },

      // ---------- Descuento general de la venta ----------
      // `_descuentoGeneralAMano` evita el toast de "se quitó solo" en `mostrar`
      // cuando el cambio lo pidió el propio usuario (aplicar uno nuevo o Quitar).
      async aplicarDescuentoGeneral() {
        const cuerpo = L.cuerpoDescuentoGeneral(this.descuentoGeneral.modo, this.descuentoGeneral.valor);
        if (!cuerpo) { window.toast('Escribí el total final o el porcentaje.', 'error'); return; }
        this._descuentoGeneralAMano = true;
        const ok = await this.accion(window.pedir(`${API}/${this.venta.id}/descuento-general`, { method: 'POST', body: cuerpo }))
          .finally(() => { this._descuentoGeneralAMano = false; });
        if (ok) this.descuentoGeneral.valor = '';
      },
      quitarDescuentoGeneral() {
        this._descuentoGeneralAMano = true;
        return this.accion(window.pedir(`${API}/${this.venta.id}/descuento-general`,
                                        { method: 'POST', body: { porcentaje: null, total: null } }))
          .finally(() => { this._descuentoGeneralAMano = false; });
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
          // Primero terminan las escrituras en vuelo (p. ej. el cambio de un
          // medio de pago, o una cantidad tipeada): si alguna falló, el toast
          // de error ya se mostró y no hay que confirmar con datos a medio
          // aplicar (rejected: no debería pasar, `accion()` no rechaza, pero
          // se cubre igual; value === false: falló y ya se avisó).
          const resultados = await Promise.allSettled([...this._enVuelo]);
          if (resultados.some((r) => r.status === 'rejected' || r.value === false)) return;
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
          if (L.recalcularTrasConfirmar(e)) {
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
