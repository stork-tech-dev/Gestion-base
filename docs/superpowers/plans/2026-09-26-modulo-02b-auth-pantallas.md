# Módulo 02-B — Pantallas de autenticación, usuarios, roles y permisos: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Las pantallas HTML del módulo 02 sobre la API del plan 02-A: login, cambio obligatorio de contraseña, recuperación de contraseña, sesión obligatoria en todas las páginas, sidebar y hub de Configuraciones filtrados por permisos, ABM de usuarios con "Accesos permitidos", ABM de roles, árbol de permisos (rol y usuario) e historial de accesos.

**Architecture:** Las páginas (FastAPI + Jinja2) solo arman el layout y el contexto; los datos se cargan desde la API con componentes Alpine (`static/js/<pantalla>.js`) que usan `pedir()`. Sesión por cookies HttpOnly (nunca se leen tokens en JS). Una dependency de páginas redirige a `/login` o `/cambiar-password`; la visibilidad de ítems y tarjetas usa `resolver_permiso` (misma barrera que la API). Las pantallas solo ofrecen lo que el autor puede otorgar (flag `otorgable` que agrega la API).

**Tech Stack:** FastAPI, Jinja2, Alpine.js 3.14.8, Tailwind CDN, macros de `templates/components/`, pytest (render de páginas) y `node --check` para el JS.

**Spec:** `modulos/02_auth_usuarios.md` (sección FRONTEND) + `CLAUDE.md` (Design System, Principios 1, 2, 5, 6) + `docs/pendientes.md` ("Para el módulo 02-B").

## Global Constraints

- Código, textos de pantalla y comentarios en español (voseo: "Elegí", "Ingresá").
- **Git:** rama local `modulo-02-auth-usuarios`. UN commit por tarea: `feat(pantallas): …` (o `fix(pantallas): …` en correcciones) + línea en blanco + `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. NUNCA push, amend, reset, rebase ni merge.
- Tests en el contenedor: `docker compose exec backend pytest …`; suite completa antes de cada commit. Todo JS nuevo o modificado pasa `node --check <archivo>` en el host.
- Nunca leer, guardar ni loguear en JavaScript `access_token`/`refresh_token`: la sesión son las cookies HttpOnly.
- Cambios de estado solo por la API (POST/PUT/PATCH/DELETE vía `pedir`). Ninguna página HTML cambia estado por GET.
- `requiere_permiso`/`resolver_permiso` siguen siendo la única barrera. Las plantillas solo ocultan lo que no se puede hacer.
- Reusar SIEMPRE los macros existentes de `templates/components/` (`encabezado`, `barra_filtros`, `tabla`, `paginacion`, `modal`, `campo`, `combobox`, `switch_activos`, `accion`, `acciones`, `hub`, `icono`, `marca`, `contenedor_toasts`) y los globales de `app.js` (`pedir`, `toast`, `confirmar`, `normalizarTexto`, `pesos`). Nada de `confirm()`/`alert()` del navegador.
- Mobile-first, sin scroll horizontal de página (las tablas scrollean dentro de su tarjeta), toque ≥ 44px.
- Filtros de tablas chicas (usuarios, roles, historial): en tiempo real (debounce 400 ms en texto); siempre "Limpiar filtros" y contador de registros. Paginación de a 10.
- Los modales solo se cierran con la X.

## Desvíos deliberados respecto del spec

1. No se crea `components/campo_auth.html`: las pantallas de autenticación usan el macro `campo` existente (Principio 2).
2. Se agrega la página `/reset-password` (el spec decía que no existía, pero el mail de recuperación apunta ahí), con `Referrer-Policy: no-referrer`.
3. El `<head>` común se extrae a `components/_head.html` (lo usan `base.html` y `auth/base_auth.html`).
4. La API agrega el flag `otorgable` a accesos y al árbol del usuario (y a los accesos de un rol en el alta) para que las pantallas solo ofrezcan lo que el autor puede conceder (requisito de seguridad del 02-A).
5. Árbol de permisos: al desmarcar el permiso general de un módulo se desmarcan también sus recursos, y al guardar no se mandan como filas propias los recursos que ya cubre el general (evita filas "pegadas" que después no se pueden quitar).

---

## File Structure

```
backend/app/services/permisos.py          (mod) puede_otorgar + flag otorgable
backend/app/schemas/permisos.py           (mod) otorgable en NodoPermiso y AccesoResponse
backend/app/api/v1/usuarios.py            (mod) pasa el autor a accesos/árbol
backend/app/api/pages.py                  (rewrite) sesión de páginas, visibilidad, rutas del módulo
backend/main.py                           (mod) registrar manejadores de páginas
backend/app/templates/components/_head.html            (new) head común
backend/app/templates/base.html                        (mod) usa _head, rol del usuario
backend/app/templates/auth/base_auth.html              (new)
backend/app/templates/auth/login.html, cambiar_password.html, reset_password.html (new)
backend/app/templates/pages/sin_permiso.html           (new)
backend/app/templates/pages/configuracion/index.html   (new)
backend/app/templates/pages/usuarios/listado.html, _modal_detalle.html, _modal_form.html, permisos.html, historial.html (new)
backend/app/templates/pages/roles/listado.html, _modal_form.html, permisos.html (new)
backend/app/templates/components/permisos_tree.html    (new) macro arbol_permisos
backend/app/static/js/app.js              (mod) escaparHtml, estadoHtml, fecha, fechaHora, diaMes, erroresDeCampos
backend/app/static/js/auth.js, usuarios.js, roles.js, permisos.js, historial.js (new)
backend/tests/conftest.py                 (mod) fixture iniciar_sesion
backend/tests/test_pages.py               (mod) páginas con sesión
backend/tests/test_paginas_sesion.py, test_paginas_auth.py, test_paginas_usuarios.py, test_paginas_roles.py, test_paginas_permisos.py (new)
backend/tests/test_permisos_service.py, test_usuarios_api.py (mod) otorgable
```

---

### Task 1: API — flag `otorgable` en accesos y árbol del usuario

**Files:**
- Modify: `backend/app/services/permisos.py`, `backend/app/schemas/permisos.py`, `backend/app/api/v1/usuarios.py`
- Test: `backend/tests/test_permisos_service.py`, `backend/tests/test_usuarios_api.py`

**Interfaces:**
- Consumes (existentes): `MODULOS_RESERVADOS_AL_ADMIN`, `_validar_otorgables(db, autor, nuevas)`, `_nodo(...)`, `_arbol(...)`, `accesos_de_rol(db, rol)`, `accesos_de_usuario(db, usuario)`, `arbol_de_usuario(db, usuario)`, `resolver_permiso` (import local, ver comentario existente).
- Produces: `puede_otorgar(db, autor, modulo: Modulo, recurso: Recurso | None, accion: str) -> bool` (autor `None` o admin → True; módulo reservado → False; si no, `resolver_permiso` del autor). Firmas nuevas: `accesos_de_rol(db, rol, autor=None)`, `accesos_de_usuario(db, usuario, autor=None)`, `arbol_de_usuario(db, usuario, autor=None)`. Cada acceso incluye `"otorgable": bool`; cada nodo del árbol de usuario incluye `otorgable_<accion>` (bool en las acciones que aplican cuando hay autor; ausente/None si no). `AccesoResponse.otorgable: bool = True`; `NodoPermiso.otorgable_ver|crear|editar|eliminar: bool | None = None`.

- [ ] **Step 1: Tests que fallan**

Agregar a `backend/tests/test_permisos_service.py`:
```python
def test_otorgable_segun_el_autor(db, crear_usuario):
    supervisor = crear_usuario("supervisor")
    vendedor = crear_usuario("vendedor")
    admin = crear_usuario("admin")
    accesos = {a["clave"]: a for a in permisos.accesos_de_usuario(db, vendedor, autor=supervisor)}
    assert accesos["auditoria::ver"]["otorgable"] is False          # reservado al Admin
    assert accesos["usuarios::crear"]["otorgable"] is False         # reservado al Admin
    assert accesos["stock:stock.baja:crear"]["otorgable"] is True   # el supervisor lo tiene
    assert accesos["caja:caja.retiro:crear"]["otorgable"] is True   # caja crear general del supervisor
    assert accesos["proveedores:dolar.cambio_masivo:editar"]["otorgable"] is False  # proveedores solo ver
    assert all(a["otorgable"] for a in permisos.accesos_de_usuario(db, vendedor, autor=admin))
    assert all(a["otorgable"] for a in permisos.accesos_de_usuario(db, vendedor))


def test_otorgable_en_el_arbol_y_en_los_accesos_del_rol(db, crear_usuario):
    supervisor = crear_usuario("supervisor")
    vendedor = crear_usuario("vendedor")
    arbol = permisos.arbol_de_usuario(db, vendedor, autor=supervisor)
    assert _nodo(arbol, "usuarios")["otorgable_ver"] is False
    assert _nodo(arbol, "stock", "stock.baja")["otorgable_crear"] is True
    assert _nodo(arbol, "proveedores")["otorgable_editar"] is False
    assert _nodo(arbol, "stock", "stock.baja").get("otorgable_ver") is None  # "ver" no aplica
    assert "otorgable_ver" not in _nodo(permisos.arbol_de_usuario(db, vendedor), "stock")
    rol_vendedor = vendedor.rol
    accesos_rol = {a["clave"]: a for a in permisos.accesos_de_rol(db, rol_vendedor, autor=supervisor)}
    assert accesos_rol["auditoria::ver"]["otorgable"] is False
```

Agregar a `backend/tests/test_usuarios_api.py`:
```python
def test_accesos_informan_lo_otorgable_para_el_autor(client, crear_usuario, headers_de):
    h = headers_de(crear_usuario("supervisor"))
    vendedor = crear_usuario("vendedor")
    accesos = {a["clave"]: a for a in client.get(f"{URL}/{vendedor.id}/accesos", headers=h).json()}
    assert accesos["auditoria::ver"]["otorgable"] is False
    assert accesos["stock:stock.baja:crear"]["otorgable"] is True
    arbol = client.get(f"{URL}/{vendedor.id}/permisos", headers=h).json()
    usuarios_nodo = next(n for n in arbol["modulos"] if n["modulo"] == "usuarios")
    assert usuarios_nodo["otorgable_ver"] is False
```

- [ ] **Step 2: Correr y ver que falla** — `docker compose exec backend pytest tests/test_permisos_service.py tests/test_usuarios_api.py -v` → FAIL (`TypeError: ... unexpected keyword argument 'autor'`).

- [ ] **Step 3: Implementación**

En `backend/app/services/permisos.py`:

1. Después de `MODULOS_RESERVADOS_AL_ADMIN`, agregar la función pública y hacer que `_validar_otorgables` la use (mismos mensajes que hoy):
```python
def puede_otorgar(db, autor, modulo: Modulo, recurso: Recurso | None, accion: str) -> bool:
    """¿El autor puede conceder esta acción como permiso propio de otro usuario?
    Misma regla que _validar_otorgables (la usan las pantallas para ofrecer solo
    lo otorgable): el Admin todo; el resto, nunca módulos reservados al Admin y
    solo lo que él mismo tiene."""
    if autor is None or autor.es_admin:
        return True
    if modulo in MODULOS_RESERVADOS_AL_ADMIN:
        return False
    # Import local: core.seguridad importa services.auth (ciclo de imports).
    from app.core.seguridad import resolver_permiso

    return resolver_permiso(db, autor.id, modulo, accion, recurso)
```
y dentro de `_validar_otorgables`, reemplazar el cuerpo del `for` por:
```python
    for modulo, recurso, accion in nuevas:
        if modulo in MODULOS_RESERVADOS_AL_ADMIN:
            raise SinPermiso(f"Solo el Admin puede otorgar permisos de {LABEL_MODULO[modulo]}")
        if not puede_otorgar(db, autor, modulo, recurso, accion):
            destino = f"{modulo.value}/{recurso.value}" if recurso else modulo.value
            raise SinPermiso(f"No podés otorgar un permiso que no tenés: {accion} en {destino}")
