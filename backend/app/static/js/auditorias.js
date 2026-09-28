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
        return window.categoriasOpciones(this.arbol);
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
      async imprimirPdf(fila) {
        await window.abrirPdf(`${API}/${fila.id}/pdf`);
      },
    };
  };

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

      // ¿Ya hay, entre los ítems cargados, uno del mismo producto que el
      // código tipeado/escaneado? Compara contra el código completo (con
      // verificador, como lo guarda cada ítem) y contra el SKU solo (los
      // primeros 5 caracteres): cubre tanto escanear la etiqueta de vuelta
      // como tipear el SKU a mano.
      _itemPorCodigo(codigo) {
        const normalizado = (codigo || '').trim().toUpperCase();
        if (!normalizado || !this.auditoria) return null;
        return this.auditoria.items.find((i) => {
          const c = (i.codigo || '').toUpperCase();
          return c === normalizado || c.slice(0, 5) === normalizado;
        }) || null;
      },

      // Re-escanear un producto ya contado pisaba lo contado sin avisar.
      // window.confirmar solo admite sí/no, así que va en dos pasos: primero
      // ofrece sumar (sí = N+M); si dice que no, ofrece reemplazar (sí = M,
      // no = cancela el alta). Devuelve la cantidad a mandar, o null si se canceló.
      async _resolverRecontado(item, cantidadNueva) {
        const suma = item.cantidad_contada + cantidadNueva;
        const sumar = await window.confirmar({
          titulo: `Ya contaste ${item.cantidad_contada} de "${item.descripcion}"`,
          mensaje: `¿Sumar ${cantidadNueva}? Vas a tener ${suma}.`,
          textoConfirmar: 'Sumar',
        });
        if (sumar) return suma;
        const reemplazar = await window.confirmar({
          titulo: `¿Reemplazar el conteo de "${item.descripcion}"?`,
          mensaje: `Los ${item.cantidad_contada} contados pasan a ser ${cantidadNueva}.`,
          textoConfirmar: 'Reemplazar',
          peligro: true,
        });
        return reemplazar ? cantidadNueva : null;
      },

      async agregarPorCodigo() {
        const codigo = (this.codigo || '').trim();
        if (!codigo) {
          this.$refs.inputCodigo.focus();
          return;
        }
        const cantidad = Math.max(0, Math.trunc(Number(this.contadas)) || 0);
        const existente = this._itemPorCodigo(codigo);
        let cantidadContada = cantidad;
        if (existente) {
          cantidadContada = await this._resolverRecontado(existente, cantidad);
          if (cantidadContada === null) return;  // canceló los dos pasos
        }
        this.agregando = true;
        try {
          const item = await window.pedir(`${API}/${this.id}/items/por-codigo`, {
            method: 'POST',
            body: { codigo, cantidad_contada: cantidadContada },
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
          // 409 más frecuente acá: el ajuste de algún producto no se pudo
          // aplicar porque el stock real cambió después de contarlo (ej. se
          // vendió con faltante entre el conteo y el cierre).
          const mensaje = e.status === 409
            ? `${e.message} Volvé a escanear ese producto para tomar el stock actual.`
            : e.message;
          window.toast(mensaje, 'error');
        } finally {
          this.cerrando = false;
        }
      },

      // ---------- PDF ----------
      async imprimirPdf() {
        await window.abrirPdf(`${API}/${this.id}/pdf`);
      },
    };
  };
})();
