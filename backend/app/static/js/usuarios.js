/* Pantalla de usuarios: listado con filtros, detalle, alta/edición con
   "Accesos permitidos" y activar/desactivar. Todos los datos salen de la API. */
(function () {
  'use strict';

  const API = '/api/v1/usuarios';
  const formVacio = () => ({
    id: null, username: '', nombre: '', rol_id: null, email: '', fecha_nacimiento: '', celular: '', password: '',
  });

  window.usuariosListado = function ({ esAdmin, usuarioActualId, rolesGestionables, rolesFiltro, puedeEditar }) {
    return {
      rolesFiltro,
      filtros: { nombre: '', rol_id: null },
      soloActivos: true,
      pagina: 1,
      tamano: 10,
      total: 0,
      filas: [],
      cargando: false,
      rolesAsignables: [],
      detalle: null,
      verAbierto: false,
      formAbierto: false,
      form: formVacio(),
      rolOriginal: null,
      errores: {},
      guardando: false,
      accesos: [],
      marcados: [],
      _espera: null,

      async init() {
        this.cargar();
        try {
          this.rolesAsignables = await window.pedir(`${API}/roles-asignables`);
        } catch (e) {
          window.toast(e.message, 'error');
        }
      },

      filtrar() {
        clearTimeout(this._espera);
        this._espera = setTimeout(() => { this.pagina = 1; this.cargar(); }, 400);
      },

      limpiarFiltros() {
        this.filtros = { nombre: '', rol_id: null };
        this.soloActivos = true;
        this.pagina = 1;
        this.cargar();
      },

      async cargar() {
        this.cargando = true;
        const params = new URLSearchParams({ pagina: this.pagina, tamano: this.tamano });
        if (this.filtros.nombre.trim()) params.set('nombre', this.filtros.nombre.trim());
        if (this.filtros.rol_id) params.set('rol_id', this.filtros.rol_id);
        if (this.soloActivos) params.set('activo', 'true');
        try {
          const respuesta = await window.pedir(`${API}?${params}`);
          this.filas = respuesta.resultados;
          this.total = respuesta.total;
        } catch (e) {
          window.toast(e.message, 'error');
        } finally {
          this.cargando = false;
        }
      },

      celdaUsuario(u) {
        const inactivo = u.activo ? '' : ` ${window.estadoHtml('Inactivo', 'peligro')}`;
        return window.escaparHtml(u.username) + inactivo;
      },

      // Solo oculta botones: la API vuelve a validar todo.
      puedeGestionar(u) {
        if (!puedeEditar) return false;
        if (esAdmin) return true;
        return u.id !== usuarioActualId && (rolesGestionables || []).includes(u.rol);
      },

      ver(u) {
        this.detalle = u;
        this.verAbierto = true;
      },

      nuevo() {
        this.form = formVacio();
        this.rolOriginal = null;
        this.errores = {};
        this.accesos = [];
        this.marcados = [];
        this.formAbierto = true;
      },

      async editar(u) {
        this.form = {
          id: u.id, username: u.username, nombre: u.nombre, rol_id: u.rol_id, email: u.email || '',
          fecha_nacimiento: u.fecha_nacimiento || '', celular: u.celular || '', password: '',
        };
        this.rolOriginal = u.rol_id;
        this.errores = {};
        this.accesos = [];
        this.marcados = [];
        this.formAbierto = true;
        try {
          this.accesos = await window.pedir(`${API}/${u.id}/accesos`);
          this.marcados = this.accesos.filter((a) => a.override && !a.heredado).map((a) => a.clave);
        } catch (e) {
          window.toast(e.message, 'error');
        }
      },

      async alCambiarRol() {
        if (!this.form.rol_id) {
          this.accesos = [];
          return;
        }
        try {
          const delRol = await window.pedir(`${API}/accesos?rol_id=${this.form.rol_id}`);
          const heredados = new Set(delRol.filter((a) => a.heredado).map((a) => a.clave));
          this.marcados = this.marcados.filter((clave) => !heredados.has(clave));
          this.accesos = delRol;
        } catch (e) {
          window.toast(e.message, 'error');
        }
      },

      marcado(a) {
        return a.heredado || this.marcados.includes(a.clave);
      },

      // Lo heredado no se toca; lo no otorgable no se puede agregar (sí quitar).
      bloqueado(a) {
        return a.heredado || (!a.otorgable && !this.marcados.includes(a.clave));
      },

      alternarAcceso(a) {
        if (this.bloqueado(a)) return;
        const i = this.marcados.indexOf(a.clave);
        if (i >= 0) this.marcados.splice(i, 1);
        else this.marcados.push(a.clave);
      },

      _cuerpo() {
        const cuerpo = {
          nombre: this.form.nombre,
          email: this.form.email || null,
          fecha_nacimiento: this.form.fecha_nacimiento || null,
          celular: this.form.celular || null,
        };
        if (!this.form.id) {
          return { ...cuerpo, username: this.form.username, password: this.form.password, rol_id: this.form.rol_id };
        }
        if (this.form.rol_id !== this.rolOriginal) cuerpo.rol_id = this.form.rol_id;
        if (this.form.password) cuerpo.password = this.form.password;
        return cuerpo;
      },

      async guardar() {
        const esAlta = !this.form.id;
        this.guardando = true;
        this.errores = {};
        try {
          const usuario = await window.pedir(esAlta ? API : `${API}/${this.form.id}`, {
            method: esAlta ? 'POST' : 'PUT',
            body: this._cuerpo(),
          });
          this.form.id = usuario.id;  // si falla lo que sigue, reintentar edita en vez de duplicar
          await window.pedir(`${API}/${usuario.id}/accesos`, { method: 'PUT', body: { accesos: this.marcados } });
          window.toast(esAlta ? 'Usuario creado. Va a cambiar la contraseña en su primer ingreso.' : 'Cambios guardados.');
          this.formAbierto = false;
        } catch (e) {
          this.errores = window.erroresDeCampos(e);
          window.toast(e.message, 'error');
        } finally {
          this.guardando = false;
          this.cargar();
        }
      },

      async cambiarEstado(u, activo) {
        const ok = await window.confirmar({
          titulo: activo ? `¿Activar a ${u.nombre}?` : `¿Desactivar a ${u.nombre}?`,
          mensaje: activo ? 'Va a poder volver a ingresar.' : 'No va a poder ingresar y se cierran sus sesiones abiertas.',
          textoConfirmar: activo ? 'Activar' : 'Desactivar',
          peligro: !activo,
        });
        if (!ok) return;
        try {
          await window.pedir(`${API}/${u.id}/estado`, { method: 'PATCH', body: { activo } });
          window.toast(activo ? 'Usuario activado.' : 'Usuario desactivado.');
          this.cargar();
        } catch (e) {
          window.toast(e.message, 'error');
        }
      },
    };
  };
})();
