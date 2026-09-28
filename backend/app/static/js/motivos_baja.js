/* ABM simple de motivos de baja de stock (Rotura, Extravío, etc.). Todos los
   datos salen de la API (GET/POST/PUT /api/v1/stock/motivos-baja). */
(function () {
  'use strict';

  const API = '/api/v1/stock/motivos-baja';
  const filtrosVacios = () => ({ nombre: '', activos: true });
  const formVacio = () => ({ id: null, nombre: '', activo: true });

  window.motivosBaja = function () {
    return {
      filtros: filtrosVacios(),
      filas: [],
      cargando: false,
      _ultima: window.ultimaRespuesta(),
      _espera: null,
      formAbierto: false,
      form: formVacio(),
      errores: {},
      guardando: false,

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
        this.cargar();
      },

      async cargar() {
        this.cargando = true;
        const params = new URLSearchParams();
        const nombre = (this.filtros.nombre || '').trim();
        if (nombre) params.set('nombre', nombre);
        params.set('activo', this.filtros.activos ? 'true' : 'false');
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

      celdaEstado(m) {
        return m.activo ? window.estadoHtml('Activo', 'exito') : window.estadoHtml('Inactivo', 'peligro');
      },

      nuevo() {
        this.form = formVacio();
        this.errores = {};
        this.formAbierto = true;
      },

      editar(m) {
        this.form = { id: m.id, nombre: m.nombre, activo: m.activo };
        this.errores = {};
        this.formAbierto = true;
      },

      async guardar() {
        const esAlta = !this.form.id;
        this.guardando = true;
        this.errores = {};
        try {
          if (esAlta) {
            await window.pedir(API, { method: 'POST', body: { nombre: this.form.nombre } });
            window.toast('Motivo creado.');
          } else {
            await window.pedir(`${API}/${this.form.id}`, {
              method: 'PUT',
              body: { nombre: this.form.nombre, activo: this.form.activo },
            });
            window.toast('Cambios guardados.');
          }
          this.formAbierto = false;
          this.cargar();
        } catch (e) {
          this.errores = window.erroresDeCampos(e);
          window.toast(e.message, 'error');
        } finally {
          this.guardando = false;
        }
      },

      async cambiarEstado(m) {
        const activar = !m.activo;
        const ok = await window.confirmar({
          titulo: activar ? `¿Activar "${m.nombre}"?` : `¿Desactivar "${m.nombre}"?`,
          mensaje: activar ? 'Va a volver a estar disponible para registrar bajas.' : 'No va a estar disponible para registrar bajas nuevas.',
          textoConfirmar: activar ? 'Activar' : 'Desactivar',
          peligro: !activar,
        });
        if (!ok) return;
        try {
          await window.pedir(`${API}/${m.id}`, { method: 'PUT', body: { nombre: m.nombre, activo: activar } });
          window.toast(activar ? 'Motivo activado.' : 'Motivo desactivado.');
          this.cargar();
        } catch (e) {
          window.toast(e.message, 'error');
        }
      },
    };
  };
})();
