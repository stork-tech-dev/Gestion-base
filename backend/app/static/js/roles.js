/* Pantalla de roles (solo Admin): filtros, alta/edición, activar/desactivar y eliminar. */
(function () {
  'use strict';

  const API = '/api/v1/roles';
  const formVacio = () => ({ id: null, nombre: '', descripcion: '', es_sistema: false });

  window.rolesListado = function () {
    return {
      filtros: { nombre: '', tipo: '', estado: '' },
      filas: [],
      cargando: false,
      formAbierto: false,
      form: formVacio(),
      errores: {},
      guardando: false,
      _espera: null,

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
        this.filtros = { nombre: '', tipo: '', estado: '' };
        this.cargar();
      },

      async cargar() {
        this.cargando = true;
        const params = new URLSearchParams();
        if (this.filtros.nombre.trim()) params.set('nombre', this.filtros.nombre.trim());
        if (this.filtros.tipo) params.set('es_sistema', this.filtros.tipo === 'sistema');
        if (this.filtros.estado) params.set('activo', this.filtros.estado === 'activos');
        try {
          this.filas = await window.pedir(`${API}?${params}`);
        } catch (e) {
          window.toast(e.message, 'error');
        } finally {
          this.cargando = false;
        }
      },

      celdaNombre(r) {
        const sistema = r.es_sistema ? ' <span class="text-xs text-texto-muted">(del sistema)</span>' : '';
        return window.escaparHtml(r.nombre) + sistema;
      },

      nuevo() {
        this.form = formVacio();
        this.errores = {};
        this.formAbierto = true;
      },

      editar(r) {
        this.form = { id: r.id, nombre: r.nombre, descripcion: r.descripcion || '', es_sistema: r.es_sistema };
        this.errores = {};
        this.formAbierto = true;
      },

      async guardar() {
        const esAlta = !this.form.id;
        this.guardando = true;
        this.errores = {};
        try {
          await window.pedir(esAlta ? API : `${API}/${this.form.id}`, {
            method: esAlta ? 'POST' : 'PUT',
            body: { nombre: this.form.nombre, descripcion: this.form.descripcion || null },
          });
          window.toast(esAlta ? 'Rol creado. Definí sus permisos desde "Permisos".' : 'Cambios guardados.');
          this.formAbierto = false;
          this.cargar();
        } catch (e) {
          this.errores = window.erroresDeCampos(e);
          window.toast(e.message, 'error');
        } finally {
          this.guardando = false;
        }
      },

      async cambiarEstado(r, activo) {
        const conUsuarios = !activo && r.cantidad_usuarios > 0;
        const ok = await window.confirmar({
          titulo: activo ? `¿Activar el rol ${r.nombre}?` : `¿Desactivar el rol ${r.nombre}?`,
          mensaje: activo ? 'Se va a poder asignar a usuarios.' : 'No se va a poder asignar a usuarios nuevos.',
          advertencia: conUsuarios
            ? `El rol tiene ${r.cantidad_usuarios} usuario(s). Si alguno está activo, primero hay que desactivarlo o cambiarle el rol.`
            : '',
          textoConfirmar: activo ? 'Activar' : 'Desactivar',
          peligro: !activo,
        });
        if (!ok) return;
        try {
          await window.pedir(`${API}/${r.id}/estado`, { method: 'PATCH', body: { activo } });
          window.toast(activo ? 'Rol activado.' : 'Rol desactivado.');
          this.cargar();
        } catch (e) {
          window.toast(e.message, 'error');
        }
      },

      async eliminar(r) {
        const ok = await window.confirmar({
          titulo: `¿Eliminar el rol ${r.nombre}?`,
          mensaje: 'Se borra junto con sus permisos. No se puede deshacer.',
          textoConfirmar: 'Eliminar',
          peligro: true,
        });
        if (!ok) return;
        try {
          await window.pedir(`${API}/${r.id}`, { method: 'DELETE' });
          window.toast('Rol eliminado.');
          this.cargar();
        } catch (e) {
          window.toast(e.message, 'error');
        }
      },
    };
  };
})();
