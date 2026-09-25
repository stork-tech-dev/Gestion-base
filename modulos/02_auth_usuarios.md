# SESIÓN 02 — Autenticación y Usuarios
# [CLAUDE.md se carga automáticamente — no hace falta incluirlo]

## PREREQUISITOS
- Sesión 01 completada y funcionando
- Tablas `auditoria`, `configuracion_sistema` y `motivos_baja` ya existentes

## OBJETIVO DE ESTA SESIÓN
Implementar autenticación (JWT en cookies HttpOnly con sesión deslizante por
inactividad), gestión de roles y usuarios, y el sistema de permisos que es la
base de seguridad de todos los módulos siguientes.

---

## CONSTANTES DE DOMINIO — `/app/core/permisos.py`

Fuente de verdad de módulos, recursos, roles y etiquetas. Nunca escribir estos
literales fuera de este archivo.

```python
class Modulo(str, Enum):
    CLIENTES = "clientes"; PROVEEDORES = "proveedores"; PRODUCTOS = "productos"
    STOCK = "stock"; VENTAS = "ventas"; CAJA = "caja"
    CONFIGURACION = "configuracion"; USUARIOS = "usuarios"
    AUDITORIA = "auditoria"; IMPORTACION = "importacion"   # sesión 08
    REPORTES = "reportes"                                  # sesión 09

class Recurso(str, Enum):
    # Operaciones puntuales
    DOLAR_CAMBIO_MASIVO = "dolar.cambio_masivo"            # PROVEEDORES / editar
    CAJA_ARQUEO = "caja.arqueo"                            # CAJA / crear
    CAJA_RETIRO = "caja.retiro"                            # CAJA / crear
    VENTA_DESCUENTO = "venta.descuento"                    # VENTAS / crear
    VENTA_ANULAR = "venta.anular"                          # VENTAS / eliminar (sesión 06)
    STOCK_BAJA = "stock.baja"                              # STOCK / crear
    STOCK_AUDITORIA = "stock.auditoria"                    # STOCK / crear
    STOCK_MOTIVOS_BAJA = "stock.motivos_baja"              # STOCK / editar
    PROMOCIONES = "configuracion.promociones"              # CONFIGURACION / editar
```

Además:
- `ACCIONES = ("ver", "crear", "editar", "eliminar")`.
- Constantes de roles del sistema, **siempre referenciados por nombre**:
  `ROL_ADMIN="admin"`, `ROL_SUPERVISOR="supervisor"`, `ROL_VENDEDOR="vendedor"`,
  `ROLES_SISTEMA`. Son los únicos roles de sistema; los roles personalizados
  se crean desde `/roles`.
- `LABEL_MODULO` y `LABEL_RECURSO` (etiquetas legibles; la API y el árbol dicen lo mismo).
- `MODULO_DE_RECURSO` (a qué módulo cuelga cada recurso — define el árbol).
- `ACCIONES_DE_RECURSO` (qué acciones tienen sentido en cada recurso; el resto
  se muestra "—" y se guarda en FALSE). Ver comentarios del Enum arriba.
- `recursos_de_modulo(modulo)`.
- **Catálogo de "Accesos permitidos"** (vista plana de permisos para el
  formulario de usuario): `ACCESOS_DE_MODULO` =
  `(CONFIGURACION, ver, "Acceso a tablas y configuración")`,
  `(USUARIOS, crear, "Crear usuarios")`, `(AUDITORIA, ver, "Consultar la auditoría")`,
  `(IMPORTACION, crear, "Importar datos desde Excel")`, `(REPORTES, ver, "Consultar reportes")`,
  más un casillero por cada (recurso, acción) de `ACCIONES_DE_RECURSO`. Etiqueta
  con verbo ("Consultar/Registrar/Modificar: <label en minúscula>").
  Cada acceso tiene `clave = "<modulo>:<recurso|''>:<accion>"`.
  Funciones `catalogo_accesos()` y `acceso_por_clave(clave)`.

---

## MODELO DE DATOS (migración 0002)

