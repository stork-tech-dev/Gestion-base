/* Medios de pago y sus planes de cuotas. Todos los datos salen de la API
   (/api/v1/configuracion/medios-de-pago y /planes-cuotas). Los medios y sus
   planes son pocos: se filtran en tiempo real, sin paginado. */
(function () {
  'use strict';

  const API = '/api/v1/configuracion/medios-de-pago';
  const PLANES_API = '/api/v1/configuracion/planes-cuotas';

  const filtrosVacios = () => ({ nombre: '', cuotas: '' });
  const formVacio = () => ({ id: null, nombre: '', soporta_cuotas: false, es_efectivo: false });
  const planVacio = (medioId) => ({
    id: null, medio_de_pago_id: medioId, cuotas: 1, recargo_cliente: '0', costo_medio: '0', monto_minimo: '0',
  });

  window.mediosPagoListado = function ({ puedeEditar }) {
    return {
      puedeEditar,
      filtros: filtrosVacios(),
      soloActivos: true,
      filas: [],
      cargando: false,
      _ultima: window.ultimaRespuesta(),
      _espera: null,

      ficha: null,
      fichaAbierta: false,

      formAbierto: false,
      form: formVacio(),
      errores: {},
      guardando: false,

      planForm: null,
      planFormAbierto: false,
      erroresPlan: {},
      guardandoPlan: false,

      get total() {
        return this.filas.length;
      },

      init() {
        this.cargar();
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
        if (this.filtros.cuotas) params.set('soporta_cuotas', this.filtros.cuotas);
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

      celdaMarcas(m) {
        const partes = [];
        if (m.soporta_cuotas) partes.push(window.badgeHtml('Cuotas', 'primario'));
        if (m.es_efectivo) partes.push(window.badgeHtml('Efectivo', 'exito'));
        return partes.join(' ') || '—';
      },

      celdaEstado(m) {
        return m.activo ? window.estadoHtml('Activo', 'exito') : window.estadoHtml('Inactivo', 'peligro');
      },

      ver(m) {
        this.ficha = m;
        this.fichaAbierta = true;
      },

      nuevo() {
        this.form = formVacio();
        this.errores = {};
        this.formAbierto = true;
      },

      editar(m) {
        this.form = { id: m.id, nombre: m.nombre, soporta_cuotas: m.soporta_cuotas, es_efectivo: m.es_efectivo };
        this.errores = {};
        this.formAbierto = true;
      },

      // El efectivo de la caja no admite cuotas (CHECK de la base): se
      // excluyen entre sí para no depender solo de la validación del backend.
      alAlternarCuotas() {
        if (this.form.soporta_cuotas) this.form.es_efectivo = false;
      },

      alAlternarEfectivo() {
        if (this.form.es_efectivo) this.form.soporta_cuotas = false;
      },

      async guardar() {
        const esAlta = !this.form.id;
        this.guardando = true;
        this.errores = {};
        try {
          const cuerpo = { nombre: this.form.nombre, soporta_cuotas: this.form.soporta_cuotas, es_efectivo: this.form.es_efectivo };
          await window.pedir(esAlta ? API : `${API}/${this.form.id}`, { method: esAlta ? 'POST' : 'PUT', body: cuerpo });
          window.toast(esAlta ? 'Medio de pago creado.' : 'Cambios guardados.');
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
          mensaje: activo ? 'Va a volver a estar disponible para cobrar.' : 'No va a estar disponible para cobrar ventas nuevas.',
          textoConfirmar: activo ? 'Activar' : 'Desactivar',
          peligro: !activo,
        });
        if (!ok) return;
        try {
          await window.pedir(`${API}/${m.id}/estado`, { method: 'PATCH', body: { activo } });
          window.toast(activo ? 'Medio de pago activado.' : 'Medio de pago desactivado.');
          this.cargar();
        } catch (e) {
          window.toast(e.message, 'error');
        }
      },

      // ---------- Planes de cuotas (dentro de la ficha del medio) ----------
      async _recargarPlanes() {
        try {
          this.ficha.planes = await window.pedir(`${API}/${this.ficha.id}/planes`);
        } catch (e) {
          window.toast(e.message, 'error');
        }
      },

      nuevoPlan() {
        this.planForm = planVacio(this.ficha.id);
        this.erroresPlan = {};
        this.planFormAbierto = true;
      },

      editarPlan(p) {
        this.planForm = { ...p };
        this.erroresPlan = {};
        this.planFormAbierto = true;
      },

      async guardarPlan() {
        const esAlta = !this.planForm.id;
        this.guardandoPlan = true;
        this.erroresPlan = {};
        try {
          const cuerpo = {
            cuotas: this.planForm.cuotas,
            recargo_cliente: this.planForm.recargo_cliente,
            costo_medio: this.planForm.costo_medio,
            monto_minimo: this.planForm.monto_minimo,
          };
          await window.pedir(esAlta ? `${API}/${this.ficha.id}/planes` : `${PLANES_API}/${this.planForm.id}`, {
            method: esAlta ? 'POST' : 'PUT',
            body: cuerpo,
          });
          window.toast(esAlta ? 'Plan creado.' : 'Cambios guardados.');
          this.planFormAbierto = false;
          await this._recargarPlanes();
          this.cargar();
        } catch (e) {
          this.erroresPlan = window.erroresDeCampos(e);
          window.toast(e.message, 'error');
        } finally {
          this.guardandoPlan = false;
        }
      },

      async cambiarEstadoPlan(p, activo) {
        const ok = await window.confirmar({
          titulo: activo ? `¿Activar el plan de ${p.cuotas} cuotas?` : `¿Desactivar el plan de ${p.cuotas} cuotas?`,
          mensaje: activo ? 'Va a volver a ofrecerse en la venta.' : 'No se va a ofrecer en ventas nuevas.',
          textoConfirmar: activo ? 'Activar' : 'Desactivar',
          peligro: !activo,
        });
        if (!ok) return;
        try {
          await window.pedir(`${PLANES_API}/${p.id}/estado`, { method: 'PATCH', body: { activo } });
          window.toast(activo ? 'Plan activado.' : 'Plan desactivado.');
          await this._recargarPlanes();
        } catch (e) {
          window.toast(e.message, 'error');
        }
      },
    };
  };
})();
