/* Fotos de un producto (alta, toma con cámara, marcar principal, borrado):
   componente Alpine reutilizable, usado por la ficha de solo lectura
   (pages/productos/_modal_ficha.html) y por el formulario de edición
   (components/producto_form.html, que guarda los cambios al instante).
   Antes vivía como métodos de la ficha en productos.js: se MOVIERON acá
   (no se copiaron) para no repetir la lógica en dos componentes.

   `fotos` se captura una sola vez al montar (igual que `productoId`): el
   propio componente mantiene después su copia actualizada con `recargar()`
   tras cada cambio, en vez de depender de que el padre se lo vuelva a pasar.
   `alCambiar` (opcional): lo llama el padre para refrescarse a sí mismo (la
   ficha) o el listado (el formulario de edición) — mismo efecto que tenían
   subirFoto/marcarPrincipal/borrarFoto antes, que solo refrescaban la ficha. */
(function () {
  'use strict';

  const API = '/api/v1/productos';

  // `vigilarProducto` (opcional, string): expresión Alpine con el id "real"
  // del producto en el padre (ej. "form.id"). Cubre un caso que el montaje
  // inicial no cubre solo: un `x-if` que no pasa por "falsy" entre un
  // producto y otro (ej. editar el producto A y, sin cerrar el modal entre
  // medio, editar el B) no reinicializa este componente, y quedaría
  // `productoId` viejo — subiendo fotos al producto equivocado. Con
  // `vigilarProducto`, cualquier cambio de esa expresión (lo detecta
  // `$watch`, a diferencia de `x-if` que solo mira verdadero/falso)
  // resincroniza `productoId` y recarga. La ficha no lo necesita (abrirFicha
  // sí pasa por `ficha = null` entre una y otra, así que `x-if="ficha"`
  // remonta solo); el formulario de edición sí.
  window.fotosProducto = function ({ productoId, fotos, alCambiar, vigilarProducto }) {
    return {
      productoId,
      fotos: fotos || [],

      init() {
        if (!vigilarProducto) return;
        this.$watch(vigilarProducto, (nuevoId) => {
          if (nuevoId == null || nuevoId === this.productoId) return;
          this.productoId = nuevoId;
          this.recargar();
        });
      },

      get puedeSubir() {
        return this.fotos.length < 5;
      },

      async recargar() {
        try {
          const detalle = await window.pedir(`${API}/${this.productoId}`);
          this.fotos = detalle.fotos;
        } catch (e) {
          window.toast(e.message, 'error');
        }
      },

      // Recarga la propia copia y avisa al padre (si le interesa refrescarse
      // él también, ej. la ficha o la fila del listado).
      async _avisar() {
        await this.recargar();
        if (alCambiar) alCambiar();
      },

      async subirFoto(archivo) {
        if (!archivo) return;
        const datos = new FormData();
        datos.append('archivo', archivo);
        try {
          await window.pedir(`${API}/${this.productoId}/fotos`, { method: 'POST', body: datos });
          window.toast('Foto subida.');
          await this._avisar();
        } catch (e) {
          window.toast(e.message, 'error');
        }
      },

      async capturarFoto(camara) {
        const blob = await camara.capturar();
        camara.detener();
        await this.subirFoto(blob);
      },

      async marcarPrincipal(f) {
        try {
          await window.pedir(`${API}/fotos/${f.id}/principal`, { method: 'PATCH' });
          await this._avisar();
        } catch (e) {
          window.toast(e.message, 'error');
        }
      },

      async borrarFoto(f) {
        const ok = await window.confirmar({
          titulo: '¿Borrar esta foto?',
          mensaje: 'No se puede deshacer.',
          textoConfirmar: 'Borrar',
          peligro: true,
        });
        if (!ok) return;
        try {
          await window.pedir(`${API}/fotos/${f.id}`, { method: 'DELETE' });
          window.toast('Foto borrada.');
          await this._avisar();
        } catch (e) {
          window.toast(e.message, 'error');
        }
      },
    };
  };
})();