```sql
roles (
  id          BIGSERIAL PK,
  nombre      VARCHAR(50) UNIQUE NOT NULL,
  descripcion VARCHAR(255),
  es_sistema  BOOLEAN DEFAULT FALSE NOT NULL,   -- los 3 del seed: no se borran ni renombran
  activo      BOOLEAN DEFAULT TRUE NOT NULL,
  created_at, updated_at TIMESTAMP NOT NULL DEFAULT now()
)

usuarios (
  id                   BIGSERIAL PK,
  username             VARCHAR(50) UNIQUE NOT NULL,
  email                VARCHAR(255) UNIQUE,              -- opcional
  password_hash        VARCHAR(255) NOT NULL,
  nombre               VARCHAR(150) NOT NULL,
  rol_id               BIGINT FK → roles.id ON DELETE RESTRICT NOT NULL,
  activo               BOOLEAN DEFAULT TRUE NOT NULL,
  fecha_nacimiento     DATE,
  celular              VARCHAR(20),                       -- normalizado a "+?dígitos" (6 a 19 dígitos)
  clave_especial_hash  VARCHAR(255),                      -- solo Admin; NUNCA en un schema de respuesta
  created_at, updated_at TIMESTAMP NOT NULL DEFAULT now(),
  ultimo_acceso        TIMESTAMP                          -- NULL = debe cambiar la contraseña
)
-- configuracion_sistema.updated_by pasa a ser FK → usuarios.id ON DELETE SET NULL

rol_permisos (
  id, rol_id BIGINT FK → roles.id ON DELETE CASCADE NOT NULL,
  modulo VARCHAR(50) NOT NULL, recurso VARCHAR(100),   -- recurso NULL = módulo completo
  puede_ver, puede_crear, puede_editar, puede_eliminar BOOLEAN DEFAULT FALSE NOT NULL,
  CONSTRAINT uq_rol_permisos_rol_modulo_recurso UNIQUE NULLS NOT DISTINCT (rol_id, modulo, recurso)
)

usuario_permisos (   -- overrides individuales, siempre aditivos (OR)
  mismas columnas con usuario_id FK → usuarios.id ON DELETE CASCADE,
  CONSTRAINT uq_usuario_permisos_usuario_modulo_recurso UNIQUE NULLS NOT DISTINCT (usuario_id, modulo, recurso)
)
-- NULLS NOT DISTINCT (PostgreSQL 15) es obligatorio: sin él, las filas con
-- recurso NULL se duplican y el ON CONFLICT del seed no hace nada.

historial_accesos (   -- append-only: triggers trg_historial_no_update / trg_historial_no_delete
  id, usuario_id BIGINT FK → usuarios.id ON DELETE CASCADE NOT NULL,
  timestamp TIMESTAMP NOT NULL DEFAULT now(),
  ip_origen VARCHAR(45),
  resultado ENUM resultado_acceso ('exitoso','fallido') NOT NULL,
  detalle   VARCHAR(255)            -- motivo del fallo
)

sesiones (   -- refresh tokens emitidos; se guarda solo el jti
  id, usuario_id FK → usuarios.id ON DELETE CASCADE,
  jti        VARCHAR(64) UNIQUE NOT NULL,
  creada_en  TIMESTAMP NOT NULL DEFAULT now(),
  expira_en  TIMESTAMP NOT NULL,     -- VENTANA DE INACTIVIDAD deslizante, no el vencimiento del JWT
  revocada   BOOLEAN DEFAULT FALSE NOT NULL,
  ip_origen  VARCHAR(45)
)
```

Los enums de SQLAlchemy usan `values_callable=lambda e: [i.value for i in e]`
para que en la base queden los valores en minúscula.

---

## BACKEND — SERVICES

### `/app/core/permisos.py`

**`resolver_permiso(db, usuario_id, modulo, accion, recurso=None) -> bool`** —
ÚNICA barrera de acceso del sistema:
1. Usuario inexistente o inactivo → False.
2. Rol `admin` → True siempre (se resuelve dentro de esta función).
3. Rol nulo o inactivo → False.
4. Busca en `usuario_permisos` y luego en `rol_permisos` filas del módulo con
   `recurso IS NULL` y, si se pidió un recurso, también la del recurso exacto,
   con `puede_<accion> = TRUE`. Resultado = OR de todo.
   El permiso general del módulo habilita cualquier recurso del módulo;
   tener un recurso puntual NO da acceso general.
5. Acción fuera de `ACCIONES` → `ValueError`.

**`get_current_user(request, db)`**: toma el JWT del header
`Authorization: Bearer` (prioridad), o de `request.state.access_renovado`
(dejado por el middleware), o de la cookie `access_token`. 401 si falta,
es inválido o el usuario está inactivo.

