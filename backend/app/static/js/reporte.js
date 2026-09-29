/* Pantalla genérica de reportes (/reportes/{clave}): filtros según lo que
   admite el reporte, tabla con las columnas que devuelve la API
   (app/api/v1/reportes.py), gráfico arriba (Chart.js) y fila de totales.
   Excel y PDF usan los filtros de la última búsqueda exitosa (lo que se
   está viendo). */
(function () {
  'use strict';

  const API = '/api/v1/reportes';
  const NUMERICOS = ['entero', 'moneda', 'porcentaje'];
  const CATALOGOS = ['proveedor_id', 'categoria_id', 'usuario_id', 'medio_de_pago_id'];
  const MAX_BARRAS = 10;   // barras: el gráfico muestra las primeras N filas; la tabla, todas
  const UN_DIA_MS = 24 * 60 * 60 * 1000;

  // Fechas ISO ("AAAA-MM-DD") como texto/UTC, nunca con hora local (evita que
  // un huso horario negativo corra el día al calcular la lista de períodos).
  function diasEntre(desdeIso, hastaIso) {
    const dias = [];
    for (let t = Date.parse(`${desdeIso}T00:00:00Z`); t <= Date.parse(`${hastaIso}T00:00:00Z`); t += UN_DIA_MS) {
      dias.push(new Date(t).toISOString().slice(0, 10));
    }
    return dias;
  }

  function mesesEntre(desdeIso, hastaIso) {
    const meses = [];
    const fin = Date.UTC(Number(hastaIso.slice(0, 4)), Number(hastaIso.slice(5, 7)) - 1, 1);
    let cursor = Date.UTC(Number(desdeIso.slice(0, 4)), Number(desdeIso.slice(5, 7)) - 1, 1);
    while (cursor <= fin) {
      meses.push(new Date(cursor).toISOString().slice(0, 10));
      cursor = Date.UTC(new Date(cursor).getUTCFullYear(), new Date(cursor).getUTCMonth() + 1, 1);
    }
    return meses;
  }

  // Todos los períodos (día o mes) entre filtros.desde y filtros.hasta, con
  // las filas que no tienen dato en 0 (para que la línea no una dos puntos
  // lejanos como si fuera una tendencia continua).
  function completarPeriodos(filas, clave, valor, tipo, desde, hasta) {
    const periodos = tipo === 'mes' ? mesesEntre(desde, hasta) : diasEntre(desde, hasta);
    const porPeriodo = Object.fromEntries(filas.map((fila) => [fila[clave], fila]));
    return periodos.map((periodo) => porPeriodo[periodo] || { [clave]: periodo, [valor]: 0 });
  }

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

    // Datos del gráfico (una serie) a partir de la respuesta: barras = las
    // primeras MAX_BARRAS filas en el orden del reporte; línea = todas, y si
    // la etiqueta es fecha o mes, con los períodos sin datos completados en 0
    // entre filtros.desde y filtros.hasta (si no vienen, no completa).
    // Las etiquetas usan el mismo formato que la tabla. null = no se dibuja.
    datosGrafico: (grafico, columnas, filas, filtros) => {
      if (!grafico || !filas.length) return null;
      const tipos = Object.fromEntries(columnas.map((c) => [c.clave, c.tipo]));
      const formatear = window.reporteLogica.formatear;
      const [claveEtiqueta] = grafico.etiquetas;
      const tipoEtiqueta = tipos[claveEtiqueta];
      const completar = grafico.tipo === 'linea' && (tipoEtiqueta === 'fecha' || tipoEtiqueta === 'mes')
        && filtros && filtros.desde && filtros.hasta;
      const completas = completar
        ? completarPeriodos(filas, claveEtiqueta, grafico.valor, tipoEtiqueta, filtros.desde, filtros.hasta)
        : filas;
      const visibles = grafico.tipo === 'barras' ? completas.slice(0, MAX_BARRAS) : completas;
      return {
        tipo: grafico.tipo,
        titulo: grafico.titulo,
        tipoValor: tipos[grafico.valor],
        recortado: visibles.length < completas.length,
        maximo: MAX_BARRAS,
        etiquetas: visibles.map((fila) => grafico.etiquetas
          .map((clave) => formatear(fila[clave], tipos[clave])).filter(Boolean).join(' · ')),
        valores: visibles.map((fila) => Number(fila[grafico.valor]) || 0),
      };
    },
  };
  const L = window.reporteLogica;

  window.reporte = function ({ clave, admitidos, agrupaciones, hoyIso, inicioMesIso }) {
    const iniciales = () => L.filtrosIniciales({ admitidos, agrupaciones, hoyIso, inicioMesIso });
    // Instancia de Chart.js FUERA del estado reactivo (el proxy de Alpine la rompe).
    let chart = null;
    return {
      filtros: iniciales(),
      aplicados: null,   // query de la última búsqueda exitosa (la usan Excel y PDF)
      opciones: { proveedores: [], categorias: [], vendedores: [], medios_de_pago: [] },
      columnas: [],
      filas: [],
      totales: {},
      grafico: null,   // datosGrafico de la última respuesta (null = sin gráfico)
      hayGraficos: typeof window.Chart !== 'undefined',   // false si no cargó el CDN de Chart.js
      cargando: false,
      _ultima: window.ultimaRespuesta(),

      init() {
        this.buscar();
        if (CATALOGOS.some((c) => admitidos.includes(c))) this._cargarOpciones();
        // Redibujar con los colores del tema al alternar claro/oscuro.
        if (typeof MutationObserver !== 'undefined') {
          new MutationObserver(() => this._dibujar())
            .observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
        }
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
          this.grafico = L.datosGrafico(respuesta.grafico, respuesta.columnas, respuesta.filas, respuesta.filtros);
          this.$nextTick(() => this._dibujar());
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

      // Dibuja (o borra) el gráfico con el color primario del tema actual.
      _dibujar() {
        if (chart) { chart.destroy(); chart = null; }
        const lienzo = this.$refs.grafico;
        if (!this.grafico || !lienzo || typeof window.Chart === 'undefined') return;
        // Datos planos, no el proxy reactivo de Alpine (Chart.js muta lo que le pasamos).
        const g = window.Alpine ? window.Alpine.raw(this.grafico) : this.grafico;
        const estilo = getComputedStyle(document.documentElement);
        const color = (variable) => estilo.getPropertyValue(variable).trim();
        const barras = g.tipo === 'barras';
        const formatear = (valor) => L.formatear(valor, g.tipoValor);
        const ejeValor = { beginAtZero: true, grid: { color: color('--color-border') },
                           ticks: { color: color('--color-text-muted'), callback: (valor) => formatear(valor) } };
        if (g.tipoValor === 'entero') ejeValor.ticks.precision = 0;
        const ejeGrupo = { grid: { display: false }, ticks: { color: color('--color-text-muted') } };
        // Barras horizontales: etiquetas largas truncadas (el tooltip sigue
        // mostrando el nombre completo, que es el título por defecto).
        if (barras) {
          ejeGrupo.ticks.callback = function (valor) {
            const texto = this.getLabelForValue(valor);
            return texto.length > 22 ? `${texto.slice(0, 22)}…` : texto;
          };
        }
        chart = new window.Chart(lienzo, {
          type: barras ? 'bar' : 'line',
          data: {
            labels: [...g.etiquetas],
            datasets: [{
              data: [...g.valores], backgroundColor: color('--color-primary'), borderColor: color('--color-primary'),
              borderWidth: 2, borderRadius: 4, maxBarThickness: 28, pointRadius: 3, pointHoverRadius: 5, tension: 0.2,
            }],
          },
          options: {
            indexAxis: barras ? 'y' : 'x',
            responsive: true,
            maintainAspectRatio: false,
            animation: false,
            plugins: { legend: { display: false }, tooltip: { callbacks: { label: (ctx) => formatear(ctx.raw) } } },
            scales: barras ? { x: ejeValor, y: ejeGrupo } : { x: ejeGrupo, y: ejeValor },
          },
        });
      },

      // ---------- Celdas ----------
      alineacion(columna) { return L.alineacion(columna.tipo); },
      celda(fila, columna) { return L.formatear(fila[columna.clave], columna.tipo); },
      // Fila de totales: "Total" en la primera columna (la del grupo, que no se totaliza).
      celdaTotal(columna, indice) { return indice === 0 ? 'Total' : L.formatear(this.totales[columna.clave], columna.tipo); },
    };
  };
})();
