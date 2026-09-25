/* Funciones JavaScript globales (sin build). Se carga ANTES que Alpine. */
(function () {
  'use strict';

  // ---------- Tema claro / oscuro (persistido en localStorage.theme) ----------
  window.temaApp = function () {
    return {
      oscuro: document.documentElement.classList.contains('dark'),
      alternarTema() {
        this.oscuro = !this.oscuro;
        try { localStorage.theme = this.oscuro ? 'dark' : 'light'; } catch (e) { /* sin storage */ }
      },
    };
  };

  // ---------- Formato de números (es-AR). Decimales solo si existen. ----------
  function formatearNumero(valor) {
    if (valor === null || valor === undefined || valor === '') return '';
    const n = Number(valor);
    if (Number.isNaN(n)) return '';
    const decimales = Number.isInteger(n) ? 0 : 2;
    return n.toLocaleString('es-AR', { minimumFractionDigits: decimales, maximumFractionDigits: 2 });
  }
  window.pesos = formatearNumero;
  window.formatearDolar = formatearNumero;

  // ---------- Toasts ----------
  window.toast = function (mensaje, tipo = 'exito', duracion = 4000) {
    window.dispatchEvent(new CustomEvent('toast', { detail: { mensaje, tipo, duracion } }));
  };
  window.toasts = function () {
    return {
      lista: [],
      siguiente: 1,
      agregar({ mensaje, tipo = 'exito', duracion = 4000 } = {}) {
        if (!mensaje) return;
        const id = this.siguiente++;
        this.lista.push({ id, mensaje, tipo });
        if (duracion > 0) setTimeout(() => this.quitar(id), duracion);
      },
      quitar(id) { this.lista = this.lista.filter((t) => t.id !== id); },
    };
  };

  // ---------- Pedidos JSON a la API ----------
  function mensajeDeError(datos, status) {
    const detalle = datos && datos.detail;
    if (typeof detalle === 'string') return detalle;
    if (Array.isArray(detalle) && detalle.length) return detalle[0].msg || 'Datos inválidos.';
    return `Error ${status}`;
  }
  window.mensajeDeError = mensajeDeError;

  window.pedir = async function (url, opciones = {}) {
    const op = { credentials: 'same-origin', ...opciones, headers: { Accept: 'application/json', ...(opciones.headers || {}) } };
    if (op.body !== undefined && !(op.body instanceof FormData) && typeof op.body !== 'string') {
      op.body = JSON.stringify(op.body);
      op.headers['Content-Type'] = 'application/json';
    }
    const respuesta = await fetch(url, op);
    if (respuesta.status === 204) return null;
    const esJson = (respuesta.headers.get('content-type') || '').includes('application/json');
    const datos = esJson ? await respuesta.json() : await respuesta.text();
    if (!respuesta.ok) {
      const error = new Error(mensajeDeError(esJson ? datos : null, respuesta.status));
      error.status = respuesta.status;
      error.datos = datos;  // para marcar campos en errores 422
      throw error;
    }
    return datos;
  };

  // ---------- Texto y categorías ----------
  window.normalizarTexto = (texto) =>
    String(texto ?? '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().trim();

  /** Ids desde la raíz hasta `id` en un árbol [{id, nombre, hijos: [...]}]. */
  window.rutaDeIds = function (arbol, id, camino = []) {
    for (const nodo of arbol || []) {
      const actual = [...camino, nodo.id];
      if (nodo.id == id) return actual;
      const encontrado = window.rutaDeIds(nodo.hijos, id, actual);
      if (encontrado.length) return encontrado;
    }
    return [];
  };

  /** Camino legible de una categoría: "Ropa > Remeras > Lisas". */
  window.rutaCategoria = function (arbol, id, separador = ' > ') {
    const nombres = [];
    let nivel = arbol;
    for (const idNodo of window.rutaDeIds(arbol, id)) {
      const nodo = (nivel || []).find((n) => n.id == idNodo);
      nombres.push(nodo.nombre);
      nivel = nodo.hijos;
    }
    return nombres.join(separador);
  };

  // ---------- Combobox (select con búsqueda) ----------
  window.combobox = function ({ fuente, texto = 'texto', valor = 'id' }) {
    return {
      seleccion: null,
      busqueda: '',
      abierto: false,
      activo: 0,
      campoTexto: texto,
      campoValor: valor,
      get opciones() { return fuente() || []; },
      get filtradas() {
        const q = window.normalizarTexto(this.busqueda);
        return this.opciones.filter((o) => window.normalizarTexto(o[this.campoTexto]).includes(q)).slice(0, 50);
      },
      get etiqueta() {
        const elegida = this.opciones.find((o) => o[this.campoValor] == this.seleccion);
        return elegida ? elegida[this.campoTexto] : '';
      },
      abrir() {
        this.abierto = true;
        this.busqueda = '';
        this.activo = 0;
        this.$nextTick(() => this.$refs.buscador && this.$refs.buscador.focus());
      },
      cerrar() { this.abierto = false; },
      alternar() { this.abierto ? this.cerrar() : this.abrir(); },
      elegir(opcion) {
        this.seleccion = opcion ? opcion[this.campoValor] : null;
        this.cerrar();
        this.$dispatch('cambio', this.seleccion);
      },
      mover(delta) {
        const total = this.filtradas.length;
        if (total) this.activo = (this.activo + delta + total) % total;
      },
      confirmar() {
        const opcion = this.filtradas[this.activo];
        if (opcion) this.elegir(opcion);
      },
    };
  };

  // ---------- Confirmación global (reemplaza a confirm()) ----------
  window.confirmar = function (opciones = {}) {
    return new Promise((resolver) => {
      window.dispatchEvent(new CustomEvent('confirmar', { detail: { ...opciones, resolver } }));
    });
  };
  window.dialogoConfirmacion = function () {
    return {
      abierto: false,
      titulo: '',
      mensaje: '',
      advertencia: '',
      textoConfirmar: 'Confirmar',
      peligro: false,
      resolver: null,
      abrir(d) {
        this.titulo = d.titulo || '¿Confirmás la acción?';
        this.mensaje = d.mensaje || '';
        this.advertencia = d.advertencia || '';
        this.textoConfirmar = d.textoConfirmar || 'Confirmar';
        this.peligro = !!d.peligro;
        this.resolver = d.resolver;
        this.abierto = true;
        this.$nextTick(() => this.$refs.confirmar && this.$refs.confirmar.focus());
      },
      responder(valor) {
        this.abierto = false;
        if (this.resolver) this.resolver(valor);
        this.resolver = null;
      },
    };
  };

  // ---------- Cámara (fotos de productos) ----------
  window.webcamCapture = function () {
    return {
      stream: null,
      activa: false,
      error: '',
      async iniciar() {
        this.error = '';
        try {
          this.stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' }, audio: false });
          this.$refs.video.srcObject = this.stream;
          this.activa = true;
        } catch (e) {
          this.error = 'No se pudo acceder a la cámara.';
        }
      },
      capturar(tipo = 'image/jpeg', calidad = 0.9) {
        const video = this.$refs.video;
        const lienzo = document.createElement('canvas');
        lienzo.width = video.videoWidth;
        lienzo.height = video.videoHeight;
        lienzo.getContext('2d').drawImage(video, 0, 0);
        return new Promise((resolver) => lienzo.toBlob(resolver, tipo, calidad));
      },
      detener() {
        if (this.stream) this.stream.getTracks().forEach((t) => t.stop());
        this.stream = null;
        this.activa = false;
      },
    };
  };

  // ---------- Sesión ----------
  window.cerrarSesion = async function () {
    try {
      await fetch('/api/v1/auth/logout', { method: 'POST', credentials: 'same-origin' });
    } finally {
      window.location.href = '/login';
    }
  };

  let sesionVencidaAvisada = false;
  function avisarSesionVencida() {
    if (sesionVencidaAvisada) return;
    sesionVencidaAvisada = true;
    window.toast('Tu sesión venció. Volvé a ingresar.', 'error');
    setTimeout(() => { window.location.href = '/login'; }, 1500);
  }

  // Wrapper de fetch: cuenta como actividad y detecta la sesión vencida.
  const fetchOriginal = window.fetch.bind(window);
  window.fetch = async function (recurso, opciones) {
    const respuesta = await fetchOriginal(recurso, opciones);
    const url = String((recurso && recurso.url) || recurso);
    window.dispatchEvent(new Event('sesion:actividad'));
    if (respuesta.status === 401 && !url.includes('/api/v1/auth/')) avisarSesionVencida();
    return respuesta;
  };

  document.addEventListener('htmx:afterRequest', () => window.dispatchEvent(new Event('sesion:actividad')));
  document.addEventListener('htmx:responseError', (evento) => {
    const xhr = evento.detail.xhr;
    if (xhr.status === 401) return avisarSesionVencida();
    let datos = null;
    try { datos = JSON.parse(xhr.responseText); } catch (e) { /* no es JSON */ }
    window.toast(mensajeDeError(datos, xhr.status), 'error');
  });
  document.addEventListener('htmx:sendError', () => window.toast('Sin conexión con el servidor.', 'error'));

  /** Aviso 2 minutos antes del vencimiento por inactividad. */
  window.avisoSesion = function (minutos) {
    const total = minutos * 60 * 1000;
    const anticipo = 2 * 60 * 1000;
    return {
      visible: false,
      ultima: Date.now(),
      intervalo: null,
      init() {
        window.addEventListener('sesion:actividad', () => { if (!this.visible) this.ultima = Date.now(); });
        this.intervalo = setInterval(() => this.revisar(), 15000);
      },
      revisar() {
        const inactivo = Date.now() - this.ultima;
        if (inactivo >= total) {
          clearInterval(this.intervalo);
          avisarSesionVencida();
        } else if (inactivo >= total - anticipo) {
          this.visible = true;
        }
      },
      async seguir() {
        try {
          await window.pedir('/api/v1/auth/refresh', { method: 'POST' });
          this.ultima = Date.now();
          this.visible = false;
        } catch (e) {
          avisarSesionVencida();
        }
      },
    };
  };

  // ---------- Atajos globales ----------
  const ATAJOS = { F2: 'atajo-buscar', F10: 'atajo-confirmar', Escape: 'atajo-cancelar' };
  document.addEventListener('keydown', (evento) => {
    const nombre = ATAJOS[evento.key];
    if (!nombre) return;
    if (evento.key !== 'Escape') evento.preventDefault();
    window.dispatchEvent(new CustomEvent(nombre));
  });
})();