**`requiere_permiso(modulo, accion, recurso=None)`**: dependency que devuelve el
usuario o 403 `"Sin permiso para '<accion>' en '<destino>'"`.

**`requiere_admin`**: dependency para operaciones exclusivas (roles).

### `/app/services/auth.py`
- `hash_password` / `verificar_password`: bcrypt (passlib).
- JWT HS256 con claim `tipo` (`access`, `refresh`, `reset`); `verificar_token(token, tipo)`
  lanza `TokenInvalido`.
- `generar_tokens(db, usuario_id, ip)`: access (30 min) + refresh (7 días, con
  `jti`); crea la fila en `sesiones` con `expira_en = ahora + SESION_INACTIVIDAD_MINUTOS`.
- `registrar_actividad(db, sesion)`: corre la ventana a `ahora + 30 min`, con
  tope `creada_en + 7 días`, y escribe como mucho una vez por minuto.
- `sesion_vigente(db, refresh)`: valida firma, que la sesión exista, no esté
  revocada y no haya vencido por inactividad (si venció, la marca revocada).
- `refrescar_access_token(db, refresh)`: usa `sesion_vigente`, exige usuario
  activo, registra actividad y emite access nuevo.
- `revocar_sesion(db, refresh)` (idempotente) y `revocar_sesiones_de_usuario(db, id)`.
- `autenticar_usuario(db, username, password, ip)`: registra SIEMPRE el intento
  en `historial_accesos` y en `auditoria` (`auth.login` / `auth.login_fallido`, con
  detalle: "Usuario inexistente", "Contraseña incorrecta", "Usuario inactivo",
  "Rol inactivo"). Mensaje de error siempre genérico:
  "Usuario o contraseña incorrectos".
- `marcar_acceso(db, usuario)` sella `ultimo_acceso`;
  `debe_cambiar_password(usuario)` = `ultimo_acceso IS NULL`.
- `generar_token_reset(usuario)`: JWT de 30 minutos con claim `pwd` =
  últimos 16 caracteres del hash actual (single-use sin tabla).
  `validar_token_reset(db, token)`.
- `cambiar_password(db, usuario, nueva, autor_id, ip)`: cambia hash, revoca todas
  las sesiones y audita `usuario.cambiar_password` (sin la contraseña).

### `/app/core/email.py`
`smtp_configurado()`, `enviar_email(...)` (si no hay SMTP, loguea y devuelve
False), `enviar_reset_password(destinatario, nombre, token)` con link
`{APP_URL}/reset-password?token=...`.

### `/app/middleware/auth_refresh_middleware.py` — `AuthRefreshMiddleware`
En cada request (salvo `/api/v1/auth/login`, `/api/v1/auth/refresh`, `/static`,
`/docs`, `/redoc`, `/openapi.json`, `/favicon`, y salvo que venga un Bearer):
- Si hay cookie de refresh y el access venció → `refrescar_access_token`, deja el
  token nuevo en `request.state.access_renovado` y en la cookie de respuesta
  (salvo que el handler ya haya tocado la cookie, p.ej. logout).
- Si el access sigue vigente → registra actividad (corre la ventana).
- Si la sesión está caída (`TokenInvalido`) → borra las cookies.
- Nunca levanta excepción.

### `/app/services/roles.py`
- `listar_roles(nombre, activo, es_sistema)` con `cantidad_usuarios`.
- `crear_rol`: nombre obligatorio y único; crea `rol_permisos` vacíos (todo FALSE)
  para todos los módulos (`permisos.crear_permisos_vacios`).
- `editar_rol`: los de sistema no se renombran (solo descripción).
- `cambiar_estado_rol`: no desactivar con usuarios activos
  ("El rol tiene N usuario(s) activo(s): desactivarlos o reasignarlos…").
- `eliminar_rol`: solo no-sistema y sin usuarios asociados.
- Todo audita (`rol.crear`, `rol.editar`, `rol.activar`, `rol.desactivar`,
  `rol.eliminar`, `rol.permisos_actualizar`). Errores de regla → 409.

### `/app/services/usuarios.py`
- `validar_puede_gestionar(autor, rol_objetivo)`: Admin gestiona a
  todos; Supervisor solo a usuarios con rol `vendedor` (→ 403).
