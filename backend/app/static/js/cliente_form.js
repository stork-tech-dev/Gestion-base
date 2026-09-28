/* Formulario de cliente (macro components/cliente_form.html): datos vacíos y
   cuerpo del request de alta/edición. ÚNICA definición, la usan el listado de
   clientes (clientes.js) y el alta rápida de la pantalla de venta (venta.js). */
(function () {
  'use strict';

  const textoONull = (valor) => String(valor ?? '').trim() || null;

  window.clienteFormulario = {
    vacio: () => ({
      id: null, nombre: '', dni: '', cuit: '', condicion_iva: 'consumidor_final',
      domicilio: '', codigo_postal: '', localidad: '', telefono: '', email: '',
    }),
    // Campos opcionales vacíos → null (la API los guarda como NULL).
    cuerpo: (form) => ({
      nombre: form.nombre,
      dni: textoONull(form.dni),
      cuit: textoONull(form.cuit),
      condicion_iva: form.condicion_iva,
      domicilio: textoONull(form.domicilio),
      codigo_postal: textoONull(form.codigo_postal),
      localidad: textoONull(form.localidad),
      telefono: textoONull(form.telefono),
      email: textoONull(form.email),
    }),
  };
})();
