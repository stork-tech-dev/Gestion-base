# SESIÓN 07 — Caja y Turnos
# [CLAUDE.md se carga automáticamente — no hace falta incluirlo]

## PREREQUISITOS
- Sesiones 01 a 06 completadas y funcionando
- Tablas `usuarios`, `roles`, `ventas` (con `turno_id` y `turno_anulacion_id`),
  `venta_pagos` y `medios_de_pago` (con `es_efectivo`) ya existentes
- `resolver_permiso` ya implementado

## OBJETIVO DE ESTA SESIÓN
Caja por turnos: apertura, sumarse, cierre con arqueo, retiros de efectivo,
notificaciones al Admin cuando el arqueo da diferencia, y el **turno como
requisito para vender y anular** (con bloqueo duro por un turno de un día
anterior sin cerrar). Frontend de escritorio (responsive): página "Caja" y
pantalla de cierre.

## CONTEXTO DE NEGOCIO
Hay un **único punto de venta** y, por lo tanto, una sola caja. Un turno es el
período de trabajo: se abre, se opera y se cierra con un arqueo. Varios
usuarios pueden trabajar en el mismo turno (caja compartida). El sistema no
maneja la terminal de pago (Clover/Payway): solo registra los cobros y los
compara en el arqueo.

**Preparado para multi-local:** ningún service asume "la única caja" fuera de
`obtener_turno_activo()` / `turno_para_operar()`. Si en el futuro hay locales,
esas dos funciones reciben el local y el resto no cambia.

Fuera de alcance: gift cards, señas y configuración de arqueo desde pantalla.

---

## PARTE 1 — MODELO DE DATOS (migración de esta sesión)

`Modulo.CAJA = "caja"` en `core/permisos.py` (con `LABEL_MODULO` "Caja"); los
recursos `caja.arqueo` y `caja.retiro` cuelgan de `CAJA` en `MODULO_DE_RECURSO`
(ya declarados en la sesión 02).

