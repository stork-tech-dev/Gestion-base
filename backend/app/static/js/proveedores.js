/* Proveedores: listado con filtros, ficha, alta/edición (moneda y dólar
   propio con historial) y baja lógica. Todos los datos salen de la API. */
(function () {
  'use strict';

  const API = '/api/v1/proveedores';
  const ESTADOS = {
    activo: ['Activo', 'exito'],
    desactivado: ['Desactivado', 'neutro'],
    inhabilitado: ['Inhabilitado', 'peligro'],
  };
  const ORIGENES = {
    manual: 'Manual',
    masivo_valor: 'Masivo (valor)',
    masivo_porcentaje: 'Masivo (%)',
    importacion_excel: 'Excel',
  };
  const filtrosVacios = () => ({ nombre: '', pais: '', provincia: '', estado: '', moneda: '', dolar_desde: '', dolar_hasta: '' });
  const formVacio = () => ({
    id: null, nombre: '', pais: '', provincia: '', telefono: '', email: '', notas: '',
    moneda: 'ars', monedaOriginal: null, dolar_actual: '',
  });
  const textoONull = (valor) => String(valor ?? '').trim() || null;

  window.proveedoresListado = function ({ usaDolar, puedeEditar, esAdmin }) {
    return {
      usaDolar,
      puedeEditar,
      filtros: filtrosVacios(),
      filas: [],
      cargando: false,
      _ultima: window.ultimaRespuesta(),
      _ultimaHistorial: window.ultimaRespuesta(),
      _espera: null,
      ficha: null,
      fichaAbierta: false,
      formAbierto: false,
      form: formVacio(),
      errores: {},
      guardando: false,
      historial: [],
      dolarNuevo: '',
      aplicandoDolar: false,
      baja: null,
      bajaAbierta: false,
      dandoDeBaja: false,

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
        for (const [clave, valor] of Object.entries(this.filtros)) {
          const limpio = String(valor ?? '').trim();
          if (limpio) params.set(clave, limpio);
        }
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

      celdaContacto(p) {
        const partes = [p.email, p.telefono].filter(Boolean).map((v) => window.escaparHtml(v));
        return partes.length ? partes.join('<br>') : '—';
      },

      celdaEstado(p) {
        const [texto, variante] = ESTADOS[p.estado] || [p.estado, 'neutro'];
        return window.estadoHtml(texto, variante);
      },

      monedaTexto(p) {
        return p.moneda === 'usd' ? 'Dólares' : 'Pesos';
      },

      dolarTexto(p) {
        return p.moneda === 'usd' ? `US$ ${window.formatearDolar(p.dolar_actual)}` : '—';
      },

      origenTexto(origen) {
        return ORIGENES[origen] || origen;
      },

      // Solo oculta botones: la API vuelve a validar todo.
      puedeReactivar(p) {
        return puedeEditar && p.estado !== 'activo' && (esAdmin || p.estado === 'desactivado');
      },

      ver(p) {
        this.ficha = p;
        this.fichaAbierta = true;
      },

      nuevo() {
        this.form = formVacio();
        this.errores = {};
        this.historial = [];
        this.dolarNuevo = '';
        this.formAbierto = true;
      },

      async editar(p) {
        this.form = {
          id: p.id, nombre: p.nombre, pais: p.pais || '', provincia: p.provincia || '', telefono: p.telefono || '',
          email: p.email || '', notas: p.notas || '', moneda: p.moneda, monedaOriginal: p.moneda,
          dolar_actual: p.dolar_actual || '',
        };
        this.errores = {};
        this.historial = [];
        this.dolarNuevo = '';
        this.formAbierto = true;
        if (p.moneda === 'usd') await this.cargarHistorial();
      },

      async cargarHistorial() {
        const id = this.form.id;
        try {
          const historial = await this._ultimaHistorial(window.pedir(`${API}/${id}/dolar/historial`));
          // undefined: llegó un pedido más nuevo. form.id distinto: se pasó a
          // otro proveedor sin volver a pedir el historial (ej. quedó en
          // pesos), así que el secuenciador solo no alcanza para descartarla.
          if (historial === undefined || this.form.id !== id) return;
          this.historial = historial;
        } catch (e) {
          window.toast(e.message, 'error');
        }
      },

      // El dólar se pide en el alta en dólares o al pasar un proveedor de pesos a dólares.
      pideDolarInicial() {
        return this.form.moneda === 'usd' && this.form.monedaOriginal !== 'usd';
      },

      _cuerpo() {
        const cuerpo = {
          nombre: this.form.nombre,
          pais: textoONull(this.form.pais),
          provincia: textoONull(this.form.provincia),
          telefono: textoONull(this.form.telefono),
          email: textoONull(this.form.email),
          notas: textoONull(this.form.notas),
          moneda: this.form.moneda,
        };
        if (this.pideDolarInicial()) cuerpo.dolar_actual = textoONull(this.form.dolar_actual);
        return cuerpo;
      },

      async guardar() {
        const esAlta = !this.form.id;
        this.guardando = true;
        this.errores = {};
        try {
          const proveedor = await window.pedir(esAlta ? API : `${API}/${this.form.id}`, {
            method: esAlta ? 'POST' : 'PUT',
            body: this._cuerpo(),
          });
          window.toast(esAlta ? 'Proveedor creado.' : 'Cambios guardados.');
          this.formAbierto = false;
          // El primer proveedor en dólares hace aparecer los controles del dólar.
          if (proveedor.en_dolares && !this.usaDolar) {
            window.location.reload();
            return;
          }
          this.cargar();
        } catch (e) {
          this.errores = window.erroresDeCampos(e);
          window.toast(e.message, 'error');
        } finally {
          this.guardando = false;
        }
      },

      async aplicarDolar() {
        this.aplicandoDolar = true;
        try {
          const proveedor = await window.pedir(`${API}/${this.form.id}/dolar`, {
            method: 'PATCH',
            body: { valor_nuevo: this.dolarNuevo },
          });
          this.form.dolar_actual = proveedor.dolar_actual;
          this.dolarNuevo = '';
          window.toast('Dólar actualizado. Los precios de sus productos se recalculan con el valor nuevo.');
          await this.cargarHistorial();
          this.cargar();
        } catch (e) {
          window.toast(e.message, 'error');
        } finally {
          this.aplicandoDolar = false;
        }
      },

      abrirBaja(p) {
        this.baja = { proveedor: p, estado: 'desactivado', advertencia: '' };
        this.bajaAbierta = true;
      },

      async confirmarBaja(confirmarConProductos) {
        this.dandoDeBaja = true;
        try {
          await window.pedir(`${API}/${this.baja.proveedor.id}/estado`, {
            method: 'PATCH',
            body: { estado: this.baja.estado, confirmar_con_productos: confirmarConProductos },
          });
          window.toast(this.baja.estado === 'inhabilitado' ? 'Proveedor inhabilitado.' : 'Proveedor desactivado.');
          this.bajaAbierta = false;
          this.cargar();
        } catch (e) {
          // 409 por productos activos: se muestra y se ofrece dar de baja igual.
          if (e.status === 409 && !confirmarConProductos) this.baja.advertencia = e.message;
          else window.toast(e.message, 'error');
        } finally {
          this.dandoDeBaja = false;
        }
      },

      async reactivar(p) {
        const ok = await window.confirmar({
          titulo: `¿Reactivar a ${p.nombre}?`,
          mensaje: 'Va a volver a estar disponible para cargar productos.',
          textoConfirmar: 'Reactivar',
        });
        if (!ok) return;
        try {
          await window.pedir(`${API}/${p.id}/estado`, {
            method: 'PATCH',
            body: { estado: 'activo', confirmar_con_productos: false },
          });
          window.toast('Proveedor reactivado.');
          this.cargar();
        } catch (e) {
          window.toast(e.message, 'error');
        }
      },
    };
  };
})();