- `roles_asignables(autor)`: activos; nadie puede asignar `admin`;
  el Supervisor solo ve `vendedor`.
- `listar_usuarios(nombre, username, email, rol_id, activo, pagina, tamano)`
  con ILIKE, orden por nombre.
- `crear_usuario`: rol activo, único usuario `admin`, username único
  (normalizado a minúscula), email único. `ultimo_acceso` queda NULL (fuerza
  cambio de contraseña).
- `editar_usuario`: el username no se edita; no se puede asignar
  `admin` ni cambiarle el rol al Admin; si se manda
  `password` se resetea `ultimo_acceso` a NULL y se revocan sus sesiones.
  Los campos personales distinguen "no enviado" de "enviado en null"
  (`model_fields_set`).
- `cambiar_estado_usuario`: nadie se desactiva a sí mismo; no se desactiva al
  Admin; desactivar revoca sus sesiones.
- `historial_de_usuario(usuario_id, desde, hasta, resultado, pagina, tamano)`.
- Clave especial: `validar_clave_especial` / `resetear_clave_especial`; para
  usuarios que no son Admin → `NoEncontrado` (404).
- Todo audita (`usuario.crear`, `usuario.editar`, `usuario.activar` / `usuario.desactivar`,
  `usuario.permisos_actualizar`, `usuario.accesos_actualizar`, `usuario.clave_especial_resetear`).

### `/app/services/permisos.py`
- `arbol_de_rol(rol_id)`, `arbol_de_usuario(usuario)` — este último con, por
  nodo, `puede_*` (efectivo), `heredado_*` (del rol) y `override_*`.
  Las acciones que no aplican van en `null`.
- `actualizar_permisos_rol`, `actualizar_permisos_usuario` (valida módulo/recurso
  contra los Enums; acciones no aplicables se guardan FALSE).
- `accesos_de_rol(rol_id)`, `accesos_de_usuario(usuario)` → lista de
  `{clave, label, heredado, override, permitido}`.
- `actualizar_accesos_usuario(usuario, claves_marcadas)`: solo toca la acción de
  cada acceso del catálogo; lo heredado del rol no se persiste como override.
- `crear_permisos_vacios(rol)`.

---

## BACKEND — ENDPOINTS

### Autenticación (`/api/v1/auth`)
```
POST /login            → {username, password} → TokenResponse
                          {access_token, refresh_token, expires_in,
                           usuario: {id, username, nombre, rol, debe_cambiar_password}}
                          Setea cookies HttpOnly SameSite=lax (access 30 min, refresh 7 días).
                          Solo sella ultimo_acceso si no debe cambiar contraseña.
POST /refresh          → refresh del body o de la cookie → nuevo access (cookie)
POST /logout           → revoca el refresh, audita auth.logout, borra cookies

POST /forgot-password  → {username}: respuesta siempre genérica; envía email solo
                          si existe, está activo y tiene email. Audita auth.reset_solicitar
POST /reset-password   → {token, password_nueva}: 400 si el token es inválido o ya usado
POST /cambiar-password → {password_actual, password_nueva}: cambio obligatorio del
                          primer ingreso; re-emite tokens
GET  /me               → usuario autenticado
```
(No existe página HTML `/reset-password`: el link del email apunta ahí pero el
reseteo se aplica por la API.)

### Roles (`/api/v1/roles`, solo Admin)
```
GET    /roles?nombre=&activo=&es_sistema=   → listado con cantidad_usuarios
POST   /roles                               → crear (201)
PUT    /roles/{id}                          → editar
PATCH  /roles/{id}/estado                   → activar/desactivar
DELETE /roles/{id}                          → eliminar (no-sistema, sin usuarios)
GET    /roles/{id}/permisos                 → árbol del rol
PUT    /roles/{id}/permisos                 → guardar árbol
```

