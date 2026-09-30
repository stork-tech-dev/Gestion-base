/* Listado de productos (filtros + paginación) y su ficha (fotos, código de
   barras, impresión de etiquetas). Todos los datos salen de la API.
   La ficha va secuenciada con `ultimaRespuesta` y, además, comparando el id
   pedido contra `_abrirId`: abrir otra ficha mientras la anterior carga
   descarta la respuesta vieja aunque llegue después que el secuenciador ya
   soltó el pedido más nuevo (mismo motivo que `cargarHistorial` en
   proveedores.js). */
(function () {
  'use strict';

  const API = '/api/v1/productos';

  const filtrosVacios = () => ({ busqueda: '', categoria_id: null, proveedor_id: null, temporada: '', activos: true, stock_cero: false });

  // Resultado de la búsqueda "vacía con el switch en Activos": se sugiere mirar los inactivos.
  function sugerirInactivos(filtros, total, cargando) {
    return !cargando && total === 0 && filtros.activos && !!(filtros.busqueda || '').trim();
  }

  // `temporadas`: [[valor, texto]] (TEMPORADAS de pages.py, única definición).
  window.productosUtil = { sugerirInactivos };

  window.productosListado = function ({ puedeEditar, temporadas = [] }) {
    const TEMPORADAS = temporadas.map(([id, texto]) => ({ id, texto }));
    const TEXTO_TEMPORADA = Object.fromEntries(temporadas);
    return {
      puedeEditar,
      filtros: filtrosVacios(),
      filas: [],
      total: 0,
      pagina: 1,
      tamano: 10,
      cargando: false,
      _ultima: window.ultimaRespuesta(),
      _ultimaFicha: window.ultimaRespuesta(),
      _espera: null,
      _abrirId: null,
      arbol: [],
      proveedores: [],
      temporadas: TEMPORADAS,
      ficha: null,
      fichaAbierta: false,
      cantEtiquetas: 1,
      imprimiendo: false,

      // ---------- "Stock 0" + desactivación masiva ----------
      seleccionados: new Set(),
      desactivando: false,

      init() {
        this.cargar();
        this._cargarCatalogos();
        window.addEventListener('producto-guardado', (evento) => {
          this.cargar(this.pagina);
          const producto = evento && evento.detail;
          if (this.ficha && producto && this.ficha.id === producto.id) this._refrescarFicha();
        });
      },

      // Por separado: si falla uno, el otro filtro igual queda cargado.
      _cargarCatalogos() {
        window.pedir('/api/v1/categorias/arbol')
          .then((arbol) => { this.arbol = arbol; })
          .catch((e) => window.toast(e.message, 'error'));
        // Todos (también los inactivos) para el filtro; ruta con PRODUCTOS ver.
        window.pedir(`${API}/proveedores`)
          .then((proveedores) => { this.proveedores = proveedores; })
          .catch((e) => window.toast(e.message, 'error'));
      },

      get sugerirInactivos() {
        return sugerirInactivos(this.filtros, this.total, this.cargando);
      },

      // Lista plana del árbol (todos los niveles), con el camino completo como texto.
      get categoriasOpciones() {
        return window.categoriasOpciones(this.arbol);
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
        if (this.filtros.temporada) params.set('temporada', this.filtros.temporada);
        params.set('activo', this.filtros.activos ? 'true' : 'false');
        if (this.filtros.stock_cero) params.set('stock_cero', 'true');
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

      // `tabla` no tiene slot por columna: se arma el <img>/placeholder a mano,
      // con la URL (única parte que viene de la API) pasada por escaparHtml.
      fotoHtml(p) {
        const clases = 'h-10 w-10 shrink-0 rounded-input bg-surface-alt object-cover';
        if (!p.foto_url) return `<div class="${clases}"></div>`;
        return `<img src="${window.escaparHtml(p.foto_url)}" alt="Foto del producto" class="${clases}" loading="lazy">`;
      },

      codigoHtml(p) {
        return window.escaparHtml(p.codigo_con_verificador) +
          '<span class="block text-xs text-texto-muted">+ dígito verificador</span>';
      },

      costoTexto(p) {
        return p.moneda === 'usd' ? window.dolares(p.costo) : '$ ' + window.pesos(p.costo);
      },

      temporadaTexto(t) {
        return TEXTO_TEMPORADA[t] || t;
      },

      // stockHtml: window.stockHtml (app.js) — misma celda que /stock.

      // ---------- "Stock 0" + desactivación masiva ----------

      alternarStockCero() {
        // Cambiar el filtro invalida la selección: puede referirse a productos
        // que ya no están en esta vista (otra página, otros filtros).
        this.seleccionados = new Set();
        this.cargar(1);
      },

      checkboxHtml(p) {
        const marcado = this.seleccionados.has(p.id) ? 'checked' : '';
        return `<label class="flex min-h-toque items-center justify-center"><input type="checkbox" class="h-5 w-5" data-producto-id="${p.id}" ${marcado} aria-label="Seleccionar ${window.escaparHtml(p.descripcion)}"></label>`;
      },

      // Delegado: los checkboxes de la tabla se arman como HTML (x-html), así
      // que no tienen x-model propio; el click burbujea hasta acá.
      alternarSeleccionClick(evento) {
        const casilla = evento.target.closest('input[type="checkbox"][data-producto-id]');
        if (!casilla) return;
        const id = Number(casilla.dataset.productoId);
        if (casilla.checked) this.seleccionados.add(id);
        else this.seleccionados.delete(id);
        this.seleccionados = new Set(this.seleccionados);  // fuerza la reactividad
      },

      get todosSeleccionadosDeLaPagina() {
        return this.filas.length > 0 && this.filas.every((f) => this.seleccionados.has(f.id));
      },

      alternarTodos(marcar) {
        const seleccionados = new Set(this.seleccionados);
        for (const f of this.filas) {
          if (marcar) seleccionados.add(f.id);
          else seleccionados.delete(f.id);
        }
        this.seleccionados = seleccionados;
      },

      async desactivarSeleccionados() {
        const ids = [...this.seleccionados];
        if (!ids.length) return;
        const ok = await window.confirmar({
          titulo: `¿Desactivar ${ids.length} producto${ids.length === 1 ? '' : 's'}?`,
          mensaje: 'No van a estar disponibles para la venta.',
          textoConfirmar: 'Desactivar',
          peligro: true,
        });
        if (!ok) return;
        this.desactivando = true;
        let exitos = 0;
        const fallidos = [];
        // En serie (no Promise.all): cada PATCH es una auditoría propia;
        // en paralelo se pierde el orden y es más difícil leer qué falló.
        for (const id of ids) {
          try {
            await window.pedir(`${API}/${id}/estado`, { method: 'PATCH', body: { activo: false } });
            exitos++;
          } catch (e) {
            const fila = this.filas.find((f) => f.id === id);
            fallidos.push(fila ? fila.descripcion : `#${id}`);
          }
        }
        this.desactivando = false;
        this.seleccionados = new Set();
        if (exitos) window.toast(`${exitos} producto${exitos === 1 ? '' : 's'} desactivado${exitos === 1 ? '' : 's'}.`);
        if (fallidos.length) window.toast(`No se pudo desactivar: ${fallidos.join(', ')}.`, 'error');
        this.cargar(this.pagina);
      },

      // ---------- Ficha ----------

      async abrirFicha(p) {
        // Sin la ficha anterior mientras carga (ni si falla la carga).
        this.ficha = null;
        this.fichaAbierta = true;
        this.cantEtiquetas = 1;
        const id = p.id;
        this._abrirId = id;
        try {
          const detalle = await this._ultimaFicha(window.pedir(`${API}/${id}`));
          // undefined: llegó un pedido más nuevo. _abrirId distinto: se abrió
          // otra ficha antes de que este pedido llegara a salir.
          if (detalle === undefined || this._abrirId !== id) return;
          this.ficha = detalle;
        } catch (e) {
          window.toast(e.message, 'error');
        }
      },

      async _refrescarFicha() {
        if (!this.ficha) return;
        const id = this.ficha.id;
        try {
          const detalle = await window.pedir(`${API}/${id}`);
          if (this.ficha && this.ficha.id === id) this.ficha = detalle;
        } catch (e) {
          window.toast(e.message, 'error');
        }
      },

      async editar(p) {
        try {
          const detalle = await window.pedir(`${API}/${p.id}`);
          window.dispatchEvent(new CustomEvent('abrir-producto-form', { detail: { producto: detalle } }));
        } catch (e) {
          window.toast(e.message, 'error');
        }
      },

      async cambiarEstado(p) {
        const activar = !p.activo;
        const ok = await window.confirmar({
          titulo: activar ? `¿Activar "${p.descripcion}"?` : `¿Desactivar "${p.descripcion}"?`,
          mensaje: activar ? 'Va a volver a estar disponible para la venta.' : 'No va a estar disponible para la venta.',
          textoConfirmar: activar ? 'Activar' : 'Desactivar',
          peligro: !activar,
        });
        if (!ok) return;
        try {
          await window.pedir(`${API}/${p.id}/estado`, { method: 'PATCH', body: { activo: activar } });
          window.toast(activar ? 'Producto activado.' : 'Producto desactivado.');
          this.cargar(this.pagina);
          if (this.ficha && this.ficha.id === p.id) this.ficha.activo = activar;
        } catch (e) {
          window.toast(e.message, 'error');
        }
      },

      // Fotos: ver static/js/fotos_producto.js (window.fotosProducto) — la
      // ficha lo usa vía la macro components/fotos_producto.html, con
      // `al_cambiar="_refrescarFicha()"` para refrescarse tras cada cambio.

      // ---------- Etiquetas ----------

      // window.abrirPdf (app.js): abre la ventana en el MISMO click (antes
      // del fetch, si no el navegador la bloquea) y ahí muestra el blob.
      async imprimir(tipo) {
        if (!this.ficha) return;
        const cantidad = Math.max(1, Math.trunc(Number(this.cantEtiquetas)) || 1);
        this.imprimiendo = true;
        await window.abrirPdf(`${API}/etiquetas`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ items: [{ producto_id: this.ficha.id, cantidad }], tipo }),
        });
        this.imprimiendo = false;
      },
    };
  };
})();