```sql
-- ENUM estado_turno: abierto, cerrado
-- ENUM tipo_notificacion: diferencia_arqueo
-- (los enums usan values_callable para guardar los valores en minúscula)

turnos (
  id BIGSERIAL PK,
  estado               estado_turno NOT NULL DEFAULT 'abierto',   -- índice
  efectivo_apertura    NUMERIC(10,2) NOT NULL,                    -- CHECK >= 0
  usuario_apertura_id  BIGINT FK → usuarios.id NOT NULL,
  usuario_cierre_id    BIGINT FK → usuarios.id,
  fecha_apertura       TIMESTAMP NOT NULL,
  fecha_cierre         TIMESTAMP,
  notas                TEXT,
  created_at, updated_at TIMESTAMP NOT NULL
)
-- UNIQUE INDEX uq_turnos_un_abierto ON turnos ((true)) WHERE estado = 'abierto'
--   → nunca hay dos turnos abiertos a la vez

-- En esta migración se agregan las FKs pendientes de la sesión 06:
--   ventas.turno_id           → turnos.id ON DELETE RESTRICT
--   ventas.turno_anulacion_id → turnos.id ON DELETE RESTRICT

turno_usuarios (   -- quiénes trabajan en el turno
  id BIGSERIAL PK,
  turno_id   BIGINT FK → turnos.id NOT NULL,   -- índice
  usuario_id BIGINT FK → usuarios.id NOT NULL,
  ingreso    TIMESTAMP NOT NULL,
  UNIQUE (turno_id, usuario_id)
)

retiros_efectivo (
  id BIGSERIAL PK,
  turno_id    BIGINT FK → turnos.id NOT NULL,   -- índice
  monto       NUMERIC(10,2) NOT NULL,           -- CHECK > 0
  motivo      VARCHAR(255) NOT NULL,
  usuario_id  BIGINT FK → usuarios.id NOT NULL, -- quien lo registra (tiene caja.retiro)
  timestamp   TIMESTAMP NOT NULL
)

medios_pago_arqueo_config (   -- cómo se arquea cada medio (opcional por medio; solo seed/SQL)
  id BIGSERIAL PK,
  medio_de_pago_id   BIGINT FK → medios_de_pago.id UNIQUE NOT NULL,
  agrupa_en_terminal BOOLEAN NOT NULL DEFAULT FALSE,
  grupo_terminal     VARCHAR(60),             -- ej. 'Clover/Payway'
  es_informativo     BOOLEAN NOT NULL DEFAULT FALSE,   -- aparece pero no suma
  updated_at         TIMESTAMP NOT NULL
)

arqueos (
  id BIGSERIAL PK,
  turno_id             BIGINT FK → turnos.id UNIQUE NOT NULL,
  usuario_id           BIGINT FK → usuarios.id NOT NULL,
  total_esperado       NUMERIC(10,2) NOT NULL,
  total_declarado      NUMERIC(10,2) NOT NULL,
  diferencia           NUMERIC(10,2) GENERATED ALWAYS AS (total_declarado - total_esperado) STORED,
  notificacion_enviada BOOLEAN NOT NULL DEFAULT FALSE,
  created_at           TIMESTAMP NOT NULL
)

arqueo_items (
  id BIGSERIAL PK,
  arqueo_id        BIGINT FK → arqueos.id NOT NULL,   -- índice
  medio_de_pago_id BIGINT FK → medios_de_pago.id,     -- NULL si es un grupo de terminal
  grupo_terminal   VARCHAR(60),
  monto_esperado   NUMERIC(10,2) NOT NULL,
  monto_declarado  NUMERIC(10,2) NOT NULL,
  diferencia       NUMERIC(10,2) GENERATED ALWAYS AS (monto_declarado - monto_esperado) STORED,
  es_informativo   BOOLEAN NOT NULL DEFAULT FALSE,
  CHECK ((medio_de_pago_id IS NULL) <> (grupo_terminal IS NULL))
)

notificaciones (
  id BIGSERIAL PK,
  usuario_id BIGINT FK → usuarios.id NOT NULL,   -- índice
  tipo       tipo_notificacion NOT NULL,
  titulo     VARCHAR(200) NOT NULL,
  cuerpo     TEXT NOT NULL,
  leida      BOOLEAN NOT NULL DEFAULT FALSE,
  metadata   JSONB,                              -- atributo `metadata_` en el modelo
  created_at TIMESTAMP NOT NULL
)
```

Seed de permisos (en la migración, protegido con `ON CONFLICT DO NOTHING`):
- `supervisor` → `caja` (recurso NULL) ver + crear: con `crear` general ya
  quedan habilitados `caja.arqueo` y `caja.retiro`.
- `vendedor` → `caja` ver + recurso `caja.arqueo` crear: abre, se suma y
  cierra el turno, pero no registra retiros.

---

## PARTE 2 — SERVICES

### `/app/services/turnos.py`
- `obtener_turno_activo()`: el turno abierto (de hoy o anterior) con usuarios,
  usuario de apertura y la marca `es_de_dia_anterior`. Única función que
  responde "cuál es la caja abierta".
- **`turno_para_operar()`**: devuelve el turno abierto **de hoy** o levanta 409:
  - turno abierto de un día anterior → "Hay un turno del dd/mm/aaaa sin
    cerrar. Cerrá el turno anterior antes de continuar." (**bloqueo duro**);
  - ningún turno abierto → "No hay un turno de caja abierto.".
  La llaman `confirmar_venta` y `anular_venta` (sesión 06) y `registrar_retiro`.
- `abrir_turno(usuario_id, efectivo_apertura, notas)`:
  1. bloqueo si hay turno abierto de un día anterior;
  2. si ya hay uno abierto hoy → 409 "Ya hay un turno abierto hoy. Usá 'Unirme
     al turno' para sumarte.";
  3. crea el turno y la fila en `turno_usuarios`; audita `turno.abierto`.
- `unirse_a_turno(usuario_id)`: inserta en `turno_usuarios` si no estaba; 409 si
  no hay turno abierto. Audita `turno.unirse`.