```
(borrar el import local de `resolver_permiso` que queda sin uso dentro de `_validar_otorgables`).

2. `_nodo` y `_arbol` reciben un parámetro opcional `otorgable=None` (callable `(modulo, recurso, accion) -> bool`). En `_nodo`, en la rama de usuario (cuando `filas_usuario is not None`), después de calcular `override`:
```python
        if otorgable is not None:
            nodo[f"otorgable_{accion}"] = otorgable(modulo, recurso, accion)
```
`_arbol` pasa `otorgable` a cada `_nodo`. `arbol_de_usuario(db, usuario, autor=None)`:
```python
def arbol_de_usuario(db, usuario, autor=None) -> dict:
    es_admin = usuario.es_admin
    bloqueado = not es_admin and not usuario.rol.activo
    otorgable = None if autor is None else (lambda m, r, a: puede_otorgar(db, autor, m, r, a))
    return _arbol(_filas_de_rol(db, usuario.rol_id), _filas_de_usuario(db, usuario.id), es_admin, bloqueado, otorgable)
```

3. `accesos_de_rol(db, rol, autor=None)` y `accesos_de_usuario(db, usuario, autor=None)`: agregar a cada dict `"otorgable": puede_otorgar(db, autor, acceso.modulo, acceso.recurso, acceso.accion)`.

En `backend/app/schemas/permisos.py`: en `NodoPermiso`, agregar `otorgable_ver`, `otorgable_crear`, `otorgable_editar`, `otorgable_eliminar` (`bool | None = None`, con un comentario "solo en el árbol de un usuario pedido por un autor: si puede concederlo"); en `AccesoResponse`, `otorgable: bool = True`.

En `backend/app/api/v1/usuarios.py`: en `accesos_de_rol`, `accesos`, `guardar_accesos`, `ver_permisos` y `guardar_permisos`, usar el usuario que devuelve la dependency (renombrar `_` a `autor` donde haga falta) y pasarlo: `permisos.accesos_de_rol(db, rol, autor=autor)`, `permisos.accesos_de_usuario(db, usuario, autor=autor)`, `permisos.arbol_de_usuario(db, usuario, autor=autor)`.

- [ ] **Step 4: Correr y ver que pasa** — los dos archivos de test, luego la suite completa.

- [ ] **Step 5: Commit** — `feat(pantallas): la API informa qué permisos puede otorgar cada autor`.

---

### Task 2: Sesión en las páginas, sidebar/hub por permisos y utilidades de JS

**Files:**
- Rewrite: `backend/app/api/pages.py`
- Create: `backend/app/templates/components/_head.html`, `backend/app/templates/pages/sin_permiso.html`, `backend/app/templates/pages/configuracion/index.html`
- Modify: `backend/app/templates/base.html`, `backend/main.py`, `backend/app/static/js/app.js`, `backend/tests/conftest.py`, `backend/tests/test_pages.py`
- Test: `backend/tests/test_paginas_sesion.py`

**Interfaces:**
- Consumes: `token_de_request`, `usuario_de_token`, `resolver_permiso`, `TokenInvalido`, `templates`, services de roles/usuarios, `Modulo`.
- Produces (`app.api.pages`): `router`; `Redireccion(url)` y `PaginaSinPermiso(contexto)` (excepciones); `registrar_manejadores_paginas(app)`; `usuario_de_pagina(request, db) -> Usuario | None`; `requiere_sesion` (dependency → `Usuario`, redirige 303 a `/login` o `/cambiar-password`); `requiere_pagina(item: dict)` (dependency → `Usuario` o página 403); `SECCION_USUARIOS`, `SECCION_ROLES`, `CONFIGURACION_SECCIONES`, `MENU_SIDEBAR`, `MENU_SIDEBAR_PIE`; `_visible(item, usuario, db)`; `menu_visible(items, usuario, db)`; `contexto_base(request, db, actual, usuario, **extra)` (claves: `request, menu, menu_pie, actual, usuario_actual, es_admin, inactividad_minutos` + extra). Ítem: `nombre, url, icono` y opcionales `oculto`, `solo_admin`, `hub_configuracion`, `modulo` (Modulo), `accion` (default "ver"), `recurso`, `descripcion`, `title`.
- Produces (`app.js`): `escaparHtml(texto)`, `estadoHtml(texto, variante)` (variantes `exito|peligro|neutro|primario`, mismas clases que `estado_texto` de `badge.html`), `fecha(iso)` → "dd/mm/aaaa", `fechaHora(iso)` → "dd/mm/aaaa hh:mm", `diaMes(iso)` → "dd/mm", `erroresDeCampos(error)` → `{campo: mensaje}` desde un 422.
- Produces (conftest): fixture `iniciar_sesion(usuario) -> TestClient` (setea las cookies de una sesión nueva en `client`).

- [ ] **Step 1: Fixture y tests que fallan**

En `backend/tests/conftest.py` agregar:
```python
@pytest.fixture
def iniciar_sesion(client, db):
    """Deja al `client` con las cookies de una sesión nueva del usuario."""
    from app.services.auth import generar_tokens

    def _iniciar(usuario):
        access, refresh, _ = generar_tokens(db, usuario, "127.0.0.1")
        client.cookies.set("access_token", access)
        client.cookies.set("refresh_token", refresh)
        return client

    return _iniciar
