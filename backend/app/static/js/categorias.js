/* Categorías de productos: árbol colapsable (alta, edición, mover y borrar)
   más una lista plana cuando hay algún filtro activo. Todos los datos salen
   de la API; el árbol se recorre en JS porque Alpine no soporta un
   `x-for` recursivo. */
(function () {
  'use strict';

  const API = '/api/v1/categorias';

  // Ids de un nodo y todos sus descendientes (su "rama").
  function idsDeRama(nodo) {
    let ids = [nodo.id];
    for (const hijo of nodo.hijos || []) ids = ids.concat(idsDeRama(hijo));
    return ids;
  }

  // Niveles que ocupa la rama de `nodo` (1 si es hoja), igual que el backend.
  function profundidadDeRama(nodo) {
    if (!nodo.hijos || !nodo.hijos.length) return 1;
    return 1 + Math.max(...nodo.hijos.map(profundidadDeRama));
  }

  window.categoriasArbol = function ({ puedeCrear, puedeEditar, puedeEliminar, nivelMaximo }) {
    return {
      puedeCrear,
      puedeEditar,
      puedeEliminar,
      nivelMaximo,
      arbol: [],
      abiertos: {},
      filtros: { nombre: '', nivel: '' },
      planas: [],
      cargando: false,
      _ultima: window.ultimaRespuesta(),
      _espera: null,

      formAbierto: false,
      form: { id: null, nombre: '', orden: 0, parent_id: null },
      errores: {},
      guardando: false,

      moverAbierto: false,
      moverNodo: null,
      moverDestino: '',
      moviendo: false,

      init() {
        this.cargar();
      },

      get hayFiltro() {
        return !!(this.filtros.nombre.trim() || this.filtros.nivel);
      },

      // Nodos del árbol en orden DFS con `profundidad`, omitiendo los hijos
      // de nodos colapsados.
      get visibles() {
        const resultado = [];
        const recorrer = (nodos, profundidad) => {
          for (const nodo of nodos) {
            resultado.push({ ...nodo, profundidad });
            if (nodo.hijos && nodo.hijos.length && this.abiertos[nodo.id]) recorrer(nodo.hijos, profundidad + 1);
          }
        };
        recorrer(this.arbol, 0);
        return resultado;
      },

      get total() {
        return this.hayFiltro ? this.planas.length : this.visibles.length;
      },

      filtrar() {
        clearTimeout(this._espera);
        this._espera = setTimeout(() => this.cargar(), 400);
      },

      limpiarFiltros() {
        this.filtros = { nombre: '', nivel: '' };
        this.cargar();
      },

      async cargar() {
        this.cargando = true;
        const params = new URLSearchParams();
        if (this.filtros.nombre.trim()) params.set('nombre', this.filtros.nombre.trim());
        if (this.filtros.nivel) params.set('nivel', this.filtros.nivel);
        const hayFiltro = this.hayFiltro;
        try {
          const [arbol, planas] = await this._ultima(Promise.all([
            window.pedir(`${API}/arbol`),
            hayFiltro ? window.pedir(`${API}?${params}`) : Promise.resolve([]),
          ]));
          if (arbol === undefined) return;  // llegó una carga más nueva
          this.arbol = arbol;
          this.planas = hayFiltro ? planas : [];
          // Todas las raíces abiertas la primera vez que aparecen (no pisa
          // lo que el usuario ya haya colapsado/expandido a mano).
          for (const raiz of this.arbol) {
            if (!(raiz.id in this.abiertos)) this.abiertos[raiz.id] = true;
          }
          this.cargando = false;
        } catch (e) {
          this.cargando = false;
          window.toast(e.message, 'error');
        }
      },

      get caminoPadre() {
        if (this.form.parent_id == null) return 'Categoría raíz';
        return 'Dentro de: ' + window.rutaCategoria(this.arbol, this.form.parent_id);
      },

      nuevaRaiz() {
        this.form = { id: null, nombre: '', orden: 0, parent_id: null };
        this.errores = {};
        this.formAbierto = true;
      },

      nuevaHija(n) {
        this.form = { id: null, nombre: '', orden: 0, parent_id: n.id };
        this.errores = {};
        this.formAbierto = true;
      },

      editar(n) {
        this.form = { id: n.id, nombre: n.nombre, orden: n.orden, parent_id: n.parent_id };
        this.errores = {};
        this.formAbierto = true;
      },

      async guardar() {
        const esAlta = !this.form.id;
        this.guardando = true;
        this.errores = {};
        try {
          const cuerpo = { nombre: this.form.nombre, orden: Number(this.form.orden) || 0 };
          if (esAlta) cuerpo.parent_id = this.form.parent_id;
          await window.pedir(esAlta ? API : `${API}/${this.form.id}`, { method: esAlta ? 'POST' : 'PUT', body: cuerpo });
          window.toast(esAlta ? 'Categoría creada.' : 'Cambios guardados.');
          this.formAbierto = false;
          this.cargar();
        } catch (e) {
          this.errores = window.erroresDeCampos(e);
          window.toast(e.message, 'error');
        } finally {
          this.guardando = false;
        }
      },

      abrirMover(n) {
        this.moverNodo = n;
        this.moverDestino = n.parent_id == null ? '' : String(n.parent_id);
        this.moverAbierto = true;
      },

      // "Categoría raíz" + todas las categorías (camino completo) excepto la
      // propia rama y las que dejarían la rama en más de `nivelMaximo` niveles
      // (el backend vuelve a validar todo esto igual).
      get destinosPosibles() {
        if (!this.moverNodo) return [];
        const excluidos = new Set(idsDeRama(this.moverNodo));
        const profundidad = profundidadDeRama(this.moverNodo);
        const opciones = [{ id: null, texto: 'Categoría raíz' }];
        const recorrer = (nodos) => {
          for (const nodo of nodos) {
            if (excluidos.has(nodo.id)) continue;  // ni la rama propia ni sus hijos
            const nuevoNivel = nodo.nivel + 1;
            if (nuevoNivel + profundidad - 1 <= this.nivelMaximo) {
              opciones.push({ id: nodo.id, texto: window.rutaCategoria(this.arbol, nodo.id) });
            }
            if (nodo.hijos) recorrer(nodo.hijos);
          }
        };
        recorrer(this.arbol);
        return opciones;
      },

      async mover() {
        this.moviendo = true;
        try {
          const parentId = this.moverDestino === '' ? null : Number(this.moverDestino);
          await window.pedir(`${API}/${this.moverNodo.id}/mover`, { method: 'PATCH', body: { parent_id: parentId } });
          window.toast('Categoría movida.');
          this.moverAbierto = false;
          this.cargar();
        } catch (e) {
          window.toast(e.message, 'error');
        } finally {
          this.moviendo = false;
        }
      },

      async eliminar(n) {
        const ok = await window.confirmar({
          titulo: `¿Eliminar la categoría ${n.nombre}?`,
          textoConfirmar: 'Eliminar',
          peligro: true,
        });
        if (!ok) return;
        try {
          await window.pedir(`${API}/${n.id}`, { method: 'DELETE' });
          window.toast('Categoría eliminada.');
          this.cargar();
        } catch (e) {
          // 409: tiene subcategorías o productos.
          window.toast(e.message, 'error');
        }
      },
    };
  };
})();
