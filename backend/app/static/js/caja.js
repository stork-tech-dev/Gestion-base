/* Caja (/caja) y cierre de turno (/caja/cerrar/{id}). El esperado lo calcula
   SIEMPRE el backend (GET /turnos/{id}/arqueo/esperado); acá solo se muestra
   la diferencia mientras se tipea, en centavos enteros (nunca float). */
(function () {
  'use strict';

  const API = '/api/v1/turnos';

  window.cajaLogica = {
    // "1.500,50" / "1500.5" / "1500" → 150050 centavos; vacío o inválido → null.
    aCentavos: (texto) => {
      if (texto === null || texto === undefined) return null;
      let limpio = String(texto).trim().replace(/\s|\$/g, '');
      if (!limpio) return null;
      if (limpio.includes(',')) limpio = limpio.replace(/\./g, '').replace(',', '.');
      if (!/^-?\d+(\.\d{1,2})?$/.test(limpio)) return null;
      const [entero, dec = ''] = limpio.replace('-', '').split('.');
      const centavos = Number(entero) * 100 + Number((dec + '00').slice(0, 2));
      return limpio.startsWith('-') ? -centavos : centavos;
    },
    claveDe: (item) => (item.grupo_terminal ? `g:${item.grupo_terminal}` : `m:${item.medio_de_pago_id}`),
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
    payloadArqueo(items, declarados) {
      const aTexto = (c) => (c / 100).toFixed(2);
      return {
        items_declarados: items.map((i) => ({
          medio_de_pago_id: i.medio_de_pago_id,
          grupo_terminal: i.grupo_terminal,
          monto_declarado: i.es_informativo ? String(i.monto_esperado)
            : aTexto(this.aCentavos(declarados[this.claveDe(i)])),
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
      cargandoArqueo: false,

      // ----- Turnos anteriores (Principio 5: tabla de alto volumen, "Buscar" explícito) -----
      filtros: { desde: '', hasta: '' },
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
        this.filtros = { desde: '', hasta: '' };
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
        this.abriendo = true;
        this.erroresAbrir = {};
        const centavos = L.aCentavos(this.formAbrir.efectivo_apertura);
        const efectivo_apertura = centavos === null ? '0.00' : (centavos / 100).toFixed(2);
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
        this.retirando = true;
        this.erroresRetiro = {};
        const centavos = L.aCentavos(this.formRetiro.monto);
        try {
          await window.pedir(`${API}/retiros`, {
            method: 'POST',
            body: { monto: centavos === null ? this.formRetiro.monto : (centavos / 100).toFixed(2), motivo: this.formRetiro.motivo },
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
          window.toast(e.message, 'error');
        } finally {
          this.cargando = false;
        }
      },

      diferenciaDe(item) {
        return L.diferencia(this.declarados[L.claveDe(item)], item.monto_esperado);
      },

      get totalDeclarado() {
        return L.totalDeclarado(this.items, this.declarados);
      },

      get diferenciaTotal() {
        const total = this.totalDeclarado;
        return total === null ? null : total - L.aCentavos(this.totalEsperado);
      },

      get puedeCerrar() {
        return this.totalDeclarado !== null && !this.cerrando;
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
