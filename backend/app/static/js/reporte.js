/* Pantalla genérica de reportes (/reportes/{clave}): filtros según lo que
   admite el reporte, tabla con las columnas que devuelve la API
   (app/api/v1/reportes.py) y fila de totales. Excel y PDF usan los filtros
   de la última búsqueda exitosa (lo que se está viendo). */
(function () {
  'use strict';

  const API = '/api/v1/reportes';
  const NUMERICOS = ['entero', 'moneda', 'porcentaje'];
  const CATALOGOS = ['proveedor_id', 'categoria_id', 'usuario_id', 'medio_de_pago_id'];

  // ---------- Lógica pura (testeada con node --test en tests_js/reporte.test.mjs) ----------
  window.reporteLogica = {
    // Por defecto: mes actual, primera agrupación del reporte, nivel 1,
    // orden por unidades y límite 50 (los mismos que completa el backend).
    filtrosIniciales: ({ admitidos, agrupaciones, hoyIso, inicioMesIso }) => {
      const filtros = {};
      if (admitidos.includes('desde')) { filtros.desde = inicioMesIso; filtros.hasta = hoyIso; }
      if (agrupaciones.length) filtros.agrupar = agrupaciones[0];
      if (admitidos.includes('nivel')) filtros.nivel = '1';
      if (admitidos.includes('orden')) filtros.orden = 'unidades';
      if (admitidos.includes('limite')) filtros.limite = '50';
      for (const clave of CATALOGOS) if (admitidos.includes(clave)) filtros[clave] = null;
      return filtros;
    },

    // Query de la API: solo los filtros admitidos y con valor; el nivel solo
    // al agrupar por categoría (el backend rechaza el resto con 422).
    queryDeFiltros: (filtros, admitidos) => {
      const params = {};
      for (const clave of admitidos) {
        const valor = filtros[clave];
        if (valor === null || valor === undefined) continue;
        const texto = String(valor).trim();
        if (!texto) continue;
        if (clave === 'nivel' && filtros.agrupar !== 'categoria') continue;
        params[clave] = texto;
      }
      return params;
    },

    // Celda según el tipo de columna (la API manda números crudos).
    formatear: (valor, tipo) => {
      if (valor === null || valor === undefined || valor === '') return '';
      switch (tipo) {
        case 'entero': return window.pesos(valor);
        case 'moneda': return '$ ' + window.pesos(valor);
        case 'porcentaje':
          return Number(valor).toLocaleString('es-AR', { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + ' %';
        case 'fecha': return window.fecha(valor);
        case 'mes': return window.fecha(valor).slice(3);   // "01/03/2025" → "03/2025"
        default: return String(valor);
      }
    },

    alineacion: (tipo) => (NUMERICOS.includes(tipo) ? 'text-right whitespace-nowrap' : ''),
  };
  const L = window.reporteLogica;

  window.reporte = function ({ clave, admitidos, agrupaciones, hoyIso, inicioMesIso }) {
    const iniciales = () => L.filtrosIniciales({ admitidos, agrupaciones, hoyIso, inicioMesIso });
    return {
      filtros: iniciales(),
      aplicados: null,   // query de la última búsqueda exitosa (la usan Excel y PDF)
      opciones: { proveedores: [], categorias: [], vendedores: [], medios_de_pago: [] },
      columnas: [],
      filas: [],
      totales: {},
      cargando: false,
      _ultima: window.ultimaRespuesta(),

      init() {
        this.buscar();
        if (CATALOGOS.some((c) => admitidos.includes(c))) this._cargarOpciones();
      },

      async _cargarOpciones() {
        try {
          this.opciones = await window.pedir(`${API}/opciones`);
        } catch (e) {
          window.toast(e.message, 'error');
        }
      },

      limpiarFiltros() {
        this.filtros = iniciales();
        this.buscar();
      },

      async buscar() {
        const params = L.queryDeFiltros(this.filtros, admitidos);
        this.cargando = true;
        try {
          const respuesta = await this._ultima(window.pedir(`${API}/${clave}?${new URLSearchParams(params)}`));
          if (respuesta === undefined) return;   // llegó un pedido más nuevo
          this.columnas = respuesta.columnas;
          this.filas = respuesta.filas;
          this.totales = respuesta.totales;
          this.aplicados = params;
          // Si el usuario borró Desde/Hasta, el backend completó el mes
          // actual: reflejarlo en los inputs (solo esos dos campos).
          if (admitidos.includes('desde')) {
            this.filtros.desde = respuesta.filtros.desde;
            this.filtros.hasta = respuesta.filtros.hasta;
          }
          this.cargando = false;
        } catch (e) {
          this.cargando = false;
          window.toast(e.message, 'error');
        }
      },

      urlExportar(formato) {
        if (!this.aplicados) return '#';
        return `${API}/${clave}/${formato}?${new URLSearchParams(this.aplicados)}`;
      },

      abrirPdf() {
        if (this.aplicados) window.abrirPdf(this.urlExportar('pdf'));
      },

      // ---------- Celdas ----------
      alineacion(columna) { return L.alineacion(columna.tipo); },
      celda(fila, columna) { return L.formatear(fila[columna.clave], columna.tipo); },
      // Fila de totales: "Total" en la primera columna (la del grupo, que no se totaliza).
      celdaTotal(columna, indice) { return indice === 0 ? 'Total' : L.formatear(this.totales[columna.clave], columna.tipo); },
    };
  };
})();
