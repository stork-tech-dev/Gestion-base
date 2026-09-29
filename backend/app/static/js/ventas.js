/* Resumen de Ventas (/ventas/resumen-ventas): listado de alto volumen (filtros
   con "Buscar" explícito, Principio 5), detalle de una venta en modal y su
   anulación. Todos los datos salen de la API (app/api/v1/ventas.py). */
(function () {
  'use strict';

  const API = '/api/v1/ventas';
  const API_CLIENTES = '/api/v1/clientes';

  // ---------- Lógica pura (testeada con node --test en tests_js/ventas.test.mjs) ----------
  window.ventasLogica = {
    // Filtros por defecto: fecha desde/hasta = hoy (hora del negocio).
    // `clienteId` llega de la ficha del cliente (chip quitable en la
    // pantalla): viaja en la query pero no es un campo de la barra de filtros.
    filtrosIniciales: (hoyIso, clienteId = null) => ({
      numero: '', codigo_cambio: '', estado: '', usuario_id: '',
      fecha_desde: hoyIso, fecha_hasta: hoyIso, cliente_id: clienteId || null,
    }),

    // Query de GET /api/v1/ventas a partir de los filtros: omite los vacíos
    // (para no mandar `estado=` ni pisar los defaults del backend) y el
    // código de cambio siempre en mayúsculas (así se guarda en la base).
    queryDeFiltros: (filtros, pagina) => {
      const params = { pagina, tamano: 10 };
      const agregar = (clave, valor) => {
        if (valor === null || valor === undefined) return;
        const texto = String(valor).trim();
        if (texto) params[clave] = texto;
      };
      agregar('numero', filtros.numero);
      agregar('codigo_cambio', filtros.codigo_cambio ? filtros.codigo_cambio.toUpperCase() : '');
      agregar('estado', filtros.estado);
      agregar('fecha_desde', filtros.fecha_desde);
      agregar('fecha_hasta', filtros.fecha_hasta);
      agregar('usuario_id', filtros.usuario_id);
      agregar('cliente_id', filtros.cliente_id);
      return params;
    },

    // Medios de pago de una VentaResumen, unidos por " + " (columna "Medio de pago").
    textoMedios: (venta) => (venta.medios || []).join(' + '),

    // Botón "Anular venta": solo confirmadas y con el permiso puntual.
    puedeAnular: (venta, permiso) => !!permiso && !!venta && venta.estado === 'confirmada',
  };
  const L = window.ventasLogica;

  window.ventasResumen = function ({ puedeAnular, clienteIdInicial, hoyIso }) {
    return {
      puedeAnular,
      filtros: L.filtrosIniciales(hoyIso, clienteIdInicial),
      clienteChip: null,   // { id, nombre } cuando llegó ?cliente_id= de la ficha del cliente
      vendedores: [],
      filas: [],
      total: 0,
      pagina: 1,
      tamano: 10,
      cargando: false,
      _ultima: window.ultimaRespuesta(),

      // ---------- Detalle ----------
      detalle: null,
      detalleId: null,
      detalleAbierto: false,
      cargandoDetalle: false,
      _ultimoDetalle: window.ultimaRespuesta(),
      anulando: false,
      motivoAnulacion: '',
      anulandoEnCurso: false,

      init() {
        this.cargar(1);
        this._cargarVendedores();
        if (this.filtros.cliente_id) this._cargarClienteChip(this.filtros.cliente_id);
      },

      get vendedoresOpciones() { return this.vendedores; },

      async _cargarVendedores() {
        try {
          this.vendedores = await window.pedir(`${API}/vendedores`);
        } catch (e) {
          window.toast(e.message, 'error');
        }
      },

      // Nombre del cliente para el chip: si falla (sin CLIENTES ver, por
      // ejemplo) el filtro sigue aplicado, solo no se ve el nombre.
      async _cargarClienteChip(id) {
        try {
          const ficha = await window.pedir(`${API_CLIENTES}/${id}`);
          this.clienteChip = { id, nombre: ficha.cliente.nombre };
        } catch (e) { /* el filtro por cliente_id sigue activo igual */ }
      },

      quitarClienteChip() {
        this.clienteChip = null;
        this.filtros.cliente_id = null;
        this.cargar(1);
      },

      // El chip de cliente no es un campo de esta barra (viene de afuera):
      // "Limpiar filtros" solo resetea los campos propios de la búsqueda.
      limpiarFiltros() {
        this.filtros = L.filtrosIniciales(hoyIso, this.filtros.cliente_id);
        this.cargar(1);
      },

      async cargar(pagina) {
        if (pagina) this.pagina = pagina;
        this.cargando = true;
        const params = new URLSearchParams(L.queryDeFiltros(this.filtros, this.pagina));
        try {
          const respuesta = await this._ultima(window.pedir(`${API}?${params}`));
          if (respuesta === undefined) return;  // llegó un pedido más nuevo
          this.filas = respuesta.resultados;
          this.total = respuesta.total;
          this.cargando = false;
        } catch (e) {
          this.cargando = false;
          window.toast(e.message, 'error');
        }
      },

      // ---------- Celdas de la tabla ----------
      medioTexto(fila) {
        return L.textoMedios(fila) || '—';
      },

      // Estado en texto de color (reusado en la fila y en el header del detalle).
      estadoTexto(fila) {
        if (fila.estado === 'confirmada') return window.estadoHtml('Confirmada', 'exito');
        if (fila.estado === 'anulada') return window.estadoHtml('Anulada', 'peligro');
        return window.estadoHtml('En curso', 'primario');
      },

      // Columna Total: anulada → tachado.
      totalTexto(fila) {
        const texto = '$ ' + window.pesos(fila.total);
        return fila.estado === 'anulada' ? `<span class="text-danger line-through">${texto}</span>` : texto;
      },

      // ---------- Detalle ----------
      async abrirDetalle(fila) {
        this.detalleId = fila.id;
        this.detalle = null;
        this.anulando = false;
        this.motivoAnulacion = '';
        this.detalleAbierto = true;
        await this.cargarDetalle(fila.id);
      },

      async cargarDetalle(id) {
        this.cargandoDetalle = true;
        try {
          const detalle = await this._ultimoDetalle(window.pedir(`${API}/${id}`));
          if (detalle === undefined) return;   // llegó un pedido más nuevo
          if (id !== this.detalleId) return;   // se cerró o se abrió otra venta mientras esperaba
          this.detalle = detalle;
          this.cargandoDetalle = false;
        } catch (e) {
          this.cargandoDetalle = false;
          window.toast(e.message, 'error');
        }
      },

      puedeAnularVenta() {
        return L.puedeAnular(this.detalle, this.puedeAnular);
      },

      abrirAnular() {
        this.motivoAnulacion = '';
        this.anulando = true;
      },

      async confirmarAnulacion() {
        const motivo = this.motivoAnulacion.trim();
        if (!motivo) return;
        const ok = await window.confirmar({
          titulo: `¿Anular la venta ${this.detalle.numero}?`,
          mensaje: 'Se devuelve el stock y el importe sale de la caja del turno actual. No se puede deshacer.',
          textoConfirmar: 'Anular',
          peligro: true,
        });
        if (!ok) return;
        this.anulandoEnCurso = true;
        try {
          await window.pedir(`${API}/${this.detalle.id}/anular`, { method: 'POST', body: { motivo } });
          window.toast('Venta anulada.');
          this.anulando = false;
          // Recarga tanto el detalle (para el aviso "Anulada el...") como la fila del listado.
          await Promise.all([this.cargarDetalle(this.detalle.id), this.cargar()]);
        } catch (e) {
          window.toast(e.message, 'error');
        } finally {
          this.anulandoEnCurso = false;
        }
      },
    };
  };
})();
