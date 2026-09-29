/* Caja (/caja) y cierre de turno (/caja/cerrar/{id}). El esperado lo calcula
   SIEMPRE el backend (GET /turnos/{id}/arqueo/esperado); acá solo se muestra
   la diferencia mientras se tipea, en centavos enteros (nunca float). */
(function () {
  'use strict';

  const API = '/api/v1/turnos';

  // Punto seguido de EXACTAMENTE 3 dígitos = separador de miles es-AR
  // ("10.000", "1.500"), nunca decimales (esos son 1 o 2 dígitos). Puede
  // combinarse con la coma decimal ("1.500,50").
  const RE_MILES = /^\d{1,3}(\.\d{3})+$/;

  window.cajaLogica = {
    // "10.000" / "1.500" / "1.500,50" / "1500.5" / "1500" → centavos;
    // vacío o inválido → null. Nunca confundir "10.50" (decimal: 2 dígitos)
    // con "10.500" (miles: 3 dígitos).
    aCentavos: (texto) => {
      if (texto === null || texto === undefined) return null;
      let limpio = String(texto).trim().replace(/\s|\$/g, '');
      if (!limpio) return null;
      const esNegativo = limpio.startsWith('-');
      if (esNegativo) limpio = limpio.slice(1);
      if (limpio.includes(',')) {
        limpio = limpio.replace(/\./g, '').replace(',', '.');
      } else if (RE_MILES.test(limpio)) {
        limpio = limpio.replace(/\./g, '');
      }
      if (!/^\d+(\.\d{1,2})?$/.test(limpio)) return null;
      const [entero, dec = ''] = limpio.split('.');
      const centavos = Number(entero) * 100 + Number((dec + '00').slice(0, 2));
      return esNegativo ? -centavos : centavos;
    },
    claveDe: (item) => (item.grupo_terminal ? `g:${item.grupo_terminal}` : `m:${item.medio_de_pago_id}`),
    // Única fuente de verdad para el error de un input de monto: vacío,
    // inválido (aCentavos no lo puede leer) y negativo (los montos de caja
    // nunca lo son) → mensaje de campo; nunca se manda nada en silencio.
    // `obligatorio` decide el mensaje del caso vacío (abrir turno permite
    // vacío = $0; retiro y cada línea del cierre lo declaran aparte).
    errorDeMonto(texto, { obligatorio = false } = {}) {
      const limpio = String(texto ?? '').trim();
      if (!limpio) return obligatorio ? 'El monto es obligatorio' : null;
      const centavos = this.aCentavos(limpio);
      return (centavos === null || centavos < 0) ? 'Monto inválido' : null;
    },
    diferencia(declarado, esperado) {
      const d = this.aCentavos(declarado);
      return d === null ? null : d - this.aCentavos(esperado);
    },
    // Suma de lo declarado en las líneas NO informativas; null si falta alguna.
    totalDeclarado(items, declarados) {
      let total = 0;
      for (const item of items.filter((i) => !i.es_informativo)) {
        const c = this.aCentavos(declarados[this.claveDe(item)]);
        if (c === null || c < 0) return null;
        total += c;
      }
      return total;
    },
    // Montos como string con 2 decimales (el backend los recibe como Decimal).
    // Las líneas informativas NO viajan: el backend ya las completa con el
    // esperado (services/arqueo.py, decisión 10) y mandar monto_declarado ahí
    // rompía la validación (ge=0) cuando el esperado es negativo.
    payloadArqueo(items, declarados) {
      const aTexto = (c) => (c / 100).toFixed(2);
      return {
        items_declarados: items.filter((i) => !i.es_informativo).map((i) => ({
          medio_de_pago_id: i.medio_de_pago_id,
          grupo_terminal: i.grupo_terminal,
          monto_declarado: aTexto(this.aCentavos(declarados[this.claveDe(i)])),
        })),
        total_declarado: aTexto(this.totalDeclarado(items, declarados)),
      };
    },
  };
  const L = window.cajaLogica;

  // ---------- Pantalla /caja: turno del día, retiros, unirse, abrir, turnos anteriores ----------
  window.cajaPantalla = function ({ usuarioId, puedeRetirar, puedeArquear }) {
    return {
      usuarioId, puedeRetirar, puedeArquear,
      verificando: true,
      turno: null,
      retiros: [],

      // ----- Abrir turno -----
      modalAbrir: false,
      formAbrir: { efectivo_apertura: '', notas: '' },
      erroresAbrir: {},
      abriendo: false,

      // ----- Unirme -----
      uniendome: false,

      // ----- Retiro -----
      modalRetiro: false,
      formRetiro: { monto: '', motivo: '' },
      erroresRetiro: {},
      retirando: false,

      // ----- Ver arqueo (turnos anteriores) -----
      modalArqueo: false,
      arqueo: null,
      arqueoFechaApertura: null,
      cargandoArqueo: false,

      // ----- Turnos anteriores (Principio 5: tabla de alto volumen, "Buscar" explícito) -----
      filtros: { estado: '', desde: '', hasta: '' },
      pagina: 1,
      tamano: 20,
      total: 0,
      filas: [],
      cargandoTurnos: false,
      _ultimaTurnos: window.ultimaRespuesta(),

      async init() {
        await Promise.all([this.cargarActivo(), this.cargarTurnos()]);
      },

      async cargarActivo() {
        this.verificando = true;
        try {
          this.turno = await window.pedir(`${API}/activo`);
          this.retiros = this.turno ? await window.pedir(`${API}/${this.turno.id}/retiros`) : [];
        } catch (e) {
          window.toast(e.message, 'error');
        } finally {
          this.verificando = false;
        }
      },

      async cargarTurnos(pagina) {
        if (pagina) this.pagina = pagina;
        this.cargandoTurnos = true;
        const params = new URLSearchParams({ pagina: this.pagina, tamano: this.tamano });
        if (this.filtros.estado) params.set('estado', this.filtros.estado);
        if (this.filtros.desde) params.set('desde', this.filtros.desde);
        if (this.filtros.hasta) params.set('hasta', this.filtros.hasta);
        try {
          const respuesta = await this._ultimaTurnos(window.pedir(`${API}?${params}`));
          if (respuesta === undefined) return;  // llegó un pedido más nuevo
          this.filas = respuesta.resultados;
          this.total = respuesta.total;
        } catch (e) {
          window.toast(e.message, 'error');
        } finally {
          this.cargandoTurnos = false;
        }
      },

      limpiarFiltrosTurnos() {
        this.filtros = { estado: '', desde: '', hasta: '' };
        this.cargarTurnos(1);
      },

      // ----- Celdas de "Turnos anteriores" -----
      diferenciaTexto(fila) {
        if (fila.diferencia_arqueo === null || fila.diferencia_arqueo === undefined) return '—';
        const texto = '$ ' + window.pesos(fila.diferencia_arqueo);
        return Number(fila.diferencia_arqueo) !== 0 ? `<span class="font-semibold text-danger">${texto}</span>` : texto;
      },
      estadoTurnoTexto(fila) {
        return fila.estado === 'cerrado' ? window.estadoHtml('Cerrado', 'neutro') : window.estadoHtml('Abierto', 'exito');
      },

      get sumado() {
        return !!this.turno && this.turno.usuarios.some((u) => u.id === this.usuarioId);
      },

      // ----- Abrir turno -----
      abrirModalAbrir() {
        this.formAbrir = { efectivo_apertura: '', notas: '' };
        this.erroresAbrir = {};
        this.modalAbrir = true;
      },

      async abrir() {
        this.erroresAbrir = {};
        // Vacío = $0 (placeholder); no vacío e ininterpretable (o negativo) =
        // error de campo, nunca se manda crudo ni como 0 (nunca en silencio).
        const texto = String(this.formAbrir.efectivo_apertura ?? '').trim();
        const error = L.errorDeMonto(texto, { obligatorio: false });
        if (error) {
          this.erroresAbrir = { efectivo_apertura: error };
          return;
        }
        const centavos = texto === '' ? 0 : L.aCentavos(texto);
        this.abriendo = true;
        const efectivo_apertura = (centavos / 100).toFixed(2);
        try {
          await window.pedir(`${API}/abrir`, {
            method: 'POST',
            body: { efectivo_apertura, notas: this.formAbrir.notas || null },
          });
          this.modalAbrir = false;
          window.toast('Turno abierto');
          await this.cargarActivo();
        } catch (e) {
          this.erroresAbrir = window.erroresDeCampos(e);
          window.toast(e.message, 'error');
        } finally {
          this.abriendo = false;
        }
      },

      // ----- Unirme -----
      async unirme() {
        this.uniendome = true;
        try {
          await window.pedir(`${API}/unirse`, { method: 'POST' });
          window.toast('Te uniste al turno');
          await this.cargarActivo();
        } catch (e) {
          window.toast(e.message, 'error');
        } finally {
          this.uniendome = false;
        }
      },

      // ----- Retiro -----
      abrirModalRetiro() {
        this.formRetiro = { monto: '', motivo: '' };
        this.erroresRetiro = {};
        this.modalRetiro = true;
      },

      async retirar() {
        this.erroresRetiro = {};
        const texto = String(this.formRetiro.monto ?? '').trim();
        // El monto es obligatorio (> 0): vacío, ininterpretable o negativo es
        // error de campo, nunca se manda crudo ni como 0 (nunca en silencio).
        const error = L.errorDeMonto(texto, { obligatorio: true });
        if (error) {
          this.erroresRetiro = { monto: error };
          return;
        }
        const centavos = L.aCentavos(texto);
        this.retirando = true;
        try {
          await window.pedir(`${API}/retiros`, {
            method: 'POST',
            body: { monto: (centavos / 100).toFixed(2), motivo: this.formRetiro.motivo },
          });
          this.modalRetiro = false;
          window.toast('Retiro registrado');
          await this.cargarActivo();
        } catch (e) {
          this.erroresRetiro = window.erroresDeCampos(e);
          window.toast(e.message, 'error');
        } finally {
          this.retirando = false;
        }
      },

      // ----- Ver arqueo (fila de "Turnos anteriores") -----
      async verArqueo(fila) {
        this.arqueo = null;
        // Título del modal: fecha de APERTURA del turno (la misma que usa la
        // notificación de diferencia), no arqueo.created_at.
        this.arqueoFechaApertura = fila.fecha_apertura;
        this.modalArqueo = true;
        this.cargandoArqueo = true;
        try {
          this.arqueo = await window.pedir(`${API}/${fila.id}/arqueo`);
        } catch (e) {
          window.toast(e.message, 'error');
        } finally {
          this.cargandoArqueo = false;
        }
      },
    };
  };

  // ---------- Pantalla /caja/cerrar/{turnoId}: arqueo y cierre ----------
  window.cerrarTurnoPantalla = function ({ turnoId }) {
    return {
      turnoId,
      cargando: true,
      error: false,
      items: [],
      efectivoApertura: '0',
      totalEsperado: '0',
      declarados: {},
      cerrando: false,

      claveDe(item) { return L.claveDe(item); },

      async init() {
        try {
          const datos = await window.pedir(`${API}/${turnoId}/arqueo/esperado`);
          this.items = datos.items;
          this.efectivoApertura = datos.efectivo_apertura;
          this.totalEsperado = datos.total_esperado;
          this.declarados = {};
          for (const item of this.items) {
            this.declarados[L.claveDe(item)] = item.es_informativo ? String(item.monto_esperado) : '';
          }
        } catch (e) {
          // Si falla el esperado no hay con qué declarar ni cerrar: se avisa
          // y se deja "Cerrar turno" deshabilitado (puedeCerrar), en vez de
          // mostrar una tabla vacía con total $0 y el botón habilitado.
          this.error = true;
          window.toast(e.message, 'error');
        } finally {
          this.cargando = false;
        }
      },

      diferenciaDe(item) {
        return L.diferencia(this.declarados[L.claveDe(item)], item.monto_esperado);
      },

      // "Monto inválido" debajo del input: solo para lo que el usuario ya
      // tipeó y no se puede leer (o es negativo). Vacío no es "inválido"
      // todavía (recién abrió la pantalla): eso lo explica motivoDeshabilitado.
      // Las líneas informativas nunca muestran error: las completa el backend.
      errorDe(item) {
        if (item.es_informativo) return null;
        return L.errorDeMonto(this.declarados[L.claveDe(item)], { obligatorio: false });
      },

      get totalDeclarado() {
        return L.totalDeclarado(this.items, this.declarados);
      },

      get diferenciaTotal() {
        const total = this.totalDeclarado;
        return total === null ? null : total - L.aCentavos(this.totalEsperado);
      },

      get puedeCerrar() {
        return !this.error && this.items.length > 0 && this.totalDeclarado !== null && !this.cerrando;
      },

      // Texto que explica por qué "Cerrar turno" está deshabilitado cuando
      // es por faltar o no poder leer algún monto (no por error de carga ni
      // por estar cerrando, que ya se explican por su cuenta).
      get motivoDeshabilitado() {
        if (this.error || this.cerrando) return null;
        return this.totalDeclarado === null ? 'Completá todos los montos para cerrar' : null;
      },

      async cerrar() {
        if (!this.puedeCerrar) return;
        const ok = await window.confirmar({
          titulo: 'Cerrar turno',
          mensaje: '¿Cerrar el turno con estos montos? No se puede deshacer.',
        });
        if (!ok) return;
        this.cerrando = true;
        try {
          await window.pedir(`${API}/${turnoId}/arqueo`, {
            method: 'POST',
            body: L.payloadArqueo(this.items, this.declarados),
          });
          window.toast('Turno cerrado');
          location.href = '/caja';
        } catch (e) {
          window.toast(e.message, 'error');
        } finally {
          this.cerrando = false;
        }
      },
    };
  };
})();