```

`backend/tests/test_paginas_sesion.py`:
```python
def test_sin_sesion_redirige_al_login(client):
    for url in ("/", "/configuracion", "/ajustes"):
        r = client.get(url, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/login"


def test_con_cambio_pendiente_redirige_a_cambiar_password(crear_usuario, iniciar_sesion):
    cliente = iniciar_sesion(crear_usuario("vendedor", debe_cambiar=True))
    r = cliente.get("/", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/cambiar-password"


def test_sidebar_filtrado_por_permisos(crear_usuario, iniciar_sesion):
    html = iniciar_sesion(crear_usuario("admin", nombre="Ana Admin")).get("/").text
    assert "Bienvenido, Ana" in html and ">Configuraciones<" in html
    assert "Ana Admin" in html and ">admin<" in html  # nombre en el sidebar y rol en el menú del badge


def test_vendedor_no_ve_configuraciones(crear_usuario, iniciar_sesion):
    html = iniciar_sesion(crear_usuario("vendedor")).get("/").text
    assert ">Configuraciones<" not in html


def test_hub_de_configuraciones_segun_permisos(crear_usuario, iniciar_sesion, client):
    html = iniciar_sesion(crear_usuario("supervisor")).get("/configuracion").text
    assert 'href="/usuarios"' in html and 'href="/roles"' not in html
    client.cookies.clear()
    html = iniciar_sesion(crear_usuario("admin")).get("/configuracion").text
    assert 'href="/usuarios"' in html and 'href="/roles"' in html


def test_hub_vacio_para_quien_no_ve_ninguna_tarjeta(crear_usuario, iniciar_sesion):
    html = iniciar_sesion(crear_usuario("vendedor")).get("/configuracion").text
    assert "No tenés secciones disponibles." in html
```

Reemplazar `backend/tests/test_pages.py` por:
```python
def test_inicio_renderiza_layout_y_saludo(crear_usuario, iniciar_sesion):
    html = iniciar_sesion(crear_usuario("admin", nombre="Ana")).get("/").text
    assert "Bienvenido, Ana" in html
    assert 'id="contenido"' in html
    assert 'aria-label="Menú principal"' in html
    assert ">Inicio<" in html and 'aria-current="page"' in html
    assert "Ajustes" in html
    assert "Auditoría" not in html
    assert "cdn.tailwindcss.com" in html
    assert "/static/js/app.js?v=" in html and "/static/css/custom.css?v=" in html
    assert 'x-data="toasts()"' in html
    assert "dialogoConfirmacion()" in html
    assert "buscador-global" in html
    assert "text-welcome" in html
    assert "avisoSesion(" in html  # aviso de sesión por vencer con usuario logueado


def test_ajustes_usa_la_pagina_pendiente(crear_usuario, iniciar_sesion):
    r = iniciar_sesion(crear_usuario("vendedor")).get("/ajustes")
    assert r.status_code == 200
    assert "Este módulo todavía no está disponible." in r.text


def test_la_api_tiene_prioridad_sobre_las_paginas(client):
    assert client.get("/api/v1/health").json() == {"status": "ok"}


def test_static_se_sirve(client):
    assert client.get("/static/js/app.js").status_code == 200
    assert client.get("/static/css/custom.css").status_code == 200
```

- [ ] **Step 2: Correr y ver que falla** — `docker compose exec backend pytest tests/test_paginas_sesion.py tests/test_pages.py -v` → FAIL (sin redirección, sin "Configuraciones").

- [ ] **Step 3: `pages.py`**

`backend/app/api/pages.py` (reemplazo completo):
```python
"""Rutas HTML (Jinja2). Fuera del esquema OpenAPI.

Toda página exige sesión (salvo login y recuperación de contraseña). La
visibilidad de ítems del sidebar, tarjetas de hubs y páginas usa la MISMA
barrera que la API (resolver_permiso). Las páginas solo arman el layout y el
contexto; los datos se cargan desde la API con Alpine.
"""
from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.permisos import Modulo
from app.core.seguridad import resolver_permiso, token_de_request, usuario_de_token
from app.core.templates import templates
from app.models import Usuario
from app.services.auth import TokenInvalido
from config import settings

router = APIRouter(include_in_schema=False)

# Tarjetas del hub Configuraciones (cada sesión agrega la suya).
SECCION_USUARIOS = {
    "nombre": "Usuarios", "descripcion": "Altas, permisos e historial de accesos",
    "url": "/usuarios", "modulo": Modulo.USUARIOS,
}
SECCION_ROLES = {
    "nombre": "Roles", "descripcion": "Perfiles de permisos y su alcance por módulo",
    "url": "/roles", "solo_admin": True,
}
CONFIGURACION_SECCIONES: list[dict] = [SECCION_USUARIOS, SECCION_ROLES]

# Sidebar: nombre, url, icono y, opcionalmente, oculto / solo_admin /
# hub_configuracion / modulo (+ accion, recurso). Cada módulo suma su ítem
# ANTES de "Configuraciones".
MENU_SIDEBAR: list[dict] = [
    {"nombre": "Inicio", "url": "/", "icono": "inicio"},
    {"nombre": "Configuraciones", "url": "/configuracion", "icono": "configuracion", "hub_configuracion": True},
    # Sin pantalla HTML de auditoría: el ítem existe pero está oculto.
    {"nombre": "Auditoría", "url": "/auditoria", "icono": "auditoria", "oculto": True},
]
MENU_SIDEBAR_PIE: list[dict] = [
    {"nombre": "Ajustes", "url": "/ajustes", "icono": "ajustes"},
]


class Redireccion(Exception):
    """Corta la página y redirige (303)."""

    def __init__(self, url: str):
        self.url = url


class PaginaSinPermiso(Exception):
    """Página 403. Lleva el contexto ya armado (la sesión de DB puede estar cerrada al renderizar)."""

    def __init__(self, contexto: dict):
        self.contexto = contexto


def registrar_manejadores_paginas(app: FastAPI) -> None:
    async def _redirigir(_request: Request, exc: Redireccion):
        return RedirectResponse(exc.url, status_code=303)

    async def _sin_permiso(request: Request, exc: PaginaSinPermiso):
        return templates.TemplateResponse(request, "pages/sin_permiso.html", exc.contexto, status_code=403)

    app.add_exception_handler(Redireccion, _redirigir)
    app.add_exception_handler(PaginaSinPermiso, _sin_permiso)


def usuario_de_pagina(request: Request, db: Session) -> Usuario | None:
    try:
        return usuario_de_token(db, token_de_request(request))
    except TokenInvalido:
        return None


def requiere_sesion(request: Request, db: Session = Depends(get_db)) -> Usuario:
    usuario = usuario_de_pagina(request, db)
    if usuario is None:
        raise Redireccion("/login")
    if usuario.debe_cambiar_password:
        raise Redireccion("/cambiar-password")
    return usuario


def _visible(item: dict, usuario: Usuario, db: Session) -> bool:
    """Regla única de visibilidad para ítems del sidebar, tarjetas y páginas."""
    if item.get("oculto"):
        return False
    if item.get("solo_admin") and not usuario.es_admin:
        return False
    if item.get("hub_configuracion"):
        return any(_visible(seccion, usuario, db) for seccion in CONFIGURACION_SECCIONES)
    if item.get("modulo") is not None:
        return resolver_permiso(db, usuario.id, item["modulo"], item.get("accion", "ver"), item.get("recurso"))
    return True


def menu_visible(items: list[dict], usuario: Usuario, db: Session) -> list[dict]:
    return [item for item in items if _visible(item, usuario, db)]


def contexto_base(request: Request, db: Session, actual: str, usuario: Usuario, **extra) -> dict:
    """Contexto común de todas las páginas con sesión."""
    return {
        "request": request,
        "menu": menu_visible(MENU_SIDEBAR, usuario, db),
        "menu_pie": menu_visible(MENU_SIDEBAR_PIE, usuario, db),
        "actual": actual,
        "usuario_actual": usuario,
        "es_admin": usuario.es_admin,
        "inactividad_minutos": settings.SESION_INACTIVIDAD_MINUTOS,
        **extra,
    }


def requiere_pagina(item: dict, actual: str = "/configuracion"):
    """Dependency: sesión + visibilidad del ítem; si no, página 403."""

    def dependencia(request: Request, db: Session = Depends(get_db),
                    usuario: Usuario = Depends(requiere_sesion)) -> Usuario:
        if not _visible(item, usuario, db):
            raise PaginaSinPermiso(contexto_base(request, db, actual, usuario))
        return usuario

    return dependencia


def _pagina(request: Request, plantilla: str, contexto: dict):
    return templates.TemplateResponse(request, plantilla, contexto)


@router.get("/")
def inicio(request: Request, db: Session = Depends(get_db), usuario: Usuario = Depends(requiere_sesion)):
    return _pagina(request, "pages/index.html", contexto_base(request, db, "/", usuario))


@router.get("/ajustes")
def ajustes(request: Request, db: Session = Depends(get_db), usuario: Usuario = Depends(requiere_sesion)):
    return _pagina(request, "pages/pendiente.html", contexto_base(request, db, "/ajustes", usuario, titulo="Ajustes"))


@router.get("/configuracion")
def configuracion(request: Request, db: Session = Depends(get_db), usuario: Usuario = Depends(requiere_sesion)):
    secciones = menu_visible(CONFIGURACION_SECCIONES, usuario, db)
    return _pagina(request, "pages/configuracion/index.html",
                   contexto_base(request, db, "/configuracion", usuario, secciones=secciones))
```
(Las rutas de login, usuarios, roles, permisos e historial se agregan en las tareas siguientes, en este mismo archivo.)

En `backend/main.py`: `from app.api.pages import registrar_manejadores_paginas` y llamarla junto a `registrar_manejadores(app)`.

- [ ] **Step 4: Plantillas**

`backend/app/templates/components/_head.html`:
```jinja
{# Head común (lo incluyen base.html y auth/base_auth.html). El <title> lo pone cada layout. #}
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
{# Tema antes de pintar: evita el parpadeo claro→oscuro. #}
<script>
  try {
    if (localStorage.theme === 'dark' || (!('theme' in localStorage) && matchMedia('(prefers-color-scheme: dark)').matches)) {
      document.documentElement.classList.add('dark');
    }
  } catch (e) {}
</script>
{% include "components/_favicon.html" %}
<script src="https://cdn.tailwindcss.com"></script>
{% include "components/_tailwind_config.html" %}
<link rel="stylesheet" href="{{ estatico('/css/custom.css') }}">
<script src="https://unpkg.com/htmx.org@2.0.4/dist/htmx.min.js"></script>
<script src="{{ estatico('/js/app.js') }}" defer></script>
<script src="https://unpkg.com/alpinejs@3.14.8/dist/cdn.min.js" defer></script>
```

En `backend/app/templates/base.html`: reemplazar todo el contenido de `<head>` (meta charset, viewport, title, script de tema, favicon, tailwind, config, css, htmx, app.js, alpine y el bloque head_extra) por:
```jinja
<head>
  <title>{% block titulo %}{{ APP_NAME }}{% endblock %}</title>
  {% include "components/_head.html" %}
  {% block head_extra %}{% endblock %}
</head>
```
y en el menú del badge cambiar `{{ usuario_actual.rol_nombre|default('') }}` por `{{ usuario_actual.rol.nombre }}`. Nada más cambia en `base.html`.

`backend/app/templates/pages/sin_permiso.html`:
```jinja
{% extends "base.html" %}
{% from "components/encabezado.html" import encabezado %}
{% block titulo %}Sin permiso · {{ APP_NAME }}{% endblock %}
{% block contenido %}
{{ encabezado("Sin permiso") }}
<div class="tarjeta flex flex-col items-start gap-4">
  <p class="text-texto">No tenés permiso para ver esta pantalla. Si lo necesitás, pedíselo a un administrador.</p>
  <a href="/" class="boton boton-secundario">Ir al inicio</a>
</div>
{% endblock %}
```

`backend/app/templates/pages/configuracion/index.html`:
```jinja
{% extends "base.html" %}
{% from "components/encabezado.html" import encabezado %}
{% from "components/hub.html" import hub %}
{% block titulo %}Configuraciones · {{ APP_NAME }}{% endblock %}
{% block contenido %}
{{ encabezado("Configuraciones") }}
{{ hub(secciones) }}
{% endblock %}
```

- [ ] **Step 5: Utilidades en `app.js`**

Agregar a `backend/app/static/js/app.js`, dentro del IIFE, después de la sección "Texto y categorías":
```js
  // ---------- HTML seguro y estados ----------
  const ENTIDADES_HTML = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
  window.escaparHtml = (texto) => String(texto ?? '').replace(/[&<>"']/g, (c) => ENTIDADES_HTML[c]);

  // Mismas clases que estado_texto() de components/badge.html (celdas x-html de tablas).
  const CLASES_ESTADO = { exito: 'text-success', peligro: 'text-danger', primario: 'text-primary', neutro: 'text-texto-muted' };
  window.estadoHtml = (texto, variante = 'neutro') =>
    `<span class="text-sm font-semibold ${CLASES_ESTADO[variante] || CLASES_ESTADO.neutro}">${window.escaparHtml(texto)}</span>`;

  // ---------- Fechas (la API manda hora del negocio sin zona: no convertir) ----------
  function partesFecha(iso) {
    const m = /^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2}))?/.exec(String(iso ?? ''));
    return m ? { a: m[1], mes: m[2], d: m[3], h: m[4], min: m[5] } : null;
  }
  window.fecha = (iso) => { const p = partesFecha(iso); return p ? `${p.d}/${p.mes}/${p.a}` : ''; };
  window.diaMes = (iso) => { const p = partesFecha(iso); return p ? `${p.d}/${p.mes}` : ''; };
  window.fechaHora = (iso) => {
    const p = partesFecha(iso);
    if (!p) return '';
    return p.h ? `${p.d}/${p.mes}/${p.a} ${p.h}:${p.min}` : `${p.d}/${p.mes}/${p.a}`;
  };

  // ---------- Errores de validación (422) por campo ----------
  window.erroresDeCampos = function (error) {
    const detalle = error && error.status === 422 && error.datos && error.datos.detail;
    if (!Array.isArray(detalle)) return {};
    const errores = {};
    for (const item of detalle) {
      const campo = Array.isArray(item.loc) ? item.loc[item.loc.length - 1] : null;
      if (campo && !errores[campo]) errores[campo] = item.msg;
    }
    return errores;
  };
```

- [ ] **Step 6: Correr y ver que pasa**

`docker compose exec backend pytest tests/test_paginas_sesion.py tests/test_pages.py -v`, `node --check backend/app/static/js/app.js`, suite completa.

- [ ] **Step 7: Commit** — `feat(pantallas): sesión obligatoria en páginas y menú por permisos`.

---

### Task 3: Login, cambio de contraseña y recuperación

**Files:**
- Create: `backend/app/templates/auth/base_auth.html`, `auth/login.html`, `auth/cambiar_password.html`, `auth/reset_password.html`, `backend/app/static/js/auth.js`
- Modify: `backend/app/api/pages.py` (rutas `/login`, `/cambiar-password`, `/reset-password`)
- Test: `backend/tests/test_paginas_auth.py`

**Interfaces:**
- Consumes: `usuario_de_pagina`, `templates`, macros `campo`, `marca`, `contenedor_toasts`; `pedir`, `toast`, `cerrarSesion` de app.js; API `/api/v1/auth/login|forgot-password|cambiar-password|reset-password`.
- Produces: rutas `GET /login` (con sesión → 303 `/`), `GET /cambiar-password` (sin sesión → 303 `/login`; contexto `obligatorio`), `GET /reset-password?token=` (header `Referrer-Policy: no-referrer`); componentes Alpine `login()`, `cambiarPassword()`, `resetPassword(token)`.

- [ ] **Step 1: Tests que fallan**

`backend/tests/test_paginas_auth.py`:
```python
def test_login_sin_sesion(client):
    r = client.get("/login")
    assert r.status_code == 200
    assert 'x-data="login()"' in r.text and "Iniciar Sesión" in r.text and "¿Olvidé mi contraseña?" in r.text
    assert "/static/js/auth.js?v=" in r.text


def test_login_con_sesion_va_al_inicio(crear_usuario, iniciar_sesion):
    r = iniciar_sesion(crear_usuario("vendedor")).get("/login", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/"


def test_cambiar_password(client, crear_usuario, iniciar_sesion):
    assert client.get("/cambiar-password", follow_redirects=False).headers["location"] == "/login"
    html = iniciar_sesion(crear_usuario("vendedor", debe_cambiar=True)).get("/cambiar-password").text
    assert 'x-data="cambiarPassword()"' in html and "elegí una propia" in html


def test_cambiar_password_voluntario(crear_usuario, iniciar_sesion):
    html = iniciar_sesion(crear_usuario("vendedor")).get("/cambiar-password").text
    assert 'x-data="cambiarPassword()"' in html and "elegí una propia" not in html


def test_reset_password(client):
    r = client.get("/reset-password", params={"token": "abc.def"})
    assert r.status_code == 200 and r.headers["referrer-policy"] == "no-referrer"
    assert "resetPassword(&#34;abc.def&#34;)" in r.text
    r = client.get("/reset-password")
    assert "El enlace no es válido" in r.text
```

- [ ] **Step 2: Correr y ver que falla** — `docker compose exec backend pytest tests/test_paginas_auth.py -v` → FAIL (404).

- [ ] **Step 3: Rutas** (agregar a `backend/app/api/pages.py`)

```python
@router.get("/login")
def login(request: Request, db: Session = Depends(get_db)):
    if usuario_de_pagina(request, db) is not None:
        return RedirectResponse("/", status_code=303)
    return _pagina(request, "auth/login.html", {"request": request})


@router.get("/cambiar-password")
def cambiar_password(request: Request, db: Session = Depends(get_db)):
    usuario = usuario_de_pagina(request, db)
    if usuario is None:
        return RedirectResponse("/login", status_code=303)
    return _pagina(request, "auth/cambiar_password.html",
                   {"request": request, "obligatorio": usuario.debe_cambiar_password})


@router.get("/reset-password")
def reset_password(request: Request, token: str = ""):
    respuesta = _pagina(request, "auth/reset_password.html", {"request": request, "token": token})
    # El token viaja en la URL: que no se filtre a los CDN por el Referer.
    respuesta.headers["Referrer-Policy"] = "no-referrer"
    return respuesta
```

- [ ] **Step 4: Plantillas**

`backend/app/templates/auth/base_auth.html`:
```jinja
{% from "components/marca.html" import marca %}
{% from "components/toast.html" import contenedor_toasts %}
<!doctype html>
<html lang="es">
<head>
  <title>{% block titulo %}{{ APP_NAME }}{% endblock %}</title>
  {% include "components/_head.html" %}
  {% block head_extra %}{% endblock %}
</head>
<body class="flex min-h-screen items-center justify-center bg-bg p-4 font-sans text-texto antialiased"
      x-data="temaApp()" x-effect="document.documentElement.classList.toggle('dark', oscuro)">
  <main class="tarjeta w-full max-w-md p-6 sm:p-8">
    <div class="mb-6 flex justify-center">{{ marca("max-h-16 w-auto text-center") }}</div>
    {% block contenido %}{% endblock %}
  </main>
  {{ contenedor_toasts() }}
  {% block scripts %}{% endblock %}
</body>
</html>
```

`backend/app/templates/auth/login.html`:
```jinja
{% extends "auth/base_auth.html" %}
{% from "components/form_field.html" import campo %}
{% block titulo %}Iniciar sesión · {{ APP_NAME }}{% endblock %}
{% block contenido %}
<div x-data="login()">
  <form x-show="!olvide" @submit.prevent="ingresar()" class="flex flex-col gap-4" novalidate>
    <h1 class="text-2xl font-bold text-texto-header">Iniciar sesión</h1>
    {{ campo("username", "Usuario", modelo="username", requerido=True, atributos='autocomplete="username" autofocus') }}
    {{ campo("password", "Contraseña", tipo="password", modelo="password", requerido=True, atributos='autocomplete="current-password"') }}
    <button type="submit" class="boton boton-primario w-full" :disabled="enviando">
      <span x-text="enviando ? 'Ingresando…' : 'Iniciar Sesión'">Iniciar Sesión</span>
    </button>
    <button type="button" class="min-h-toque self-center text-sm text-primary hover:underline" @click="olvide = true">¿Olvidé mi contraseña?</button>
  </form>

  <form x-show="olvide" x-cloak @submit.prevent="recuperar()" class="flex flex-col gap-4" novalidate>
    <h1 class="text-2xl font-bold text-texto-header">Recuperar contraseña</h1>
    <p class="text-sm text-texto-muted">Ingresá tu usuario. Si tiene un email cargado, te mandamos un enlace para elegir una contraseña nueva.</p>
    {{ campo("usuario_recuperar", "Usuario", modelo="usernameRecuperar", requerido=True, atributos='autocomplete="username"') }}
    <button type="submit" class="boton boton-primario w-full" :disabled="enviando">
      <span x-text="enviando ? 'Enviando…' : 'Enviar instrucciones'">Enviar instrucciones</span>
    </button>
    <p class="rounded-input bg-success/10 p-3 text-sm text-success" x-show="mensaje" x-text="mensaje"></p>
    <button type="button" class="min-h-toque self-center text-sm text-primary hover:underline" @click="olvide = false; mensaje = ''">Volver al ingreso</button>
  </form>
</div>
{% endblock %}
{% block scripts %}<script src="{{ estatico('/js/auth.js') }}"></script>{% endblock %}
```

`backend/app/templates/auth/cambiar_password.html`:
```jinja
{% extends "auth/base_auth.html" %}
{% from "components/form_field.html" import campo %}
{% block titulo %}Cambiar contraseña · {{ APP_NAME }}{% endblock %}
{% block contenido %}
<form x-data="cambiarPassword()" @submit.prevent="guardar()" class="flex flex-col gap-4" novalidate>
  <h1 class="text-2xl font-bold text-texto-header">Cambiá tu contraseña</h1>
  {% if obligatorio %}
  <p class="text-sm text-texto-muted">Es tu primer ingreso o te asignaron una contraseña nueva: elegí una propia para continuar.</p>
  {% endif %}
  {{ campo("actual", "Contraseña actual", tipo="password", modelo="actual", requerido=True, atributos='autocomplete="current-password"') }}
  {{ campo("nueva", "Contraseña nueva", tipo="password", modelo="nueva", requerido=True, error="errores.password_nueva", ayuda="Mínimo 8 caracteres.", atributos='autocomplete="new-password"') }}
  {{ campo("confirmacion", "Repetí la contraseña nueva", tipo="password", modelo="confirmacion", requerido=True, atributos='autocomplete="new-password"') }}
  <button type="submit" class="boton boton-primario w-full" :disabled="enviando">
    <span x-text="enviando ? 'Guardando…' : 'Cambiar contraseña'">Cambiar contraseña</span>
  </button>
  {% if obligatorio %}
  <button type="button" class="min-h-toque self-center text-sm text-primary hover:underline" @click="cerrarSesion()">Cerrar sesión</button>
  {% else %}
  <a href="/" class="min-h-toque self-center text-sm text-primary hover:underline">Volver</a>
  {% endif %}
</form>
{% endblock %}
{% block scripts %}<script src="{{ estatico('/js/auth.js') }}"></script>{% endblock %}
```

`backend/app/templates/auth/reset_password.html`:
```jinja
{% extends "auth/base_auth.html" %}
{% from "components/form_field.html" import campo %}
{% block titulo %}Nueva contraseña · {{ APP_NAME }}{% endblock %}
{% block head_extra %}<meta name="referrer" content="no-referrer">{% endblock %}
{% block contenido %}
{% if token %}
<div x-data="resetPassword({{ token|js }})">
  <form x-show="!listo" @submit.prevent="guardar()" class="flex flex-col gap-4" novalidate>
    <h1 class="text-2xl font-bold text-texto-header">Elegí una contraseña nueva</h1>
    {{ campo("nueva", "Contraseña nueva", tipo="password", modelo="nueva", requerido=True, error="errores.password_nueva", ayuda="Mínimo 8 caracteres.", atributos='autocomplete="new-password"') }}
    {{ campo("confirmacion", "Repetí la contraseña nueva", tipo="password", modelo="confirmacion", requerido=True, atributos='autocomplete="new-password"') }}
    <button type="submit" class="boton boton-primario w-full" :disabled="enviando">
      <span x-text="enviando ? 'Guardando…' : 'Guardar contraseña'">Guardar contraseña</span>
    </button>
  </form>
  <div x-show="listo" x-cloak class="flex flex-col gap-4">
    <p class="text-texto">Listo: tu contraseña quedó actualizada.</p>
    <a href="/login" class="boton boton-primario w-full">Ingresar</a>
  </div>
</div>
{% else %}
<div class="flex flex-col gap-4">
  <p class="text-texto">El enlace no es válido. Pedí uno nuevo desde "¿Olvidé mi contraseña?".</p>
  <a href="/login" class="boton boton-secundario w-full">Ir al ingreso</a>
</div>
{% endif %}
{% endblock %}
{% block scripts %}<script src="{{ estatico('/js/auth.js') }}"></script>{% endblock %}
```

- [ ] **Step 5: `static/js/auth.js`**

```js
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
```

- [ ] **Step 6: Correr y ver que pasa** — `docker compose exec backend pytest tests/test_paginas_auth.py -v`, `node --check backend/app/static/js/auth.js`, suite completa. Prueba manual rápida por curl: `curl -s -o /dev/null -w "%{http_code}\n" localhost:8000/login` → 200.

- [ ] **Step 7: Commit** — `feat(pantallas): login, cambio y recuperación de contraseña`.

---

### Task 4: Pantalla de usuarios

**Files:**
- Create: `backend/app/templates/pages/usuarios/listado.html`, `_modal_detalle.html`, `_modal_form.html`, `backend/app/static/js/usuarios.js`
- Modify: `backend/app/api/pages.py` (ruta `/usuarios`)
- Test: `backend/tests/test_paginas_usuarios.py`

**Interfaces:**
- Consumes: `requiere_pagina(SECCION_USUARIOS)`, `contexto_base`, `resolver_permiso`, `services.roles.listar_roles`, `services.usuarios.roles_asignables`; API `/api/v1/usuarios` (listado, roles-asignables, accesos, alta, edición, estado); macros y globales de JS.
- Produces: ruta `GET /usuarios` (contexto extra: `roles_filtro: [{id, nombre}]`, `roles_gestionables: list[str] | None` (None = todos, para el Admin), `puede_crear`, `puede_editar`); componente `usuariosListado({esAdmin, usuarioActualId, rolesGestionables, rolesFiltro, puedeEditar})`.

- [ ] **Step 1: Tests que fallan**

`backend/tests/test_paginas_usuarios.py`:
```python
def test_admin_ve_la_pantalla_de_usuarios(crear_usuario, iniciar_sesion):
    r = iniciar_sesion(crear_usuario("admin")).get("/usuarios")
    assert r.status_code == 200
    html = r.text
    assert "usuariosListado(" in html and "/static/js/usuarios.js?v=" in html
    assert "Crear nuevo" in html
    assert 'href="/configuracion"' in html  # volver a Configuraciones
    assert "Accesos permitidos:" in html
    assert "&#34;supervisor&#34;" in html  # roles del filtro (todos, para el Admin)


def test_supervisor_ve_solo_vendedores_como_gestionables(crear_usuario, iniciar_sesion):
    html = iniciar_sesion(crear_usuario("supervisor")).get("/usuarios").text
    assert "rolesGestionables: [&#34;vendedor&#34;]" in html


def test_vendedor_no_entra_a_usuarios(crear_usuario, iniciar_sesion):
    r = iniciar_sesion(crear_usuario("vendedor")).get("/usuarios")
    assert r.status_code == 403 and "No tenés permiso" in r.text
```

- [ ] **Step 2: Correr y ver que falla** — FAIL (404).

- [ ] **Step 3: Ruta** (agregar a `pages.py`; importar `from app.services import roles as servicio_roles, usuarios as servicio_usuarios`)

```python
@router.get("/usuarios")
def usuarios(request: Request, db: Session = Depends(get_db),
             usuario: Usuario = Depends(requiere_pagina(SECCION_USUARIOS))):
    if usuario.es_admin:
        roles_filtro = [{"id": r.id, "nombre": r.nombre} for r, _ in servicio_roles.listar_roles(db)]
        roles_gestionables = None  # el Admin gestiona a todos
    else:
        roles_filtro = [{"id": r.id, "nombre": r.nombre} for r in servicio_usuarios.roles_asignables(db, usuario)]
        roles_gestionables = [r["nombre"] for r in roles_filtro]  # misma regla que validar_puede_gestionar
    return _pagina(request, "pages/usuarios/listado.html", contexto_base(
        request, db, "/configuracion", usuario,
        roles_filtro=roles_filtro,
        roles_gestionables=roles_gestionables,
        puede_crear=resolver_permiso(db, usuario.id, Modulo.USUARIOS, "crear"),
        puede_editar=resolver_permiso(db, usuario.id, Modulo.USUARIOS, "editar"),
    ))
```

- [ ] **Step 4: Plantillas**

`backend/app/templates/pages/usuarios/listado.html`:
```jinja
{% extends "base.html" %}
{% from "components/encabezado.html" import encabezado %}
{% from "components/table.html" import barra_filtros, tabla %}
{% from "components/paginacion.html" import paginacion %}
{% from "components/switch_activos.html" import switch_activos %}
{% from "components/combobox.html" import combobox %}
{% from "components/botones.html" import accion, acciones %}
{% from "components/icons.html" import icono %}
{% block titulo %}Usuarios · {{ APP_NAME }}{% endblock %}
{% block contenido %}
<div x-data="usuariosListado({ esAdmin: {{ es_admin|js }}, usuarioActualId: {{ usuario_actual.id|js }}, rolesGestionables: {{ roles_gestionables|js }}, rolesFiltro: {{ roles_filtro|js }}, puedeEditar: {{ puede_editar|js }} })">
  {% call encabezado("Usuarios", "/configuracion", "Configuraciones") %}
    {% if puede_crear %}
    <button type="button" class="boton boton-acento" @click="nuevo()">{{ icono("mas", "w-4 h-4") }}<span>Crear nuevo</span></button>
    {% endif %}
  {% endcall %}

  {% call barra_filtros(extras=switch_activos("soloActivos", "pagina = 1; cargar()")) %}
    <input type="search" class="campo" placeholder="Nombre" aria-label="Filtrar por nombre" x-model="filtros.nombre" @input="filtrar()">
    {{ combobox("filtro-rol", "rolesFiltro", "filtros.rol_id", texto="nombre", vacio="Rol (todos)", al_cambiar="pagina = 1; cargar()") }}
  {% endcall %}

  {% set columnas = [
    {"titulo": "Usuario", "expr": "celdaUsuario(fila)", "html": True},
    {"titulo": "Nombre", "expr": "fila.nombre"},
    {"titulo": "Rol", "expr": "fila.rol"},
    {"titulo": "Celular", "expr": "fila.celular || '—'"},
    {"titulo": "Cumpleaños", "expr": "fila.fecha_nacimiento ? diaMes(fila.fecha_nacimiento) : '—'"},
    {"titulo": "Último acceso", "expr": "fila.ultimo_acceso ? fechaHora(fila.ultimo_acceso) : 'Nunca'"},
  ] %}
  {% call tabla(columnas, cargando="cargando") %}
    {% call acciones() %}
      {{ accion("ver", atributos='@click="ver(fila)"') }}
      {{ accion("editar", atributos='x-show="puedeGestionar(fila)" @click="editar(fila)"') }}
      {{ accion("borrar", texto="Desactivar", atributos='x-show="puedeGestionar(fila) && fila.activo" @click="cambiarEstado(fila, false)"') }}
      {{ accion("activar", atributos='x-show="puedeGestionar(fila) && !fila.activo" @click="cambiarEstado(fila, true)"') }}
    {% endcall %}
  {% endcall %}
  {{ paginacion() }}

  {% include "pages/usuarios/_modal_detalle.html" %}
  {% include "pages/usuarios/_modal_form.html" %}
</div>
{% endblock %}
{% block scripts %}<script src="{{ estatico('/js/usuarios.js') }}"></script>{% endblock %}
```

`backend/app/templates/pages/usuarios/_modal_detalle.html`:
```jinja
{% from "components/modal.html" import modal %}
{% call modal("Usuario", "modal-usuario-detalle", abierto="verAbierto", titulo_expr="detalle ? detalle.nombre : ''") %}
<template x-if="detalle">
  <div>
    <dl class="grid grid-cols-1 gap-4 sm:grid-cols-2">
      <div><dt class="text-sm text-texto-muted">Usuario</dt><dd class="text-texto" x-text="detalle.username"></dd></div>
      <div><dt class="text-sm text-texto-muted">Rol</dt><dd class="text-texto" x-text="detalle.rol"></dd></div>
      <div><dt class="text-sm text-texto-muted">Mail</dt><dd class="text-texto" x-text="detalle.email || '—'"></dd></div>
      <div><dt class="text-sm text-texto-muted">Celular</dt><dd class="text-texto" x-text="detalle.celular || '—'"></dd></div>
      <div><dt class="text-sm text-texto-muted">Cumpleaños</dt><dd class="text-texto" x-text="detalle.fecha_nacimiento ? diaMes(detalle.fecha_nacimiento) : '—'"></dd></div>
      <div><dt class="text-sm text-texto-muted">Estado</dt><dd x-html="detalle.activo ? estadoHtml('Activo', 'exito') : estadoHtml('Inactivo', 'peligro')"></dd></div>
      <div><dt class="text-sm text-texto-muted">Último acceso</dt><dd class="text-texto" x-text="detalle.ultimo_acceso ? fechaHora(detalle.ultimo_acceso) : 'Nunca'"></dd></div>
      <div><dt class="text-sm text-texto-muted">Alta</dt><dd class="text-texto" x-text="fecha(detalle.created_at)"></dd></div>
    </dl>
    <div class="mt-6 flex flex-wrap gap-2">
      <a class="boton boton-secundario" :href="`/usuarios/${detalle.id}/permisos`">Permisos</a>
      <a class="boton boton-secundario" :href="`/usuarios/${detalle.id}/historial`">Historial de accesos</a>
    </div>
  </div>
</template>
{% endcall %}
```

`backend/app/templates/pages/usuarios/_modal_form.html`:
```jinja
{% from "components/modal.html" import modal %}
{% from "components/form_field.html" import campo %}
{% from "components/combobox.html" import combobox %}
{% call modal("Usuario", "modal-usuario-form", abierto="formAbierto", titulo_expr="form.id ? 'Editar usuario' : 'Nuevo usuario'") %}
<form @submit.prevent="guardar()" class="flex flex-col gap-6" novalidate>
  <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
    {{ campo("u-nombre", "Nombre", modelo="form.nombre", requerido=True, error="errores.nombre") }}
    {{ campo("u-username", "Usuario", modelo="form.username", requerido=True, error="errores.username", atributos=':disabled="form.id !== null" autocomplete="off"') }}
    <div class="flex flex-col gap-1">
      {{ combobox("u-rol", "rolesAsignables", "form.rol_id", texto="nombre", etiqueta="Rol *", vacio="Elegí un rol", placeholder="Buscar rol…", al_cambiar="alCambiarRol()") }}
      <p class="text-sm text-danger" x-show="errores.rol_id" x-text="errores.rol_id" x-cloak></p>
    </div>
    {{ campo("u-nacimiento", "Fecha de nacimiento", tipo="date", modelo="form.fecha_nacimiento", error="errores.fecha_nacimiento") }}
    {{ campo("u-celular", "Celular", tipo="tel", modelo="form.celular", placeholder="+3512108190", error="errores.celular") }}
    {{ campo("u-email", "Mail", tipo="email", modelo="form.email", error="errores.email") }}
    {{ campo("u-password", "Contraseña", tipo="password", modelo="form.password", error="errores.password", ayuda="Mínimo 8 caracteres. Al editar, dejala vacía para no cambiarla. El usuario la cambia en su primer ingreso.", atributos='autocomplete="new-password"') }}
  </div>

  <fieldset class="flex flex-col gap-2">
    <legend class="text-lg font-medium text-texto">Accesos permitidos:</legend>
    <p class="text-sm text-texto-muted" x-show="!accesos.length">Elegí un rol para ver sus accesos.</p>
    <p class="text-sm text-texto-muted" x-show="accesos.length">Los marcados en gris vienen del rol. Los que no podés otorgar aparecen deshabilitados.</p>
    <ul class="grid grid-cols-1 gap-1 sm:grid-cols-2">
      <template x-for="a in accesos" :key="a.clave">
        <li>
          <label class="inline-flex min-h-toque items-center gap-2"
                 :class="bloqueado(a) ? 'cursor-not-allowed text-texto-disabled' : 'cursor-pointer text-texto'">
            <input type="checkbox" class="acceso-check" :checked="marcado(a)" :disabled="bloqueado(a)" @change="alternarAcceso(a)">
            <span x-text="a.label"></span>
            <span class="text-xs text-texto-muted" x-show="a.heredado">(del rol)</span>
          </label>
        </li>
      </template>
    </ul>
  </fieldset>

  <div class="flex justify-end">
    <button type="submit" class="boton boton-primario" :disabled="guardando"
            x-text="guardando ? 'Guardando…' : (form.id ? 'Finalizar' : 'Crear')"></button>
  </div>
</form>
{% endcall %}
```

- [ ] **Step 5: `static/js/usuarios.js`**

```js
/* Pantalla de usuarios: listado con filtros, detalle, alta/edición con
   "Accesos permitidos" y activar/desactivar. Todos los datos salen de la API. */
(function () {
  'use strict';

  const API = '/api/v1/usuarios';
  const formVacio = () => ({
    id: null, username: '', nombre: '', rol_id: null, email: '', fecha_nacimiento: '', celular: '', password: '',
  });

  window.usuariosListado = function ({ esAdmin, usuarioActualId, rolesGestionables, rolesFiltro, puedeEditar }) {
    return {
      rolesFiltro,
      filtros: { nombre: '', rol_id: null },
      soloActivos: true,
      pagina: 1,
      tamano: 10,
      total: 0,
      filas: [],
      cargando: false,
      rolesAsignables: [],
      detalle: null,
      verAbierto: false,
      formAbierto: false,
      form: formVacio(),
      rolOriginal: null,
      errores: {},
      guardando: false,
      accesos: [],
      marcados: [],
      _espera: null,

      async init() {
        this.cargar();
        try {
          this.rolesAsignables = await window.pedir(`${API}/roles-asignables`);
        } catch (e) {
          window.toast(e.message, 'error');
        }
      },

      filtrar() {
        clearTimeout(this._espera);
        this._espera = setTimeout(() => { this.pagina = 1; this.cargar(); }, 400);
      },

      limpiarFiltros() {
        this.filtros = { nombre: '', rol_id: null };
        this.soloActivos = true;
        this.pagina = 1;
        this.cargar();
      },

      async cargar() {
        this.cargando = true;
        const params = new URLSearchParams({ pagina: this.pagina, tamano: this.tamano });
        if (this.filtros.nombre.trim()) params.set('nombre', this.filtros.nombre.trim());
        if (this.filtros.rol_id) params.set('rol_id', this.filtros.rol_id);
        if (this.soloActivos) params.set('activo', 'true');
        try {
          const respuesta = await window.pedir(`${API}?${params}`);
          this.filas = respuesta.resultados;
          this.total = respuesta.total;
        } catch (e) {
          window.toast(e.message, 'error');
        } finally {
          this.cargando = false;
        }
      },

      celdaUsuario(u) {
        const inactivo = u.activo ? '' : ` ${window.estadoHtml('Inactivo', 'peligro')}`;
        return window.escaparHtml(u.username) + inactivo;
      },

      // Solo oculta botones: la API vuelve a validar todo.
      puedeGestionar(u) {
        if (!puedeEditar) return false;
        if (esAdmin) return true;
        return u.id !== usuarioActualId && (rolesGestionables || []).includes(u.rol);
      },

      ver(u) {
        this.detalle = u;
        this.verAbierto = true;
      },

      nuevo() {
        this.form = formVacio();
        this.rolOriginal = null;
        this.errores = {};
        this.accesos = [];
        this.marcados = [];
        this.formAbierto = true;
      },

      async editar(u) {
        this.form = {
          id: u.id, username: u.username, nombre: u.nombre, rol_id: u.rol_id, email: u.email || '',
          fecha_nacimiento: u.fecha_nacimiento || '', celular: u.celular || '', password: '',
        };
        this.rolOriginal = u.rol_id;
        this.errores = {};
        this.accesos = [];
        this.marcados = [];
        this.formAbierto = true;
        try {
          this.accesos = await window.pedir(`${API}/${u.id}/accesos`);
          this.marcados = this.accesos.filter((a) => a.override && !a.heredado).map((a) => a.clave);
        } catch (e) {
          window.toast(e.message, 'error');
        }
      },

      async alCambiarRol() {
        if (!this.form.rol_id) {
          this.accesos = [];
          return;
        }
        try {
          const delRol = await window.pedir(`${API}/accesos?rol_id=${this.form.rol_id}`);
          const heredados = new Set(delRol.filter((a) => a.heredado).map((a) => a.clave));
          this.marcados = this.marcados.filter((clave) => !heredados.has(clave));
          this.accesos = delRol;
        } catch (e) {
          window.toast(e.message, 'error');
        }
      },

      marcado(a) {
        return a.heredado || this.marcados.includes(a.clave);
      },

      // Lo heredado no se toca; lo no otorgable no se puede agregar (sí quitar).
      bloqueado(a) {
        return a.heredado || (!a.otorgable && !this.marcados.includes(a.clave));
      },

      alternarAcceso(a) {
        if (this.bloqueado(a)) return;
        const i = this.marcados.indexOf(a.clave);
        if (i >= 0) this.marcados.splice(i, 1);
        else this.marcados.push(a.clave);
      },

      _cuerpo() {
        const cuerpo = {
          nombre: this.form.nombre,
          email: this.form.email || null,
          fecha_nacimiento: this.form.fecha_nacimiento || null,
          celular: this.form.celular || null,
        };
        if (!this.form.id) {
          return { ...cuerpo, username: this.form.username, password: this.form.password, rol_id: this.form.rol_id };
        }
        if (this.form.rol_id !== this.rolOriginal) cuerpo.rol_id = this.form.rol_id;
        if (this.form.password) cuerpo.password = this.form.password;
        return cuerpo;
      },

      async guardar() {
        const esAlta = !this.form.id;
        this.guardando = true;
        this.errores = {};
        try {
          const usuario = await window.pedir(esAlta ? API : `${API}/${this.form.id}`, {
            method: esAlta ? 'POST' : 'PUT',
            body: this._cuerpo(),
          });
          this.form.id = usuario.id;  // si falla lo que sigue, reintentar edita en vez de duplicar
          await window.pedir(`${API}/${usuario.id}/accesos`, { method: 'PUT', body: { accesos: this.marcados } });
          window.toast(esAlta ? 'Usuario creado. Va a cambiar la contraseña en su primer ingreso.' : 'Cambios guardados.');
          this.formAbierto = false;
        } catch (e) {
          this.errores = window.erroresDeCampos(e);
          window.toast(e.message, 'error');
        } finally {
          this.guardando = false;
          this.cargar();
        }
      },

      async cambiarEstado(u, activo) {
        const ok = await window.confirmar({
          titulo: activo ? `¿Activar a ${u.nombre}?` : `¿Desactivar a ${u.nombre}?`,
          mensaje: activo ? 'Va a poder volver a ingresar.' : 'No va a poder ingresar y se cierran sus sesiones abiertas.',
          textoConfirmar: activo ? 'Activar' : 'Desactivar',
          peligro: !activo,
        });
        if (!ok) return;
        try {
          await window.pedir(`${API}/${u.id}/estado`, { method: 'PATCH', body: { activo } });
          window.toast(activo ? 'Usuario activado.' : 'Usuario desactivado.');
          this.cargar();
        } catch (e) {
          window.toast(e.message, 'error');
        }
      },
    };
  };
})();
```

- [ ] **Step 6: Correr y ver que pasa** — `docker compose exec backend pytest tests/test_paginas_usuarios.py -v`, `node --check backend/app/static/js/usuarios.js`, suite completa.

- [ ] **Step 7: Commit** — `feat(pantallas): ABM de usuarios con accesos permitidos`.

---

### Task 5: Pantalla de roles

**Files:**
- Create: `backend/app/templates/pages/roles/listado.html`, `_modal_form.html`, `backend/app/static/js/roles.js`
- Modify: `backend/app/api/pages.py` (ruta `/roles`)
- Test: `backend/tests/test_paginas_roles.py`

**Interfaces:**
- Consumes: `requiere_pagina(SECCION_ROLES)`; API `/api/v1/roles` (listado con filtros `nombre, activo, es_sistema`, alta, edición, estado, eliminación).
- Produces: ruta `GET /roles`; componente `rolesListado()`.

- [ ] **Step 1: Tests que fallan**

`backend/tests/test_paginas_roles.py`:
```python
def test_admin_ve_roles(crear_usuario, iniciar_sesion):
    r = iniciar_sesion(crear_usuario("admin")).get("/roles")
    assert r.status_code == 200
    assert 'x-data="rolesListado()"' in r.text and "/static/js/roles.js?v=" in r.text
    assert "Tipo (todos)" in r.text and "Limpiar filtros" in r.text


def test_supervisor_no_ve_roles(crear_usuario, iniciar_sesion):
    r = iniciar_sesion(crear_usuario("supervisor")).get("/roles")
    assert r.status_code == 403
```

- [ ] **Step 2: Correr y ver que falla** — FAIL (404).

- [ ] **Step 3: Ruta** (en `pages.py`)

```python
@router.get("/roles")
def roles(request: Request, db: Session = Depends(get_db),
          usuario: Usuario = Depends(requiere_pagina(SECCION_ROLES))):
    return _pagina(request, "pages/roles/listado.html", contexto_base(request, db, "/configuracion", usuario))
```

- [ ] **Step 4: Plantillas**

`backend/app/templates/pages/roles/listado.html`:
```jinja
{% extends "base.html" %}
{% from "components/encabezado.html" import encabezado %}
{% from "components/table.html" import barra_filtros, tabla %}
{% from "components/botones.html" import accion, acciones %}
{% from "components/icons.html" import icono %}
{% block titulo %}Roles · {{ APP_NAME }}{% endblock %}
{% block contenido %}
<div x-data="rolesListado()">
  {% call encabezado("Roles", "/configuracion", "Configuraciones") %}
    <button type="button" class="boton boton-acento" @click="nuevo()">{{ icono("mas", "w-4 h-4") }}<span>Crear nuevo</span></button>
  {% endcall %}

  {% call barra_filtros() %}
    <input type="search" class="campo" placeholder="Nombre" aria-label="Filtrar por nombre" x-model="filtros.nombre" @input="filtrar()">
    <select class="campo" aria-label="Tipo de rol" x-model="filtros.tipo" @change="cargar()">
      <option value="">Tipo (todos)</option>
      <option value="sistema">Del sistema</option>
      <option value="personalizados">Personalizados</option>
    </select>
    <select class="campo" aria-label="Estado" x-model="filtros.estado" @change="cargar()">
      <option value="">Estado (todos)</option>
      <option value="activos">Activos</option>
      <option value="inactivos">Inactivos</option>
    </select>
  {% endcall %}

  {% set columnas = [
    {"titulo": "Nombre", "expr": "celdaNombre(fila)", "html": True},
    {"titulo": "Descripción", "expr": "fila.descripcion || '—'"},
    {"titulo": "Usuarios", "expr": "fila.cantidad_usuarios", "clase": "text-right"},
    {"titulo": "Estado", "expr": "fila.activo ? estadoHtml('Activo', 'exito') : estadoHtml('Inactivo', 'peligro')", "html": True},
  ] %}
  {% call tabla(columnas, cargando="cargando") %}
    {% call acciones() %}
      {{ accion("permisos", texto="Permisos", icono_nombre="candado", enlace=True, atributos=':href="`/roles/${fila.id}/permisos`"') }}
      {{ accion("editar", atributos='@click="editar(fila)"') }}
      {{ accion("borrar", texto="Desactivar", icono_nombre="salir", atributos='x-show="fila.activo" @click="cambiarEstado(fila, false)"') }}
      {{ accion("activar", atributos='x-show="!fila.activo" @click="cambiarEstado(fila, true)"') }}
      {{ accion("borrar", texto="Eliminar", atributos='x-show="!fila.es_sistema" @click="eliminar(fila)"') }}
    {% endcall %}
  {% endcall %}

  {% include "pages/roles/_modal_form.html" %}
</div>
{% endblock %}
{% block scripts %}<script src="{{ estatico('/js/roles.js') }}"></script>{% endblock %}
```

`backend/app/templates/pages/roles/_modal_form.html`:
```jinja
{% from "components/modal.html" import modal %}
{% from "components/form_field.html" import campo %}
{% call modal("Rol", "modal-rol-form", abierto="formAbierto", ancho="max-w-lg", titulo_expr="form.id ? 'Editar rol' : 'Nuevo rol'") %}
<form @submit.prevent="guardar()" class="flex flex-col gap-4" novalidate>
  {{ campo("r-nombre", "Nombre", modelo="form.nombre", requerido=True, error="errores.nombre", ayuda="Los roles del sistema no se renombran.", atributos=':disabled="form.es_sistema"') }}
  {{ campo("r-descripcion", "Descripción", modelo="form.descripcion", error="errores.descripcion") }}
  <div class="flex justify-end">
    <button type="submit" class="boton boton-primario" :disabled="guardando"
            x-text="guardando ? 'Guardando…' : (form.id ? 'Finalizar' : 'Crear')"></button>
  </div>
</form>
{% endcall %}
```

- [ ] **Step 5: `static/js/roles.js`**

```js
/* Pantalla de roles (solo Admin): filtros, alta/edición, activar/desactivar y eliminar. */
(function () {
  'use strict';

  const API = '/api/v1/roles';
  const formVacio = () => ({ id: null, nombre: '', descripcion: '', es_sistema: false });

  window.rolesListado = function () {
    return {
      filtros: { nombre: '', tipo: '', estado: '' },
      filas: [],
      cargando: false,
      formAbierto: false,
      form: formVacio(),
      errores: {},
      guardando: false,
      _espera: null,

      get total() {
        return this.filas.length;
      },

      init() {
        this.cargar();
      },

      filtrar() {
        clearTimeout(this._espera);
        this._espera = setTimeout(() => this.cargar(), 400);
      },

      limpiarFiltros() {
        this.filtros = { nombre: '', tipo: '', estado: '' };
        this.cargar();
      },

      async cargar() {
        this.cargando = true;
        const params = new URLSearchParams();
        if (this.filtros.nombre.trim()) params.set('nombre', this.filtros.nombre.trim());
        if (this.filtros.tipo) params.set('es_sistema', this.filtros.tipo === 'sistema');
        if (this.filtros.estado) params.set('activo', this.filtros.estado === 'activos');
        try {
          this.filas = await window.pedir(`${API}?${params}`);
        } catch (e) {
          window.toast(e.message, 'error');
        } finally {
          this.cargando = false;
        }
      },

      celdaNombre(r) {
        const sistema = r.es_sistema ? ' <span class="text-xs text-texto-muted">(del sistema)</span>' : '';
        return window.escaparHtml(r.nombre) + sistema;
      },

      nuevo() {
        this.form = formVacio();
        this.errores = {};
        this.formAbierto = true;
      },

      editar(r) {
        this.form = { id: r.id, nombre: r.nombre, descripcion: r.descripcion || '', es_sistema: r.es_sistema };
        this.errores = {};
        this.formAbierto = true;
      },

      async guardar() {
        const esAlta = !this.form.id;
        this.guardando = true;
        this.errores = {};
        try {
          await window.pedir(esAlta ? API : `${API}/${this.form.id}`, {
            method: esAlta ? 'POST' : 'PUT',
            body: { nombre: this.form.nombre, descripcion: this.form.descripcion || null },
          });
          window.toast(esAlta ? 'Rol creado. Definí sus permisos desde "Permisos".' : 'Cambios guardados.');
          this.formAbierto = false;
          this.cargar();
        } catch (e) {
          this.errores = window.erroresDeCampos(e);
          window.toast(e.message, 'error');
        } finally {
          this.guardando = false;
        }
      },

      async cambiarEstado(r, activo) {
        const conUsuarios = !activo && r.cantidad_usuarios > 0;
        const ok = await window.confirmar({
          titulo: activo ? `¿Activar el rol ${r.nombre}?` : `¿Desactivar el rol ${r.nombre}?`,
          mensaje: activo ? 'Se va a poder asignar a usuarios.' : 'No se va a poder asignar a usuarios nuevos.',
          advertencia: conUsuarios
            ? `El rol tiene ${r.cantidad_usuarios} usuario(s). Si alguno está activo, primero hay que desactivarlo o cambiarle el rol.`
            : '',
          textoConfirmar: activo ? 'Activar' : 'Desactivar',
          peligro: !activo,
        });
        if (!ok) return;
        try {
          await window.pedir(`${API}/${r.id}/estado`, { method: 'PATCH', body: { activo } });
          window.toast(activo ? 'Rol activado.' : 'Rol desactivado.');
          this.cargar();
        } catch (e) {
          window.toast(e.message, 'error');
        }
      },

      async eliminar(r) {
        const ok = await window.confirmar({
          titulo: `¿Eliminar el rol ${r.nombre}?`,
          mensaje: 'Se borra junto con sus permisos. No se puede deshacer.',
          textoConfirmar: 'Eliminar',
          peligro: true,
        });
        if (!ok) return;
        try {
          await window.pedir(`${API}/${r.id}`, { method: 'DELETE' });
          window.toast('Rol eliminado.');
          this.cargar();
        } catch (e) {
          window.toast(e.message, 'error');
        }
      },
    };
  };
})();
```

- [ ] **Step 6: Correr y ver que pasa** — tests de la tarea, `node --check backend/app/static/js/roles.js`, suite completa.

- [ ] **Step 7: Commit** — `feat(pantallas): ABM de roles`.

---

### Task 6: Árbol de permisos (rol y usuario)

**Files:**
- Create: `backend/app/templates/components/permisos_tree.html`, `backend/app/static/js/permisos.js`, `backend/app/templates/pages/roles/permisos.html`, `backend/app/templates/pages/usuarios/permisos.html`
- Modify: `backend/app/api/pages.py` (rutas `/roles/{rol_id}/permisos`, `/usuarios/{usuario_id}/permisos`)
- Test: `backend/tests/test_paginas_permisos.py`, `backend/tests/test_componentes.py` (compila el macro nuevo)

**Interfaces:**
- Consumes: `requiere_pagina`, `services.roles.obtener_rol`, `services.usuarios.obtener_usuario`, `services.usuarios.validar_puede_gestionar`, `SinPermiso`, `ROL_ADMIN`; API `GET/PUT /api/v1/roles/{id}/permisos` y `/api/v1/usuarios/{id}/permisos` (árbol `{modulos: [nodo]}` con `puede_*`, y en usuario `heredado_*`, `override_*`, `otorgable_*`).
- Produces: macro `arbol_permisos(url_datos, url_guardar, modo="rol", editable=True)`; componente `arbolPermisos({urlDatos, urlGuardar, modo, editable})`; rutas de página.

- [ ] **Step 1: Tests que fallan**

`backend/tests/test_paginas_permisos.py`:
```python
from sqlalchemy import select

from app.models import Rol


def _rol_id(db, nombre):
    return db.scalar(select(Rol.id).where(Rol.nombre == nombre))


def test_permisos_de_un_rol(crear_usuario, iniciar_sesion, db):
    rol_id = _rol_id(db, "vendedor")
    html = iniciar_sesion(crear_usuario("admin")).get(f"/roles/{rol_id}/permisos").text
    assert "arbolPermisos(" in html and f"/api/v1/roles/{rol_id}/permisos" in html
    assert "Guardar permisos" in html and "Expandir todo" in html
    assert "/static/js/permisos.js?v=" in html


def test_permisos_del_rol_admin_son_de_solo_lectura(crear_usuario, iniciar_sesion, db):
    html = iniciar_sesion(crear_usuario("admin")).get(f"/roles/{_rol_id(db, 'admin')}/permisos").text
    assert "tiene acceso total" in html and "editable: false" in html


def test_permisos_de_un_usuario(crear_usuario, iniciar_sesion):
    vendedor = crear_usuario("vendedor", nombre="Vera")
    html = iniciar_sesion(crear_usuario("supervisor")).get(f"/usuarios/{vendedor.id}/permisos").text
    assert "Permisos de Vera" in html and "&#34;usuario&#34;" in html and "editable: true" in html


def test_supervisor_ve_pero_no_edita_a_otro_supervisor(crear_usuario, iniciar_sesion):
    otro = crear_usuario("supervisor")
    html = iniciar_sesion(crear_usuario("supervisor")).get(f"/usuarios/{otro.id}/permisos").text
    assert "editable: false" in html


def test_vendedor_no_entra(crear_usuario, iniciar_sesion, db):
    cliente = iniciar_sesion(crear_usuario("vendedor"))
    assert cliente.get(f"/roles/{_rol_id(db, 'vendedor')}/permisos").status_code == 403
```

En `backend/tests/test_componentes.py`, agregar `"permisos_tree"` a la lista del test parametrizado `test_todos_los_componentes_compilan`.

- [ ] **Step 2: Correr y ver que falla** — FAIL (404 / TemplateNotFound).

- [ ] **Step 3: Rutas** (en `pages.py`; importar `from app.core.errores import SinPermiso` y `from app.core.permisos import ROL_ADMIN`)

```python
@router.get("/roles/{rol_id}/permisos")
def permisos_de_rol(rol_id: int, request: Request, db: Session = Depends(get_db),
                    usuario: Usuario = Depends(requiere_pagina(SECCION_ROLES))):
    rol = servicio_roles.obtener_rol(db, rol_id)
    return _pagina(request, "pages/roles/permisos.html", contexto_base(
        request, db, "/configuracion", usuario, rol=rol, editable=rol.nombre != ROL_ADMIN,
    ))


@router.get("/usuarios/{usuario_id}/permisos")
def permisos_de_usuario(usuario_id: int, request: Request, db: Session = Depends(get_db),
                        usuario: Usuario = Depends(requiere_pagina(SECCION_USUARIOS))):
    objetivo = servicio_usuarios.obtener_usuario(db, usuario_id)
    editable = resolver_permiso(db, usuario.id, Modulo.USUARIOS, "editar")
    if editable:
        try:
            servicio_usuarios.validar_puede_gestionar(usuario, objetivo.rol, objetivo)
        except SinPermiso:
            editable = False
    return _pagina(request, "pages/usuarios/permisos.html", contexto_base(
        request, db, "/configuracion", usuario, objetivo=objetivo, editable=editable,
    ))
```

- [ ] **Step 4: Macro del árbol**

`backend/app/templates/components/permisos_tree.html`:
```jinja
{% from "components/icons.html" import icono %}
{# Árbol de permisos (rol o usuario). Tabla Módulo | Ver | Crear | Editar |
   Eliminar; cada módulo se expande para mostrar sus recursos. Las acciones
   que no aplican se ven "—". Guardar pide confirmación (sin autoguardado). #}
{% set ACCIONES_ARBOL = [("ver", "Ver"), ("crear", "Crear"), ("editar", "Editar"), ("eliminar", "Eliminar")] %}

{% macro celda_permiso(nodo, accion) -%}
<template x-if="aplica({{ nodo }}, '{{ accion }}')">
  <input type="checkbox" class="acceso-check" :class="claseCelda({{ nodo }}, '{{ accion }}')"
         :checked="marcado({{ nodo }}, '{{ accion }}')" :disabled="bloqueado({{ nodo }}, '{{ accion }}')"
         @change="alternar({{ nodo }}, '{{ accion }}')" :aria-label="`{{ accion }}: ${ {{ nodo }}.label }`">
</template>
<template x-if="!aplica({{ nodo }}, '{{ accion }}')"><span class="text-texto-disabled" title="No aplica">—</span></template>
{%- endmacro %}

{% macro arbol_permisos(url_datos, url_guardar, modo="rol", editable=True) -%}
<div x-data="arbolPermisos({ urlDatos: {{ url_datos|js }}, urlGuardar: {{ url_guardar|js }}, modo: {{ modo|js }}, editable: {{ editable|js }} })">
  <div class="mb-4 flex flex-wrap items-center justify-between gap-3">
    <div class="flex flex-wrap gap-2">
      <button type="button" class="boton boton-secundario" @click="expandirTodo(true)">Expandir todo</button>
      <button type="button" class="boton boton-secundario" @click="expandirTodo(false)">Colapsar todo</button>
    </div>
    <div class="flex flex-wrap items-center gap-3" x-show="editable">
      <p class="text-sm font-semibold text-danger" x-show="hayCambios" x-cloak>Hay cambios sin guardar</p>
      <button type="button" class="boton boton-primario" :disabled="!hayCambios || guardando" @click="guardar()"
              x-text="guardando ? 'Guardando…' : 'Guardar permisos'">Guardar permisos</button>
    </div>
  </div>
  {% if modo == "usuario" %}
  <p class="mb-3 text-sm text-texto-muted">En gris, lo que hereda del rol (no se quita desde acá). Marcados en color, los permisos propios de este usuario. Lo que no podés otorgar aparece deshabilitado.</p>
  {% endif %}
  <div class="tarjeta overflow-hidden p-0">
    <div class="overflow-x-auto">
      <table class="tabla">
        <thead>
          <tr>
            <th scope="col">Módulo</th>
            {% for _, titulo in ACCIONES_ARBOL %}<th scope="col" class="text-center">{{ titulo }}</th>{% endfor %}
          </tr>
        </thead>
        <template x-for="m in modulos" :key="m.modulo">
          <tbody>
            <tr>
              <td>
                <button type="button" class="inline-flex min-h-toque items-center gap-2 font-semibold text-texto"
                        @click="abiertos[m.modulo] = !abiertos[m.modulo]" :aria-expanded="!!abiertos[m.modulo]"
                        :disabled="!m.recursos.length">
                  <span x-show="m.recursos.length" class="transition-transform" :class="abiertos[m.modulo] ? 'rotate-90' : ''">{{ icono("chevron-derecha", "w-4 h-4") }}</span>
                  <span x-text="m.label"></span>
                </button>
              </td>
              {% for accion, _ in ACCIONES_ARBOL %}<td class="text-center">{{ celda_permiso("m", accion) }}</td>{% endfor %}
            </tr>
            <template x-for="r in m.recursos" :key="r.recurso">
              <tr x-show="abiertos[m.modulo]">
                <td class="pl-10 text-texto-muted" x-text="r.label"></td>
                {% for accion, _ in ACCIONES_ARBOL %}<td class="text-center">{{ celda_permiso("r", accion) }}</td>{% endfor %}
              </tr>
            </template>
          </tbody>
        </template>
      </table>
    </div>
  </div>
  <p x-show="cargando" class="py-6 text-center text-texto-muted">Cargando…</p>
</div>
{%- endmacro %}
```

- [ ] **Step 5: `static/js/permisos.js`**

```js
/* Árbol de permisos de un rol o de un usuario. En modo "usuario" solo se
   editan los permisos propios (overrides); lo heredado del rol queda fijo. */
(function () {
  'use strict';

  const ACCIONES = ['ver', 'crear', 'editar', 'eliminar'];

  window.arbolPermisos = function ({ urlDatos, urlGuardar, modo, editable }) {
    const campo = (accion) => (modo === 'usuario' ? `override_${accion}` : `puede_${accion}`);

    return {
      modo,
      editable,
      modulos: [],
      abiertos: {},
      original: '',
      cargando: true,
      guardando: false,

      async init() {
        await this.cargar();
      },

      async cargar() {
        this.cargando = true;
        try {
          this._recibir(await window.pedir(urlDatos));
        } catch (e) {
          window.toast(e.message, 'error');
        } finally {
          this.cargando = false;
        }
      },

      _recibir(arbol) {
        this.modulos = arbol.modulos;
        this.original = JSON.stringify(this.entradas());
      },

      get hayCambios() {
        return JSON.stringify(this.entradas()) !== this.original;
      },

      // null en puede_<accion> = la acción no aplica a ese módulo/recurso.
      aplica(nodo, accion) {
        return nodo[`puede_${accion}`] !== null && nodo[`puede_${accion}`] !== undefined;
      },

      marcado(nodo, accion) {
        if (modo === 'usuario') return !!(nodo[`heredado_${accion}`] || nodo[`override_${accion}`]);
        return !!nodo[`puede_${accion}`];
      },

      bloqueado(nodo, accion) {
        if (!editable) return true;
        if (modo !== 'usuario') return false;
        if (nodo[`heredado_${accion}`]) return true;
        // No otorgable: no se puede agregar, pero sí quitar lo que ya tiene.
        return nodo[`otorgable_${accion}`] === false && !nodo[`override_${accion}`];
      },

      claseCelda(nodo, accion) {
        if (modo === 'usuario' && nodo[`heredado_${accion}`]) return 'opacity-50';
        if (modo === 'usuario' && nodo[`override_${accion}`]) return 'accent-accent';
        return '';
      },

      _modulo(nombre) {
        return this.modulos.find((m) => m.modulo === nombre);
      },

      alternar(nodo, accion) {
        if (this.bloqueado(nodo, accion)) return;
        const clave = campo(accion);
        nodo[clave] = !nodo[clave];
        if (nodo.recurso === null) {
          // Marcar el general sugiere sus recursos; desmarcarlo los desmarca.
          for (const r of this._modulo(nodo.modulo).recursos) {
            if (this.aplica(r, accion) && !this.bloqueado(r, accion)) r[clave] = nodo[clave];
          }
        }
      },

      expandirTodo(abrir) {
        for (const m of this.modulos) this.abiertos[m.modulo] = abrir;
      },

      // Lo que se manda a la API. Un recurso cubierto por el permiso general
      // de su módulo no se guarda como fila propia (quedaría "pegado").
      entradas() {
        const salida = [];
        for (const m of this.modulos) {
          for (const nodo of [m, ...m.recursos]) {
            const entrada = { modulo: nodo.modulo, recurso: nodo.recurso };
            for (const accion of ACCIONES) {
              const cubierto = nodo.recurso !== null && this.aplica(m, accion) && m[campo(accion)];
              entrada[`puede_${accion}`] = this.aplica(nodo, accion) && !!nodo[campo(accion)] && !cubierto;
            }
            salida.push(entrada);
          }
        }
        return salida;
      },

      async guardar() {
        const ok = await window.confirmar({
          titulo: '¿Guardar los permisos?',
          mensaje: 'Los cambios rigen desde el próximo pedido de cada usuario afectado.',
          textoConfirmar: 'Guardar',
        });
        if (!ok) return;
        this.guardando = true;
        try {
          this._recibir(await window.pedir(urlGuardar, { method: 'PUT', body: { permisos: this.entradas() } }));
          window.toast('Permisos guardados.');
        } catch (e) {
          window.toast(e.message, 'error');
        } finally {
          this.guardando = false;
        }
      },
    };
  };
})();
```

- [ ] **Step 6: Páginas**

`backend/app/templates/pages/roles/permisos.html`:
```jinja
{% extends "base.html" %}
{% from "components/encabezado.html" import encabezado %}
{% from "components/permisos_tree.html" import arbol_permisos %}
{% block titulo %}Permisos de {{ rol.nombre }} · {{ APP_NAME }}{% endblock %}
{% block contenido %}
{{ encabezado("Permisos del rol " ~ rol.nombre, "/roles", "Roles") }}
{% if not editable %}
<p class="mb-4 rounded-input bg-primary/10 p-3 text-sm text-texto">El rol Admin tiene acceso total: sus permisos no se editan.</p>
{% endif %}
{{ arbol_permisos("/api/v1/roles/" ~ rol.id ~ "/permisos", "/api/v1/roles/" ~ rol.id ~ "/permisos", "rol", editable) }}
{% endblock %}
{% block scripts %}<script src="{{ estatico('/js/permisos.js') }}"></script>{% endblock %}
```

`backend/app/templates/pages/usuarios/permisos.html`:
```jinja
{% extends "base.html" %}
{% from "components/encabezado.html" import encabezado %}
{% from "components/permisos_tree.html" import arbol_permisos %}
{% block titulo %}Permisos de {{ objetivo.nombre }} · {{ APP_NAME }}{% endblock %}
{% block contenido %}
{{ encabezado("Permisos de " ~ objetivo.nombre, "/usuarios", "Usuarios") }}
<p class="mb-4 text-sm text-texto-muted">Rol: <span class="font-semibold text-texto">{{ objetivo.rol.nombre }}</span>{% if not editable %} · Solo lectura{% endif %}</p>
{{ arbol_permisos("/api/v1/usuarios/" ~ objetivo.id ~ "/permisos", "/api/v1/usuarios/" ~ objetivo.id ~ "/permisos", "usuario", editable) }}
{% endblock %}
{% block scripts %}<script src="{{ estatico('/js/permisos.js') }}"></script>{% endblock %}
```

Nota: los tests buscan `editable: true|false` en el HTML: el filtro `|js` de un bool de Python da `true`/`false` (JSON), así que `editable: {{ editable|js }}` renderiza `editable: true`.

- [ ] **Step 7: Correr y ver que pasa** — tests de la tarea + `test_componentes.py`, `node --check backend/app/static/js/permisos.js`, suite completa.

- [ ] **Step 8: Commit** — `feat(pantallas): árbol de permisos de roles y usuarios`.

---

### Task 7: Historial de accesos y verificación final

**Files:**
- Create: `backend/app/templates/pages/usuarios/historial.html`, `backend/app/static/js/historial.js`
- Modify: `backend/app/api/pages.py` (ruta `/usuarios/{usuario_id}/historial`)
- Test: `backend/tests/test_paginas_usuarios.py` (agregar)

**Interfaces:**
- Consumes: `requiere_pagina(SECCION_USUARIOS)`, `servicio_usuarios.obtener_usuario`; API `GET /api/v1/usuarios/{id}/historial?desde&hasta&resultado&pagina&tamano`.
- Produces: ruta de página; componente `historialAccesos(usuarioId)`.

- [ ] **Step 1: Test que falla** (agregar a `backend/tests/test_paginas_usuarios.py`)

```python
def test_historial_de_accesos(crear_usuario, iniciar_sesion):
    vendedor = crear_usuario("vendedor", nombre="Hugo")
    html = iniciar_sesion(crear_usuario("admin")).get(f"/usuarios/{vendedor.id}/historial").text
    assert "Historial de accesos de Hugo" in html
    assert f"historialAccesos({vendedor.id})" in html and "/static/js/historial.js?v=" in html
    assert "Resultado (todos)" in html
```

- [ ] **Step 2: Correr y ver que falla** — FAIL (404).

- [ ] **Step 3: Ruta**

```python
@router.get("/usuarios/{usuario_id}/historial")
def historial_de_usuario(usuario_id: int, request: Request, db: Session = Depends(get_db),
                         usuario: Usuario = Depends(requiere_pagina(SECCION_USUARIOS))):
    objetivo = servicio_usuarios.obtener_usuario(db, usuario_id)
    return _pagina(request, "pages/usuarios/historial.html",
                   contexto_base(request, db, "/configuracion", usuario, objetivo=objetivo))
```

- [ ] **Step 4: Plantilla y JS**

`backend/app/templates/pages/usuarios/historial.html`:
```jinja
{% extends "base.html" %}
{% from "components/encabezado.html" import encabezado %}
{% from "components/table.html" import barra_filtros, tabla %}
{% from "components/paginacion.html" import paginacion %}
{% block titulo %}Historial de accesos · {{ APP_NAME }}{% endblock %}
{% block contenido %}
<div x-data="historialAccesos({{ objetivo.id|js }})">
  {{ encabezado("Historial de accesos de " ~ objetivo.nombre, "/usuarios", "Usuarios") }}
  {% call barra_filtros() %}
    <label class="flex flex-col gap-1 text-sm text-texto-muted">Desde
      <input type="date" class="campo" x-model="filtros.desde" @change="pagina = 1; cargar()"></label>
    <label class="flex flex-col gap-1 text-sm text-texto-muted">Hasta
      <input type="date" class="campo" x-model="filtros.hasta" @change="pagina = 1; cargar()"></label>
    <label class="flex flex-col gap-1 text-sm text-texto-muted">Resultado
      <select class="campo" x-model="filtros.resultado" @change="pagina = 1; cargar()">
        <option value="">Resultado (todos)</option>
        <option value="exitoso">Exitoso</option>
        <option value="fallido">Fallido</option>
      </select></label>
  {% endcall %}
  {% set columnas = [
    {"titulo": "Fecha y hora", "expr": "fechaHora(fila.timestamp)"},
    {"titulo": "IP", "expr": "fila.ip_origen || '—'"},
    {"titulo": "Resultado", "expr": "fila.resultado === 'exitoso' ? estadoHtml('Exitoso', 'exito') : estadoHtml('Fallido', 'peligro')", "html": True},
    {"titulo": "Detalle", "expr": "fila.detalle || '—'"},
  ] %}
  {{ tabla(columnas, cargando="cargando", vacio="Sin ingresos registrados.") }}
  {{ paginacion() }}
</div>
{% endblock %}
{% block scripts %}<script src="{{ estatico('/js/historial.js') }}"></script>{% endblock %}
```

`backend/app/static/js/historial.js`:
```js
/* Historial de accesos de un usuario (solo lectura, paginado). */
(function () {
  'use strict';

  window.historialAccesos = function (usuarioId) {
    return {
      filtros: { desde: '', hasta: '', resultado: '' },
      pagina: 1,
      tamano: 10,
      total: 0,
      filas: [],
      cargando: false,

      init() {
        this.cargar();
      },

      limpiarFiltros() {
        this.filtros = { desde: '', hasta: '', resultado: '' };
        this.pagina = 1;
        this.cargar();
      },

      async cargar() {
        this.cargando = true;
        const params = new URLSearchParams({ pagina: this.pagina, tamano: this.tamano });
        for (const [clave, valor] of Object.entries(this.filtros)) {
          if (valor) params.set(clave, valor);
        }
        try {
          const respuesta = await window.pedir(`/api/v1/usuarios/${usuarioId}/historial?${params}`);
          this.filas = respuesta.resultados;
          this.total = respuesta.total;
        } catch (e) {
          window.toast(e.message, 'error');
        } finally {
          this.cargando = false;
        }
      },
    };
  };
})();
```

- [ ] **Step 5: Verificación final**

```bash
docker compose exec backend pytest -p no:warnings                  # suite completa verde
for f in app auth usuarios roles permisos historial; do node --check backend/app/static/js/$f.js; done
docker compose restart backend && sleep 5
curl -s -o /dev/null -w "%{http_code}\n" localhost:8000/            # 303 (sin sesión)
curl -s -o /dev/null -w "%{http_code}\n" localhost:8000/login       # 200
```
Checklist manual para el usuario (navegador, http://localhost:8000): ingresar como `admin` / `Admin1234!` → obliga a cambiar la contraseña → inicio; crear un supervisor y un vendedor desde Usuarios; entrar como supervisor y verificar que en "Accesos permitidos" no puede marcar Auditoría ni Usuarios; árbol de permisos de un rol (marcar, guardar, recargar); historial de accesos; tema oscuro y pantalla de 360px de ancho.

- [ ] **Step 6: Commit** — `feat(pantallas): historial de accesos`.
