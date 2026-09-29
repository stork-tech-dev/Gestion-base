// Pantalla "Importar desde Excel" (sesión 08). El frontend no lee el Excel:
// sube el archivo y muestra lo que devuelve la API (validar / importar).
(function () {
  const API = '/api/v1/importacion';
  const TAMANO_PAGINA = 10;

  const textos = {
    resumen(r) {
      return `${r.filas_leidas} filas leídas · ${r.filas_validas} listas para importar`;
    },
    confirmacion(r, etiqueta) {
      return `Se van a crear ${r.filas_validas} ${etiqueta.toLowerCase()}. Esta acción no se deshace desde el sistema.`;
    },
    exito(r, etiqueta) {
      return `Listo: se crearon ${r.creados} ${etiqueta.toLowerCase()}.`;
    },
  };
  window.importacionTextos = textos;

  window.importacion = function (tipos) {
    return {
      tipos,
      tipo: tipos[0],
      archivo: null,
      arrastrando: false,
      resultado: null,        // último ResultadoImportacion de /validar
      validado: null,         // archivo sobre el que se hizo esa validación
      importado: null,        // ResultadoImportacion de /importar (éxito)
      ocupado: false,
      pagina: 1,
      tamano: TAMANO_PAGINA,

      get urlPlantilla() { return `${API}/${this.tipo.valor}/plantilla`; },
      get errores() { return this.resultado ? this.resultado.errores : []; },
      get erroresPagina() {
        const desde = (this.pagina - 1) * this.tamano;
        return this.errores.slice(desde, desde + this.tamano);
      },
      // Importar solo si la validación dio 0 errores y el archivo no cambió.
      get puedeImportar() {
        return !this.ocupado && !!this.resultado && !this.errores.length &&
          this.resultado.filas_validas > 0 && this.validado === this.archivo;
      },
      resumen() { return this.resultado ? textos.resumen(this.resultado) : ''; },

      limpiar() {
        this.resultado = null;
        this.validado = null;
        this.importado = null;
        this.pagina = 1;
      },
      elegirTipo(tipo) {
        if (tipo === this.tipo) return;
        this.tipo = tipo;
        this.archivo = null;
        if (this.$refs && this.$refs.archivo) this.$refs.archivo.value = '';
        this.limpiar();
      },
      elegirArchivo(archivo) {
        this.archivo = archivo || null;
        this.limpiar();
      },
      soltar(evento) {
        this.arrastrando = false;
        this.elegirArchivo(evento.dataTransfer.files[0]);
      },

      async enviar(accion) {
        const datos = new FormData();
        datos.append('archivo', this.archivo);
        return window.pedir(`${API}/${this.tipo.valor}/${accion}`, { method: 'POST', body: datos });
      },

      async validar() {
        if (!this.archivo) return window.toast('Elegí un archivo .xlsx.', 'error');
        const archivo = this.archivo;
        this.ocupado = true;
        try {
          const resultado = await this.enviar('validar');
          if (archivo !== this.archivo) return;   // cambiaron el archivo mientras tanto
          this.limpiar();
          this.resultado = resultado;
          this.validado = archivo;
        } catch (e) {
          window.toast(e.message, 'error');
        } finally {
          this.ocupado = false;
        }
      },

      async importar() {
        if (!this.puedeImportar) return;
        const confirmado = await window.confirmar({
          titulo: `Importar ${this.tipo.etiqueta.toLowerCase()}`,
          mensaje: textos.confirmacion(this.resultado, this.tipo.etiqueta),
          textoConfirmar: 'Importar',
        });
        if (!confirmado) return;
        this.ocupado = true;
        try {
          const resultado = await this.enviar('importar');
          if (resultado.aplicado) {
            this.limpiar();
            this.importado = resultado;
            this.archivo = null;
            if (this.$refs && this.$refs.archivo) this.$refs.archivo.value = '';
            window.toast(textos.exito(resultado, this.tipo.etiqueta));
          } else {
            // Algo cambió en la base desde que se validó: mostrar los errores nuevos.
            this.resultado = resultado;
            window.toast('No se importó nada: revisá los errores.', 'error');
          }
        } catch (e) {
          window.toast(e.message, 'error');
        } finally {
          this.ocupado = false;
        }
      },
    };
  };
})();
