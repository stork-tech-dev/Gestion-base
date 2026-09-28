/* Formulario de producto (alta y edición), macro components/producto_form.html.
   Categoría en cascada (hasta NIVEL_MAXIMO niveles), proveedor fijo en la
   edición, preview de precio y búsqueda de productos parecidos por
   descripción: ambos pisables, así que van secuenciados con `ultimaRespuesta`
   (y, para los parecidos, también contra `_apertura`: reabrir con otro
   producto no vuelve a pedir similares por sí solo, así que el secuenciador
   solo no alcanza para descartar una respuesta vieja — mismo motivo que
   `cargarHistorial` en proveedores.js). */
(function () {
  'use strict';

  const API = '/api/v1/productos';

  // ---------- Funciones puras (testeables sin Alpine) ----------

  // Nodo del árbol (o null) con ese id, recorriendo `hijos` en profundidad.
  function buscarNodo(arbol, id) {
    for (const nodo of arbol || []) {
      if (nodo.id == id) return nodo;
      const encontrado = buscarNodo(nodo.hijos, id);
      if (encontrado) return encontrado;
    }
    return null;
  }

  // Ids desde la raíz hasta `categoriaId` (reusa rutaDeIds de app.js); [] si no hay categoría.
  function nivelesDeCategoria(arbol, categoriaId) {
    if (categoriaId === null || categoriaId === undefined) return [];
    return window.rutaDeIds(arbol, categoriaId);
  }

  // Opciones del nivel `nivel` (0 = raíces): los hijos del nodo elegido en el nivel anterior.
  function opcionesDeNivel(arbol, elegidos, nivel) {
    let nodos = arbol || [];
    for (let i = 0; i < nivel; i++) {
      const nodo = nodos.find((n) => n.id == elegidos[i]);
      nodos = (nodo && nodo.hijos) || [];
    }
    return nodos;
  }

  function esHoja(arbol, id) {
    const nodo = buscarNodo(arbol, id);
    return !!nodo && (!nodo.hijos || nodo.hijos.length === 0);
  }

  // Entero truncado, mínimo 0 (queda listo para el stock del módulo 05).
  function stockEntero(valor) {
    const entero = Math.trunc(Number(valor));
    return Number.isFinite(entero) && entero > 0 ? entero : 0;
  }

  window.productoFormUtil = { nivelesDeCategoria, opcionesDeNivel, esHoja, stockEntero };

  // ---------- Estado inicial del form ----------

  function formVacio(margenDefault) {
    return {
      id: null,
      proveedor_id: null,
      proveedorNombre: '',
      proveedorMoneda: null,
      sku_proveedor: '',
      descripcion: '',
      costo: '',
      margen: margenDefault,
      peso_gramos: '',
      descuento_producto: '0',
      temporada: 'atemporal',
      ubicacion_deposito: '',
      stock_infinito: false,
    };
  }

  function formDesdeProducto(p) {
    return {
      id: p.id,
      proveedor_id: p.proveedor.id,
      proveedorNombre: p.proveedor.nombre,
      proveedorMoneda: p.proveedor.moneda,
      sku_proveedor: p.sku_proveedor || '',
      descripcion: p.descripcion,
      costo: String(p.costo),
      margen: String(p.margen),
      peso_gramos: p.peso_gramos === null || p.peso_gramos === undefined ? '' : String(p.peso_gramos),
      descuento_producto: String(p.descuento_producto),
      temporada: p.temporada,
      ubicacion_deposito: p.ubicacion_deposito || '',
      stock_infinito: !!p.stock_infinito,
    };
  }

  function numeroValido(valor, { permiteCero = true } = {}) {
    if (valor === '' || valor === null || valor === undefined) return false;
    const n = Number(valor);
    if (Number.isNaN(n)) return false;
    return permiteCero ? n >= 0 : n > 0;
  }

  // ---------- Componente Alpine ----------

  window.productoForm = function ({ esAdmin, nivelMaximo, margenDefault, descuentoMaximo }) {
    return {
      esAdmin,
      nivelMaximo,
      margenDefault,
      descuentoMaximo,

      abierto: false,
      form: formVacio(margenDefault),
      elegidos: [],
      arbol: [],
      proveedores: [],
      errores: {},
      guardando: false,
      precioPreview: null,
      dolarProveedor: null,
      similares: [],
      similarActivo: 0,
      fotoInicial: null,

      _apertura: 0,
      _ultimaPreview: window.ultimaRespuesta(),
      _ultimaSimilares: window.ultimaRespuesta(),
      _ultimaArbol: window.ultimaRespuesta(),
      _ultimaProveedores: window.ultimaRespuesta(),

      async abrir(producto) {
        const apertura = ++this._apertura;
        this.abierto = true;
        this.errores = {};
        this.guardando = false;
        this.precioPreview = null;
        this.dolarProveedor = null;
        this.similares = [];
        this.similarActivo = 0;
        this.fotoInicial = null;
        this.arbol = [];
        this.elegidos = [];

        if (producto) {
          this.form = formDesdeProducto(producto);
          // En la edición se ve el precio actual (y el dólar si corresponde) sin tocar nada.
          this.precioPreview = producto.precio_venta;
          const pedidos = [this._cargarArbol(apertura, producto.categoria.id)];
          if (producto.proveedor.moneda === 'usd') pedidos.push(this._cargarDolar(apertura));
          await Promise.all(pedidos);
        } else {
          this.form = formVacio(this.margenDefault);
          this.proveedores = [];
          // Por separado: si falla uno, el otro igual queda cargado.
          await Promise.all([this._cargarArbol(apertura, null), this._cargarProveedores(apertura)]);
        }
      },

      // undefined (llegó un pedido más nuevo) o apertura distinta (se abrió
      // otro producto mientras cargaba): la respuesta ya no corresponde.
      async _cargarArbol(apertura, categoriaId) {
        try {
          const arbol = await this._ultimaArbol(window.pedir('/api/v1/categorias/arbol'));
          if (arbol === undefined || apertura !== this._apertura) return;
          this.arbol = arbol;
          if (categoriaId !== null) this.elegidos = nivelesDeCategoria(arbol, categoriaId);
        } catch (e) {
          window.toast(e.message, 'error');
        }
      },

      // Solo activos; ruta con PRODUCTOS ver (el Vendedor no ve /proveedores).
      async _cargarProveedores(apertura) {
        try {
          const proveedores = await this._ultimaProveedores(window.pedir(`${API}/proveedores?solo_activos=true`));
          if (proveedores === undefined || apertura !== this._apertura) return;
          this.proveedores = proveedores;
        } catch (e) {
          window.toast(e.message, 'error');
        }
      },

      // Edición de un producto en dólares: el dólar vigente del proveedor. Del
      // preview se toma SOLO el dólar; el precio que se muestra es el guardado.
      // Va por el mismo secuenciador que pedirPreview: si el usuario ya cambió
      // costo o margen, gana esa respuesta.
      async _cargarDolar(apertura) {
        const params = new URLSearchParams({ proveedor_id: this.form.proveedor_id, costo: this.form.costo, margen: this.form.margen });
        try {
          const datos = await this._ultimaPreview(window.pedir(`${API}/precio-preview?${params}`));
          if (datos === undefined || apertura !== this._apertura) return;
          this.dolarProveedor = datos.dolar_proveedor;
        } catch (e) {
          // Sin el dólar se sigue mostrando el precio guardado.
        }
      },

      // Niveles con selector visible: el 0 (raíces) siempre, y cada siguiente
      // solo si el anterior tiene una opción elegida CON hijos entre los que elegir.
      get nivelesVisibles() {
        const niveles = [0];
        for (let n = 1; n < this.nivelMaximo; n++) {
          const anterior = this.elegidos[n - 1];
          if (anterior === undefined || anterior === null) break;
          if (!this.opcionesDeNivel(n).length) break;
          niveles.push(n);
        }
        return niveles;
      },

      opcionesDeNivel(nivel) {
        return opcionesDeNivel(this.arbol, this.elegidos, nivel);
      },

      // Cambiar un nivel recorta los siguientes (ya no corresponden a la rama nueva).
      elegirNivel(nivel, valor) {
        const id = valor === '' || valor === null || valor === undefined ? null : Number(valor);
        this.elegidos = this.elegidos.slice(0, nivel);
        if (id !== null) this.elegidos.push(id);
        this.errores.categoria_id = '';
      },

      // Solo cuenta como categoría elegida si se llegó hasta una hoja.
      get categoriaId() {
        if (!this.elegidos.length) return null;
        const ultimo = this.elegidos[this.elegidos.length - 1];
        return esHoja(this.arbol, ultimo) ? ultimo : null;
      },

      // Moneda del proveedor elegido (alta) o del producto (edición, no editable).
      get moneda() {
        if (this.form.id) return this.form.proveedorMoneda;
        const proveedor = (this.proveedores || []).find((p) => p.id == this.form.proveedor_id);
        return proveedor ? proveedor.moneda : null;
      },

      get proveedoresOpciones() {
        return (this.proveedores || []).map((p) => ({
          id: p.id,
          texto: p.nombre + (p.moneda === 'usd' ? ' (US$)' : ' ($)'),
        }));
      },

      alCambiarProveedor() {
        this.pedirPreview();
      },

      // Se llama con @input.debounce.300ms desde costo y margen.
      async pedirPreview() {
        const proveedorId = this.form.proveedor_id;
        const costoValido = numeroValido(this.form.costo, { permiteCero: false });
        const margenValido = numeroValido(this.form.margen);
        const apertura = this._apertura;
        if (!proveedorId || !costoValido || !margenValido) {
          // Invalida también un pedido en vuelo: su respuesta ya no corresponde.
          this._ultimaPreview(Promise.resolve(null));
          this.precioPreview = null;
          this.dolarProveedor = null;
          return;
        }
        try {
          const params = new URLSearchParams({ proveedor_id: proveedorId, costo: this.form.costo, margen: this.form.margen });
          const datos = await this._ultimaPreview(window.pedir(`${API}/precio-preview?${params}`));
          // Respuesta vieja: llegó otra más nueva o se abrió otro producto mientras tanto.
          if (datos === undefined || apertura !== this._apertura) return;
          this.precioPreview = datos.precio_venta;
          this.dolarProveedor = datos.dolar_proveedor;
        } catch (e) {
          this.precioPreview = null;
          this.dolarProveedor = null;
        }
      },

      // Se llama con @input.debounce.300ms desde descripción.
      async buscarSimilares() {
        const apertura = this._apertura;
        const descripcion = this.form.descripcion || '';
        if (descripcion.length < 10) {
          this.similares = [];
          this.similarActivo = 0;
          return;
        }
        try {
          const params = new URLSearchParams({ descripcion });
          if (this.categoriaId) params.set('categoria_id', this.categoriaId);
          if (this.form.proveedor_id) params.set('proveedor_id', this.form.proveedor_id);
          const similares = await this._ultimaSimilares(window.pedir(`${API}/similares?${params}`));
          // undefined: llegó una búsqueda más nueva. apertura distinta: se abrió
          // otro producto sin volver a buscar (ej. descripción corta), así que
          // el secuenciador solo no alcanza para descartarla.
          if (similares === undefined || apertura !== this._apertura) return;
          this.similares = similares;
          this.similarActivo = 0;
        } catch (e) {
          this.similares = [];
        }
      },

      moverSimilar(delta) {
        const total = this.similares.length;
        if (total) this.similarActivo = (this.similarActivo + delta + total) % total;
      },

      elegirSimilar(s) {
        this.form.descripcion = s.descripcion;
        this.similares = [];
        this.similarActivo = 0;
      },

      // Parecido con la MISMA descripción normalizada (probable duplicado, no solo similar).
      get duplicadoExacto() {
        const normalizada = window.normalizarTexto(this.form.descripcion);
        if (!normalizada) return null;
        // En la edición, el propio producto no cuenta como duplicado.
        return this.similares.find((s) => s.id !== this.form.id && window.normalizarTexto(s.descripcion) === normalizada) || null;
      },

      cuerpo() {
        const cuerpo = {
          categoria_id: this.categoriaId,
          descripcion: this.form.descripcion,
          costo: String(this.form.costo),
          margen: this.form.margen === '' || this.form.margen === null || this.form.margen === undefined
            ? null : String(this.form.margen),
          sku_proveedor: (this.form.sku_proveedor || '').trim() || null,
          descuento_producto: String(this.form.descuento_producto || 0),
          peso_gramos: this.form.peso_gramos === '' || this.form.peso_gramos === null || this.form.peso_gramos === undefined
            ? null : String(this.form.peso_gramos),
          temporada: this.form.temporada,
          ubicacion_deposito: (this.form.ubicacion_deposito || '').trim() || null,
          stock_infinito: !!this.form.stock_infinito,
        };
        if (!this.form.id) cuerpo.proveedor_id = this.form.proveedor_id;
        return cuerpo;
      },

      async guardar() {
        this.errores = {};
        if (this.categoriaId === null) {
          this.errores.categoria_id = 'Elegí hasta el último nivel: la categoría del producto es la del final de la rama.';
          return;
        }
        this.guardando = true;
        const esAlta = !this.form.id;
        try {
          const producto = await window.pedir(esAlta ? API : `${API}/${this.form.id}`, {
            method: esAlta ? 'POST' : 'PUT',
            body: this.cuerpo(),
          });
          if (esAlta && this.fotoInicial) {
            try {
              const datosFoto = new FormData();
              datosFoto.append('archivo', this.fotoInicial);
              await window.pedir(`${API}/${producto.id}/fotos`, { method: 'POST', body: datosFoto });
            } catch (e) {
              // El producto ya quedó creado: se avisa, pero no se corta el flujo.
              window.toast('El producto se creó, pero la foto no se pudo subir: ' + e.message, 'error');
            }
          }
          window.toast(esAlta ? 'Producto creado.' : 'Cambios guardados.');
          window.dispatchEvent(new CustomEvent('producto-guardado', { detail: producto }));
          this.abierto = false;
        } catch (e) {
          this.errores = window.erroresDeCampos(e);
          window.toast(e.message, 'error');
        } finally {
          this.guardando = false;
        }
      },

      elegirArchivo(e) {
        const archivo = e.target.files && e.target.files[0];
        if (archivo) this.fotoInicial = archivo;
      },

      async capturarFoto(camara) {
        this.fotoInicial = await camara.capturar();
        camara.detener();
      },
    };
  };
})();