- `registrar_retiro(monto, motivo, usuario_id)`: sobre `turno_para_operar()`,
  monto > 0; audita `caja.retiro_efectivo`. (El permiso lo exige el endpoint
  con el recurso `caja.retiro`.)
- `listar_turnos(estado, desde, hasta, pagina, tamano)`.

### `/app/services/arqueo.py`
- `_movimientos_por_medio(turno)`: por medio de pago,
  **+** `venta_pagos.monto_total` de las ventas con `turno_id = turno`
  (confirmadas **o** anuladas después: el dinero entró en este turno) y
  **−** `venta_pagos.monto_total` de las ventas con `turno_anulacion_id = turno`
  (el dinero salió en este turno). Se arquea **por turno, no por franja
  horaria**.
- `calcular_esperado(turno_id)`: arma una línea por medio activo (o por grupo
  de terminal según `medios_pago_arqueo_config`) con esos importes. En la línea
  del medio `es_efectivo` (`medios_pago.medio_efectivo()`):
  **esperado = efectivo_apertura + cobros − anulaciones − retiros** (el cajón
  físico incluye el fondo inicial). Una línea puede quedar negativa (se muestra
  tal cual). `total_esperado` = suma de las líneas no informativas.
- `registrar_arqueo(turno_id, items_declarados, total_declarado, usuario_id)`:
  turno abierto y sin arqueo previo; recalcula el esperado en el backend
  (nunca confía en el del cliente); guarda arqueo + ítems; **cierra el turno**
  (estado, fecha y usuario de cierre); si la diferencia ≠ 0 crea una
  `notificacion` para cada usuario activo con rol **Admin** (título
  "Diferencia en arqueo — dd/mm/aaaa", cuerpo con fecha, diferencia, usuarios
  del turno y detalle por medio; metadata con turno_id, diferencia y usuarios)
  y marca `notificacion_enviada`. Todo en una transacción. Audita
  `caja.arqueo_cerrado`.
- Una venta que queda `en_curso` al cerrar el turno no bloquea el cierre: se
  confirmará (o no) en el turno siguiente.

---

## PARTE 3 — ENDPOINTS

### Turnos (`/api/v1/turnos`)
```
GET    /activo                    → TurnoResponse | null                  [CAJA ver]
POST   /abrir                     → {efectivo_apertura >= 0, notas} (201) [CAJA ver]
POST   /unirse                    → sin body                              [CAJA ver]
GET    ""                         → paginado (tamano 20); filtros estado, desde, hasta  [CAJA ver]
GET    /{id}                      → detalle                               [CAJA ver]
POST   /retiros                   → {monto > 0, motivo} sobre el turno para operar
                                                                          [CAJA crear + caja.retiro]
GET    /{id}/retiros                                                      [CAJA ver]
GET    /{id}/arqueo/esperado      → {turno_id, items[{medio_de_pago_id, medio_nombre,
                                    grupo_terminal, monto_esperado, es_informativo}],
                                    efectivo_apertura, total_esperado}
                                                                          [CAJA crear + caja.arqueo]
POST   /{id}/arqueo               → {items_declarados, total_declarado} → cierra el turno  [idem]
GET    /{id}/arqueo                                                       [CAJA ver]
```
`TurnoResponse`: id, estado, efectivo_apertura, fecha_apertura, fecha_cierre,
notas, es_de_dia_anterior, usuario_apertura_nombre, usuario_cierre_nombre,
usuarios [{id, nombre, ingreso}], diferencia_arqueo (null si no está cerrado).

### Notificaciones (`/api/v1/notificaciones`)
```
GET    ""                           → notificaciones del usuario logueado   [CAJA ver]
PATCH  /{id}/leer                                                          [CAJA ver]
PATCH  /leer-todas                  → 204                                  [CAJA ver]
```
(La campanita del header sigue deshabilitada: no hay panel de notificaciones.)

---

## PARTE 4 — FRONTEND (escritorio, responsive)

