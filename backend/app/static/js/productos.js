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

  const TEMPORADAS = [
    { id: 'atemporal', texto: 'Atemporal' },
    { id: 'otoño_invierno', texto: 'Otoño-Invierno' },
    { id: 'primavera_verano', texto: 'Primavera-Verano' },
  ];
  const TEXTO_TEMPORADA = Object.fromEntries(TEMPORADAS.map((t) => [t.id, t.texto]));

  const filtrosVacios = () => ({ busqueda: '', categoria_id: null, proveedor_id: null, temporada: '', activos: true });

  window.productosListado = function ({ puedeEditar }) {
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

      init() {
        this.cargar();
        this._cargarCatalogos();
        window.addEventListener('producto-guardado', (evento) => {
          this.cargar(this.pagina);
          const producto = evento && evento.detail;
          if (this.ficha && producto && this.ficha.id === producto.id) this._refrescarFicha();
        });
      },

      async _cargarCatalogos() {
        try {
          const [arbol, proveedores] = await Promise.all([
            window.pedir('/api/v1/categorias/arbol'),
            window.pedir('/api/v1/proveedores'),
          ]);
          this.arbol = arbol;
          this.proveedores = proveedores;
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
        if (this.filtros.temporada) params.set('temporada', this.filtros.temporada);
        params.set('activo', this.filtros.activos ? 'true' : 'false');
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

      // ---------- Ficha ----------

      async abrirFicha(p) {
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

      // ---------- Fotos ----------

      async subirFoto(archivo) {
        if (!archivo || !this.ficha) return;
        const datos = new FormData();
        datos.append('archivo', archivo);
        try {
          await window.pedir(`${API}/${this.ficha.id}/fotos`, { method: 'POST', body: datos });
          window.toast('Foto subida.');
          await this._refrescarFicha();
        } catch (e) {
          window.toast(e.message, 'error');
        }
      },

      async capturarFoto(camara) {
        const blob = await camara.capturar();
        camara.detener();
        await this.subirFoto(blob);
      },

      async marcarPrincipal(f) {
        try {
          await window.pedir(`${API}/fotos/${f.id}/principal`, { method: 'PATCH' });
          await this._refrescarFicha();
        } catch (e) {
          window.toast(e.message, 'error');
        }
      },

      async borrarFoto(f) {
        const ok = await window.confirmar({
          titulo: '¿Borrar esta foto?',
          mensaje: 'No se puede deshacer.',
          textoConfirmar: 'Borrar',
          peligro: true,
        });
        if (!ok) return;
        try {
          await window.pedir(`${API}/fotos/${f.id}`, { method: 'DELETE' });
          window.toast('Foto borrada.');
          await this._refrescarFicha();
        } catch (e) {
          window.toast(e.message, 'error');
        }
      },

      // ---------- Etiquetas ----------

      // El PDF viaja como blob: `pedir` asume JSON, así que se usa fetch directo.
      async imprimir(tipo) {
        if (!this.ficha) return;
        const cantidad = Math.max(1, Math.trunc(Number(this.cantEtiquetas)) || 1);
        this.imprimiendo = true;
        try {
          const respuesta = await fetch(`${API}/etiquetas`, {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json', Accept: 'application/pdf' },
            body: JSON.stringify({ items: [{ producto_id: this.ficha.id, cantidad }], tipo }),
          });
          if (!respuesta.ok) {
            let datos = null;
            try { datos = await respuesta.json(); } catch (e) { /* no era JSON */ }
            throw new Error(window.mensajeDeError(datos, respuesta.status));
          }
          const blob = await respuesta.blob();
          window.open(URL.createObjectURL(blob));
        } catch (e) {
          window.toast(e.message, 'error');
        } finally {
          this.imprimiendo = false;
        }
      },
    };
  };
})();
