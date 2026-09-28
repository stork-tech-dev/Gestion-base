/* Promociones de ventas (2x1, 3x2 y % descuento), con su alcance (productos,
   categorías y medios de pago). Todos los datos salen de la API
   (/api/v1/configuracion/promociones y .../promociones/catalogos). Pocas
   promociones: se filtran en tiempo real, sin paginado. */
(function () {
  'use strict';

  const API = '/api/v1/configuracion/promociones';
  const CATALOGOS_URL = '/api/v1/configuracion/promociones/catalogos';

  const TIPOS = { dos_x_uno: '2x1', tres_x_dos: '3x2', porcentaje: '% Porcentaje' };

  const filtrosVacios = () => ({ nombre: '', tipo: '', vigencia: '' });
  const formVacio = () => ({
    id: null, nombre: '', nota: '', tipo: 'dos_x_uno', porcentaje_descuento: '',
    fecha_inicio: '', fecha_fin: '', alcances: [], medio_de_pago_ids: [],
  });
  const textoONull = (valor) => String(valor ?? '').trim() || null;

  window.promocionesListado = function ({ puedeEditar }) {
    return {
      puedeEditar,
      filtros: filtrosVacios(),
      soloActivos: true,
      filas: [],
      cargando: false,
      _ultima: window.ultimaRespuesta(),
      _espera: null,
      catalogo: { productos: [], categorias: [], medios: [] },

      formAbierto: false,
      form: formVacio(),
      errores: {},
      guardando: false,
      nuevoAlcanceTipo: 'producto',
      nuevoProductoId: null,
      nuevoCategoriaId: null,

      get total() {
        return this.filas.length;
      },

      async init() {
        this.cargar();
        try {
          this.catalogo = await window.pedir(CATALOGOS_URL);
        } catch (e) {
          window.toast(e.message, 'error');
        }
      },

      filtrar() {
        clearTimeout(this._espera);
        this._espera = setTimeout(() => this.cargar(), 400);
      },

      limpiarFiltros() {
        this.filtros = filtrosVacios();
        this.soloActivos = true;
        this.cargar();
      },

      async cargar() {
        this.cargando = true;
        const params = new URLSearchParams();
        const nombre = this.filtros.nombre.trim();
        if (nombre) params.set('nombre', nombre);
        if (this.filtros.tipo) params.set('tipo', this.filtros.tipo);
        if (this.filtros.vigencia) params.set('rige_hoy', this.filtros.vigencia);
        if (this.soloActivos) params.set('activo', 'true');
        try {
          const filas = await this._ultima(window.pedir(`${API}?${params}`));
          if (filas === undefined) return;  // llegó una respuesta más nueva
          this.filas = filas;
          this.cargando = false;
        } catch (e) {
          this.cargando = false;
          window.toast(e.message, 'error');
        }
      },

      celdaNombre(p) {
        const nombre = window.escaparHtml(p.nombre);
        return p.nota ? `<span title="${window.escaparHtml(p.nota)}">${nombre}</span>` : nombre;
      },

      celdaEstado(p) {
        return p.activo ? window.estadoHtml('Activo', 'exito') : window.estadoHtml('Inactivo', 'peligro');
      },

      tipoTexto(p) {
        return TIPOS[p.tipo] || p.tipo;
      },

      vigenciaTexto(p) {
        if (!p.fecha_inicio && !p.fecha_fin) return 'Sin límite';
        const desde = p.fecha_inicio ? window.fecha(p.fecha_inicio) : '';
        const hasta = p.fecha_fin ? window.fecha(p.fecha_fin) : '';
        if (desde && hasta) return `${desde} – ${hasta}`;
        return desde ? `Desde ${desde}` : `Hasta ${hasta}`;
      },

      textoAlcance(a) {
        if (a.tipo_alcance === 'todos_productos') return 'Todos los productos';
        if (a.tipo_alcance === 'todos_categorias') return 'Todas las categorías';
        if (a.tipo_alcance === 'producto') {
          const p = this.catalogo.productos.find((x) => x.id === a.referencia_id);
          return p ? p.descripcion : `Producto #${a.referencia_id}`;
        }
        if (a.tipo_alcance === 'categoria') {
          const c = this.catalogo.categorias.find((x) => x.id === a.referencia_id);
          return c ? c.camino : `Categoría #${a.referencia_id}`;
        }
        return '';
      },

      alcanceResumen(p) {
        const partes = p.alcances.filter((a) => a.tipo_alcance !== 'medio_de_pago').map((a) => this.textoAlcance(a));
        return partes.join(', ') || '—';
      },

      agregarAlcance() {
        const tipo = this.nuevoAlcanceTipo;
        let referenciaId = 0;
        if (tipo === 'producto') {
          if (!this.nuevoProductoId) return;
          referenciaId = this.nuevoProductoId;
        } else if (tipo === 'categoria') {
          if (!this.nuevoCategoriaId) return;
          referenciaId = this.nuevoCategoriaId;
        }
        const yaExiste = this.form.alcances.some((a) => a.tipo_alcance === tipo && a.referencia_id === referenciaId);
        if (yaExiste) {
          window.toast('Ese alcance ya está agregado.', 'error');
          return;
        }
        this.form.alcances.push({ tipo_alcance: tipo, referencia_id: referenciaId });
        this.nuevoProductoId = null;
        this.nuevoCategoriaId = null;
      },

      quitarAlcance(indice) {
        this.form.alcances.splice(indice, 1);
      },

      alternarMedio(id) {
        const i = this.form.medio_de_pago_ids.indexOf(id);
        if (i >= 0) this.form.medio_de_pago_ids.splice(i, 1);
        else this.form.medio_de_pago_ids.push(id);
      },

      nuevo() {
        this.form = formVacio();
        this.errores = {};
        this.nuevoAlcanceTipo = 'producto';
        this.nuevoProductoId = null;
        this.nuevoCategoriaId = null;
        this.formAbierto = true;
      },

      editar(p) {
        const medios = p.alcances.filter((a) => a.tipo_alcance === 'medio_de_pago').map((a) => a.referencia_id);
        const resto = p.alcances.filter((a) => a.tipo_alcance !== 'medio_de_pago')
          .map((a) => ({ tipo_alcance: a.tipo_alcance, referencia_id: a.referencia_id }));
        this.form = {
          id: p.id, nombre: p.nombre, nota: p.nota || '', tipo: p.tipo,
          porcentaje_descuento: p.porcentaje_descuento ?? '',
          fecha_inicio: p.fecha_inicio || '', fecha_fin: p.fecha_fin || '',
          alcances: resto, medio_de_pago_ids: medios,
        };
        this.errores = {};
        this.nuevoAlcanceTipo = 'producto';
        this.nuevoProductoId = null;
        this.nuevoCategoriaId = null;
        this.formAbierto = true;
      },

      _cuerpo() {
        const alcances = [
          ...this.form.alcances,
          ...this.form.medio_de_pago_ids.map((id) => ({ tipo_alcance: 'medio_de_pago', referencia_id: id })),
        ];
        return {
          nombre: this.form.nombre,
          nota: textoONull(this.form.nota),
          tipo: this.form.tipo,
          porcentaje_descuento: this.form.tipo === 'porcentaje' ? Number(this.form.porcentaje_descuento) : null,
          fecha_inicio: this.form.fecha_inicio || null,
          fecha_fin: this.form.fecha_fin || null,
          alcances,
        };
      },

      async guardar() {
        const esAlta = !this.form.id;
        this.guardando = true;
        this.errores = {};
        try {
          await window.pedir(esAlta ? API : `${API}/${this.form.id}`, { method: esAlta ? 'POST' : 'PUT', body: this._cuerpo() });
          window.toast(esAlta ? 'Promoción creada.' : 'Cambios guardados.');
          this.formAbierto = false;
          this.cargar();
        } catch (e) {
          this.errores = window.erroresDeCampos(e);
          window.toast(e.message, 'error');
        } finally {
          this.guardando = false;
        }
      },

      async cambiarEstado(p, activo) {
        const ok = await window.confirmar({
          titulo: activo ? `¿Activar "${p.nombre}"?` : `¿Desactivar "${p.nombre}"?`,
          mensaje: activo ? 'Va a volver a poder aplicarse en las ventas.' : 'No se va a aplicar en ventas nuevas.',
          textoConfirmar: activo ? 'Activar' : 'Desactivar',
          peligro: !activo,
        });
        if (!ok) return;
        try {
          await window.pedir(`${API}/${p.id}/estado`, { method: 'PATCH', body: { activo } });
          window.toast(activo ? 'Promoción activada.' : 'Promoción desactivada.');
          this.cargar();
        } catch (e) {
          window.toast(e.message, 'error');
        }
      },
    };
  };
})();
