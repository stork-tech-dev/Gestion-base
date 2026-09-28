/* Listado de stock (filtros + paginación) y sus acciones: ingreso, mínimo,
   baja y el historial de movimientos de un producto. Todos los datos salen
   de la API (app/api/v1/stock.py). */
(function () {
  'use strict';

  const API = '/api/v1/stock';

  // Textos legibles de TipoMovimientoStock (app/models/stock.py).
  const TIPOS_MOVIMIENTO = {
    ingreso_proveedor: 'Ingreso de proveedor',
    venta: 'Venta',
    anulacion_venta: 'Anulación de venta',
    baja: 'Baja',
    ajuste_auditoria: 'Ajuste de auditoría',
  };

  const filtrosVacios = () => ({ busqueda: '', categoria_id: null, proveedor_id: null, solo_bajo_minimo: false });
  const resumenVacio = () => ({ productos_con_stock: 0, unidades: 0, valorizado: 0, bajo_minimo: 0 });

  window.stockListado = function ({ puedeIngresar, puedeMinimos, puedeBaja }) {
    return {
      puedeIngresar,
      puedeMinimos,
      puedeBaja,
      filtros: filtrosVacios(),
      filas: [],
      total: 0,
      pagina: 1,
      tamano: 10,
      cargando: false,
      _ultima: window.ultimaRespuesta(),
      _espera: null,
      resumen: resumenVacio(),
      arbol: [],
      proveedores: [],
      motivos: [],

      // ---------- Ingreso ----------
      ingreso: null,
      ingresoAbierto: false,
      guardandoIngreso: false,

      // ---------- Mínimo ----------
      minimo: null,
      minimoAbierto: false,
      guardandoMinimo: false,

      // ---------- Baja ----------
      baja: null,
      bajaAbierta: false,
      guardandoBaja: false,

      // ---------- Movimientos ----------
      movimientosProducto: null,
      movimientosAbierto: false,
      movimientosFilas: [],
      movimientosTotal: 0,
      movimientosPagina: 1,
      movimientosCargando: false,
      _ultimaMovimientos: window.ultimaRespuesta(),

      init() {
        this.cargar();
        this.cargarResumen();
        this._cargarCatalogos();
      },

      // Por separado: si falla uno, el resto igual queda cargado (ej. un
      // Vendedor con STOCK ver pero sin PRODUCTOS ver no puede pedir
      // /api/v1/productos/proveedores; el filtro de proveedor queda vacío
      // sin romper la pantalla).
      _cargarCatalogos() {
        window.pedir('/api/v1/categorias/arbol')
          .then((arbol) => { this.arbol = arbol; })
          .catch((e) => window.toast(e.message, 'error'));
        window.pedir('/api/v1/productos/proveedores')
          .then((proveedores) => { this.proveedores = proveedores; })
          .catch((e) => window.toast(e.message, 'error'));
        if (this.puedeBaja) {
          window.pedir(`${API}/motivos-baja?activo=true`)
            .then((motivos) => { this.motivos = motivos; })
            .catch((e) => window.toast(e.message, 'error'));
        }
      },

      async cargarResumen() {
        try {
          this.resumen = await window.pedir(`${API}/resumen`);
        } catch (e) {
          window.toast(e.message, 'error');
        }
      },

      // Lista plana del árbol (todos los niveles), con el camino completo como texto.
      get categoriasOpciones() {
        const opciones = [];
        const recorrer = (nodos) => {
          for (const n of nodos || []) {
            opciones.push({ id: n.id, texto: window.rutaCategoria(this.arbol, n.id) });
            recorrer(n.hijos);
          }
        };
        recorrer(this.arbol);
        return opciones;
      },

      filtrar() {
        clearTimeout(this._espera);
        this._espera = setTimeout(() => this.cargar(1), 400);
      },

      limpiarFiltros() {
        this.filtros = filtrosVacios();
        this.cargar(1);
      },

      async cargar(pagina) {
        if (pagina) this.pagina = pagina;
        this.cargando = true;
        const params = new URLSearchParams({ pagina: this.pagina, tamano: this.tamano });
        const busqueda = (this.filtros.busqueda || '').trim();
        if (busqueda) params.set('busqueda', busqueda);
        if (this.filtros.categoria_id) params.set('categoria_id', this.filtros.categoria_id);
        if (this.filtros.proveedor_id) params.set('proveedor_id', this.filtros.proveedor_id);
        if (this.filtros.solo_bajo_minimo) params.set('solo_bajo_minimo', 'true');
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

      fotoHtml(p) {
        const clases = 'h-10 w-10 shrink-0 rounded-input bg-surface-alt object-cover';
        if (!p.foto_url) return `<div class="${clases}"></div>`;
        return `<img src="${window.escaparHtml(p.foto_url)}" alt="Foto del producto" class="${clases}" loading="lazy">`;
      },

      stockHtml(p) {
        const clase = p.stock < 0 ? 'font-semibold text-danger' : '';
        return `<span class="${clase}">${p.stock}</span>`;
      },

      minimoHtml(p) {
        const reponer = p.bajo_minimo ? ' <span class="font-semibold text-danger">Reponer</span>' : '';
        return `${p.stock_minimo}${reponer}`;
      },

      // ---------- Ingreso ----------

      abrirIngreso(p) {
        this.ingreso = { producto: p, cantidad: 1, notas: '' };
        this.ingresoAbierto = true;
      },

      async guardarIngreso() {
        this.guardandoIngreso = true;
        try {
          await window.pedir(`${API}/ingresos`, {
            method: 'POST',
            body: {
              producto_id: this.ingreso.producto.producto_id,
              cantidad: Number(this.ingreso.cantidad),
              notas: (this.ingreso.notas || '').trim() || null,
            },
          });
          window.toast('Ingreso registrado.');
          this.ingresoAbierto = false;
          this.cargar(this.pagina);
          this.cargarResumen();
        } catch (e) {
          window.toast(e.message, 'error');
        } finally {
          this.guardandoIngreso = false;
        }
      },

      // ---------- Mínimo ----------

      abrirMinimo(p) {
        this.minimo = { producto: p, stock_minimo: p.stock_minimo };
        this.minimoAbierto = true;
      },

      async guardarMinimo() {
        this.guardandoMinimo = true;
        try {
          await window.pedir(`${API}/minimos/${this.minimo.producto.producto_id}`, {
            method: 'PUT',
            body: { stock_minimo: Number(this.minimo.stock_minimo) },
          });
          window.toast('Mínimo actualizado.');
          this.minimoAbierto = false;
          this.cargar(this.pagina);
          this.cargarResumen();
        } catch (e) {
          window.toast(e.message, 'error');
        } finally {
          this.guardandoMinimo = false;
        }
      },

      // ---------- Baja ----------

      abrirBaja(p) {
        this.baja = { producto: p, cantidad: 1, motivo_baja_id: '', notas: '' };
        this.bajaAbierta = true;
      },

      async guardarBaja() {
        this.guardandoBaja = true;
        try {
          await window.pedir(`${API}/bajas`, {
            method: 'POST',
            body: {
              producto_id: this.baja.producto.producto_id,
              cantidad: Number(this.baja.cantidad),
              motivo_baja_id: Number(this.baja.motivo_baja_id),
              notas: (this.baja.notas || '').trim() || null,
            },
          });
          window.toast('Baja registrada.');
          this.bajaAbierta = false;
          this.cargar(this.pagina);
          this.cargarResumen();
        } catch (e) {
          window.toast(e.message, 'error');
        } finally {
          this.guardandoBaja = false;
        }
      },

      // ---------- Movimientos ----------

      tipoTexto(tipo) {
        return TIPOS_MOVIMIENTO[tipo] || tipo;
      },

      cantidadTexto(m) {
        return (m.cantidad > 0 ? '+' : '') + m.cantidad;
      },

      async abrirMovimientos(p) {
        this.movimientosProducto = p;
        this.movimientosAbierto = true;
        this.movimientosFilas = [];
        this.movimientosTotal = 0;
        await this.cargarMovimientos(1);
      },

      async cargarMovimientos(pagina) {
        if (pagina) this.movimientosPagina = pagina;
        const productoId = this.movimientosProducto.producto_id;
        this.movimientosCargando = true;
        const params = new URLSearchParams({ producto_id: productoId, pagina: this.movimientosPagina, tamano: 10 });
        try {
          const respuesta = await this._ultimaMovimientos(window.pedir(`${API}/movimientos?${params}`));
          // undefined: llegó un pedido más nuevo. Si mientras tanto se abrió
          // el modal de otro producto, movimientosProducto ya cambió: se
          // descarta igual aunque el secuenciador solo no alcance a verlo
          // (mismo motivo que abrirFicha en productos.js).
          if (respuesta === undefined || !this.movimientosProducto || this.movimientosProducto.producto_id !== productoId) return;
          this.movimientosFilas = respuesta.resultados;
          this.movimientosTotal = respuesta.total;
          this.movimientosCargando = false;
        } catch (e) {
          this.movimientosCargando = false;
          window.toast(e.message, 'error');
        }
      },
    };
  };
})();