### Usuarios (`/api/v1/usuarios`)
```
GET    /usuarios                         → paginado; filtros nombre, username, email,
                                            rol_id, activo                          [USUARIOS ver]
GET    /usuarios/roles-asignables                                                 [USUARIOS ver]
GET    /usuarios/accesos?rol_id=         → accesos que otorga un rol (alta)       [USUARIOS ver]
GET    /usuarios/{id}/accesos            → accesos efectivos                      [USUARIOS ver]
PUT    /usuarios/{id}/accesos            → {accesos: [claves]}                    [USUARIOS editar]
GET    /usuarios/{id}                                                             [USUARIOS ver]
POST   /usuarios                         → alta (201)                             [USUARIOS crear]
PUT    /usuarios/{id}                    → edición                                [USUARIOS editar]
PATCH  /usuarios/{id}/estado             → {activo}                               [USUARIOS editar]
GET    /usuarios/{id}/permisos           → árbol efectivo (heredado/override)     [USUARIOS ver]
PUT    /usuarios/{id}/permisos           → overrides                              [USUARIOS editar]
GET    /usuarios/{id}/historial?desde=&hasta=&resultado=                          [USUARIOS ver]
POST   /usuarios/{id}/clave-especial/validar   → {clave} → {valida}               [USUARIOS ver]
PATCH  /usuarios/{id}/clave-especial/resetear  → {clave_nueva}                    [USUARIOS editar]
```
Las rutas fijas (`roles-asignables`, `accesos`) se declaran
ANTES de `/{usuario_id}`. Toda gestión sobre un usuario pasa por
`validar_puede_gestionar`.

`UsuarioResponse`: id, username, email, nombre, rol_id, rol, activo,
fecha_nacimiento, celular, created_at, updated_at, ultimo_acceso.
Sin hashes. Alta: username 3-50, nombre 1-150, password 8-128, email opcional
(`EmailStr`).

### Seed (se agrega a `seed.sql`)
- Roles del sistema (`es_sistema = TRUE`): `admin`, `supervisor`, `vendedor`.
- Usuario `admin` / `Admin1234!` (bcrypt cost 12), rol `admin`,
  `ultimo_acceso NULL` (obliga cambio en el primer login).
- `rol_permisos` generales (recurso NULL) — ver/crear/editar/eliminar:

| Rol | Módulos |
|---|---|
| admin | todos con V/C/E/E; auditoria y reportes solo ver (en la práctica `resolver_permiso` le da todo) |
| supervisor | clientes VCE; proveedores V; productos V; stock V; ventas VCE; caja VC (sesión 07); usuarios VCE; reportes V (sesión 09) |
| vendedor | clientes VC; productos V; stock V; ventas VC; caja V (sesión 07) |

La importación (sesión 08) queda solo para el Admin (o un rol personalizado).

- `rol_permisos` por recurso:
  supervisor → `venta.descuento` crear, `venta.anular` eliminar (sesión 06),
  `stock.baja` crear, `stock.auditoria` crear,
  `configuracion.promociones` ver/crear/editar (sesión 06);
  vendedor → `venta.descuento` crear, `stock.baja` crear, `stock.auditoria` crear,
  `caja.arqueo` crear (sesión 07: puede cerrar el turno, pero no hacer retiros).
- Todo con `ON CONFLICT (rol_id, modulo, recurso) DO NOTHING` y protegido con
  `to_regclass`.

---

## FRONTEND

### Rutas HTML (`app/api/pages.py`)
- `usuario_de_pagina` (como `get_current_user` pero devuelve None) y
  `requiere_sesion`: sin sesión → 303 a `/login`; con cambio de contraseña
  pendiente → 303 a `/cambiar-password`. Todas las páginas lo usan.
- Sidebar filtrado con `resolver_permiso` (`menu_visible`), con la misma regla
  `_visible()` para ítems y tarjetas de hubs: `oculto`, `solo_admin`,
  `hub_configuracion`, `modulo`, `recurso`.
- `GET /login`, `GET /cambiar-password`, `GET /usuarios`,
  `GET /usuarios/{id}/permisos`, `GET /usuarios/{id}/historial`, `GET /roles`,
  `GET /roles/{id}/permisos`.

### Login (`auth/base_auth.html` + `auth/login.html`)
- Layout propio de autenticación con la marca del sistema (`marca()`) y la misma config de
  Tailwind. Campos con el macro `components/campo_auth.html`.
- Formulario usuario + contraseña, botón "Iniciar Sesión", spinner, toast de error.
- "¿Olvidé mi contraseña?" despliega un segundo formulario (usuario) que llama a
  `POST /auth/forgot-password` y muestra el mensaje genérico.
- Tras el login: si `debe_cambiar_password` → `/cambiar-password`, si no → `/`.
- Si ya hay sesión, `/login` redirige a `/`.

### Cambiar contraseña (`auth/cambiar_password.html`)
"Cambiá tu contraseña": actual + nueva + confirmación → `POST /auth/cambiar-password` → `/`.

