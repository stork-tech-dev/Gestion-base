/* Clientes de ventas: listado con filtros, alta/edición, activar/desactivar
   y ficha (compras confirmadas + promociones exclusivas). Todos los datos
   salen de la API (/api/v1/clientes). */
(function () {
  'use strict';

  const API = '/api/v1/clientes';
  const PROMOCIONES_API = '/api/v1/configuracion/promociones';

  const filtrosVacios = () => ({ busqueda: '', localidad: '', condicion_iva: '' });
  const formVacio = () => ({
    id: null, nombre: '', dni: '', cuit: '', condicion_iva: 'consumidor_final',
    domicilio: '', codigo_postal: '', localidad: '', telefono: '', email: '',
  });
  const textoONull = (valor) => String(valor ?? '').trim() || null;

  window.clientesListado = function ({ puedeCrear, puedeEditar, puedeVerPromociones, condicionesIva }) {
    return {
      puedeCrear,
      puedeEditar,
      puedeVerPromociones,
      condicionesIva,
      filtros: filtrosVacios(),
      soloActivos: true,
      pagina: 1,
      tamano: 10,
      total: 0,
      filas: [],
      cargando: false,
      _ultima: window.ultimaRespuesta(),
      _ultimaFicha: window.ultimaRespuesta(),
      formAbierto: false,
      form: formVacio(),
      errores: {},
      guardando: false,

      ficha: null,
      fichaAbierta: false,
      promocionesCatalogo: [],
      promocionElegida: '',
      asignando: false,
      _espera: null,

      init() {
        this.cargar();
      },

      filtrar() {
        clearTimeout(this._espera);
        this._espera = setTimeout(() => { this.pagina = 1; this.cargar(); }, 400);
      },

      limpiarFiltros() {
        this.filtros = filtrosVacios();
        this.soloActivos = true;
        this.pagina = 1;
        this.cargar();
      },

      async cargar() {
        this.cargando = true;
        const params = new URLSearchParams({ pagina: this.pagina, tamano: this.tamano });
        const busqueda = this.filtros.busqueda.trim();
        const localidad = this.filtros.localidad.trim();
        if (busqueda) params.set('busqueda', busqueda);
        if (localidad) params.set('localidad', localidad);
        if (this.filtros.condicion_iva) params.set('condicion_iva', this.filtros.condicion_iva);
        if (this.soloActivos) params.set('activo', 'true');
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

      condicionIvaTexto(c) {
        const par = this.condicionesIva.find(([valor]) => valor === c.condicion_iva);
        return par ? par[1] : c.condicion_iva;
      },

      celdaEstado(c) {
        return c.activo ? window.estadoHtml('Activo', 'exito') : window.estadoHtml('Inactivo', 'peligro');
      },

      get promocionesDisponibles() {
        if (!this.ficha) return [];
        const asignadas = new Set(this.ficha.promociones.map((p) => p.id));
        return this.promocionesCatalogo.filter((p) => !asignadas.has(p.id));
      },

      nuevo() {
        this.form = formVacio();
        this.errores = {};
        this.formAbierto = true;
      },

      editar(c) {
        this.form = {
          id: c.id, nombre: c.nombre, dni: c.dni || '', cuit: c.cuit || '', condicion_iva: c.condicion_iva,
          domicilio: c.domicilio || '', codigo_postal: c.codigo_postal || '', localidad: c.localidad || '',
          telefono: c.telefono || '', email: c.email || '',
        };
        this.errores = {};
        this.formAbierto = true;
      },

      _cuerpo() {
        return {
          nombre: this.form.nombre,
          dni: textoONull(this.form.dni),
          cuit: textoONull(this.form.cuit),
          condicion_iva: this.form.condicion_iva,
          domicilio: textoONull(this.form.domicilio),
          codigo_postal: textoONull(this.form.codigo_postal),
          localidad: textoONull(this.form.localidad),
          telefono: textoONull(this.form.telefono),
          email: textoONull(this.form.email),
        };
      },

      async guardar() {
        const esAlta = !this.form.id;
        this.guardando = true;
        this.errores = {};
        try {
          await window.pedir(esAlta ? API : `${API}/${this.form.id}`, {
            method: esAlta ? 'POST' : 'PUT',
            body: this._cuerpo(),
          });
          window.toast(esAlta ? 'Cliente creado.' : 'Cambios guardados.');
          this.formAbierto = false;
          this.cargar();
        } catch (e) {
          this.errores = window.erroresDeCampos(e);
          window.toast(e.message, 'error');
        } finally {
          this.guardando = false;
        }
      },

      async cambiarEstado(c, activo) {
        const ok = await window.confirmar({
          titulo: activo ? `¿Activar a "${c.nombre}"?` : `¿Desactivar a "${c.nombre}"?`,
          mensaje: activo ? 'Va a volver a poder elegirse en una venta.' : 'No va a poder elegirse en ventas nuevas.',
          textoConfirmar: activo ? 'Activar' : 'Desactivar',
          peligro: !activo,
        });
        if (!ok) return;
        try {
          await window.pedir(`${API}/${c.id}/estado`, { method: 'PATCH', body: { activo } });
          window.toast(activo ? 'Cliente activado.' : 'Cliente desactivado.');
          this.cargar();
        } catch (e) {
          window.toast(e.message, 'error');
        }
      },

      // ---------- Ficha ----------
      async ver(c) {
        try {
          const ficha = await this._ultimaFicha(window.pedir(`${API}/${c.id}`));
          if (ficha === undefined) return;  // se pidió la ficha de otro cliente antes de que llegue esta
          this.ficha = ficha;
          this.promocionElegida = '';
          this.fichaAbierta = true;
          if (this.puedeEditar && this.puedeVerPromociones) await this.cargarPromocionesCatalogo();
        } catch (e) {
          window.toast(e.message, 'error');
        }
      },

      async cargarPromocionesCatalogo() {
        try {
          this.promocionesCatalogo = await window.pedir(`${PROMOCIONES_API}?activo=true`);
        } catch (e) {
          window.toast(e.message, 'error');
        }
      },

      async asignarPromocion() {
        if (!this.promocionElegida) return;
        this.asignando = true;
        try {
          this.ficha = await window.pedir(`${API}/${this.ficha.cliente.id}/promociones`, {
            method: 'POST',
            body: { promocion_id: Number(this.promocionElegida) },
          });
          this.promocionElegida = '';
          window.toast('Promoción asignada.');
        } catch (e) {
          window.toast(e.message, 'error');
        } finally {
          this.asignando = false;
        }
      },

      async quitarPromocion(p) {
        const ok = await window.confirmar({
          titulo: `¿Quitar "${p.nombre}"?`,
          mensaje: 'El cliente deja de tener acceso a esta promoción exclusiva.',
          textoConfirmar: 'Quitar',
          peligro: true,
        });
        if (!ok) return;
        try {
          await window.pedir(`${API}/${this.ficha.cliente.id}/promociones/${p.id}`, { method: 'DELETE' });
          this.ficha.promociones = this.ficha.promociones.filter((x) => x.id !== p.id);
          window.toast('Promoción quitada.');
        } catch (e) {
          window.toast(e.message, 'error');
        }
      },
    };
  };
})();
