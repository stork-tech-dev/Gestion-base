/* Cambio masivo del dólar: por valor o porcentaje (con vista previa y
   confirmación) o importando el Excel de proveedores en dólares. */
(function () {
  'use strict';

  const API = '/api/v1/proveedores';

  window.dolarMasivo = function () {
    return {
      proveedores: [],
      seleccion: [],
      modalidad: 'valor',
      valor: '',
      vista: [],
      cargando: true,
      calculando: false,
      aplicando: false,
      archivo: null,
      subiendo: false,
      resultado: null,

      init() {
        this.cargar();
      },

      async cargar() {
        this.cargando = true;
        try {
          // No usa GET /proveedores: quien solo tiene el permiso puntual del
          // cambio masivo (sin "ver" proveedores) recibiría un 403.
          this.proveedores = await window.pedir(`${API}/dolar/activos`);
          this.seleccion = this.proveedores.map((p) => p.id);
        } catch (e) {
          window.toast(e.message, 'error');
        } finally {
          this.cargando = false;
        }
      },

      get todos() {
        return this.proveedores.length > 0 && this.seleccion.length === this.proveedores.length;
      },

      alternarTodos() {
        this.seleccion = this.todos ? [] : this.proveedores.map((p) => p.id);
        this.vista = [];
      },

      _cuerpo() {
        return { proveedor_ids: this.todos ? null : this.seleccion, modalidad: this.modalidad, valor: this.valor };
      },

      async previsualizar() {
        if (!this.seleccion.length) return window.toast('Elegí al menos un proveedor.', 'error');
        this.calculando = true;
        try {
          this.vista = await window.pedir(`${API}/dolar/masivo/preview`, { method: 'POST', body: this._cuerpo() });
        } catch (e) {
          this.vista = [];
          window.toast(e.message, 'error');
        } finally {
          this.calculando = false;
        }
      },

      async aplicar() {
        const ok = await window.confirmar({
          titulo: '¿Aplicar el cambio del dólar?',
          mensaje: `Se actualiza el dólar de ${this.vista.length} proveedor(es) y se recalculan los precios de sus productos.`,
          textoConfirmar: 'Aplicar',
        });
        if (!ok) return;
        this.aplicando = true;
        try {
          const aplicados = await window.pedir(`${API}/dolar/masivo`, { method: 'POST', body: this._cuerpo() });
          window.toast(`Dólar actualizado en ${aplicados.length} proveedor(es).`);
          this.vista = [];
          this.valor = '';
          await this.cargar();
        } catch (e) {
          window.toast(e.message, 'error');
        } finally {
          this.aplicando = false;
        }
      },

      elegirArchivo(evento) {
        this.archivo = evento.target.files[0] || null;
        this.resultado = null;
      },

      async subir() {
        if (!this.archivo) return window.toast('Elegí un archivo .xlsx.', 'error');
        const datos = new FormData();
        datos.append('archivo', this.archivo);
        this.subiendo = true;
        try {
          this.resultado = await window.pedir(`${API}/dolar/importar`, { method: 'POST', body: datos });
          if (!this.resultado.errores.length) {
            window.toast(`Listo: ${this.resultado.aplicados} actualizado(s), ${this.resultado.sin_cambios} sin cambios.`);
            await this.cargar();
          }
        } catch (e) {
          window.toast(e.message, 'error');
        } finally {
          this.subiendo = false;
        }
      },
    };
  };
})();