### Usuarios (`/usuarios`, dentro del hub Configuraciones)
- Encabezado "Usuarios" con volver a "Configuraciones" y botón "+ Crear nuevo".
- Filtros en tiempo real: Nombre (texto, debounce 400 ms), Rol (select)
  + contador "N registros encontrados" + switch "solo activos" (`switch_activos`).
- Tabla en tarjeta: Usuario (con "Inactivo" en rojo si aplica), Nombre, Rol,
  Celular, Cumpleaños (dd/mm), Último acceso; acciones Ver / Editar /
  Desactivar (papelera) o Activar. Filas sin alternado, línea separadora y
  sombra al hover; inactivos con opacidad. Paginación de 10.
- Modal de detalle con links a "Permisos" y "Historial de accesos".
- Modal de alta/edición: Nombre*, Usuario*, Rol* (roles asignables; al cambiarlo
  recarga los accesos heredados), Fecha de Nacimiento, Celular
  (placeholder "+3512108190"), Mail, Contraseña (* solo en alta).
  Sección **"Accesos permitidos:"**: lista plana de casilleros
  del catálogo; lo heredado del rol aparece marcado y bloqueado; lo marcado
  extra se guarda con `PUT /usuarios/{id}/accesos` después del alta/edición.
  Botón "Crear" (alta) / "Finalizar" (edición). El modal solo se cierra con la X.
- Confirmación antes de desactivar/activar.

### Roles (`/roles`, solo Admin, dentro del hub Configuraciones)
Filtros: nombre, "Tipo (todos) / Del sistema / Personalizados", estado; botón
"Limpiar filtros". Tabla: Nombre, Descripción, Usuarios, Estado, acciones.
Roles de sistema: nombre no editable y sin eliminar. Confirmación antes de
desactivar, con advertencia si tiene usuarios.

### Árbol de permisos (`components/permisos_tree.html` + `static/js/permisos.js`)
Macro `arbol_permisos(url_datos, url_guardar, modo='rol'|'usuario')`, usado en
`/roles/{id}/permisos` y `/usuarios/{id}/permisos`:
- Tabla Módulo | Ver | Crear | Editar | Eliminar; cada módulo expandible con sus
  recursos; las acciones que no aplican muestran "—".
- Marcar el permiso general de un módulo marca sus recursos como sugerencia
  (siguen editables).
- Modo usuario: lo heredado del rol en gris y bloqueado; los overrides en azul;
  solo se agregan, nunca se quitan.
- "Expandir todo" / "Colapsar todo", aviso "Hay cambios sin guardar".
- Botón "Guardar permisos" con diálogo de confirmación del sistema
  (`modal_confirmacion`, no `confirm()` del navegador). Sin autoguardado.

### Historial de accesos (`/usuarios/{id}/historial`)
Tabla Fecha y hora, IP, Resultado (Exitoso verde / Fallido rojo), Detalle.
Filtros: rango de fechas y resultado (Todos/Exitoso/Fallido). Paginado.

### Sesión
- Aviso "Tu sesión está por vencer" 2 minutos antes (ver sesión 01).
- Menú del badge de usuario: "Cambiar contraseña" y "Cerrar sesión"
  (`POST /auth/logout` → `/login`).

---

## CRITERIOS DE ACEPTACIÓN

- Login por username; todo intento queda en `historial_accesos` y `auditoria`.
- Primer ingreso de `admin` obliga a cambiar la contraseña.
- Token expirado con refresh vivo → el middleware lo renueva sin que el usuario
  lo note; 30 minutos sin actividad → la sesión cae (401) y el frontend va al login.
- Logout revoca el refresh: no se puede volver a renovar con él.
- `resolver_permiso()` es la única validación de acceso; un recurso puntual no
  da acceso general, y el general sí habilita sus recursos.
- Supervisor gestionando un usuario no-vendedor → 403.
- No se puede crear un segundo `admin` ni asignarle ese rol a nadie.
- Roles de sistema: no se renombran ni eliminan; no se desactiva un rol con
  usuarios activos.
- `clave_especial_hash` y `password_hash` fuera de todos los schemas de respuesta.
- El UNIQUE de permisos rechaza duplicados con recurso NULL.
- Recuperación de contraseña: solo envía si el usuario tiene email; el token es
  de un solo uso.
