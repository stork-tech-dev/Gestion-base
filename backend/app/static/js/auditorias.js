/* Auditorías de inventario (conteos de stock): listado + inicio de un
   conteo nuevo, y la pantalla de conteo (escaneo, edición inline de lo
   contado y cierre). Todos los datos salen de la API
   (app/api/v1/auditorias_inventario.py). */
(function () {
  'use strict';

  const API = '/api/v1/auditorias-inventario';

  // ---------- Listado ----------

  const filtrosVacios = () => ({ estado: '', desde: '', hasta: '' });

  window.auditoriasListado = function ({ puedeAuditar }) {
    return {
      puedeAuditar,
      filtros: filtrosVacios(),
      filas: [],
      total: 0,
      pagina: 1,
      tamano: 10,
      cargando: false,
      _ultima: window.ultimaRespuesta(),
      hayEnCurso: false,
      arbol: [],
      iniciarAbierto: false,
      nuevoConteo: null,
      guardandoInicio: false,

      init() {
        this.cargar(1);
        if (this.puedeAuditar) {
          this._revisarEnCurso();
          window.pedir('/api/v1/categorias/arbol')
            .then((arbol) => { this.arbol = arbol; })
            .catch((e) => window.toast(e.message, 'error'));
        }
      },

      async _revisarEnCurso() {
        try {
          const respuesta = await window.pedir(`${API}?estado=en_curso&pagina=1&tamano=1`);
          this.hayEnCurso = respuesta.total > 0;
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

      limpiarFiltros() {
        this.filtros = filtrosVacios();
        this.cargar(1);
      },

      async cargar(pagina) {
        if (pagina) this.pagina = pagina;
        this.cargando = true;
        const params = new URLSearchParams({ pagina: this.pagina, tamano: this.tamano });
        if (this.filtros.estado) params.set('estado', this.filtros.estado);
        if (this.filtros.desde) params.set('desde', this.filtros.desde);
        if (this.filtros.hasta) params.set('hasta', this.filtros.hasta);
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

      estadoTexto(fila) {
        return fila.estado === 'en_curso'
          ? window.estadoHtml('En curso', 'primario')
          : window.estadoHtml('Cerrada', 'exito');
      },

      // ---------- Iniciar conteo ----------

      abrirIniciar() {
        this.nuevoConteo = { filtro_categoria_id: null, notas: '' };
        this.iniciarAbierto = true;
      },

      async iniciarConteo() {
        this.guardandoInicio = true;
        try {
          const auditoria = await window.pedir(API, {
            method: 'POST',
            body: {
              filtro_categoria_id: this.nuevoConteo.filtro_categoria_id || null,
              notas: (this.nuevoConteo.notas || '').trim() || null,
            },
          });
          // La pantalla de conteo se abre como página propia (no un modal).
          window.location.href = `/auditorias-inventario/${auditoria.id}`;
        } catch (e) {
          window.toast(e.message, 'error');
          this.guardandoInicio = false;
        }
      },

      // ---------- PDF ----------
      // Mismo patrón que imprimir() en productos.js: la ventana se abre en
      // el MISMO click (antes del fetch), si no el navegador la bloquea.
      async imprimirPdf(fila) {
        await imprimirPdfDe(fila.id);
      },
    };
  };

  // El PDF viaja como blob: `pedir` asume JSON, así que se usa fetch directo.
  async function imprimirPdfDe(auditoriaId) {
    const ventana = window.open('', '_blank');
    if (!ventana) {
      window.toast('El navegador bloqueó la ventana; habilitá las ventanas emergentes.', 'error');
      return;
    }
    try {
      const respuesta = await fetch(`${API}/${auditoriaId}/pdf`, {
        credentials: 'same-origin',
        headers: { Accept: 'application/pdf' },
      });
      if (!respuesta.ok) {
        let datos = null;
        try { datos = await respuesta.json(); } catch (e) { /* no era JSON */ }
        throw new Error(window.mensajeDeError(datos, respuesta.status));
      }
      const url = URL.createObjectURL(await respuesta.blob());
      ventana.location = url;
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch (e) {
      ventana.close();
      window.toast(e.message, 'error');
    }
  }

  // ---------- Pantalla de conteo ----------

  window.auditoriaConteo = function ({ id, puedeAuditar }) {
    return {
      id,
      puedeAuditar,
      auditoria: null,
      cargando: false,
      codigo: '',
      contadas: 1,
      agregando: false,
      cerrando: false,

      get puedeEditar() {
        return this.puedeAuditar && !!this.auditoria && this.auditoria.estado === 'en_curso';
      },

      init() {
        this.cargar();
      },

      async cargar() {
        this.cargando = true;
        try {
          this.auditoria = await window.pedir(`${API}/${this.id}`);
          this.cargando = false;
        } catch (e) {
          this.cargando = false;
          window.toast(e.message, 'error');
        }
      },

      _upsertItem(item) {
        const indice = this.auditoria.items.findIndex((i) => i.id === item.id);
        if (indice === -1) this.auditoria.items.push(item);
        else this.auditoria.items.splice(indice, 1, item);
      },

      async agregarPorCodigo() {
        const codigo = (this.codigo || '').trim();
        if (!codigo) {
          this.$refs.inputCodigo.focus();
          return;
        }
        const cantidad = Math.max(0, Math.trunc(Number(this.contadas)) || 0);
        this.agregando = true;
        try {
          const item = await window.pedir(`${API}/${this.id}/items/por-codigo`, {
            method: 'POST',
            body: { codigo, cantidad_contada: cantidad },
          });
          this._upsertItem(item);
          this.auditoria.cantidad_items = this.auditoria.items.length;
          this.codigo = '';
          this.contadas = 1;
        } catch (e) {
          window.toast(e.message, 'error');
        } finally {
          this.agregando = false;
          this.$nextTick(() => this.$refs.inputCodigo && this.$refs.inputCodigo.focus());
        }
      },

      async guardarContado(item, valorCrudo) {
        const valor = Math.max(0, Math.trunc(Number(valorCrudo)) || 0);
        if (valor === item.cantidad_contada) return;
        try {
          const actualizado = await window.pedir(`${API}/${this.id}/items/${item.id}`, {
            method: 'PATCH',
            body: { cantidad_contada: valor },
          });
          this._upsertItem(actualizado);
        } catch (e) {
          window.toast(e.message, 'error');
          this.cargar();  // vuelve a traer el valor real si el guardado falló
        }
      },

      async quitarItem(item) {
        const ok = await window.confirmar({
          titulo: `¿Quitar "${item.descripcion}" del conteo?`,
          mensaje: 'Se puede volver a escanear si hace falta.',
          textoConfirmar: 'Quitar',
          peligro: true,
        });
        if (!ok) return;
        try {
          await window.pedir(`${API}/${this.id}/items/${item.id}`, { method: 'DELETE' });
          this.auditoria.items = this.auditoria.items.filter((i) => i.id !== item.id);
          this.auditoria.cantidad_items = this.auditoria.items.length;
        } catch (e) {
          window.toast(e.message, 'error');
        }
      },

      async cerrarConteo() {
        const ok = await window.confirmar({
          titulo: '¿Cerrar el conteo?',
          mensaje: 'Se ajusta el stock de los productos con diferencias.',
          textoConfirmar: 'Cerrar',
          peligro: true,
        });
        if (!ok) return;
        this.cerrando = true;
        try {
          const cerrada = await window.pedir(`${API}/${this.id}/finalizar`, { method: 'PATCH' });
          this.auditoria = { ...this.auditoria, ...cerrada };
          window.toast('Conteo cerrado; el stock quedó ajustado.');
        } catch (e) {
          window.toast(e.message, 'error');
        } finally {
          this.cerrando = false;
        }
      },

      // ---------- PDF ----------
      async imprimirPdf() {
        await imprimirPdfDe(this.id);
      },
    };
  };
})();
