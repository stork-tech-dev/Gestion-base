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
      precio_venta: '',
      peso_gramos: '',
      descuento_producto: '0',
      temporada: 'atemporal',
      ubicacion_deposito: '',
      stock_infinito: false,
      stock_inicial: '0',
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
      precio_venta: String(p.precio_venta),
      peso_gramos: p.peso_gramos === null || p.peso_gramos === undefined ? '' : String(p.peso_gramos),
      descuento_producto: String(p.descuento_producto),
      temporada: p.temporada,
      ubicacion_deposito: p.ubicacion_deposito || '',
      stock_infinito: !!p.stock_infinito,
      fotos: p.fotos || [],
    };
  }

  function numeroValido(valor, { permiteCero = true } = {}) {
    if (valor === '' || valor === null || valor === undefined) return false;
    const n = Number(valor);
    if (Number.isNaN(n)) return false;
    return permiteCero ? n >= 0 : n > 0;
  }

  // ---------- Margen ↔ precio de venta (funciones puras, testeables) ----------

  // Valor null/'' → null (así lo manda el body; el otro modo siempre va en null).
  function _oNulo(valor) {
    return valor === '' || valor === null || valor === undefined ? null : String(valor);
  }

  // Parámetros del GET /precio-preview: costo siempre; margen O precio_venta
  // según el modo vigente (el campo del otro modo no se manda).
  function paramsPreview(form, modo) {
    const params = { proveedor_id: form.proveedor_id, costo: form.costo };
    if (modo === 'precio') params.precio_venta = form.precio_venta;
    else params.margen = form.margen;
    return params;
  }

  // Mitad del body que manda el precio: margen O precio_venta, el otro en
  // null (el service los trata como "no vino" y usa el que corresponda).
  function cuerpoPrecio(form, modo) {
    return modo === 'precio'
      ? { precio_venta: _oNulo(form.precio_venta), margen: null }
      : { margen: _oNulo(form.margen), precio_venta: null };
  }

  // Leyenda debajo del precio calculado. Vacía sin redondeo configurado
  // (multiplo <= 0) o con el precio cargado a mano (no pasa por la fórmula).
  function textoRedondeo(redondeo, redondeado) {
    const multiplo = Number(redondeo);
    if (!redondeado || !Number.isFinite(multiplo) || multiplo <= 0) return '';
    return 'Redondeado hacia arriba a múltiplos de $ ' + window.pesos(redondeo);
  }

  window.productoFormLogica = { paramsPreview, cuerpoPrecio, textoRedondeo };

  // ---------- Componente Alpine ----------

  window.productoForm = function ({ esAdmin, nivelMaximo, margenDefault, descuentoMaximo, puedeStockInicial }) {
    return {
      esAdmin,
      nivelMaximo,
      margenDefault,
      descuentoMaximo,
      puedeStockInicial,

      abierto: false,
      form: formVacio(margenDefault),
      elegidos: [],
      arbol: [],
      proveedores: [],
      errores: {},
      guardando: false,
      dolarProveedor: null,
      // Último campo que tocó el usuario entre margen y precio de venta: el
      // que manda al guardar y el que se usa al recalcular por un cambio de
      // costo. 'margen' al abrir (alta y edición).
      modoPrecio: 'margen',
      redondeo: null,
      redondeado: false,
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
        this.dolarProveedor = null;
        this.modoPrecio = 'margen';
        this.redondeo = null;
        this.redondeado = false;
        this.similares = [];
        this.similarActivo = 0;
        this.fotoInicial = null;
        this.arbol = [];
        this.elegidos = [];

        if (producto) {
          this.form = formDesdeProducto(producto);
          // En la edición se ve el precio actual (form.precio_venta) y, si
          // corresponde, el dólar vigente: ninguno de los dos se toca acá.
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
        const params = new URLSearchParams(paramsPreview(this.form, 'margen'));
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

      // Último campo tocado por el usuario: gana ese modo y se recalcula el
      // otro campo con la respuesta.
      alEditarMargen() {
        this.modoPrecio = 'margen';
        this.pedirPreview();
      },

      alEditarPrecio() {
        this.modoPrecio = 'precio';
        this.pedirPreview();
      },

      get redondeoTexto() {
        return textoRedondeo(this.redondeo, this.redondeado);
      },

      // Se llama con @input.debounce.300ms desde costo, margen y precio de
      // venta (los dos últimos, a través de alEditarMargen/alEditarPrecio).
      // Según `modoPrecio`: con margen, recalcula el precio; con precio
      // manual, recalcula el margen (el precio se respeta exacto).
      async pedirPreview() {
        const proveedorId = this.form.proveedor_id;
        const costoValido = numeroValido(this.form.costo, { permiteCero: false });
        const valorValido = this.modoPrecio === 'precio'
          ? numeroValido(this.form.precio_venta, { permiteCero: false })
          : numeroValido(this.form.margen);
        const apertura = this._apertura;
        if (!proveedorId || !costoValido || !valorValido) {
          // Invalida también un pedido en vuelo: su respuesta ya no corresponde.
          this._ultimaPreview(Promise.resolve(null));
          this.dolarProveedor = null;
          this.redondeo = null;
          this.redondeado = false;
          return;
        }
        try {
          const params = new URLSearchParams(paramsPreview(this.form, this.modoPrecio));
          const datos = await this._ultimaPreview(window.pedir(`${API}/precio-preview?${params}`));
          // Respuesta vieja: llegó otra más nueva o se abrió otro producto mientras tanto.
          if (datos === undefined || apertura !== this._apertura) return;
          this.dolarProveedor = datos.dolar_proveedor;
          this.redondeo = datos.redondeo;
          this.redondeado = datos.redondeado;
          if (this.modoPrecio === 'precio') this.form.margen = String(datos.margen);
          else this.form.precio_venta = String(datos.precio_venta);
        } catch (e) {
          this.dolarProveedor = null;
          this.redondeo = null;
          this.redondeado = false;
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
          ...cuerpoPrecio(this.form, this.modoPrecio),
          sku_proveedor: (this.form.sku_proveedor || '').trim() || null,
          descuento_producto: String(this.form.descuento_producto || 0),
          peso_gramos: this.form.peso_gramos === '' || this.form.peso_gramos === null || this.form.peso_gramos === undefined
            ? null : String(this.form.peso_gramos),
          temporada: this.form.temporada,
          ubicacion_deposito: (this.form.ubicacion_deposito || '').trim() || null,
          stock_infinito: !!this.form.stock_infinito,
        };
        if (!this.form.id) {
          cuerpo.proveedor_id = this.form.proveedor_id;
          cuerpo.stock_inicial = stockEntero(this.form.stock_inicial);
        }
        return cuerpo;
      },

      async guardar() {
        this.errores = {};
        if (this.categoriaId === null) {
          this.errores.categoria_id = 'Elegí hasta el último nivel: la categoría del producto es la del final de la rama.';
          return;
        }
        // Modo 'precio': el precio es obligatorio (si no, cuerpoPrecio manda
        // {margen: null, precio_venta: null} y el alta caería en el margen
        // por defecto en silencio).
        if (this.modoPrecio === 'precio' && !numeroValido(this.form.precio_venta, { permiteCero: false })) {
          this.errores.precio_venta = 'El precio de venta es obligatorio.';
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
