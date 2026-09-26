/* Pantallas de autenticación. La sesión viaja en cookies HttpOnly: este
   archivo nunca lee ni guarda tokens. */
(function () {
  'use strict';

  const MENSAJE_CONFIRMACION = 'La confirmación no coincide con la contraseña nueva.';

  window.login = function () {
    return {
      username: '',
      password: '',
      enviando: false,
      olvide: false,
      usernameRecuperar: '',
      mensaje: '',
      async ingresar() {
        this.enviando = true;
        try {
          const datos = await window.pedir('/api/v1/auth/login', {
            method: 'POST',
            body: { username: this.username, password: this.password },
          });
          window.location.href = datos.usuario.debe_cambiar_password ? '/cambiar-password' : '/';
        } catch (e) {
          this.password = '';
          window.toast(e.message, 'error');
        } finally {
          this.enviando = false;
        }
      },
      async recuperar() {
        this.enviando = true;
        this.mensaje = '';
        try {
          const datos = await window.pedir('/api/v1/auth/forgot-password', {
            method: 'POST',
            body: { username: this.usernameRecuperar },
          });
          this.mensaje = datos.mensaje;
        } catch (e) {
          window.toast(e.message, 'error');
        } finally {
          this.enviando = false;
        }
      },
    };
  };

  window.cambiarPassword = function () {
    return {
      actual: '',
      nueva: '',
      confirmacion: '',
      enviando: false,
      errores: {},
      async guardar() {
        this.errores = {};
        if (this.nueva !== this.confirmacion) return window.toast(MENSAJE_CONFIRMACION, 'error');
        this.enviando = true;
        try {
          await window.pedir('/api/v1/auth/cambiar-password', {
            method: 'POST',
            body: { password_actual: this.actual, password_nueva: this.nueva },
          });
          window.location.href = '/';
        } catch (e) {
          this.errores = window.erroresDeCampos(e);
          window.toast(e.message, 'error');
        } finally {
          this.enviando = false;
        }
      },
    };
  };

  window.resetPassword = function (token) {
    return {
      nueva: '',
      confirmacion: '',
      enviando: false,
      listo: false,
      errores: {},
      init() {
        // El token ya está en el componente: sacarlo de la URL para que no
        // quede en el historial del navegador.
        history.replaceState(null, '', '/reset-password');
      },
      async guardar() {
        this.errores = {};
        if (this.nueva !== this.confirmacion) return window.toast(MENSAJE_CONFIRMACION, 'error');
        this.enviando = true;
        try {
          await window.pedir('/api/v1/auth/reset-password', {
            method: 'POST',
            body: { token, password_nueva: this.nueva },
          });
          this.listo = true;
        } catch (e) {
          this.errores = window.erroresDeCampos(e);
          window.toast(e.message, 'error');
        } finally {
          this.enviando = false;
        }
      },
    };
  };
})();
