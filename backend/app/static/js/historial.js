/* Historial de accesos de un usuario (solo lectura, paginado). */
(function () {
  'use strict';

  window.historialAccesos = function (usuarioId) {
    return {
      filtros: { desde: '', hasta: '', resultado: '' },
      pagina: 1,
      tamano: 10,
      total: 0,
      filas: [],
      cargando: false,

      init() {
        this.cargar();
      },

      limpiarFiltros() {
        this.filtros = { desde: '', hasta: '', resultado: '' };
        this.pagina = 1;
        this.cargar();
      },

      async cargar() {
        this.cargando = true;
        const params = new URLSearchParams({ pagina: this.pagina, tamano: this.tamano });
        for (const [clave, valor] of Object.entries(this.filtros)) {
          if (valor) params.set(clave, valor);
        }
        try {
          const respuesta = await window.pedir(`/api/v1/usuarios/${usuarioId}/historial?${params}`);
          this.filas = respuesta.resultados;
          this.total = respuesta.total;
        } catch (e) {
          window.toast(e.message, 'error');
        } finally {
          this.cargando = false;
        }
      },
    };
  };
})();
