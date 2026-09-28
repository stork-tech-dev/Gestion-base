/* Motivos de descuento en ventas (nota, % sugerido, cuotas sin interés,
   vigencia y medios de pago en los que rige). Todos los datos salen de la
   API (/api/v1/configuracion/motivos-descuento); el catálogo de medios de
   pago sale de /api/v1/configuracion/medios-de-pago (misma pantalla, mismo
   permiso CONFIGURACION ver). Pocos motivos: se filtran en tiempo real, sin
   paginado. */
(function () {
  'use strict';

  const API = '/api/v1/configuracion/motivos-descuento';
  const MEDIOS_API = '/api/v1/configuracion/medios-de-pago';

  const filtrosVacios = () => ({ nombre: '', habilita: '' });
  const formVacio = () => ({
    id: null, nombre: '', nota: '', sinSugerido: true, porcentaje_sugerido: '',
    habilita_cuotas_sin_interes: false, fecha_inicio: '', fecha_fin: '', medio_de_pago_ids: [],
  });
  const textoONull = (valor) => String(valor ?? '').trim() || null;

  window.motivosDescuentoListado = function ({ puedeEditar, porcentajesDescuento }) {
    return {
      puedeEditar,
      porcentajesDescuento,
      filtros: filtrosVacios(),
      soloActivos: true,
      filas: [],
      cargando: false,
      _ultima: window.ultimaRespuesta(),
      _espera: null,
      mediosCatalogo: [],

      formAbierto: false,
      form: formVacio(),
      errores: {},
      guardando: false,

      get total() {
        return this.filas.length;
      },

      async init() {
        this.cargar();
        try {
          this.mediosCatalogo = await window.pedir(`${MEDIOS_API}?activo=true`);
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
        if (this.filtros.habilita) params.set('habilita_cuotas_sin_interes', this.filtros.habilita);
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

      celdaNombre(m) {
        const nombre = window.escaparHtml(m.nombre);
        return m.nota ? `<span title="${window.escaparHtml(m.nota)}">${nombre}</span>` : nombre;
      },

      porcentajeTexto(m) {
        // La API manda "10.00" (NUMERIC(5,2)): se muestra "10%".
        return m.porcentaje_sugerido === null ? 'Lo elige quien vende' : `${Number(m.porcentaje_sugerido)}%`;
      },

      celdaEstado(m) {
        return m.activo ? window.estadoHtml('Activo', 'exito') : window.estadoHtml('Inactivo', 'peligro');
      },

      alAlternarSinSugerido() {
        if (this.form.sinSugerido) this.form.porcentaje_sugerido = '';
      },

      alternarMedio(id) {
        const i = this.form.medio_de_pago_ids.indexOf(id);
        if (i >= 0) this.form.medio_de_pago_ids.splice(i, 1);
        else this.form.medio_de_pago_ids.push(id);
      },

      nuevo() {
        this.form = formVacio();
        this.errores = {};
        this.formAbierto = true;
      },

      editar(m) {
        this.form = {
          id: m.id, nombre: m.nombre, nota: m.nota || '',
          sinSugerido: m.porcentaje_sugerido === null,
          // "10.00" → "10", para que coincida con la opción del select.
          porcentaje_sugerido: m.porcentaje_sugerido === null ? '' : String(Number(m.porcentaje_sugerido)),
          habilita_cuotas_sin_interes: m.habilita_cuotas_sin_interes,
          fecha_inicio: m.fecha_inicio || '', fecha_fin: m.fecha_fin || '',
          medio_de_pago_ids: [...m.medio_de_pago_ids],
        };
        this.errores = {};
        this.formAbierto = true;
      },

      _cuerpo() {
        return {
          nombre: this.form.nombre,
          nota: textoONull(this.form.nota),
          porcentaje_sugerido: this.form.sinSugerido ? null : Number(this.form.porcentaje_sugerido),
          habilita_cuotas_sin_interes: this.form.habilita_cuotas_sin_interes,
          fecha_inicio: this.form.fecha_inicio || null,
          fecha_fin: this.form.fecha_fin || null,
          medio_de_pago_ids: this.form.medio_de_pago_ids,
        };
      },

      async guardar() {
        const esAlta = !this.form.id;
        this.guardando = true;
        this.errores = {};
        try {
          await window.pedir(esAlta ? API : `${API}/${this.form.id}`, { method: esAlta ? 'POST' : 'PUT', body: this._cuerpo() });
          window.toast(esAlta ? 'Motivo de descuento creado.' : 'Cambios guardados.');
          this.formAbierto = false;
          this.cargar();
        } catch (e) {
          this.errores = window.erroresDeCampos(e);
          window.toast(e.message, 'error');
        } finally {
          this.guardando = false;
        }
      },

      async cambiarEstado(m, activo) {
        const ok = await window.confirmar({
          titulo: activo ? `¿Activar "${m.nombre}"?` : `¿Desactivar "${m.nombre}"?`,
          mensaje: activo ? 'Va a volver a poder aplicarse en las ventas.' : 'No se va a poder aplicar en ventas nuevas.',
          textoConfirmar: activo ? 'Activar' : 'Desactivar',
          peligro: !activo,
        });
        if (!ok) return;
        try {
          await window.pedir(`${API}/${m.id}/estado`, { method: 'PATCH', body: { activo } });
          window.toast(activo ? 'Motivo activado.' : 'Motivo desactivado.');
          this.cargar();
        } catch (e) {
          window.toast(e.message, 'error');
        }
      },
    };
  };
})();
