/* Árbol de permisos de un rol o de un usuario. En modo "usuario" solo se
   editan los permisos propios (overrides); lo heredado del rol queda fijo. */
(function () {
  'use strict';

  const ACCIONES = ['ver', 'crear', 'editar', 'eliminar'];

  window.arbolPermisos = function ({ urlDatos, urlGuardar, modo, editable }) {
    const campo = (accion) => (modo === 'usuario' ? `override_${accion}` : `puede_${accion}`);

    return {
      modo,
      editable,
      modulos: [],
      abiertos: {},
      original: '',
      cargando: true,
      guardando: false,

      async init() {
        await this.cargar();
      },

      async cargar() {
        this.cargando = true;
        try {
          this._recibir(await window.pedir(urlDatos));
        } catch (e) {
          window.toast(e.message, 'error');
        } finally {
          this.cargando = false;
        }
      },

      _recibir(arbol) {
        this.modulos = arbol.modulos;
        this.original = JSON.stringify(this.entradas());
      },

      get hayCambios() {
        return JSON.stringify(this.entradas()) !== this.original;
      },

      // null en puede_<accion> = la acción no aplica a ese módulo/recurso.
      aplica(nodo, accion) {
        return nodo[`puede_${accion}`] !== null && nodo[`puede_${accion}`] !== undefined;
      },

      marcado(nodo, accion) {
        if (modo === 'usuario') return !!(nodo[`heredado_${accion}`] || nodo[`override_${accion}`]);
        return !!nodo[`puede_${accion}`];
      },

      // Un recurso "cubierto" ya está habilitado por el permiso general de su
      // módulo (en el campo editable: puede_<accion> en modo rol,
      // override_<accion> en modo usuario). Se ve marcado y no admite click
      // directo, pero no se manda como fila propia (ver entradas()): única
      // fuente de esta regla, la usan bloqueado/claseCelda/entradas.
      cubierto(nodo, accion) {
        if (nodo.recurso === null) return false;
        const general = this._modulo(nodo.modulo);
        return this.aplica(general, accion) && !!general[campo(accion)];
      },

      bloqueado(nodo, accion) {
        if (!editable) return true;
        if (this.cubierto(nodo, accion)) return true;
        return this._bloqueadoPorOtroMotivo(nodo, accion);
      },

      // Bloqueo por motivos ajenos a estar cubierto por el general: lo usa la
      // cascada de alternar(), que debe poder marcar/desmarcar un recurso
      // cubierto aunque el click directo sobre esa celda esté deshabilitado.
      _bloqueadoPorOtroMotivo(nodo, accion) {
        if (!editable) return true;
        if (modo !== 'usuario') return false;
        if (nodo[`heredado_${accion}`]) return true;
        // No otorgable: no se puede agregar, pero sí quitar lo que ya tiene.
        return nodo[`otorgable_${accion}`] === false && !nodo[`override_${accion}`];
      },

      claseCelda(nodo, accion) {
        if (this.cubierto(nodo, accion)) return 'opacity-50';
        if (modo === 'usuario' && nodo[`heredado_${accion}`]) return 'opacity-50';
        if (modo === 'usuario' && nodo[`override_${accion}`]) return 'accent-accent';
        return '';
      },

      _modulo(nombre) {
        return this.modulos.find((m) => m.modulo === nombre);
      },

      alternar(nodo, accion) {
        if (this.bloqueado(nodo, accion)) return;
        const clave = campo(accion);
        nodo[clave] = !nodo[clave];
        if (nodo.recurso === null) {
          // Marcar el general sugiere sus recursos; desmarcarlo los desmarca.
          // Se cascada aunque el recurso quede "cubierto" al marcar (ese
          // bloqueo es solo para el click directo, no para esta propagación).
          for (const r of this._modulo(nodo.modulo).recursos) {
            if (this.aplica(r, accion) && !this._bloqueadoPorOtroMotivo(r, accion)) r[clave] = nodo[clave];
          }
        }
      },

      expandirTodo(abrir) {
        for (const m of this.modulos) this.abiertos[m.modulo] = abrir;
      },

      // Lo que se manda a la API. Un recurso cubierto por el permiso general
      // de su módulo no se guarda como fila propia (quedaría "pegado").
      entradas() {
        const salida = [];
        for (const m of this.modulos) {
          for (const nodo of [m, ...m.recursos]) {
            const entrada = { modulo: nodo.modulo, recurso: nodo.recurso };
            for (const accion of ACCIONES) {
              entrada[`puede_${accion}`] =
                this.aplica(nodo, accion) && !!nodo[campo(accion)] && !this.cubierto(nodo, accion);
            }
            salida.push(entrada);
          }
        }
        return salida;
      },

      async guardar() {
        const ok = await window.confirmar({
          titulo: '¿Guardar los permisos?',
          mensaje: 'Los cambios rigen desde el próximo pedido de cada usuario afectado.',
          textoConfirmar: 'Guardar',
        });
        if (!ok) return;
        this.guardando = true;
        try {
          this._recibir(await window.pedir(urlGuardar, { method: 'PUT', body: { permisos: this.entradas() } }));
          window.toast('Permisos guardados.');
        } catch (e) {
          window.toast(e.message, 'error');
        } finally {
          this.guardando = false;
        }
      },
    };
  };
})();
