/* Tablero de inicio (/): un componente Alpine por bloque. Cada uno pide su
   API existente por su cuenta (si uno falla, los demás se ven igual) y solo
   se renderiza si el usuario tiene el permiso de esa API (pages.py). */
(function () {
  'use strict';

  const ALERTAS_STOCK = 5;

  // ---------- Lógica pura (testeada con node --test en tests_js/inicio.test.mjs) ----------
  window.inicioLogica = {
    // Qué muestra la tarjeta de Caja según GET /api/v1/turnos/activo.
    estadoCaja: (turno) => {
      if (!turno) return 'sin_turno';
      return turno.es_de_dia_anterior ? 'dia_anterior' : 'abierto';
    },
    // Anuladas de hoy: "Ninguna" o "2 · $ 3.500".
    textoAnuladas: (totales) => (Number(totales.anuladas)
      ? `${totales.anuladas} · $ ${window.pesos(totales.anuladas_monto)}`
      : 'Ninguna'),
  };
  const L = window.inicioLogica;

  // Estado y carga comunes a todos los bloques. Sin toast: un error se
  // muestra adentro de su tarjeta ("No se pudo cargar.").
  function bloque(url, alCargar) {
    return {
      cargando: true,
      error: false,
      async init() {
        try {
          alCargar.call(this, await window.pedir(url));
        } catch (e) {
          this.error = true;
        } finally {
          this.cargando = false;
        }
      },
    };
  }

  window.inicioCaja = () => ({
    turno: null,
    get estado() { return L.estadoCaja(this.turno); },
    ...bloque('/api/v1/turnos/activo', function (turno) { this.turno = turno; }),
  });

  window.inicioVentasHoy = ({ hoyIso }) => ({
    totales: null,
    textoAnuladas: L.textoAnuladas,
    ...bloque(`/api/v1/reportes/ventas-periodo?${new URLSearchParams({ desde: hoyIso, hasta: hoyIso })}`,
      function (reporte) { this.totales = reporte.totales; }),
  });

  window.inicioStock = () => ({
    productos: [],
    ...bloque(`/api/v1/stock/alertas?limite=${ALERTAS_STOCK}`, function (lista) { this.productos = lista; }),
  });
})();