Sidebar: ítem "Caja" (`/caja`, módulo CAJA ver).

### `/caja` (`pages/caja/index.html` + `static/js/caja.js`)
Encabezado "Caja".

**Bloque "Turno del día"** (tarjeta):
- "Verificando turno…" mientras consulta `GET /turnos/activo`.
- Sin turno: botón **"Iniciar turno"** → modal "Iniciar el turno del día" con
  efectivo inicial (placeholder `$0`), notas y "Confirmar" ("Abriendo…").
- Con turno abierto hoy: "Turno iniciado" + fecha/hora, abierto por, efectivo
  inicial y usuarios del turno. Si el usuario logueado no está sumado, botón
  **"Unirme al turno"** ("Uniéndome…"). Botones **"Retiro de efectivo"** (si
  tiene `caja.retiro`: modal con monto y motivo) y **"Cerrar turno"** (si tiene
  `caja.arqueo`; → `/caja/cerrar/{turno_id}`).
- Con turno abierto de un día anterior: aviso en rojo con el mensaje de bloqueo
  y solo el botón "Cerrar turno".
- Debajo, la lista de retiros del turno (Hora, Monto, Motivo, Usuario).
- Los errores del backend se muestran tal cual (toast).

**Bloque "Turnos anteriores"**: tabla paginada con filtros de fecha: Apertura,
Cierre, Abierto por, Cerrado por, Diferencia (en rojo si ≠ 0), Estado; acción
"Ver arqueo" (modal con Medio | Esperado | Declarado | Diferencia y totales).

### Cerrar turno — `GET /caja/cerrar/{turno_id}` (`pages/caja/cerrar_turno.html`)
Layout estándar con volver a "Caja". Texto "Completá las novedades de caja
antes de cerrar el turno."; tabla con una línea por ítem de `arqueo/esperado`:
Medio | Esperado | Declarado (input) | Diferencia (se calcula al tipear); la
línea de efectivo aclara "incluye $X de fondo inicial"; los informativos
aparecen como "(informativo)" y deshabilitados. "Total declarado" y diferencia
total. Botón **"Cerrar turno"** ("Cerrando…") con `modal_confirmacion` →
`POST /turnos/{id}/arqueo` → vuelve a `/caja`.

**No construido en esta versión:** pantalla de configuración de arqueo por
medio (solo SQL/seed) y panel de notificaciones.

---

## TESTS (`test_turnos.py`, `test_arqueo.py`)
- Un solo turno abierto; abrir con uno de hoy → 409 (hay que sumarse).
- Turno de ayer abierto → `turno_para_operar` 409 con la fecha; sin turno →
  409 "No hay un turno de caja abierto.".
- `confirmar_venta` y `anular_venta` sin turno de hoy → 409.
- Esperado: efectivo = apertura + cobros − anulaciones − retiros; una venta
  del turno A anulada en el turno B resta en B y no cambia el arqueo de A.
- Arqueo con diferencia → notificación a cada Admin activo, en la misma
  transacción; `diferencia` es columna generada.

---

## CRITERIOS DE ACEPTACIÓN
- Un solo turno abierto a la vez; abrir con uno abierto hoy → hay que sumarse.
- Sin turno abierto de hoy no se confirman ni anulan ventas ni se registran
  retiros; un turno de un día anterior abierto bloquea todo hasta cerrarlo.
- Cualquier usuario con `caja.arqueo` puede cerrar el turno, siempre con arqueo.
- Los retiros requieren `caja.retiro` (Supervisor y Admin por defecto).
- El esperado sale de las ventas cobradas en el turno menos las anuladas en el
  turno, agrupado según la configuración; el efectivo suma el fondo inicial y
  resta los retiros. El medio efectivo se identifica por `es_efectivo`.
- `diferencia` es columna generada en `arqueos` y `arqueo_items`.
- Diferencia ≠ 0 → una notificación para cada Admin, en la misma transacción.
- No existen tablas ni endpoints de gift cards.
