# Módulo 02-A — Autenticación, Usuarios y Permisos (backend/API): Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** API completa de autenticación (JWT en cookies HttpOnly + Bearer, sesión deslizante por inactividad), roles, usuarios, permisos (árbol y "accesos permitidos") y la consulta de auditoría, con `resolver_permiso()` como única barrera de acceso. Las pantallas HTML van en el plan 02-B.

**Architecture:** Constantes de dominio en `core/permisos.py`; barrera y dependencies de FastAPI en `core/seguridad.py`; errores de negocio tipados en `core/errores.py` traducidos a HTTP por un único handler. Services sin commit (la transacción la cierra el router). Tokens: access (30 min, claim `sid` = sesión) y refresh (7 días, claim `jti`); la tabla `sesiones` guarda la ventana de inactividad deslizante. Un middleware renueva el access vencido desde la cookie de refresh.

**Tech Stack:** FastAPI 0.115, SQLAlchemy 2.0, Alembic, PostgreSQL 15, PyJWT 2.10, bcrypt 4.2 (directo, sin passlib), pydantic 2 + email-validator, pytest.

**Spec:** `modulos/02_auth_usuarios.md` (la "clave especial" fue eliminada del alcance por decisión del usuario) + `CLAUDE.md`.

## Global Constraints

- Código y comentarios en español. `config.settings` es la única fuente de configuración.
- **Git:** rama local `modulo-02-auth-usuarios` (autorizada). UN commit por tarea, mensaje `feat(auth): …` (o `fix(auth): …` en rondas de corrección) + línea en blanco + `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. NUNCA `git push`, `--amend`, reset, rebase ni merge. Nunca commitear `.env`, `uploads/`, `backups/`.
- Tests dentro del contenedor: `docker compose exec backend pytest …` (Postgres real, base `gestion_test`, transacción revertida por test). Correr la suite completa antes de cada commit.
- Errores de regla → `ReglaDeNegocio` (409); no encontrado → `NoEncontrado` (404); sin permiso → `SinPermiso` (403); sin sesión → `NoAutenticado` (401); dato inválido de negocio → `DatoInvalido` (400). Nunca `HTTPException` en services.
- Services: nunca `commit`; los routers hacen `db.commit()` después de una escritura exitosa.
- Toda acción sensible audita con `registrar_auditoria` en la misma transacción. `estado_anterior` SIEMPRE como `snapshot(obj)` tomado antes del cambio.
- `password_hash` nunca aparece en un schema de respuesta ni en la auditoría.
- Rutas fijas antes de `/{id}` en cada router.
- Si una escritura de archivo decodifica escapes `\uXXXX`, verificar los bytes después.

## Desvíos deliberados respecto del spec

1. **Sin clave especial** (decisión del usuario): no hay `clave_especial_hash` ni sus endpoints.
2. `resolver_permiso`, `get_current_user`, `requiere_permiso` y `requiere_admin` viven en `core/seguridad.py`; `core/permisos.py` queda solo con constantes y catálogo (archivos con una responsabilidad).
3. **El access token lleva `sid`** (jti de la sesión) y `get_current_user` verifica que esa sesión siga vigente: logout, cambio de contraseña o desactivación cortan el acceso al instante y la inactividad de 30 min se cumple aunque el access no haya vencido.
4. `requiere_permiso`/`requiere_admin` rechazan con 403 a un usuario que debe cambiar la contraseña (el cambio obligatorio no se puede saltear usando la API).
5. bcrypt se usa directo (`bcrypt.hashpw`), sin passlib (passlib 1.7.4 emite warnings con bcrypt 4.x). Costo configurable `BCRYPT_ROUNDS` (12; 4 en tests).
6. El seed carga TODOS los permisos de roles de sistema (incluidos caja, reportes y recursos de sesiones futuras): `rol_permisos.modulo` es texto, no depende de otras tablas.
7. El validador de producción también rechaza el `JWT_SECRET` de ejemplo de `.env.example`.
8. Los permisos del rol `admin` no se editan (409): `resolver_permiso` ya le da todo.

---

## File Structure

```
backend/config.py                       (mod) BCRYPT_ROUNDS; validador rechaza secreto de ejemplo
backend/.env.example → /.env.example    (mod) BCRYPT_ROUNDS
backend/main.py                         (mod) handlers de errores, middleware, routers
backend/migrations/versions/0002_auth_usuarios.py
backend/migrations/seed.sql             (mod) bloque sesión 02
backend/app/core/errores.py             errores de negocio + handler único
backend/app/core/permisos.py            Modulo, Recurso, acciones, roles, labels, catálogo de accesos
backend/app/core/seguridad.py           resolver_permiso, usuario_de_token, get_current_user, requiere_permiso, requiere_admin
backend/app/core/cookies.py             poner/borrar cookies de sesión
backend/app/core/email.py               SMTP opcional + mail de recuperación
backend/app/middleware/auth_refresh_middleware.py
backend/app/models/usuarios.py          Rol, Usuario
backend/app/models/permisos.py          ColumnasPermiso, RolPermiso, UsuarioPermiso
backend/app/models/sesiones.py          ResultadoAcceso, HistorialAcceso, Sesion
backend/app/models/__init__.py          (mod)
backend/app/schemas/auth.py, roles.py, usuarios.py, permisos.py
backend/app/services/auth.py, permisos.py, roles.py, usuarios.py
backend/app/api/v1/auth.py, roles.py, usuarios.py, auditoria.py
backend/app/api/v1/__init__.py          (mod)
backend/tests/conftest.py               (mod) BCRYPT_ROUNDS=4, fixtures crear_usuario / headers_de, sesión del middleware
backend/tests/test_permisos_catalogo.py, test_modelo_usuarios.py, test_auth_service.py,
  test_seguridad.py, test_auth_api.py, test_middleware.py, test_permisos_service.py,
  test_roles_api.py, test_usuarios_api.py, test_auditoria_api.py
README.md                               (mod) credenciales iniciales y recuperación de contraseña
```

---

### Task 1: Errores de negocio y constantes de permisos

**Files:**
- Create: `backend/app/core/errores.py`, `backend/app/core/permisos.py`
- Modify: `backend/main.py` (registrar el handler)
- Test: `backend/tests/test_permisos_catalogo.py`, `backend/tests/test_errores.py`

**Interfaces:**
- Produces: `ErrorDeNegocio(mensaje)` y subclases `NoEncontrado` (404), `SinPermiso` (403), `ReglaDeNegocio` (409), `NoAutenticado` (401), `DatoInvalido` (400) con `.mensaje` y `.status_code`; `registrar_manejadores(app)` → respuesta `{"detail": mensaje}`.
- Produces: `Modulo`, `Recurso` (Enums str), `ACCIONES`, `ROL_ADMIN`, `ROL_SUPERVISOR`, `ROL_VENDEDOR`, `ROLES_SISTEMA`, `LABEL_MODULO`, `LABEL_RECURSO`, `MODULO_DE_RECURSO`, `ACCIONES_DE_RECURSO`, `ACCIONES_DE_MODULO`, `acciones_aplicables(modulo, recurso=None) -> tuple[str, ...]`, `recursos_de_modulo(modulo) -> list[Recurso]`, `validar_destino(modulo, recurso) -> tuple[Modulo, Recurso | None]` (ValueError si no existe o el recurso no es del módulo), `Acceso` (dataclass: `clave, modulo, recurso, accion, label`), `clave_acceso(modulo, recurso, accion) -> str`, `catalogo_accesos() -> list[Acceso]`, `acceso_por_clave(clave) -> Acceso | None`.

- [ ] **Step 1: Tests que fallan**

`backend/tests/test_errores.py`:
```python
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.errores import (
    DatoInvalido,
    NoAutenticado,
    NoEncontrado,
    ReglaDeNegocio,
    SinPermiso,
    registrar_manejadores,
)


@pytest.mark.parametrize(
    "error, status",
    [(NoEncontrado, 404), (SinPermiso, 403), (ReglaDeNegocio, 409), (NoAutenticado, 401), (DatoInvalido, 400)],
)
def test_errores_de_negocio_se_traducen_a_http(error, status):
    app = FastAPI()
    registrar_manejadores(app)

    @app.get("/falla")
    def falla():
        raise error("Mensaje para el usuario")

    r = TestClient(app).get("/falla")
    assert r.status_code == status
    assert r.json() == {"detail": "Mensaje para el usuario"}
```

`backend/tests/test_permisos_catalogo.py`:
```python
import pytest

from app.core.permisos import (
    ACCIONES,
    LABEL_MODULO,
    LABEL_RECURSO,
    MODULO_DE_RECURSO,
    ROLES_SISTEMA,
    Modulo,
    Recurso,
    acceso_por_clave,
    acciones_aplicables,
    catalogo_accesos,
    clave_acceso,
    recursos_de_modulo,
    validar_destino,
)


def test_todo_modulo_y_recurso_tiene_label_y_modulo():
    assert set(LABEL_MODULO) == set(Modulo)
    assert set(LABEL_RECURSO) == set(Recurso)
    assert set(MODULO_DE_RECURSO) == set(Recurso)
    for recurso in Recurso:
        assert set(acciones_aplicables(MODULO_DE_RECURSO[recurso], recurso)) <= set(ACCIONES)


def test_roles_de_sistema():
    assert ROLES_SISTEMA == ("admin", "supervisor", "vendedor")


def test_acciones_aplicables_por_modulo_y_recurso():
    assert acciones_aplicables(Modulo.STOCK) == ACCIONES
    assert acciones_aplicables(Modulo.AUDITORIA) == ("ver",)
    assert acciones_aplicables(Modulo.REPORTES) == ("ver",)
    assert acciones_aplicables(Modulo.IMPORTACION) == ("crear",)
    assert acciones_aplicables(Modulo.VENTAS, Recurso.VENTA_ANULAR) == ("eliminar",)
    assert acciones_aplicables(Modulo.CONFIGURACION, Recurso.PROMOCIONES) == ("ver", "crear", "editar")


def test_recursos_de_modulo():
    assert recursos_de_modulo(Modulo.CAJA) == [Recurso.CAJA_ARQUEO, Recurso.CAJA_RETIRO]
    assert recursos_de_modulo(Modulo.CLIENTES) == []


def test_validar_destino():
    assert validar_destino("stock", "stock.baja") == (Modulo.STOCK, Recurso.STOCK_BAJA)
    assert validar_destino("stock", None) == (Modulo.STOCK, None)
    with pytest.raises(ValueError):
        validar_destino("inventado", None)
    with pytest.raises(ValueError):
        validar_destino("ventas", "stock.baja")  # el recurso no es del módulo


def test_catalogo_de_accesos():
    catalogo = catalogo_accesos()
    claves = [a.clave for a in catalogo]
    assert len(claves) == len(set(claves))
    assert catalogo[0].label == "Acceso a tablas y configuración"
    assert clave_acceso(Modulo.CONFIGURACION, None, "ver") == "configuracion::ver"
    masivo = acceso_por_clave("proveedores:dolar.cambio_masivo:editar")
    assert masivo.label == "Modificar: cambio masivo del dólar"
    assert masivo.modulo is Modulo.PROVEEDORES and masivo.recurso is Recurso.DOLAR_CAMBIO_MASIVO
    assert acceso_por_clave("stock:stock.baja:crear").label == "Registrar: bajas de stock"
    assert acceso_por_clave("ventas:venta.anular:eliminar").label == "Realizar: anulación de ventas"
    assert acceso_por_clave("no:existe:ver") is None
    # un casillero por cada (recurso, acción aplicable) + los 5 de módulo
    esperados = 5 + sum(len(acciones_aplicables(MODULO_DE_RECURSO[r], r)) for r in Recurso)
    assert len(catalogo) == esperados
```

- [ ] **Step 2: Correr y ver que falla**

Run: `docker compose exec backend pytest tests/test_errores.py tests/test_permisos_catalogo.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.errores'`.

- [ ] **Step 3: Implementación**

`backend/app/core/errores.py`:
```python
"""Errores de negocio y su traducción a HTTP (una sola definición).

Los services levantan estos errores; nunca HTTPException. main.py registra un
único handler que responde {"detail": mensaje} con el status de cada clase.
"""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class ErrorDeNegocio(Exception):
    status_code = 400

    def __init__(self, mensaje: str):
        super().__init__(mensaje)
        self.mensaje = mensaje


class DatoInvalido(ErrorDeNegocio):
    status_code = 400


class NoAutenticado(ErrorDeNegocio):
    status_code = 401


class SinPermiso(ErrorDeNegocio):
    status_code = 403


class NoEncontrado(ErrorDeNegocio):
    status_code = 404


class ReglaDeNegocio(ErrorDeNegocio):
    status_code = 409


async def _manejar_error_de_negocio(_request: Request, exc: ErrorDeNegocio) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.mensaje})


def registrar_manejadores(app: FastAPI) -> None:
    app.add_exception_handler(ErrorDeNegocio, _manejar_error_de_negocio)
```

`backend/app/core/permisos.py`:
```python
"""Constantes de dominio de permisos: ÚNICA fuente de módulos, recursos,
acciones, roles de sistema y etiquetas. Nunca escribir estos literales fuera
de este archivo."""
from dataclasses import dataclass
from enum import Enum


class Modulo(str, Enum):
    CLIENTES = "clientes"
    PROVEEDORES = "proveedores"
    PRODUCTOS = "productos"
    STOCK = "stock"
    VENTAS = "ventas"
    CAJA = "caja"
    CONFIGURACION = "configuracion"
    USUARIOS = "usuarios"
    AUDITORIA = "auditoria"
    IMPORTACION = "importacion"  # sesión 08
    REPORTES = "reportes"  # sesión 09


class Recurso(str, Enum):
    """Operaciones puntuales que se pueden habilitar sin dar el módulo entero."""

    DOLAR_CAMBIO_MASIVO = "dolar.cambio_masivo"
    CAJA_ARQUEO = "caja.arqueo"
    CAJA_RETIRO = "caja.retiro"
    VENTA_DESCUENTO = "venta.descuento"
    VENTA_ANULAR = "venta.anular"
    STOCK_BAJA = "stock.baja"
    STOCK_AUDITORIA = "stock.auditoria"
    STOCK_MOTIVOS_BAJA = "stock.motivos_baja"
    PROMOCIONES = "configuracion.promociones"


ACCIONES = ("ver", "crear", "editar", "eliminar")

ROL_ADMIN = "admin"
ROL_SUPERVISOR = "supervisor"
ROL_VENDEDOR = "vendedor"
ROLES_SISTEMA = (ROL_ADMIN, ROL_SUPERVISOR, ROL_VENDEDOR)

LABEL_MODULO = {
    Modulo.CLIENTES: "Clientes",
    Modulo.PROVEEDORES: "Proveedores",
    Modulo.PRODUCTOS: "Productos",
    Modulo.STOCK: "Stock",
    Modulo.VENTAS: "Ventas",
    Modulo.CAJA: "Caja",
    Modulo.CONFIGURACION: "Configuración",
    Modulo.USUARIOS: "Usuarios",
    Modulo.AUDITORIA: "Auditoría",
    Modulo.IMPORTACION: "Importación",
    Modulo.REPORTES: "Reportes",
}

LABEL_RECURSO = {
    Recurso.DOLAR_CAMBIO_MASIVO: "Cambio masivo del dólar",
    Recurso.CAJA_ARQUEO: "Arqueo y cierre de turno",
    Recurso.CAJA_RETIRO: "Retiros de efectivo",
    Recurso.VENTA_DESCUENTO: "Descuentos en ventas",
    Recurso.VENTA_ANULAR: "Anulación de ventas",
    Recurso.STOCK_BAJA: "Bajas de stock",
    Recurso.STOCK_AUDITORIA: "Conteos de inventario",
    Recurso.STOCK_MOTIVOS_BAJA: "Motivos de baja",
    Recurso.PROMOCIONES: "Promociones",
}

# A qué módulo cuelga cada recurso (define el árbol de permisos).
MODULO_DE_RECURSO = {
    Recurso.DOLAR_CAMBIO_MASIVO: Modulo.PROVEEDORES,
    Recurso.CAJA_ARQUEO: Modulo.CAJA,
    Recurso.CAJA_RETIRO: Modulo.CAJA,
    Recurso.VENTA_DESCUENTO: Modulo.VENTAS,
    Recurso.VENTA_ANULAR: Modulo.VENTAS,
    Recurso.STOCK_BAJA: Modulo.STOCK,
    Recurso.STOCK_AUDITORIA: Modulo.STOCK,
    Recurso.STOCK_MOTIVOS_BAJA: Modulo.STOCK,
    Recurso.PROMOCIONES: Modulo.CONFIGURACION,
}

# Acciones con sentido en cada recurso (el resto se muestra "—" y se guarda FALSE).
ACCIONES_DE_RECURSO = {
    Recurso.DOLAR_CAMBIO_MASIVO: ("editar",),
    Recurso.CAJA_ARQUEO: ("crear",),
    Recurso.CAJA_RETIRO: ("crear",),
    Recurso.VENTA_DESCUENTO: ("crear",),
    Recurso.VENTA_ANULAR: ("eliminar",),
    Recurso.STOCK_BAJA: ("crear",),
    Recurso.STOCK_AUDITORIA: ("crear",),
    Recurso.STOCK_MOTIVOS_BAJA: ("editar",),
    Recurso.PROMOCIONES: ("ver", "crear", "editar"),
}

# Módulos cuyo permiso general no admite las 4 acciones.
ACCIONES_DE_MODULO = {
    Modulo.AUDITORIA: ("ver",),
    Modulo.REPORTES: ("ver",),
    Modulo.IMPORTACION: ("crear",),
}

# Verbo de cada acción en las etiquetas de "Accesos permitidos".
VERBO_DE_ACCION = {"ver": "Consultar", "crear": "Registrar", "editar": "Modificar", "eliminar": "Realizar"}

# Casilleros de módulo completo del catálogo de accesos (el resto sale de los recursos).
ACCESOS_DE_MODULO = (
    (Modulo.CONFIGURACION, "ver", "Acceso a tablas y configuración"),
    (Modulo.USUARIOS, "crear", "Crear usuarios"),
    (Modulo.AUDITORIA, "ver", "Consultar la auditoría"),
    (Modulo.IMPORTACION, "crear", "Importar datos desde Excel"),
    (Modulo.REPORTES, "ver", "Consultar reportes"),
)


def acciones_aplicables(modulo: Modulo, recurso: Recurso | None = None) -> tuple[str, ...]:
    if recurso is not None:
        return ACCIONES_DE_RECURSO[recurso]
    return ACCIONES_DE_MODULO.get(modulo, ACCIONES)


def recursos_de_modulo(modulo: Modulo) -> list[Recurso]:
    return [r for r in Recurso if MODULO_DE_RECURSO[r] is modulo]


def validar_destino(modulo: str, recurso: str | None) -> tuple[Modulo, Recurso | None]:
    """Convierte y valida (módulo, recurso). ValueError si no existen o el
    recurso no pertenece al módulo."""
    try:
        modulo_enum = Modulo(modulo)
        recurso_enum = Recurso(recurso) if recurso else None
    except ValueError as exc:
        raise ValueError(f"Módulo o recurso desconocido: {modulo}/{recurso}") from exc
    if recurso_enum is not None and MODULO_DE_RECURSO[recurso_enum] is not modulo_enum:
        raise ValueError(f"El recurso '{recurso}' no pertenece al módulo '{modulo}'")
    return modulo_enum, recurso_enum


@dataclass(frozen=True)
class Acceso:
    """Un casillero de "Accesos permitidos" = una acción sobre módulo o recurso."""

    clave: str
    modulo: Modulo
    recurso: Recurso | None
    accion: str
    label: str


def clave_acceso(modulo: Modulo, recurso: Recurso | None, accion: str) -> str:
    return f"{modulo.value}:{recurso.value if recurso else ''}:{accion}"


def _minuscula_inicial(texto: str) -> str:
    return texto[:1].lower() + texto[1:]


def catalogo_accesos() -> list[Acceso]:
    accesos = [
        Acceso(clave_acceso(modulo, None, accion), modulo, None, accion, label)
        for modulo, accion, label in ACCESOS_DE_MODULO
    ]
    for recurso in Recurso:
        modulo = MODULO_DE_RECURSO[recurso]
        for accion in ACCIONES_DE_RECURSO[recurso]:
            label = f"{VERBO_DE_ACCION[accion]}: {_minuscula_inicial(LABEL_RECURSO[recurso])}"
            accesos.append(Acceso(clave_acceso(modulo, recurso, accion), modulo, recurso, accion, label))
    return accesos


def acceso_por_clave(clave: str) -> Acceso | None:
    return next((a for a in catalogo_accesos() if a.clave == clave), None)
```

En `backend/main.py`: importar `from app.core.errores import registrar_manejadores` y llamar `registrar_manejadores(app)` inmediatamente después de crear `app = FastAPI(...)`.

- [ ] **Step 4: Correr y ver que pasa**

Run: `docker compose exec backend pytest tests/test_errores.py tests/test_permisos_catalogo.py -v` → todos PASS; luego la suite completa.

- [ ] **Step 5: Commit** — `feat(auth): errores de negocio y constantes de permisos`.

---

### Task 2: Migración 0002, modelos y seed de roles, admin y permisos

**Files:**
- Create: `backend/migrations/versions/0002_auth_usuarios.py`, `backend/app/models/usuarios.py`, `backend/app/models/permisos.py`, `backend/app/models/sesiones.py`
- Modify: `backend/app/models/__init__.py`, `backend/migrations/seed.sql`
- Test: `backend/tests/test_modelo_usuarios.py`

**Interfaces:**
- Consumes: `Base`, `ROL_ADMIN`.
- Produces: modelos `Rol` (`id, nombre, descripcion, es_sistema, activo, created_at, updated_at`), `Usuario` (`id, username, email, password_hash, nombre, rol_id, rol` [relación joined], `activo, fecha_nacimiento, celular, created_at, updated_at, ultimo_acceso`; propiedades `debe_cambiar_password` = `ultimo_acceso is None`, `es_admin` = `rol.nombre == ROL_ADMIN`), `RolPermiso` / `UsuarioPermiso` (`modulo, recurso, puede_ver, puede_crear, puede_editar, puede_eliminar`, método `puede(accion) -> bool`), `ResultadoAcceso` (`EXITOSO="exitoso"`, `FALLIDO="fallido"`), `HistorialAcceso` (`usuario_id, timestamp, ip_origen, resultado, detalle`), `Sesion` (`usuario_id, jti, creada_en, expira_en, revocada, ip_origen`).

- [ ] **Step 1: Tests que fallan**

`backend/tests/test_modelo_usuarios.py`:
```python
import bcrypt
import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.core.utils import ahora_db
from app.models import HistorialAcceso, ResultadoAcceso, Rol, RolPermiso, Usuario
from tests.conftest import BACKEND_DIR, ejecutar_sql


def _rol(db, nombre):
    return db.scalar(select(Rol).where(Rol.nombre == nombre))


def test_seed_crea_roles_de_sistema_y_admin(db):
    nombres = db.scalars(select(Rol.nombre).where(Rol.es_sistema.is_(True)).order_by(Rol.nombre)).all()
    assert nombres == ["admin", "supervisor", "vendedor"]
    admin = db.scalar(select(Usuario).where(Usuario.username == "admin"))
    assert admin.rol.nombre == "admin" and admin.es_admin
    assert admin.debe_cambiar_password  # ultimo_acceso NULL
    assert bcrypt.checkpw(b"Admin1234!", admin.password_hash.encode())


def test_seed_de_permisos(db):
    supervisor = _rol(db, "supervisor")
    fila = db.scalar(select(RolPermiso).where(RolPermiso.rol_id == supervisor.id, RolPermiso.modulo == "ventas", RolPermiso.recurso.is_(None)))
    assert (fila.puede_ver, fila.puede_crear, fila.puede_editar, fila.puede_eliminar) == (True, True, True, False)
    anular = db.scalar(select(RolPermiso).where(RolPermiso.rol_id == supervisor.id, RolPermiso.recurso == "venta.anular"))
    assert anular.puede("eliminar") and not anular.puede("crear")
    vendedor = _rol(db, "vendedor")
    arqueo = db.scalar(select(RolPermiso).where(RolPermiso.rol_id == vendedor.id, RolPermiso.recurso == "caja.arqueo"))
    assert arqueo.puede_crear


def test_seed_idempotente(db):
    antes = db.scalar(select(func.count()).select_from(RolPermiso))
    ejecutar_sql(db.connection(), BACKEND_DIR / "migrations" / "seed.sql")
    ejecutar_sql(db.connection(), BACKEND_DIR / "migrations" / "seed.sql")
    assert db.scalar(select(func.count()).select_from(RolPermiso)) == antes
    assert db.scalar(select(func.count()).select_from(Usuario).where(Usuario.username == "admin")) == 1


def test_permiso_de_modulo_no_se_duplica_con_recurso_null(db):
    vendedor = _rol(db, "vendedor")
    db.add(RolPermiso(rol_id=vendedor.id, modulo="clientes", recurso=None))
    with pytest.raises(IntegrityError):
        db.flush()


@pytest.mark.parametrize("sentencia", ["UPDATE historial_accesos SET detalle = 'x'", "DELETE FROM historial_accesos"])
def test_historial_de_accesos_es_inmutable(db, sentencia):
    admin = db.scalar(select(Usuario).where(Usuario.username == "admin"))
    db.add(HistorialAcceso(usuario_id=admin.id, timestamp=ahora_db(), resultado=ResultadoAcceso.EXITOSO))
    db.flush()
    with pytest.raises(DBAPIError) as error:
        db.execute(text(sentencia))
    assert "solo inserción" in str(error.value)


def test_enum_resultado_se_guarda_en_minuscula(db):
    admin = db.scalar(select(Usuario).where(Usuario.username == "admin"))
    db.add(HistorialAcceso(usuario_id=admin.id, timestamp=ahora_db(), resultado=ResultadoAcceso.FALLIDO, detalle="Contraseña incorrecta"))
    db.flush()
    assert db.execute(text("SELECT resultado::text FROM historial_accesos ORDER BY id DESC LIMIT 1")).scalar_one() == "fallido"
```

- [ ] **Step 2: Correr y ver que falla**

Run: `docker compose exec backend pytest tests/test_modelo_usuarios.py -v` → FAIL (`ImportError: cannot import name 'HistorialAcceso'`).

- [ ] **Step 3: Migración**

`backend/migrations/versions/0002_auth_usuarios.py`:
```python
"""Autenticación y usuarios: roles, usuarios, permisos, historial de accesos y sesiones.

Revision ID: 0002
Revises: 0001
"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE roles (
            id          BIGSERIAL PRIMARY KEY,
            nombre      VARCHAR(50) NOT NULL UNIQUE,
            descripcion VARCHAR(255),
            es_sistema  BOOLEAN NOT NULL DEFAULT FALSE,   -- admin/supervisor/vendedor: no se borran ni renombran
            activo      BOOLEAN NOT NULL DEFAULT TRUE,
            created_at  TIMESTAMP NOT NULL DEFAULT now(),
            updated_at  TIMESTAMP NOT NULL DEFAULT now()
        );

        CREATE TABLE usuarios (
            id               BIGSERIAL PRIMARY KEY,
            username         VARCHAR(50) NOT NULL UNIQUE,
            email            VARCHAR(255) UNIQUE,
            password_hash    VARCHAR(255) NOT NULL,
            nombre           VARCHAR(150) NOT NULL,
            rol_id           BIGINT NOT NULL REFERENCES roles (id) ON DELETE RESTRICT,
            activo           BOOLEAN NOT NULL DEFAULT TRUE,
            fecha_nacimiento DATE,
            celular          VARCHAR(20),
            created_at       TIMESTAMP NOT NULL DEFAULT now(),
            updated_at       TIMESTAMP NOT NULL DEFAULT now(),
            ultimo_acceso    TIMESTAMP              -- NULL = debe cambiar la contraseña
        );
        CREATE INDEX ix_usuarios_rol_id ON usuarios (rol_id);

        ALTER TABLE configuracion_sistema
            ADD CONSTRAINT fk_configuracion_sistema_updated_by
            FOREIGN KEY (updated_by) REFERENCES usuarios (id) ON DELETE SET NULL;

        -- NULLS NOT DISTINCT (PG15): sin él, las filas con recurso NULL se duplican
        -- y el ON CONFLICT del seed no hace nada.
        CREATE TABLE rol_permisos (
            id             BIGSERIAL PRIMARY KEY,
            rol_id         BIGINT NOT NULL REFERENCES roles (id) ON DELETE CASCADE,
            modulo         VARCHAR(50) NOT NULL,
            recurso        VARCHAR(100),            -- NULL = módulo completo
            puede_ver      BOOLEAN NOT NULL DEFAULT FALSE,
            puede_crear    BOOLEAN NOT NULL DEFAULT FALSE,
            puede_editar   BOOLEAN NOT NULL DEFAULT FALSE,
            puede_eliminar BOOLEAN NOT NULL DEFAULT FALSE,
            CONSTRAINT uq_rol_permisos_rol_modulo_recurso UNIQUE NULLS NOT DISTINCT (rol_id, modulo, recurso)
        );

        -- Overrides individuales: siempre aditivos (OR con el rol).
        CREATE TABLE usuario_permisos (
            id             BIGSERIAL PRIMARY KEY,
            usuario_id     BIGINT NOT NULL REFERENCES usuarios (id) ON DELETE CASCADE,
            modulo         VARCHAR(50) NOT NULL,
            recurso        VARCHAR(100),
            puede_ver      BOOLEAN NOT NULL DEFAULT FALSE,
            puede_crear    BOOLEAN NOT NULL DEFAULT FALSE,
            puede_editar   BOOLEAN NOT NULL DEFAULT FALSE,
            puede_eliminar BOOLEAN NOT NULL DEFAULT FALSE,
            CONSTRAINT uq_usuario_permisos_usuario_modulo_recurso UNIQUE NULLS NOT DISTINCT (usuario_id, modulo, recurso)
        );

        CREATE TYPE resultado_acceso AS ENUM ('exitoso', 'fallido');

        -- Append-only. Los usuarios nunca se borran (solo se desactivan), así que
        -- el ON DELETE CASCADE no choca con el trigger que bloquea DELETE.
        CREATE TABLE historial_accesos (
            id         BIGSERIAL PRIMARY KEY,
            usuario_id BIGINT NOT NULL REFERENCES usuarios (id) ON DELETE CASCADE,
            timestamp  TIMESTAMP NOT NULL DEFAULT now(),
            ip_origen  VARCHAR(45),
            resultado  resultado_acceso NOT NULL,
            detalle    VARCHAR(255)          -- motivo del fallo
        );
        CREATE INDEX ix_historial_accesos_usuario_timestamp ON historial_accesos (usuario_id, timestamp);

        CREATE FUNCTION historial_bloquear_modificacion() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'La tabla historial_accesos es de solo inserción (operación % bloqueada)', TG_OP
                USING ERRCODE = 'insufficient_privilege';
        END;
        $$;
        CREATE TRIGGER trg_historial_no_update BEFORE UPDATE ON historial_accesos
            FOR EACH STATEMENT EXECUTE FUNCTION historial_bloquear_modificacion();
        CREATE TRIGGER trg_historial_no_delete BEFORE DELETE ON historial_accesos
            FOR EACH STATEMENT EXECUTE FUNCTION historial_bloquear_modificacion();

        -- Refresh tokens emitidos: se guarda solo el jti.
        CREATE TABLE sesiones (
            id         BIGSERIAL PRIMARY KEY,
            usuario_id BIGINT NOT NULL REFERENCES usuarios (id) ON DELETE CASCADE,
            jti        VARCHAR(64) NOT NULL UNIQUE,
            creada_en  TIMESTAMP NOT NULL DEFAULT now(),
            expira_en  TIMESTAMP NOT NULL,   -- ventana de INACTIVIDAD deslizante, no el vencimiento del JWT
            revocada   BOOLEAN NOT NULL DEFAULT FALSE,
            ip_origen  VARCHAR(45)
        );
        CREATE INDEX ix_sesiones_usuario_id ON sesiones (usuario_id);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE sesiones;
        DROP TABLE historial_accesos;
        DROP FUNCTION historial_bloquear_modificacion();
        DROP TYPE resultado_acceso;
        DROP TABLE usuario_permisos;
        DROP TABLE rol_permisos;
        ALTER TABLE configuracion_sistema DROP CONSTRAINT fk_configuracion_sistema_updated_by;
        DROP TABLE usuarios;
        DROP TABLE roles;
        """
    )
```

- [ ] **Step 4: Modelos**

`backend/app/models/usuarios.py`:
```python
from datetime import date, datetime

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.permisos import ROL_ADMIN


class Rol(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(50), unique=True)
    descripcion: Mapped[str | None] = mapped_column(String(255))
    es_sistema: Mapped[bool] = mapped_column(Boolean, default=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True)
    email: Mapped[str | None] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    nombre: Mapped[str] = mapped_column(String(150))
    rol_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("roles.id", ondelete="RESTRICT"))
    rol: Mapped[Rol] = relationship(lazy="joined")
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    fecha_nacimiento: Mapped[date | None] = mapped_column(Date)
    celular: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    ultimo_acceso: Mapped[datetime | None] = mapped_column(DateTime)  # NULL = debe cambiar la contraseña

    @property
    def debe_cambiar_password(self) -> bool:
        return self.ultimo_acceso is None

    @property
    def es_admin(self) -> bool:
        return self.rol is not None and self.rol.nombre == ROL_ADMIN
```

`backend/app/models/permisos.py`:
```python
from sqlalchemy import BigInteger, Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ColumnasPermiso:
    """Columnas comunes a rol_permisos y usuario_permisos (una sola definición)."""

    modulo: Mapped[str] = mapped_column(String(50))
    recurso: Mapped[str | None] = mapped_column(String(100))  # NULL = módulo completo
    puede_ver: Mapped[bool] = mapped_column(Boolean, default=False)
    puede_crear: Mapped[bool] = mapped_column(Boolean, default=False)
    puede_editar: Mapped[bool] = mapped_column(Boolean, default=False)
    puede_eliminar: Mapped[bool] = mapped_column(Boolean, default=False)

    def puede(self, accion: str) -> bool:
        return bool(getattr(self, f"puede_{accion}"))


class RolPermiso(ColumnasPermiso, Base):
    __tablename__ = "rol_permisos"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    rol_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("roles.id", ondelete="CASCADE"))


class UsuarioPermiso(ColumnasPermiso, Base):
    """Overrides individuales: siempre aditivos (OR con los del rol)."""

    __tablename__ = "usuario_permisos"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    usuario_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("usuarios.id", ondelete="CASCADE"))
```

`backend/app/models/sesiones.py`:
```python
from datetime import datetime
from enum import Enum

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ResultadoAcceso(str, Enum):
    EXITOSO = "exitoso"
    FALLIDO = "fallido"


class HistorialAcceso(Base):
    """Intentos de ingreso (append-only en la base). Distinto de la auditoría."""

    __tablename__ = "historial_accesos"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    usuario_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("usuarios.id", ondelete="CASCADE"))
    timestamp: Mapped[datetime] = mapped_column(DateTime)
    ip_origen: Mapped[str | None] = mapped_column(String(45))
    resultado: Mapped[ResultadoAcceso] = mapped_column(
        SAEnum(ResultadoAcceso, name="resultado_acceso", values_callable=lambda e: [i.value for i in e])
    )
    detalle: Mapped[str | None] = mapped_column(String(255))


class Sesion(Base):
    """Refresh token emitido (se guarda solo el jti) con su ventana de inactividad."""

    __tablename__ = "sesiones"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    usuario_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("usuarios.id", ondelete="CASCADE"))
    jti: Mapped[str] = mapped_column(String(64), unique=True)
    creada_en: Mapped[datetime] = mapped_column(DateTime)
    expira_en: Mapped[datetime] = mapped_column(DateTime)  # ventana deslizante de inactividad
    revocada: Mapped[bool] = mapped_column(Boolean, default=False)
    ip_origen: Mapped[str | None] = mapped_column(String(45))
```

`backend/app/models/__init__.py`:
```python
"""Registro de todos los modelos (lo importan main.lifespan y Alembic)."""
from app.models.auditoria import Auditoria
from app.models.configuracion import ConfiguracionSistema
from app.models.motivo_baja import MotivoBaja
from app.models.permisos import RolPermiso, UsuarioPermiso
from app.models.sesiones import HistorialAcceso, ResultadoAcceso, Sesion
from app.models.usuarios import Rol, Usuario

__all__ = [
    "Auditoria",
    "ConfiguracionSistema",
    "HistorialAcceso",
    "MotivoBaja",
    "ResultadoAcceso",
    "Rol",
    "RolPermiso",
    "Sesion",
    "Usuario",
    "UsuarioPermiso",
]
```

- [ ] **Step 5: Seed (agregar al final de `backend/migrations/seed.sql`)**

```sql
-- ===== Sesión 02: roles de sistema, usuario admin y permisos =====
DO $seed02$
BEGIN
    IF to_regclass('public.roles') IS NULL THEN
        RAISE NOTICE 'Sin tabla roles: se saltea el bloque de la sesión 02';
        RETURN;
    END IF;

    INSERT INTO roles (nombre, descripcion, es_sistema) VALUES
        ('admin', 'Acceso total al sistema', TRUE),
        ('supervisor', 'Gestión del local: ventas, clientes, caja y vendedores', TRUE),
        ('vendedor', 'Ventas y consulta de productos y stock', TRUE)
    ON CONFLICT (nombre) DO NOTHING;

    -- Contraseña inicial Admin1234! (bcrypt costo 12). ultimo_acceso NULL obliga a cambiarla.
    INSERT INTO usuarios (username, password_hash, nombre, rol_id)
    SELECT 'admin', '$2b$12$mi4/vU9mVGM0LXSk8uQ.hea/EX4edBSZ83NjqocvyD8paS5pus5I2', 'Administrador', r.id
    FROM roles r WHERE r.nombre = 'admin'
    ON CONFLICT (username) DO NOTHING;

    -- Permisos generales por módulo (recurso NULL): ver, crear, editar, eliminar.
    INSERT INTO rol_permisos (rol_id, modulo, recurso, puede_ver, puede_crear, puede_editar, puede_eliminar)
    SELECT r.id, p.modulo, NULL, p.v, p.c, p.e, p.x
    FROM (VALUES
        ('admin', 'clientes', TRUE, TRUE, TRUE, TRUE),
        ('admin', 'proveedores', TRUE, TRUE, TRUE, TRUE),
        ('admin', 'productos', TRUE, TRUE, TRUE, TRUE),
        ('admin', 'stock', TRUE, TRUE, TRUE, TRUE),
        ('admin', 'ventas', TRUE, TRUE, TRUE, TRUE),
        ('admin', 'caja', TRUE, TRUE, TRUE, TRUE),
        ('admin', 'configuracion', TRUE, TRUE, TRUE, TRUE),
        ('admin', 'usuarios', TRUE, TRUE, TRUE, TRUE),
        ('admin', 'auditoria', TRUE, FALSE, FALSE, FALSE),
        ('admin', 'importacion', FALSE, TRUE, FALSE, FALSE),
        ('admin', 'reportes', TRUE, FALSE, FALSE, FALSE),
        ('supervisor', 'clientes', TRUE, TRUE, TRUE, FALSE),
        ('supervisor', 'proveedores', TRUE, FALSE, FALSE, FALSE),
        ('supervisor', 'productos', TRUE, FALSE, FALSE, FALSE),
        ('supervisor', 'stock', TRUE, FALSE, FALSE, FALSE),
        ('supervisor', 'ventas', TRUE, TRUE, TRUE, FALSE),
        ('supervisor', 'caja', TRUE, TRUE, FALSE, FALSE),
        ('supervisor', 'usuarios', TRUE, TRUE, TRUE, FALSE),
        ('supervisor', 'reportes', TRUE, FALSE, FALSE, FALSE),
        ('vendedor', 'clientes', TRUE, TRUE, FALSE, FALSE),
        ('vendedor', 'productos', TRUE, FALSE, FALSE, FALSE),
        ('vendedor', 'stock', TRUE, FALSE, FALSE, FALSE),
        ('vendedor', 'ventas', TRUE, TRUE, FALSE, FALSE),
        ('vendedor', 'caja', TRUE, FALSE, FALSE, FALSE)
    ) AS p (rol, modulo, v, c, e, x)
    JOIN roles r ON r.nombre = p.rol
    ON CONFLICT (rol_id, modulo, recurso) DO NOTHING;

    -- Permisos por recurso puntual.
    INSERT INTO rol_permisos (rol_id, modulo, recurso, puede_ver, puede_crear, puede_editar, puede_eliminar)
    SELECT r.id, p.modulo, p.recurso, p.v, p.c, p.e, p.x
    FROM (VALUES
        ('supervisor', 'ventas', 'venta.descuento', FALSE, TRUE, FALSE, FALSE),
        ('supervisor', 'ventas', 'venta.anular', FALSE, FALSE, FALSE, TRUE),
        ('supervisor', 'stock', 'stock.baja', FALSE, TRUE, FALSE, FALSE),
        ('supervisor', 'stock', 'stock.auditoria', FALSE, TRUE, FALSE, FALSE),
        ('supervisor', 'configuracion', 'configuracion.promociones', TRUE, TRUE, TRUE, FALSE),
        ('vendedor', 'ventas', 'venta.descuento', FALSE, TRUE, FALSE, FALSE),
        ('vendedor', 'stock', 'stock.baja', FALSE, TRUE, FALSE, FALSE),
        ('vendedor', 'stock', 'stock.auditoria', FALSE, TRUE, FALSE, FALSE),
        ('vendedor', 'caja', 'caja.arqueo', FALSE, TRUE, FALSE, FALSE)
    ) AS p (rol, modulo, recurso, v, c, e, x)
    JOIN roles r ON r.nombre = p.rol
    ON CONFLICT (rol_id, modulo, recurso) DO NOTHING;
END
$seed02$;
```

- [ ] **Step 6: Migrar y correr los tests**

```bash
docker compose restart backend && docker compose exec backend alembic current   # 0002 (head)
docker compose exec backend pytest tests/test_modelo_usuarios.py -v             # todos PASS
docker compose exec backend pytest                                              # suite completa
docker compose exec backend alembic downgrade -1 && docker compose exec backend alembic upgrade head && docker compose restart backend
```

- [ ] **Step 7: Commit** — `feat(auth): migración 0002, modelos de usuarios y seed de roles y permisos`.

---

### Task 3: Service de autenticación (contraseñas, JWT, sesiones, reset)

**Files:**
- Create: `backend/app/services/auth.py`, `backend/app/core/email.py`
- Modify: `backend/config.py`, `.env.example`, `backend/tests/conftest.py`
- Test: `backend/tests/test_auth_service.py`, `backend/tests/test_config.py` (agregar un test)

**Interfaces:**
- Consumes: modelos de la Task 2, `registrar_auditoria`, `ahora`, `ahora_db`, `NoAutenticado`.
- Produces (en `app.services.auth`): `TokenInvalido(Exception)`, `CredencialesInvalidas(NoAutenticado)` (mensaje `MENSAJE_CREDENCIALES = "Usuario o contraseña incorrectos"`), `hash_password(p) -> str`, `verificar_password(p, h) -> bool`, `crear_access_token(usuario_id, sid) -> str`, `verificar_token(token, tipo) -> dict`, `generar_tokens(db, usuario, ip) -> tuple[str, str, Sesion]` (access, refresh, sesión), `registrar_actividad(db, sesion)`, `sesion_vigente(db, refresh) -> Sesion`, `sesion_de_access(db, datos_access) -> Sesion`, `refrescar_access_token(db, refresh) -> str`, `revocar_sesion(db, refresh) -> Sesion | None`, `revocar_sesiones_de_usuario(db, usuario_id)`, `autenticar_usuario(db, username, password, ip) -> Usuario`, `marcar_acceso(db, usuario)`, `debe_cambiar_password(usuario) -> bool`, `generar_token_reset(usuario) -> str`, `validar_token_reset(db, token) -> Usuario`, `solicitar_reset(db, username, ip) -> None`, `cambiar_password(db, usuario, nueva, *, autor_id, ip, debe_cambiarla)`.
- Produces (conftest): fixture `crear_usuario(rol="vendedor", *, username=None, password="Clave1234", activo=True, debe_cambiar=False, nombre="Usuario De Prueba", **extra) -> Usuario` (`rol` acepta nombre o instancia `Rol`).
- Produces (`app.core.email`): `smtp_configurado()`, `enviar_email(destinatario, asunto, cuerpo) -> bool`, `enviar_reset_password(destinatario, nombre, token) -> bool` (sin SMTP loguea y devuelve False).
- Produces (config): `settings.BCRYPT_ROUNDS` (12; `.env.example` lo documenta; conftest fija `"4"`).

- [ ] **Step 1: Config y conftest**

En `backend/config.py`, dentro de "JWT y sesión", agregar:
```python
    BCRYPT_ROUNDS: int = 12  # costo de bcrypt (los tests usan 4 para ir rápido)
```
y en el validador reemplazar la condición del secreto por:
```python
        secretos_de_ejemplo = {"cambiar-en-produccion", "cambiar-por-un-secreto-largo-y-aleatorio"}
        if self.APP_ENV == "production" and (
            self.JWT_SECRET in secretos_de_ejemplo or len(self.JWT_SECRET) < 32
        ):
```
En `.env.example`, bajo `JWT y sesión`, agregar `BCRYPT_ROUNDS=12`.

En `backend/tests/test_config.py` agregar:
```python
def test_produccion_rechaza_el_secreto_de_ejemplo():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, APP_ENV="production", JWT_SECRET="cambiar-por-un-secreto-largo-y-aleatorio")
```
(usar los imports que ese archivo ya tenga; si faltan, `import pytest`, `from pydantic import ValidationError`, `from config import Settings`).

En `backend/tests/conftest.py`, junto a los otros `os.environ[...]` del principio:
```python
os.environ["BCRYPT_ROUNDS"] = "4"
```
y agregar al final:
```python
@pytest.fixture
def crear_usuario(db):
    """Fábrica de usuarios de prueba (por defecto: vendedor activo que ya cambió la contraseña)."""
    import itertools

    from sqlalchemy import select

    from app.core.utils import ahora_db
    from app.models import Rol, Usuario
    from app.services.auth import hash_password

    numeros = itertools.count(1)

    def _crear(rol="vendedor", *, username=None, password="Clave1234", activo=True, debe_cambiar=False,
               nombre="Usuario De Prueba", **extra):
        rol_obj = rol if isinstance(rol, Rol) else db.scalar(select(Rol).where(Rol.nombre == rol))
        usuario = Usuario(
            username=username or f"prueba{next(numeros)}",
            nombre=nombre,
            password_hash=hash_password(password),
            rol_id=rol_obj.id,
            activo=activo,
            ultimo_acceso=None if debe_cambiar else ahora_db(),
            **extra,
        )
        db.add(usuario)
        db.flush()
        return usuario

    return _crear
```

- [ ] **Step 2: Tests que fallan**

`backend/tests/test_auth_service.py`:
```python
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.core.utils import ahora, ahora_db
from app.models import Auditoria, HistorialAcceso, ResultadoAcceso, Sesion
from app.services import auth


def _ultima_auditoria(db, accion):
    return db.scalar(select(Auditoria).where(Auditoria.accion == accion).order_by(Auditoria.id.desc()))


# ---------- Contraseñas ----------
def test_hash_y_verificacion_de_password():
    h = auth.hash_password("Secreta123")
    assert h.startswith("$2b$") and auth.verificar_password("Secreta123", h)
    assert not auth.verificar_password("otra", h)
    assert not auth.verificar_password("Secreta123", "hash-roto")


# ---------- Tokens ----------
def test_verificar_token_valida_tipo_firma_y_vencimiento(db, crear_usuario):
    usuario = crear_usuario()
    access, refresh, sesion = auth.generar_tokens(db, usuario, "10.0.0.1")
    datos = auth.verificar_token(access, "access")
    assert datos["sub"] == str(usuario.id) and datos["sid"] == sesion.jti
    assert auth.verificar_token(refresh, "refresh")["jti"] == sesion.jti
    with pytest.raises(auth.TokenInvalido):
        auth.verificar_token(access, "refresh")
    with pytest.raises(auth.TokenInvalido):
        auth.verificar_token(access + "x", "access")
    with pytest.raises(auth.TokenInvalido):
        auth.verificar_token(None, "access")
    vencido = auth._codificar({"sub": "1", "tipo": "access", "sid": "x"}, ahora() - timedelta(seconds=1))
    with pytest.raises(auth.TokenInvalido):
        auth.verificar_token(vencido, "access")


def test_generar_tokens_crea_sesion_con_ventana_de_inactividad(db, crear_usuario):
    usuario = crear_usuario()
    _, _, sesion = auth.generar_tokens(db, usuario, "10.0.0.1")
    assert sesion.ip_origen == "10.0.0.1" and not sesion.revocada
    minutos = (sesion.expira_en - sesion.creada_en).total_seconds() / 60
    assert minutos == pytest.approx(30, abs=0.1)


def test_registrar_actividad_corre_la_ventana_con_tope(db, crear_usuario):
    usuario = crear_usuario()
    _, _, sesion = auth.generar_tokens(db, usuario, None)
    # Recién creada: correrla menos de un minuto no escribe.
    anterior = sesion.expira_en
    auth.registrar_actividad(db, sesion)
    assert sesion.expira_en == anterior
    # Con la ventana a punto de vencer, se corre hasta ahora + 30 min.
    sesion.expira_en = ahora_db() + timedelta(minutes=5)
    auth.registrar_actividad(db, sesion)
    assert sesion.expira_en > ahora_db() + timedelta(minutes=29)
    # Tope: nunca más allá de creada_en + 7 días.
    sesion.creada_en = ahora_db() - timedelta(days=7) + timedelta(minutes=10)
    sesion.expira_en = ahora_db()
    auth.registrar_actividad(db, sesion)
    assert sesion.expira_en <= sesion.creada_en + timedelta(days=7)


def test_sesion_vencida_por_inactividad_se_revoca(db, crear_usuario):
    usuario = crear_usuario()
    _, refresh, sesion = auth.generar_tokens(db, usuario, None)
    sesion.expira_en = ahora_db() - timedelta(seconds=1)
    db.flush()
    with pytest.raises(auth.TokenInvalido):
        auth.sesion_vigente(db, refresh)
    assert sesion.revocada


def test_refrescar_access_token(db, crear_usuario):
    usuario = crear_usuario()
    _, refresh, sesion = auth.generar_tokens(db, usuario, None)
    nuevo = auth.refrescar_access_token(db, refresh)
    assert auth.verificar_token(nuevo, "access")["sid"] == sesion.jti
    usuario.activo = False
    db.flush()
    with pytest.raises(auth.TokenInvalido):
        auth.refrescar_access_token(db, refresh)
    assert sesion.revocada


def test_revocar_sesion_es_idempotente(db, crear_usuario):
    usuario = crear_usuario()
    _, refresh, sesion = auth.generar_tokens(db, usuario, None)
    assert auth.revocar_sesion(db, refresh) is sesion and sesion.revocada
    assert auth.revocar_sesion(db, refresh) is sesion
    assert auth.revocar_sesion(db, "basura") is None
    with pytest.raises(auth.TokenInvalido):
        auth.sesion_vigente(db, refresh)


def test_revocar_sesiones_de_usuario(db, crear_usuario):
    usuario = crear_usuario()
    for _ in range(2):
        auth.generar_tokens(db, usuario, None)
    auth.revocar_sesiones_de_usuario(db, usuario.id)
    abiertas = db.scalars(select(Sesion).where(Sesion.usuario_id == usuario.id, Sesion.revocada.is_(False))).all()
    assert abiertas == []


# ---------- Login ----------
def test_login_exitoso_registra_historial_y_auditoria(db, crear_usuario):
    usuario = crear_usuario(username="maria", password="Clave1234")
    assert auth.autenticar_usuario(db, "  MARIA ", "Clave1234", "10.0.0.9") is usuario
    historial = db.scalar(select(HistorialAcceso).where(HistorialAcceso.usuario_id == usuario.id))
    assert historial.resultado is ResultadoAcceso.EXITOSO and historial.ip_origen == "10.0.0.9"
    registro = _ultima_auditoria(db, "auth.login")
    assert registro.usuario_id == usuario.id and registro.ip_origen == "10.0.0.9"


@pytest.mark.parametrize(
    "preparar, username, password, detalle",
    [
        (lambda u: None, "juana", "mala", "Contraseña incorrecta"),
        (lambda u: setattr(u, "activo", False), "juana", "Clave1234", "Usuario inactivo"),
        (lambda u: setattr(u.rol, "activo", False), "juana", "Clave1234", "Rol inactivo"),
    ],
)
def test_login_fallido_registra_el_motivo(db, crear_usuario, preparar, username, password, detalle):
    usuario = crear_usuario(username="juana", password="Clave1234")
    preparar(usuario)
    db.flush()
    with pytest.raises(auth.CredencialesInvalidas) as error:
        auth.autenticar_usuario(db, username, password, None)
    assert error.value.mensaje == "Usuario o contraseña incorrectos"
    historial = db.scalar(select(HistorialAcceso).where(HistorialAcceso.usuario_id == usuario.id))
    assert historial.resultado is ResultadoAcceso.FALLIDO and historial.detalle == detalle
    assert _ultima_auditoria(db, "auth.login_fallido").estado_nuevo["detalle"] == detalle


def test_login_de_usuario_inexistente_solo_audita(db):
    with pytest.raises(auth.CredencialesInvalidas):
        auth.autenticar_usuario(db, "nadie", "x", None)
    registro = _ultima_auditoria(db, "auth.login_fallido")
    assert registro.usuario_id is None
    assert registro.estado_nuevo == {"username": "nadie", "detalle": "Usuario inexistente"}


def test_marcar_acceso(db, crear_usuario):
    usuario = crear_usuario(debe_cambiar=True)
    assert auth.debe_cambiar_password(usuario)
    auth.marcar_acceso(db, usuario)
    assert not auth.debe_cambiar_password(usuario)


# ---------- Recuperación y cambio de contraseña ----------
def test_token_de_reset_es_de_un_solo_uso(db, crear_usuario):
    usuario = crear_usuario()
    token = auth.generar_token_reset(usuario)
    assert auth.validar_token_reset(db, token) is usuario
    auth.cambiar_password(db, usuario, "NuevaClave1", autor_id=usuario.id, ip=None, debe_cambiarla=False)
    with pytest.raises(auth.TokenInvalido):
        auth.validar_token_reset(db, token)


def test_token_de_reset_de_otro_tipo_no_sirve(db, crear_usuario):
    usuario = crear_usuario()
    access, _, _ = auth.generar_tokens(db, usuario, None)
    with pytest.raises(auth.TokenInvalido):
        auth.validar_token_reset(db, access)


def test_cambiar_password_revoca_sesiones_y_audita_sin_la_clave(db, crear_usuario):
    usuario = crear_usuario()
    _, refresh, _ = auth.generar_tokens(db, usuario, None)
    auth.cambiar_password(db, usuario, "OtraClave99", autor_id=None, ip="1.1.1.1", debe_cambiarla=True)
    assert auth.verificar_password("OtraClave99", usuario.password_hash)
    assert usuario.ultimo_acceso is None
    with pytest.raises(auth.TokenInvalido):
        auth.sesion_vigente(db, refresh)
    registro = _ultima_auditoria(db, "usuario.cambiar_password")
    assert registro.entidad_id == usuario.id
    assert "OtraClave99" not in str(registro.estado_nuevo)


def test_solicitar_reset_envia_solo_a_usuarios_activos_con_email(db, crear_usuario, monkeypatch):
    enviados = []
    monkeypatch.setattr(auth, "enviar_reset_password", lambda email, nombre, token: enviados.append((email, token)) or True)
    crear_usuario(username="conmail", email="conmail@example.com")
    crear_usuario(username="sinmail")
    crear_usuario(username="inactivo", email="inactivo@example.com", activo=False)
    for nombre in ("conmail", "sinmail", "inactivo", "noexiste"):
        auth.solicitar_reset(db, nombre, None)
    assert [e for e, _ in enviados] == ["conmail@example.com"]
    registros = db.scalars(select(Auditoria).where(Auditoria.accion == "auth.reset_solicitar")).all()
    assert len(registros) == 4
```

- [ ] **Step 3: Correr y ver que falla**

Run: `docker compose exec backend pytest tests/test_auth_service.py -v` → FAIL (`ModuleNotFoundError: app.services.auth` o `ImportError` de `enviar_reset_password`).

- [ ] **Step 4: Implementación**

`backend/app/core/email.py` (lo usa `solicitar_reset`; sus tests llegan en la Task 5):
```python
"""Envío de emails por SMTP (opcional: sin SMTP_HOST solo se loguea)."""
import logging
import smtplib
from email.message import EmailMessage

from config import settings

log = logging.getLogger(__name__)


def smtp_configurado() -> bool:
    return bool(settings.SMTP_HOST)


def enviar_email(destinatario: str, asunto: str, cuerpo: str) -> bool:
    if not smtp_configurado():
        log.warning("SMTP no configurado: no se envía '%s' a %s", asunto, destinatario)
        return False
    mensaje = EmailMessage()
    mensaje["From"] = settings.SMTP_FROM
    mensaje["To"] = destinatario
    mensaje["Subject"] = asunto
    mensaje.set_content(cuerpo)
    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as smtp:
            if settings.SMTP_TLS:
                smtp.starttls()
            if settings.SMTP_USER:
                smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD or "")
            smtp.send_message(mensaje)
    except (smtplib.SMTPException, OSError):
        log.exception("No se pudo enviar el email '%s' a %s", asunto, destinatario)
        return False
    return True


def enviar_reset_password(destinatario: str, nombre: str, token: str) -> bool:
    enlace = f"{settings.APP_URL.rstrip('/')}/reset-password?token={token}"
    cuerpo = (
        f"Hola {nombre}:\n\n"
        f"Para elegir una contraseña nueva entrá a:\n{enlace}\n\n"
        "El enlace vence en 30 minutos y sirve una sola vez. "
        "Si no lo pediste, ignorá este mensaje.\n"
    )
    return enviar_email(destinatario, f"{settings.APP_NAME}: recuperar contraseña", cuerpo)
```

`backend/app/services/auth.py`:
```python
"""Autenticación: contraseñas, tokens JWT y sesiones con ventana de inactividad.

- access token: 30 min, claim `sid` = jti de la sesión (se valida en cada request).
- refresh token: 7 días, claim `jti`; la fila de `sesiones` guarda la ventana
  deslizante de inactividad (`expira_en`), con tope `creada_en + 7 días`.
- reset token: 30 min, claim `pwd` = últimos 16 caracteres del hash actual
  (queda inválido apenas cambia la contraseña: un solo uso sin tabla).
"""
import secrets
from datetime import datetime, timedelta

import bcrypt
import jwt
from sqlalchemy import select, update

from app.core.auditoria import registrar_auditoria
from app.core.email import enviar_reset_password
from app.core.errores import NoAutenticado
from app.core.utils import ahora, ahora_db
from app.models import HistorialAcceso, ResultadoAcceso, Sesion, Usuario
from config import settings

MENSAJE_CREDENCIALES = "Usuario o contraseña incorrectos"
ACTIVIDAD_MINIMA = timedelta(minutes=1)  # registrar_actividad escribe como mucho una vez por minuto
RESET_MINUTOS = 30


class TokenInvalido(Exception):
    """Token ausente, mal firmado, vencido, de otro tipo o de una sesión caída."""


class CredencialesInvalidas(NoAutenticado):
    def __init__(self):
        super().__init__(MENSAJE_CREDENCIALES)


# ---------------------------------------------------------------- contraseñas
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(settings.BCRYPT_ROUNDS)).decode("ascii")


def verificar_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("ascii"))
    except ValueError:
        return False


# Hash señuelo: con usuario inexistente igual se paga el costo de bcrypt
# (el tiempo de respuesta no revela qué usernames existen).
_HASH_SENUELO = hash_password("señuelo-para-igualar-tiempos")


# ---------------------------------------------------------------- tokens
def _codificar(claims: dict, vence: datetime) -> str:
    return jwt.encode({**claims, "iat": ahora(), "exp": vence}, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def crear_access_token(usuario_id: int, sid: str) -> str:
    vence = ahora() + timedelta(minutes=settings.JWT_ACCESS_TOKEN_MINUTES)
    return _codificar({"sub": str(usuario_id), "tipo": "access", "sid": sid}, vence)


def verificar_token(token: str | None, tipo: str) -> dict:
    if not token:
        raise TokenInvalido("Falta el token")
    try:
        datos = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
            options={"require": ["exp", "sub", "tipo"]},
        )
    except jwt.PyJWTError as exc:
        raise TokenInvalido(str(exc)) from exc
    if datos.get("tipo") != tipo:
        raise TokenInvalido("Tipo de token incorrecto")
    return datos


# ---------------------------------------------------------------- sesiones
def _fin_de_ventana(sesion: Sesion) -> datetime:
    inactividad = ahora_db() + timedelta(minutes=settings.SESION_INACTIVIDAD_MINUTOS)
    tope = sesion.creada_en + timedelta(days=settings.JWT_REFRESH_TOKEN_DAYS)
    return min(inactividad, tope)


def generar_tokens(db, usuario: Usuario, ip: str | None) -> tuple[str, str, Sesion]:
    jti = secrets.token_hex(16)
    creada = ahora_db()
    sesion = Sesion(
        usuario_id=usuario.id,
        jti=jti,
        creada_en=creada,
        expira_en=creada + timedelta(minutes=settings.SESION_INACTIVIDAD_MINUTOS),
        revocada=False,
        ip_origen=ip,
    )
    db.add(sesion)
    db.flush()
    vence_refresh = ahora() + timedelta(days=settings.JWT_REFRESH_TOKEN_DAYS)
    refresh = _codificar({"sub": str(usuario.id), "tipo": "refresh", "jti": jti}, vence_refresh)
    return crear_access_token(usuario.id, jti), refresh, sesion


def registrar_actividad(db, sesion: Sesion) -> None:
    """Corre la ventana de inactividad (como mucho una escritura por minuto)."""
    nueva = _fin_de_ventana(sesion)
    if nueva - sesion.expira_en >= ACTIVIDAD_MINIMA:
        sesion.expira_en = nueva
        db.flush()


def _sesion_por_jti(db, jti: str | None) -> Sesion:
    sesion = db.scalar(select(Sesion).where(Sesion.jti == jti)) if jti else None
    if sesion is None or sesion.revocada:
        raise TokenInvalido("Sesión inexistente o revocada")
    if sesion.expira_en <= ahora_db():
        sesion.revocada = True
        db.flush()
        raise TokenInvalido("Sesión vencida por inactividad")
    return sesion


def sesion_vigente(db, refresh: str | None) -> Sesion:
    return _sesion_por_jti(db, verificar_token(refresh, "refresh").get("jti"))


def sesion_de_access(db, datos_access: dict) -> Sesion:
    return _sesion_por_jti(db, datos_access.get("sid"))


def refrescar_access_token(db, refresh: str | None) -> str:
    sesion = sesion_vigente(db, refresh)
    usuario = db.get(Usuario, sesion.usuario_id)
    if usuario is None or not usuario.activo or not usuario.rol.activo:
        sesion.revocada = True
        db.flush()
        raise TokenInvalido("Usuario o rol inactivo")
    registrar_actividad(db, sesion)
    return crear_access_token(usuario.id, sesion.jti)


def revocar_sesion(db, refresh: str | None) -> Sesion | None:
    """Idempotente: un token inválido o ya revocado no es error."""
    try:
        jti = verificar_token(refresh, "refresh").get("jti")
    except TokenInvalido:
        return None
    sesion = db.scalar(select(Sesion).where(Sesion.jti == jti))
    if sesion is not None and not sesion.revocada:
        sesion.revocada = True
        db.flush()
    return sesion


def revocar_sesiones_de_usuario(db, usuario_id: int) -> None:
    db.execute(
        update(Sesion)
        .where(Sesion.usuario_id == usuario_id, Sesion.revocada.is_(False))
        .values(revocada=True)
    )


# ---------------------------------------------------------------- login
def _registrar_intento(db, usuario, username, exitoso, detalle, ip) -> None:
    if usuario is not None:
        db.add(
            HistorialAcceso(
                usuario_id=usuario.id,
                timestamp=ahora_db(),
                ip_origen=ip,
                resultado=ResultadoAcceso.EXITOSO if exitoso else ResultadoAcceso.FALLIDO,
                detalle=detalle,
            )
        )
    registrar_auditoria(
        db,
        accion="auth.login" if exitoso else "auth.login_fallido",
        entidad="usuario",
        entidad_id=usuario.id if usuario else None,
        usuario_id=usuario.id if usuario else None,
        estado_nuevo=None if exitoso else {"username": username, "detalle": detalle},
        ip_origen=ip,
    )


def autenticar_usuario(db, username: str, password: str, ip: str | None) -> Usuario:
    """Registra SIEMPRE el intento; el mensaje de error es siempre genérico.
    El llamador debe hacer commit aunque falle (para conservar el registro)."""
    username = (username or "").strip().lower()
    usuario = db.scalar(select(Usuario).where(Usuario.username == username))
    if usuario is None:
        verificar_password(password, _HASH_SENUELO)
        detalle = "Usuario inexistente"
    elif not verificar_password(password, usuario.password_hash):
        detalle = "Contraseña incorrecta"
    elif not usuario.activo:
        detalle = "Usuario inactivo"
    elif not usuario.rol.activo:
        detalle = "Rol inactivo"
    else:
        _registrar_intento(db, usuario, username, True, None, ip)
        return usuario
    _registrar_intento(db, usuario, username, False, detalle, ip)
    raise CredencialesInvalidas()


def marcar_acceso(db, usuario: Usuario) -> None:
    usuario.ultimo_acceso = ahora_db()
    db.flush()


def debe_cambiar_password(usuario: Usuario) -> bool:
    return usuario.debe_cambiar_password


# ---------------------------------------------------------------- contraseñas olvidadas
def _huella(usuario: Usuario) -> str:
    return usuario.password_hash[-16:]


def generar_token_reset(usuario: Usuario) -> str:
    vence = ahora() + timedelta(minutes=RESET_MINUTOS)
    return _codificar({"sub": str(usuario.id), "tipo": "reset", "pwd": _huella(usuario)}, vence)


def validar_token_reset(db, token: str | None) -> Usuario:
    datos = verificar_token(token, "reset")
    try:
        usuario = db.get(Usuario, int(datos["sub"]))
    except (TypeError, ValueError) as exc:
        raise TokenInvalido("Token de recuperación inválido") from exc
    if usuario is None or not usuario.activo or datos.get("pwd") != _huella(usuario):
        raise TokenInvalido("Token de recuperación inválido o ya usado")
    return usuario


def solicitar_reset(db, username: str, ip: str | None) -> None:
    """Envía el mail solo si el usuario existe, está activo y tiene email.
    El llamador responde siempre lo mismo (no revela qué usuarios existen)."""
    username = (username or "").strip().lower()
    usuario = db.scalar(select(Usuario).where(Usuario.username == username))
    enviado = False
    if usuario is not None and usuario.activo and usuario.email:
        enviado = enviar_reset_password(usuario.email, usuario.nombre, generar_token_reset(usuario))
    registrar_auditoria(
        db,
        accion="auth.reset_solicitar",
        entidad="usuario",
        entidad_id=usuario.id if usuario else None,
        estado_nuevo={"username": username, "enviado": enviado},
        ip_origen=ip,
    )


def cambiar_password(db, usuario: Usuario, nueva: str, *, autor_id: int | None, ip: str | None,
                     debe_cambiarla: bool) -> None:
    """Cambia el hash, revoca todas las sesiones del usuario y audita (sin la clave).
    `debe_cambiarla=True` (reseteo por un admin) obliga a cambiarla al próximo ingreso."""
    usuario.password_hash = hash_password(nueva)
    usuario.ultimo_acceso = None if debe_cambiarla else ahora_db()
    db.flush()
    revocar_sesiones_de_usuario(db, usuario.id)
    registrar_auditoria(
        db,
        accion="usuario.cambiar_password",
        entidad="usuario",
        entidad_id=usuario.id,
        usuario_id=autor_id,
        estado_nuevo={"debe_cambiarla": debe_cambiarla},
        ip_origen=ip,
    )
```

- [ ] **Step 5: Correr y ver que pasa**

Run: `docker compose exec backend pytest tests/test_auth_service.py tests/test_config.py -v` → PASS; luego la suite completa.

- [ ] **Step 6: Commit** — `feat(auth): service de autenticación, tokens y sesiones`.

---

### Task 4: Barrera de acceso (`core/seguridad.py`)

**Files:**
- Create: `backend/app/core/seguridad.py`
- Modify: `backend/tests/conftest.py` (fixture `headers_de`)
- Test: `backend/tests/test_seguridad.py`

**Interfaces:**
- Consumes: `Modulo`, `Recurso`, `ACCIONES`, `ROL_ADMIN`, `validar_destino`, modelos, `verificar_token`, `sesion_de_access`, `TokenInvalido`, errores.
- Produces: `resolver_permiso(db, usuario_id, modulo, accion, recurso=None) -> bool`; `token_de_request(request) -> str | None`; `usuario_de_token(db, token) -> Usuario` (levanta `TokenInvalido`); `get_current_user(request, db) -> Usuario` (401 `NoAutenticado`); `requiere_permiso(modulo, accion, recurso=None)` → dependency que devuelve el `Usuario` o 403 `"Sin permiso para '<accion>' en '<destino>'"`; `requiere_admin` → dependency (403 `"Operación exclusiva del Admin"`); `MENSAJE_CAMBIAR_PASSWORD = "Tenés que cambiar la contraseña antes de continuar."`.
- Produces (conftest): fixture `headers_de(usuario) -> dict` con `Authorization: Bearer <access>` de una sesión nueva.

- [ ] **Step 1: Fixture**

Agregar a `backend/tests/conftest.py`:
```python
@pytest.fixture
def headers_de(db):
    """Headers Bearer de una sesión nueva del usuario dado."""
    from app.services.auth import generar_tokens

    def _headers(usuario):
        access, _, _ = generar_tokens(db, usuario, "127.0.0.1")
        return {"Authorization": f"Bearer {access}"}

    return _headers
```

- [ ] **Step 2: Tests que fallan**

`backend/tests/test_seguridad.py`:
```python
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.core.errores import registrar_manejadores
from app.core.permisos import Modulo, Recurso
from app.core.seguridad import requiere_admin, requiere_permiso, resolver_permiso
from app.models import RolPermiso, UsuarioPermiso
from app.services import auth


# ---------- resolver_permiso ----------
def test_admin_puede_todo(db, crear_usuario):
    admin = crear_usuario("admin")
    assert resolver_permiso(db, admin.id, Modulo.AUDITORIA, "eliminar")
    assert resolver_permiso(db, admin.id, "caja", "crear", "caja.retiro")


def test_usuario_inexistente_o_inactivo_no_puede(db, crear_usuario):
    inactivo = crear_usuario("admin", activo=False)
    assert not resolver_permiso(db, inactivo.id, Modulo.STOCK, "ver")
    assert not resolver_permiso(db, 999_999, Modulo.STOCK, "ver")


def test_rol_inactivo_no_puede(db, crear_usuario):
    vendedor = crear_usuario("vendedor")
    vendedor.rol.activo = False
    db.flush()
    assert not resolver_permiso(db, vendedor.id, Modulo.STOCK, "ver")


def test_permiso_general_habilita_recursos_pero_no_al_reves(db, crear_usuario):
    vendedor = crear_usuario("vendedor")
    assert resolver_permiso(db, vendedor.id, Modulo.STOCK, "ver")
    assert resolver_permiso(db, vendedor.id, Modulo.STOCK, "crear", Recurso.STOCK_BAJA)  # recurso puntual
    assert not resolver_permiso(db, vendedor.id, Modulo.STOCK, "crear")  # el recurso no da el general
    supervisor = crear_usuario("supervisor")
    assert resolver_permiso(db, supervisor.id, Modulo.CAJA, "crear", Recurso.CAJA_RETIRO)  # general caja crear


def test_override_individual_suma_al_rol(db, crear_usuario):
    vendedor = crear_usuario("vendedor")
    assert not resolver_permiso(db, vendedor.id, Modulo.CAJA, "crear", Recurso.CAJA_RETIRO)
    db.add(UsuarioPermiso(usuario_id=vendedor.id, modulo="caja", recurso="caja.retiro", puede_crear=True))
    db.flush()
    assert resolver_permiso(db, vendedor.id, Modulo.CAJA, "crear", Recurso.CAJA_RETIRO)


def test_sin_filas_no_hay_permiso(db, crear_usuario):
    vendedor = crear_usuario("vendedor")
    assert not resolver_permiso(db, vendedor.id, Modulo.PROVEEDORES, "ver")


def test_accion_invalida_levanta_error(db, crear_usuario):
    vendedor = crear_usuario("vendedor")
    with pytest.raises(ValueError):
        resolver_permiso(db, vendedor.id, Modulo.STOCK, "borrar")


# ---------- dependencies ----------
@pytest.fixture
def cliente_protegido(db):
    app = FastAPI()
    registrar_manejadores(app)

    @app.get("/stock")
    def ver_stock(usuario=Depends(requiere_permiso(Modulo.STOCK, "ver"))):
        return {"id": usuario.id}

    @app.get("/retiro")
    def retiro(usuario=Depends(requiere_permiso(Modulo.CAJA, "crear", Recurso.CAJA_RETIRO))):
        return {"id": usuario.id}

    @app.get("/admin")
    def solo_admin(usuario=Depends(requiere_admin)):
        return {"id": usuario.id}

    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


def test_sin_token_da_401(cliente_protegido):
    r = cliente_protegido.get("/stock")
    assert r.status_code == 401


def test_con_permiso_pasa_y_sin_permiso_da_403(cliente_protegido, crear_usuario, headers_de):
    vendedor = crear_usuario("vendedor")
    h = headers_de(vendedor)
    assert cliente_protegido.get("/stock", headers=h).json() == {"id": vendedor.id}
    r = cliente_protegido.get("/retiro", headers=h)
    assert r.status_code == 403
    assert r.json()["detail"] == "Sin permiso para 'crear' en 'caja/caja.retiro'"


def test_token_por_cookie(cliente_protegido, crear_usuario, db):
    vendedor = crear_usuario("vendedor")
    access, _, _ = auth.generar_tokens(db, vendedor, None)
    cliente_protegido.cookies.set("access_token", access)
    assert cliente_protegido.get("/stock").status_code == 200


def test_sesion_revocada_corta_el_access(cliente_protegido, crear_usuario, db):
    vendedor = crear_usuario("vendedor")
    access, refresh, _ = auth.generar_tokens(db, vendedor, None)
    auth.revocar_sesion(db, refresh)
    r = cliente_protegido.get("/stock", headers={"Authorization": f"Bearer {access}"})
    assert r.status_code == 401


def test_usuario_desactivado_da_401(cliente_protegido, crear_usuario, headers_de, db):
    vendedor = crear_usuario("vendedor")
    h = headers_de(vendedor)
    vendedor.activo = False
    db.flush()
    assert cliente_protegido.get("/stock", headers=h).status_code == 401


def test_debe_cambiar_password_bloquea_la_api(cliente_protegido, crear_usuario, headers_de):
    nuevo = crear_usuario("admin", debe_cambiar=True)
    r = cliente_protegido.get("/stock", headers=headers_de(nuevo))
    assert r.status_code == 403 and "cambiar la contraseña" in r.json()["detail"]


def test_requiere_admin(cliente_protegido, crear_usuario, headers_de):
    assert cliente_protegido.get("/admin", headers=headers_de(crear_usuario("supervisor"))).status_code == 403
    admin = crear_usuario("admin")
    assert cliente_protegido.get("/admin", headers=headers_de(admin)).json() == {"id": admin.id}
```

- [ ] **Step 3: Correr y ver que falla**

Run: `docker compose exec backend pytest tests/test_seguridad.py -v` → FAIL (`ModuleNotFoundError: app.core.seguridad`).

- [ ] **Step 4: Implementación**

`backend/app/core/seguridad.py`:
```python
"""Barrera de acceso ÚNICA del sistema (resolver_permiso) y dependencies de FastAPI."""
from fastapi import Depends, Request
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errores import NoAutenticado, SinPermiso
from app.core.permisos import ACCIONES, ROL_ADMIN, Modulo, Recurso, validar_destino
from app.models import RolPermiso, Usuario, UsuarioPermiso
from app.services.auth import TokenInvalido, sesion_de_access, verificar_token
from config import settings

MENSAJE_CAMBIAR_PASSWORD = "Tenés que cambiar la contraseña antes de continuar."
MENSAJE_SESION_INVALIDA = "Sesión inválida o vencida. Volvé a ingresar."


def resolver_permiso(db, usuario_id: int, modulo, accion: str, recurso=None) -> bool:
    """¿El usuario puede `accion` sobre el módulo (o el recurso puntual)?

    1. Usuario inexistente o inactivo → False.  2. Rol admin → True.
    3. Rol inactivo → False.  4. OR de overrides del usuario y permisos del rol,
    mirando la fila general del módulo y, si se pidió, la del recurso exacto:
    el permiso general habilita cualquier recurso del módulo; un recurso
    puntual NO da acceso general.
    """
    if accion not in ACCIONES:
        raise ValueError(f"Acción desconocida: {accion}")
    modulo_enum, recurso_enum = validar_destino(
        Modulo(modulo).value, Recurso(recurso).value if recurso else None
    )
    usuario = db.get(Usuario, usuario_id)
    if usuario is None or not usuario.activo:
        return False
    if usuario.rol.nombre == ROL_ADMIN:
        return True
    if not usuario.rol.activo:
        return False

    columna = f"puede_{accion}"
    for modelo, del_duenio in (
        (UsuarioPermiso, UsuarioPermiso.usuario_id == usuario.id),
        (RolPermiso, RolPermiso.rol_id == usuario.rol_id),
    ):
        destino = (
            modelo.recurso.is_(None)
            if recurso_enum is None
            else or_(modelo.recurso.is_(None), modelo.recurso == recurso_enum.value)
        )
        fila = db.scalar(
            select(modelo.id)
            .where(del_duenio, modelo.modulo == modulo_enum.value, destino, getattr(modelo, columna).is_(True))
            .limit(1)
        )
        if fila is not None:
            return True
    return False


def token_de_request(request: Request) -> str | None:
    """Prioridad: header Bearer → access renovado por el middleware → cookie."""
    autorizacion = request.headers.get("authorization", "")
    if autorizacion.lower().startswith("bearer "):
        return autorizacion[7:].strip() or None
    renovado = getattr(request.state, "access_renovado", None)
    if renovado:
        return renovado
    return request.cookies.get(settings.JWT_COOKIE_NAME)


def usuario_de_token(db, token: str | None) -> Usuario:
    """Usuario activo dueño de un access token con sesión vigente (o TokenInvalido)."""
    datos = verificar_token(token, "access")
    sesion_de_access(db, datos)
    try:
        usuario = db.get(Usuario, int(datos["sub"]))
    except (TypeError, ValueError) as exc:
        raise TokenInvalido("Token con sujeto inválido") from exc
    if usuario is None or not usuario.activo:
        raise TokenInvalido("Usuario inexistente o inactivo")
    return usuario


def get_current_user(request: Request, db: Session = Depends(get_db)) -> Usuario:
    try:
        return usuario_de_token(db, token_de_request(request))
    except TokenInvalido as exc:
        raise NoAutenticado(MENSAJE_SESION_INVALIDA) from exc


def requiere_permiso(modulo, accion: str, recurso=None):
    """Dependency: devuelve el usuario si tiene el permiso; si no, 403."""
    modulo_enum = Modulo(modulo)
    recurso_enum = Recurso(recurso) if recurso else None
    destino = f"{modulo_enum.value}/{recurso_enum.value}" if recurso_enum else modulo_enum.value

    def dependencia(usuario: Usuario = Depends(get_current_user), db: Session = Depends(get_db)) -> Usuario:
        if usuario.debe_cambiar_password:
            raise SinPermiso(MENSAJE_CAMBIAR_PASSWORD)
        if not resolver_permiso(db, usuario.id, modulo_enum, accion, recurso_enum):
            raise SinPermiso(f"Sin permiso para '{accion}' en '{destino}'")
        return usuario

    return dependencia


def requiere_admin(usuario: Usuario = Depends(get_current_user)) -> Usuario:
    """Dependency para operaciones exclusivas del Admin (roles)."""
    if usuario.debe_cambiar_password:
        raise SinPermiso(MENSAJE_CAMBIAR_PASSWORD)
    if not usuario.es_admin:
        raise SinPermiso("Operación exclusiva del Admin")
    return usuario
```

- [ ] **Step 5: Correr y ver que pasa**

Run: `docker compose exec backend pytest tests/test_seguridad.py -v` → PASS; luego la suite completa.

- [ ] **Step 6: Commit** — `feat(auth): resolver_permiso y dependencies de seguridad`.

---

### Task 5: Endpoints de autenticación, cookies y email

**Files:**
- Create: `backend/app/core/cookies.py`, `backend/app/schemas/auth.py`, `backend/app/api/v1/auth.py`
- Modify: `backend/app/api/v1/__init__.py` (`core/email.py` ya existe desde la Task 3)
- Test: `backend/tests/test_email.py`, `backend/tests/test_auth_api.py`

**Interfaces:**
- Consumes: service `auth`, `get_current_user`, `ip_de_request`, `registrar_auditoria`, errores.
- Produces: `poner_cookie_access(response, token)`, `poner_cookies_sesion(response, access, refresh)`, `borrar_cookies_sesion(response)`; schemas `Password` (Annotated str 8-128), `LoginRequest`, `UsuarioSesion` (`id, username, nombre, rol, debe_cambiar_password, es_admin`, `UsuarioSesion.desde(usuario)`), `TokenResponse`, `RefreshRequest`, `RefreshResponse`, `ForgotPasswordRequest`, `ResetPasswordRequest`, `CambiarPasswordRequest`; endpoints `/api/v1/auth/{login,refresh,logout,forgot-password,reset-password,cambiar-password,me}`.

- [ ] **Step 1: Tests que fallan**

`backend/tests/test_email.py`:
```python
from app.core import email


def test_sin_smtp_no_envia_y_lo_informa(monkeypatch):
    monkeypatch.setattr(email.settings, "SMTP_HOST", None)
    assert not email.smtp_configurado()
    assert email.enviar_reset_password("a@example.com", "Ana", "tok") is False


def test_mail_de_reset_lleva_el_enlace(monkeypatch):
    capturados = []
    monkeypatch.setattr(email, "enviar_email", lambda destino, asunto, cuerpo: capturados.append((destino, asunto, cuerpo)) or True)
    monkeypatch.setattr(email.settings, "APP_URL", "https://gestion.example.com/")
    assert email.enviar_reset_password("a@example.com", "Ana", "abc123")
    destino, asunto, cuerpo = capturados[0]
    assert destino == "a@example.com"
    assert "https://gestion.example.com/reset-password?token=abc123" in cuerpo
    assert "Hola Ana" in cuerpo
```

`backend/tests/test_auth_api.py`:
```python
from sqlalchemy import select

from app.models import HistorialAcceso, ResultadoAcceso, Sesion
from app.services import auth


def _login(client, username, password):
    return client.post("/api/v1/auth/login", json={"username": username, "password": password})


def test_login_devuelve_tokens_y_setea_cookies(client, crear_usuario):
    usuario = crear_usuario(username="ana", password="Clave1234", nombre="Ana Pérez")
    r = _login(client, "ana", "Clave1234")
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["expires_in"] == 30 * 60
    assert cuerpo["usuario"] == {
        "id": usuario.id, "username": "ana", "nombre": "Ana Pérez", "rol": "vendedor",
        "debe_cambiar_password": False, "es_admin": False,
    }
    assert r.cookies.get("access_token") and r.cookies.get("refresh_token")
    set_cookie = " ".join(r.headers.get_list("set-cookie")).lower()
    assert "httponly" in set_cookie and "samesite=lax" in set_cookie


def test_login_fallido_es_generico_y_queda_registrado(client, crear_usuario, db):
    usuario = crear_usuario(username="beto", password="Clave1234")
    r = _login(client, "beto", "mala")
    assert r.status_code == 401
    assert r.json() == {"detail": "Usuario o contraseña incorrectos"}
    fila = db.scalar(select(HistorialAcceso).where(HistorialAcceso.usuario_id == usuario.id))
    assert fila.resultado is ResultadoAcceso.FALLIDO


def test_admin_del_seed_debe_cambiar_la_password(client):
    r = _login(client, "admin", "Admin1234!")
    assert r.status_code == 200
    assert r.json()["usuario"]["debe_cambiar_password"] is True


def test_me(client, crear_usuario, headers_de):
    usuario = crear_usuario("supervisor", nombre="Sofía")
    r = client.get("/api/v1/auth/me", headers=headers_de(usuario))
    assert r.json()["nombre"] == "Sofía" and r.json()["rol"] == "supervisor"
    assert client.get("/api/v1/auth/me").status_code == 401


def test_refresh_por_cookie_y_por_body(client, crear_usuario, db):
    crear_usuario(username="caro", password="Clave1234")
    login = _login(client, "caro", "Clave1234").json()
    r = client.post("/api/v1/auth/refresh")  # cookie del login
    assert r.status_code == 200 and r.json()["access_token"]
    assert r.cookies.get("access_token")
    client.cookies.clear()
    r = client.post("/api/v1/auth/refresh", json={"refresh_token": login["refresh_token"]})
    assert r.status_code == 200


def test_refresh_invalido_da_401_y_borra_cookies(client):
    client.cookies.set("refresh_token", "basura")
    r = client.post("/api/v1/auth/refresh")
    assert r.status_code == 401
    assert 'refresh_token=""' in " ".join(r.headers.get_list("set-cookie"))


def test_logout_revoca_y_no_se_puede_renovar(client, crear_usuario, db):
    usuario = crear_usuario(username="dani", password="Clave1234")
    login = _login(client, "dani", "Clave1234").json()
    r = client.post("/api/v1/auth/logout")
    assert r.status_code == 200
    assert 'access_token=""' in " ".join(r.headers.get_list("set-cookie"))
    sesion = db.scalar(select(Sesion).where(Sesion.usuario_id == usuario.id))
    assert sesion.revocada
    r = client.post("/api/v1/auth/refresh", json={"refresh_token": login["refresh_token"]})
    assert r.status_code == 401


def test_forgot_password_siempre_responde_lo_mismo(client, crear_usuario, monkeypatch):
    enviados = []
    monkeypatch.setattr(auth, "enviar_reset_password", lambda e, n, t: enviados.append(t) or True)
    crear_usuario(username="eli", email="eli@example.com")
    r1 = client.post("/api/v1/auth/forgot-password", json={"username": "eli"})
    r2 = client.post("/api/v1/auth/forgot-password", json={"username": "noexiste"})
    assert r1.status_code == r2.status_code == 200 and r1.json() == r2.json()
    assert len(enviados) == 1


def test_reset_password_de_un_solo_uso(client, crear_usuario, monkeypatch):
    enviados = []
    monkeypatch.setattr(auth, "enviar_reset_password", lambda e, n, t: enviados.append(t) or True)
    crear_usuario(username="fede", email="fede@example.com")
    client.post("/api/v1/auth/forgot-password", json={"username": "fede"})
    cuerpo = {"token": enviados[0], "password_nueva": "NuevaClave1"}
    assert client.post("/api/v1/auth/reset-password", json=cuerpo).status_code == 200
    assert _login(client, "fede", "NuevaClave1").status_code == 200
    r = client.post("/api/v1/auth/reset-password", json=cuerpo)
    assert r.status_code == 400


def test_cambiar_password(client, crear_usuario, db):
    crear_usuario(username="gabi", password="Clave1234", debe_cambiar=True)
    viejo = _login(client, "gabi", "Clave1234").json()
    r = client.post("/api/v1/auth/cambiar-password", json={"password_actual": "mala", "password_nueva": "OtraClave1"})
    assert r.status_code == 400
    r = client.post("/api/v1/auth/cambiar-password", json={"password_actual": "Clave1234", "password_nueva": "Clave1234"})
    assert r.status_code == 400
    r = client.post("/api/v1/auth/cambiar-password", json={"password_actual": "Clave1234", "password_nueva": "OtraClave1"})
    assert r.status_code == 200
    assert r.json()["usuario"]["debe_cambiar_password"] is False
    # la sesión anterior quedó revocada; la nueva funciona
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": viejo["refresh_token"]}).status_code == 401
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {r.json()['access_token']}"}).status_code == 200


def test_password_nueva_corta_da_422(client, crear_usuario):
    crear_usuario(username="hugo", password="Clave1234")
    _login(client, "hugo", "Clave1234")
    r = client.post("/api/v1/auth/cambiar-password", json={"password_actual": "Clave1234", "password_nueva": "corta"})
    assert r.status_code == 422
```

- [ ] **Step 2: Correr y ver que falla**

Run: `docker compose exec backend pytest tests/test_email.py tests/test_auth_api.py -v` → FAIL (404 en `/api/v1/auth/login`).

- [ ] **Step 3: Implementación**


`backend/app/core/cookies.py`:
```python
"""Cookies de sesión: HttpOnly, SameSite=Lax, Secure según configuración."""
from config import settings


def _opciones() -> dict:
    return {"httponly": True, "samesite": "lax", "secure": settings.COOKIE_SECURE, "path": "/"}


def poner_cookie_access(response, token: str) -> None:
    response.set_cookie(settings.JWT_COOKIE_NAME, token, max_age=settings.JWT_ACCESS_TOKEN_MINUTES * 60, **_opciones())


def poner_cookies_sesion(response, access: str, refresh: str) -> None:
    poner_cookie_access(response, access)
    response.set_cookie(
        settings.JWT_REFRESH_COOKIE_NAME, refresh, max_age=settings.JWT_REFRESH_TOKEN_DAYS * 86400, **_opciones()
    )


def borrar_cookies_sesion(response) -> None:
    for nombre in (settings.JWT_COOKIE_NAME, settings.JWT_REFRESH_COOKIE_NAME):
        response.delete_cookie(nombre, **_opciones())
```

`backend/app/schemas/auth.py`:
```python
from typing import Annotated

from pydantic import BaseModel, Field

# Regla única de longitud de contraseñas (la reusan los schemas de usuarios).
Password = Annotated[str, Field(min_length=8, max_length=128)]


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=128)


class UsuarioSesion(BaseModel):
    id: int
    username: str
    nombre: str
    rol: str
    debe_cambiar_password: bool
    es_admin: bool

    @classmethod
    def desde(cls, usuario) -> "UsuarioSesion":
        return cls(
            id=usuario.id,
            username=usuario.username,
            nombre=usuario.nombre,
            rol=usuario.rol.nombre,
            debe_cambiar_password=usuario.debe_cambiar_password,
            es_admin=usuario.es_admin,
        )


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int  # segundos de vida del access token
    usuario: UsuarioSesion


class RefreshRequest(BaseModel):
    refresh_token: str | None = None


class RefreshResponse(BaseModel):
    access_token: str
    expires_in: int


class ForgotPasswordRequest(BaseModel):
    username: str = Field(min_length=1, max_length=50)


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=1)
    password_nueva: Password


class CambiarPasswordRequest(BaseModel):
    password_actual: str = Field(min_length=1, max_length=128)
    password_nueva: Password
```

`backend/app/api/v1/auth.py`:
```python
"""Autenticación: login, renovación, logout, recuperación y cambio de contraseña."""
from fastapi import APIRouter, Body, Depends, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.auditoria import registrar_auditoria
from app.core.cookies import borrar_cookies_sesion, poner_cookie_access, poner_cookies_sesion
from app.core.database import get_db
from app.core.errores import DatoInvalido
from app.core.seguridad import get_current_user
from app.core.utils import ip_de_request
from app.models import Usuario
from app.schemas.auth import (
    CambiarPasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    RefreshRequest,
    RefreshResponse,
    ResetPasswordRequest,
    TokenResponse,
    UsuarioSesion,
)
from app.schemas.comunes import MensajeResponse
from app.services import auth
from config import settings

router = APIRouter(prefix="/auth", tags=["auth"])

MENSAJE_RESET_SOLICITADO = "Si el usuario existe y tiene un email cargado, te enviamos las instrucciones."
MENSAJE_SESION_VENCIDA = "Sesión vencida. Volvé a ingresar."


def _token_response(usuario: Usuario, access: str, refresh: str) -> TokenResponse:
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.JWT_ACCESS_TOKEN_MINUTES * 60,
        usuario=UsuarioSesion.desde(usuario),
    )


def _refresh_de(request: Request, datos: RefreshRequest | None) -> str | None:
    return (datos.refresh_token if datos else None) or request.cookies.get(settings.JWT_REFRESH_COOKIE_NAME)


@router.post("/login", response_model=TokenResponse)
def login(datos: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    ip = ip_de_request(request)
    try:
        usuario = auth.autenticar_usuario(db, datos.username, datos.password, ip)
    except auth.CredencialesInvalidas:
        db.commit()  # el intento fallido queda registrado igual
        raise
    if not usuario.debe_cambiar_password:
        auth.marcar_acceso(db, usuario)
    access, refresh, _ = auth.generar_tokens(db, usuario, ip)
    db.commit()
    poner_cookies_sesion(response, access, refresh)
    return _token_response(usuario, access, refresh)


@router.post("/refresh", response_model=RefreshResponse)
def refresh(request: Request, response: Response, datos: RefreshRequest | None = Body(default=None),
            db: Session = Depends(get_db)):
    try:
        access = auth.refrescar_access_token(db, _refresh_de(request, datos))
    except auth.TokenInvalido:
        db.commit()  # conserva la marca de sesión revocada
        vencida = JSONResponse(status_code=401, content={"detail": MENSAJE_SESION_VENCIDA})
        borrar_cookies_sesion(vencida)
        return vencida
    db.commit()
    poner_cookie_access(response, access)
    return RefreshResponse(access_token=access, expires_in=settings.JWT_ACCESS_TOKEN_MINUTES * 60)


@router.post("/logout", response_model=MensajeResponse)
def logout(request: Request, datos: RefreshRequest | None = Body(default=None), db: Session = Depends(get_db)):
    sesion = auth.revocar_sesion(db, _refresh_de(request, datos))
    if sesion is not None:
        registrar_auditoria(
            db, accion="auth.logout", entidad="usuario", entidad_id=sesion.usuario_id,
            usuario_id=sesion.usuario_id, request=request,
        )
    db.commit()
    respuesta = JSONResponse(content={"mensaje": "Sesión cerrada."})
    borrar_cookies_sesion(respuesta)
    return respuesta


@router.post("/forgot-password", response_model=MensajeResponse)
def forgot_password(datos: ForgotPasswordRequest, request: Request, db: Session = Depends(get_db)):
    auth.solicitar_reset(db, datos.username, ip_de_request(request))
    db.commit()
    return MensajeResponse(mensaje=MENSAJE_RESET_SOLICITADO)


@router.post("/reset-password", response_model=MensajeResponse)
def reset_password(datos: ResetPasswordRequest, request: Request, db: Session = Depends(get_db)):
    try:
        usuario = auth.validar_token_reset(db, datos.token)
    except auth.TokenInvalido as exc:
        raise DatoInvalido("El enlace de recuperación es inválido, venció o ya se usó.") from exc
    auth.cambiar_password(
        db, usuario, datos.password_nueva, autor_id=usuario.id, ip=ip_de_request(request), debe_cambiarla=False
    )
    db.commit()
    return MensajeResponse(mensaje="Contraseña actualizada. Ya podés ingresar.")


@router.post("/cambiar-password", response_model=TokenResponse)
def cambiar_password(datos: CambiarPasswordRequest, request: Request, response: Response,
                     usuario: Usuario = Depends(get_current_user), db: Session = Depends(get_db)):
    if not auth.verificar_password(datos.password_actual, usuario.password_hash):
        raise DatoInvalido("La contraseña actual no es correcta.")
    if datos.password_actual == datos.password_nueva:
        raise DatoInvalido("La contraseña nueva tiene que ser distinta de la actual.")
    ip = ip_de_request(request)
    auth.cambiar_password(db, usuario, datos.password_nueva, autor_id=usuario.id, ip=ip, debe_cambiarla=False)
    access, refresh_nuevo, _ = auth.generar_tokens(db, usuario, ip)
    db.commit()
    poner_cookies_sesion(response, access, refresh_nuevo)
    return _token_response(usuario, access, refresh_nuevo)


@router.get("/me", response_model=UsuarioSesion)
def me(usuario: Usuario = Depends(get_current_user)):
    return UsuarioSesion.desde(usuario)
```

En `backend/app/api/v1/__init__.py`, agregar `from app.api.v1 import auth` (junto a `health`) y `api_router.include_router(auth.router)`.

- [ ] **Step 4: Correr y ver que pasa**

Run: `docker compose exec backend pytest tests/test_email.py tests/test_auth_api.py -v` → PASS; luego suite completa. Probar por curl: `curl -s -X POST localhost:8000/api/v1/auth/login -H 'Content-Type: application/json' -d '{"username":"admin","password":"Admin1234!"}'` → 200 con `debe_cambiar_password: true`.

- [ ] **Step 5: Commit** — `feat(auth): endpoints de autenticación, cookies y email de recuperación`.

---

### Task 6: Middleware de renovación de sesión

**Files:**
- Create: `backend/app/middleware/auth_refresh_middleware.py`
- Modify: `backend/main.py` (montar el middleware), `backend/tests/conftest.py` (fixture `client`)
- Test: `backend/tests/test_middleware.py`

**Interfaces:**
- Consumes: `auth.verificar_token`, `auth.sesion_vigente`, `auth.registrar_actividad`, `auth.refrescar_access_token`, `auth.TokenInvalido`, `poner_cookie_access`, `borrar_cookies_sesion`, `SessionLocal`.
- Produces: `AuthRefreshMiddleware`; `RUTAS_EXCLUIDAS`; `sesion_por_defecto()` (context manager). Hook de tests: `app.state.abrir_sesion_db` (callable → context manager que da una `Session`); si no existe se usa `sesion_por_defecto`.

- [ ] **Step 1: Hook en el fixture `client`**

En `backend/tests/conftest.py`, reemplazar el fixture `client` por:
```python
@pytest.fixture
def client(db):
    from contextlib import contextmanager

    from app.core.database import get_db
    from main import app

    @contextmanager
    def _misma_sesion():
        # El middleware usa la misma sesión del test (misma transacción revertida).
        yield db

    app.dependency_overrides[get_db] = lambda: db
    app.state.abrir_sesion_db = _misma_sesion
    with TestClient(app) as cliente:
        yield cliente
    app.dependency_overrides.clear()
    del app.state.abrir_sesion_db
```

- [ ] **Step 2: Tests que fallan**

`backend/tests/test_middleware.py`:
```python
from datetime import timedelta

from sqlalchemy import select

from app.core.utils import ahora, ahora_db
from app.models import Sesion
from app.services import auth


def _cookies_de_sesion(client, db, usuario):
    access, refresh, sesion = auth.generar_tokens(db, usuario, None)
    client.cookies.set("access_token", access)
    client.cookies.set("refresh_token", refresh)
    return access, refresh, sesion


def test_access_vencido_se_renueva_con_el_refresh(client, crear_usuario, db):
    usuario = crear_usuario()
    _, _, sesion = _cookies_de_sesion(client, db, usuario)
    vencido = auth._codificar({"sub": str(usuario.id), "tipo": "access", "sid": sesion.jti}, ahora() - timedelta(seconds=5))
    client.cookies.set("access_token", vencido)
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 200 and r.json()["id"] == usuario.id
    nuevo = r.cookies.get("access_token")
    assert nuevo and nuevo != vencido
    assert auth.verificar_token(nuevo, "access")["sid"] == sesion.jti


def test_access_vigente_corre_la_ventana_de_inactividad(client, crear_usuario, db):
    usuario = crear_usuario()
    _, _, sesion = _cookies_de_sesion(client, db, usuario)
    sesion.expira_en = ahora_db() + timedelta(minutes=3)
    db.flush()
    assert client.get("/api/v1/auth/me").status_code == 200
    db.refresh(sesion)
    assert sesion.expira_en > ahora_db() + timedelta(minutes=29)


def test_sesion_caida_por_inactividad_borra_cookies_y_da_401(client, crear_usuario, db):
    usuario = crear_usuario()
    _, _, sesion = _cookies_de_sesion(client, db, usuario)
    sesion.expira_en = ahora_db() - timedelta(seconds=1)
    db.flush()
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 401
    cookies = " ".join(r.headers.get_list("set-cookie"))
    assert 'access_token=""' in cookies and 'refresh_token=""' in cookies
    assert db.scalar(select(Sesion.revocada).where(Sesion.id == sesion.id))


def test_logout_no_es_pisado_por_el_middleware(client, crear_usuario, db):
    usuario = crear_usuario()
    _cookies_de_sesion(client, db, usuario)
    r = client.post("/api/v1/auth/logout")
    cookies = r.headers.get_list("set-cookie")
    assert all(c.startswith(('access_token=""', 'refresh_token=""')) for c in cookies)


def test_bearer_no_pasa_por_el_middleware(client, crear_usuario, headers_de):
    r = client.get("/api/v1/auth/me", headers=headers_de(crear_usuario()))
    assert r.status_code == 200 and not r.headers.get_list("set-cookie")


def test_rutas_estaticas_excluidas(client):
    client.cookies.set("refresh_token", "basura")
    r = client.get("/static/css/custom.css")
    assert r.status_code == 200 and not r.headers.get_list("set-cookie")


def test_el_middleware_nunca_rompe_el_request(client, crear_usuario, db):
    from contextlib import contextmanager

    from main import app

    @contextmanager
    def _falla():
        raise RuntimeError("base caída")
        yield  # noqa

    _cookies_de_sesion(client, db, crear_usuario())
    app.state.abrir_sesion_db = _falla
    assert client.get("/api/v1/health").status_code == 200
```

- [ ] **Step 3: Correr y ver que falla**

Run: `docker compose exec backend pytest tests/test_middleware.py -v` → FAIL (el access vencido da 401: no hay middleware).

- [ ] **Step 4: Implementación**

`backend/app/middleware/auth_refresh_middleware.py`:
```python
"""Sesión deslizante: renueva el access vencido usando la cookie de refresh y
corre la ventana de inactividad en cada request con access vigente.
Nunca levanta excepción: ante cualquier error deja pasar el request."""
import logging
from contextlib import contextmanager
from dataclasses import dataclass

from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.cookies import borrar_cookies_sesion, poner_cookie_access
from app.core.database import SessionLocal
from app.services import auth
from config import settings

log = logging.getLogger(__name__)

RUTAS_EXCLUIDAS = (
    "/api/v1/auth/login",
    "/api/v1/auth/refresh",
    "/static",
    "/uploads",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/favicon",
)


@contextmanager
def sesion_por_defecto():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@dataclass
class _Resultado:
    nuevo_access: str | None = None
    borrar_cookies: bool = False


def _access_vigente(token: str | None) -> bool:
    try:
        auth.verificar_token(token, "access")
    except auth.TokenInvalido:
        return False
    return True


class AuthRefreshMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if self._excluida(request):
            return await call_next(request)
        resultado = await run_in_threadpool(self._procesar, request)
        if resultado.nuevo_access:
            request.state.access_renovado = resultado.nuevo_access
        response = await call_next(request)
        tocadas = {c.split("=", 1)[0].strip() for c in response.headers.getlist("set-cookie")}
        if resultado.nuevo_access and settings.JWT_COOKIE_NAME not in tocadas:
            poner_cookie_access(response, resultado.nuevo_access)
        if resultado.borrar_cookies and settings.JWT_REFRESH_COOKIE_NAME not in tocadas:
            borrar_cookies_sesion(response)
        return response

    @staticmethod
    def _excluida(request) -> bool:
        if request.headers.get("authorization", "").lower().startswith("bearer "):
            return True
        return request.url.path.startswith(RUTAS_EXCLUIDAS)

    @staticmethod
    def _procesar(request) -> _Resultado:
        refresh = request.cookies.get(settings.JWT_REFRESH_COOKIE_NAME)
        if not refresh:
            return _Resultado()
        abrir = getattr(request.app.state, "abrir_sesion_db", sesion_por_defecto)
        try:
            with abrir() as db:
                try:
                    if _access_vigente(request.cookies.get(settings.JWT_COOKIE_NAME)):
                        auth.registrar_actividad(db, auth.sesion_vigente(db, refresh))
                        db.commit()
                        return _Resultado()
                    nuevo = auth.refrescar_access_token(db, refresh)
                    db.commit()
                    return _Resultado(nuevo_access=nuevo)
                except auth.TokenInvalido:
                    db.commit()  # conserva la marca de sesión revocada
                    return _Resultado(borrar_cookies=True)
        except Exception:  # noqa: BLE001 - el middleware nunca rompe el request
            log.exception("Error en AuthRefreshMiddleware")
            return _Resultado()
```

En `backend/main.py`: importar `from app.middleware.auth_refresh_middleware import AuthRefreshMiddleware` y reemplazar el comentario del punto de montaje por `app.add_middleware(AuthRefreshMiddleware)` (después del `CORSMiddleware`).

- [ ] **Step 5: Correr y ver que pasa**

Run: `docker compose exec backend pytest tests/test_middleware.py -v` → PASS; luego suite completa.

- [ ] **Step 6: Commit** — `feat(auth): middleware de renovación de sesión`.

---

### Task 7: Permisos (árboles y accesos) y roles

**Files:**
- Create: `backend/app/services/permisos.py`, `backend/app/services/roles.py`, `backend/app/schemas/permisos.py`, `backend/app/schemas/roles.py`, `backend/app/api/v1/roles.py`
- Modify: `backend/app/api/v1/__init__.py`
- Test: `backend/tests/test_permisos_service.py`, `backend/tests/test_roles_api.py`

**Interfaces:**
- Consumes: constantes de `core/permisos.py`, modelos, `registrar_auditoria`, `snapshot`, `normalizar_texto`, errores, `requiere_admin`, `resolver_permiso`.
- Produces (`services/permisos.py`): `crear_permisos_vacios(db, rol)`, `arbol_de_rol(db, rol) -> dict`, `arbol_de_usuario(db, usuario) -> dict`, `actualizar_permisos_rol(db, autor, rol, entradas, ip)`, `actualizar_permisos_usuario(db, autor, usuario, entradas, ip)`, `accesos_de_rol(db, rol) -> list[dict]`, `accesos_de_usuario(db, usuario) -> list[dict]`, `actualizar_accesos_usuario(db, autor, usuario, claves, ip)`. Árbol: `{"modulos": [nodo]}`, nodo = `{modulo, recurso, label, acciones_aplicables, puede_<a>, [heredado_<a>, override_<a>], recursos: [nodo]}` con `None` en las acciones que no aplican. Acceso: `{clave, label, heredado, override, permitido}`. `entradas`: lista de objetos con `modulo, recurso, puede_ver, puede_crear, puede_editar, puede_eliminar`.
- Produces (`services/roles.py`): `obtener_rol(db, rol_id) -> Rol`, `listar_roles(db, *, nombre=None, activo=None, es_sistema=None) -> list[tuple[Rol, int]]`, `crear_rol(db, autor, nombre, descripcion, ip) -> Rol`, `editar_rol(db, autor, rol, nombre, descripcion, ip) -> Rol`, `cambiar_estado_rol(db, autor, rol, activo, ip) -> Rol`, `eliminar_rol(db, autor, rol, ip)`.
- Produces (schemas): `PermisoEntrada`, `ActualizarPermisos {permisos: list[PermisoEntrada]}`, `NodoPermiso`, `ArbolPermisos`, `AccesoResponse`, `ActualizarAccesos {accesos: list[str]}`, `RolCrear`, `RolEditar`, `RolEstado`, `RolResponse`.
- Endpoints `/api/v1/roles` (todos `requiere_admin`).

- [ ] **Step 1: Tests que fallan**

`backend/tests/test_permisos_service.py`:
```python
import pytest
from sqlalchemy import select

from app.core.errores import DatoInvalido, ReglaDeNegocio
from app.core.permisos import Modulo, Recurso, recursos_de_modulo
from app.core.seguridad import resolver_permiso
from app.models import Rol, RolPermiso, UsuarioPermiso
from app.schemas.permisos import PermisoEntrada
from app.services import permisos


def _nodo(arbol, modulo, recurso=None):
    nodo = next(n for n in arbol["modulos"] if n["modulo"] == modulo)
    return nodo if recurso is None else next(r for r in nodo["recursos"] if r["recurso"] == recurso)


def test_crear_permisos_vacios(db):
    rol = Rol(nombre="cajero", es_sistema=False)
    db.add(rol)
    db.flush()
    permisos.crear_permisos_vacios(db, rol)
    filas = db.scalars(select(RolPermiso).where(RolPermiso.rol_id == rol.id)).all()
    assert len(filas) == len(Modulo) + len(Recurso)
    assert not any(f.puede_ver or f.puede_crear or f.puede_editar or f.puede_eliminar for f in filas)


def test_arbol_de_rol(db):
    vendedor = db.scalar(select(Rol).where(Rol.nombre == "vendedor"))
    arbol = permisos.arbol_de_rol(db, vendedor)
    stock = _nodo(arbol, "stock")
    assert stock["puede_ver"] is True and stock["puede_crear"] is False
    assert [r["recurso"] for r in stock["recursos"]] == [r.value for r in recursos_de_modulo(Modulo.STOCK)]
    baja = _nodo(arbol, "stock", "stock.baja")
    assert baja["puede_crear"] is True and baja["puede_ver"] is None  # "ver" no aplica
    assert _nodo(arbol, "auditoria")["acciones_aplicables"] == ["ver"]


def test_arbol_de_usuario_distingue_heredado_de_override(db, crear_usuario):
    vendedor = crear_usuario("vendedor")
    db.add(UsuarioPermiso(usuario_id=vendedor.id, modulo="proveedores", recurso=None, puede_ver=True))
    db.flush()
    arbol = permisos.arbol_de_usuario(db, vendedor)
    prov = _nodo(arbol, "proveedores")
    assert prov["puede_ver"] and prov["override_ver"] and not prov["heredado_ver"]
    stock = _nodo(arbol, "stock")
    assert stock["puede_ver"] and stock["heredado_ver"] and not stock["override_ver"]


def test_actualizar_permisos_de_rol(db, crear_usuario):
    rol = Rol(nombre="deposito", es_sistema=False)
    db.add(rol)
    db.flush()
    permisos.crear_permisos_vacios(db, rol)
    usuario = crear_usuario(rol)
    entradas = [
        PermisoEntrada(modulo="stock", recurso=None, puede_ver=True, puede_crear=True),
        PermisoEntrada(modulo="stock", recurso="stock.baja", puede_crear=True, puede_ver=True),  # ver no aplica
    ]
    permisos.actualizar_permisos_rol(db, None, rol, entradas, None)
    assert resolver_permiso(db, usuario.id, Modulo.STOCK, "crear")
    baja = db.scalar(select(RolPermiso).where(RolPermiso.rol_id == rol.id, RolPermiso.recurso == "stock.baja"))
    assert baja.puede_crear and not baja.puede_ver


def test_permisos_invalidos_o_del_admin(db):
    admin = db.scalar(select(Rol).where(Rol.nombre == "admin"))
    with pytest.raises(ReglaDeNegocio):
        permisos.actualizar_permisos_rol(db, None, admin, [], None)
    vendedor = db.scalar(select(Rol).where(Rol.nombre == "vendedor"))
    with pytest.raises(DatoInvalido):
        permisos.actualizar_permisos_rol(db, None, vendedor, [PermisoEntrada(modulo="ventas", recurso="stock.baja")], None)


def test_overrides_de_usuario_solo_guardan_lo_marcado(db, crear_usuario):
    vendedor = crear_usuario("vendedor")
    permisos.actualizar_permisos_usuario(
        db, None, vendedor, [PermisoEntrada(modulo="caja", recurso="caja.retiro", puede_crear=True)], None
    )
    assert resolver_permiso(db, vendedor.id, Modulo.CAJA, "crear", Recurso.CAJA_RETIRO)
    permisos.actualizar_permisos_usuario(db, None, vendedor, [PermisoEntrada(modulo="caja", recurso="caja.retiro")], None)
    assert db.scalars(select(UsuarioPermiso).where(UsuarioPermiso.usuario_id == vendedor.id)).all() == []


def test_accesos_de_rol_y_de_usuario(db, crear_usuario):
    vendedor = crear_usuario("vendedor")
    accesos = {a["clave"]: a for a in permisos.accesos_de_usuario(db, vendedor)}
    baja = accesos["stock:stock.baja:crear"]
    assert baja["heredado"] and baja["permitido"] and not baja["override"]
    retiro = accesos["caja:caja.retiro:crear"]
    assert not retiro["heredado"] and not retiro["permitido"]
    admin = db.scalar(select(Rol).where(Rol.nombre == "admin"))
    assert all(a["heredado"] for a in permisos.accesos_de_rol(db, admin))


def test_actualizar_accesos_no_persiste_lo_heredado(db, crear_usuario):
    vendedor = crear_usuario("vendedor")
    permisos.actualizar_accesos_usuario(db, None, vendedor, ["caja:caja.retiro:crear", "stock:stock.baja:crear"], None)
    filas = db.scalars(select(UsuarioPermiso).where(UsuarioPermiso.usuario_id == vendedor.id)).all()
    assert [(f.modulo, f.recurso, f.puede_crear) for f in filas] == [("caja", "caja.retiro", True)]
    accesos = {a["clave"]: a for a in permisos.accesos_de_usuario(db, vendedor)}
    assert accesos["caja:caja.retiro:crear"]["override"] and accesos["caja:caja.retiro:crear"]["permitido"]
    permisos.actualizar_accesos_usuario(db, None, vendedor, [], None)
    assert db.scalars(select(UsuarioPermiso).where(UsuarioPermiso.usuario_id == vendedor.id)).all() == []


def test_acceso_desconocido(db, crear_usuario):
    with pytest.raises(DatoInvalido):
        permisos.actualizar_accesos_usuario(db, None, crear_usuario("vendedor"), ["no:existe:ver"], None)
```

`backend/tests/test_roles_api.py`:
```python
from sqlalchemy import select

from app.models import Auditoria, RolPermiso

URL = "/api/v1/roles"


def test_solo_admin(client, crear_usuario, headers_de):
    assert client.get(URL, headers=headers_de(crear_usuario("supervisor"))).status_code == 403


def test_crear_listar_y_permisos_vacios(client, crear_usuario, headers_de, db):
    h = headers_de(crear_usuario("admin"))
    r = client.post(URL, json={"nombre": "Cajero", "descripcion": "Solo caja"}, headers=h)
    assert r.status_code == 201
    rol = r.json()
    assert rol["es_sistema"] is False and rol["cantidad_usuarios"] == 0
    filas = db.scalars(select(RolPermiso).where(RolPermiso.rol_id == rol["id"])).all()
    assert filas and not any(f.puede_ver for f in filas)
    assert db.scalar(select(Auditoria).where(Auditoria.accion == "rol.crear", Auditoria.entidad_id == rol["id"]))
    nombres = [x["nombre"] for x in client.get(URL, params={"es_sistema": False}, headers=h).json()]
    assert "Cajero" in nombres and "admin" not in nombres
    assert client.post(URL, json={"nombre": "cajero"}, headers=h).status_code == 409  # duplicado sin importar mayúsculas


def test_roles_de_sistema_no_se_renombran_ni_eliminan(client, crear_usuario, headers_de, db):
    h = headers_de(crear_usuario("admin"))
    vendedor = next(x for x in client.get(URL, headers=h).json() if x["nombre"] == "vendedor")
    r = client.put(f"{URL}/{vendedor['id']}", json={"nombre": "vendedores", "descripcion": "x"}, headers=h)
    assert r.status_code == 409
    r = client.put(f"{URL}/{vendedor['id']}", json={"nombre": "vendedor", "descripcion": "Nueva descripción"}, headers=h)
    assert r.status_code == 200 and r.json()["descripcion"] == "Nueva descripción"
    assert client.delete(f"{URL}/{vendedor['id']}", headers=h).status_code == 409


def test_no_se_desactiva_con_usuarios_activos(client, crear_usuario, headers_de, db):
    from app.models import Rol

    h = headers_de(crear_usuario("admin"))
    rol_id = client.post(URL, json={"nombre": "Temporal"}, headers=h).json()["id"]
    r = client.patch(f"{URL}/{rol_id}/estado", json={"activo": False}, headers=h)
    assert r.status_code == 200 and r.json()["activo"] is False
    client.patch(f"{URL}/{rol_id}/estado", json={"activo": True}, headers=h)
    crear_usuario(db.get(Rol, rol_id))
    r = client.patch(f"{URL}/{rol_id}/estado", json={"activo": False}, headers=h)
    assert r.status_code == 409 and "usuario(s) activo(s)" in r.json()["detail"]
```

Continuación de `backend/tests/test_roles_api.py`:
```python
def test_eliminar_rol(client, crear_usuario, headers_de, db):
    from app.models import Rol

    h = headers_de(crear_usuario("admin"))
    libre = client.post(URL, json={"nombre": "Libre"}, headers=h).json()["id"]
    assert client.delete(f"{URL}/{libre}", headers=h).status_code == 204
    assert db.get(Rol, libre) is None
    ocupado = client.post(URL, json={"nombre": "Ocupado"}, headers=h).json()["id"]
    crear_usuario(db.get(Rol, ocupado), activo=False)
    assert client.delete(f"{URL}/{ocupado}", headers=h).status_code == 409


def test_arbol_de_permisos_del_rol(client, crear_usuario, headers_de):
    h = headers_de(crear_usuario("admin"))
    rol_id = client.post(URL, json={"nombre": "Depósito"}, headers=h).json()["id"]
    cuerpo = {"permisos": [{"modulo": "stock", "recurso": None, "puede_ver": True}]}
    r = client.put(f"{URL}/{rol_id}/permisos", json=cuerpo, headers=h)
    assert r.status_code == 200
    stock = next(n for n in r.json()["modulos"] if n["modulo"] == "stock")
    assert stock["puede_ver"] is True
    assert client.get(f"{URL}/{rol_id}/permisos", headers=h).json() == r.json()
    malo = {"permisos": [{"modulo": "inventado", "recurso": None}]}
    assert client.put(f"{URL}/{rol_id}/permisos", json=malo, headers=h).status_code == 400


def test_rol_inexistente(client, crear_usuario, headers_de):
    h = headers_de(crear_usuario("admin"))
    assert client.get(f"{URL}/999999/permisos", headers=h).status_code == 404
```

- [ ] **Step 2: Correr y ver que falla**

Run: `docker compose exec backend pytest tests/test_permisos_service.py tests/test_roles_api.py -v` → FAIL (módulos inexistentes).

- [ ] **Step 3: Schemas**

`backend/app/schemas/permisos.py`:
```python
from pydantic import BaseModel, Field


class PermisoEntrada(BaseModel):
    modulo: str = Field(min_length=1, max_length=50)
    recurso: str | None = Field(default=None, max_length=100)
    puede_ver: bool = False
    puede_crear: bool = False
    puede_editar: bool = False
    puede_eliminar: bool = False


class ActualizarPermisos(BaseModel):
    permisos: list[PermisoEntrada]


class NodoPermiso(BaseModel):
    modulo: str
    recurso: str | None
    label: str
    acciones_aplicables: list[str]
    puede_ver: bool | None = None
    puede_crear: bool | None = None
    puede_editar: bool | None = None
    puede_eliminar: bool | None = None
    # Solo en el árbol de un usuario: de dónde sale cada permiso.
    heredado_ver: bool | None = None
    heredado_crear: bool | None = None
    heredado_editar: bool | None = None
    heredado_eliminar: bool | None = None
    override_ver: bool | None = None
    override_crear: bool | None = None
    override_editar: bool | None = None
    override_eliminar: bool | None = None
    recursos: list["NodoPermiso"] = []


class ArbolPermisos(BaseModel):
    modulos: list[NodoPermiso]


class AccesoResponse(BaseModel):
    clave: str
    label: str
    heredado: bool
    override: bool
    permitido: bool


class ActualizarAccesos(BaseModel):
    accesos: list[str]
```

`backend/app/schemas/roles.py`:
```python
from datetime import datetime

from pydantic import BaseModel, Field


class RolCrear(BaseModel):
    nombre: str = Field(min_length=1, max_length=50)
    descripcion: str | None = Field(default=None, max_length=255)


class RolEditar(RolCrear):
    pass


class RolEstado(BaseModel):
    activo: bool


class RolResponse(BaseModel):
    id: int
    nombre: str
    descripcion: str | None
    es_sistema: bool
    activo: bool
    cantidad_usuarios: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def desde(cls, rol, cantidad_usuarios: int) -> "RolResponse":
        return cls(
            id=rol.id, nombre=rol.nombre, descripcion=rol.descripcion, es_sistema=rol.es_sistema,
            activo=rol.activo, cantidad_usuarios=cantidad_usuarios, created_at=rol.created_at,
            updated_at=rol.updated_at,
        )
```

- [ ] **Step 4: Services**

`backend/app/services/permisos.py`:
```python
"""Árboles de permisos (por rol y por usuario) y "Accesos permitidos"."""
from sqlalchemy import select

from app.core.auditoria import registrar_auditoria
from app.core.errores import DatoInvalido, ReglaDeNegocio
from app.core.permisos import (
    ACCIONES,
    LABEL_MODULO,
    LABEL_RECURSO,
    ROL_ADMIN,
    Modulo,
    acceso_por_clave,
    acciones_aplicables,
    catalogo_accesos,
    recursos_de_modulo,
    validar_destino,
)
from app.models import RolPermiso, UsuarioPermiso


def _clave_fila(modulo: str, recurso: str | None) -> tuple[str, str | None]:
    return (modulo, recurso)


def _filas_de_rol(db, rol_id: int) -> dict:
    filas = db.scalars(select(RolPermiso).where(RolPermiso.rol_id == rol_id)).all()
    return {_clave_fila(f.modulo, f.recurso): f for f in filas}


def _filas_de_usuario(db, usuario_id: int) -> dict:
    filas = db.scalars(select(UsuarioPermiso).where(UsuarioPermiso.usuario_id == usuario_id)).all()
    return {_clave_fila(f.modulo, f.recurso): f for f in filas}


def _puede(filas: dict, modulo: str, recurso: str | None, accion: str) -> bool:
    """Misma regla que resolver_permiso: la fila general habilita sus recursos."""
    candidatas = [filas.get((modulo, None))]
    if recurso is not None:
        candidatas.append(filas.get((modulo, recurso)))
    return any(f is not None and f.puede(accion) for f in candidatas)


def _snapshot_filas(filas: dict) -> list[dict]:
    return [
        {"modulo": m, "recurso": r, **{a: f.puede(a) for a in ACCIONES}}
        for (m, r), f in sorted(filas.items(), key=lambda x: (x[0][0], x[0][1] or ""))
    ]


def crear_permisos_vacios(db, rol) -> None:
    """Una fila en FALSE por módulo y por recurso (roles personalizados)."""
    for modulo in Modulo:
        db.add(RolPermiso(rol_id=rol.id, modulo=modulo.value, recurso=None))
        for recurso in recursos_de_modulo(modulo):
            db.add(RolPermiso(rol_id=rol.id, modulo=modulo.value, recurso=recurso.value))
    db.flush()


def _nodo(modulo: Modulo, recurso, filas_rol: dict, filas_usuario: dict | None, es_admin: bool) -> dict:
    aplicables = acciones_aplicables(modulo, recurso)
    recurso_valor = recurso.value if recurso else None
    nodo = {
        "modulo": modulo.value,
        "recurso": recurso_valor,
        "label": LABEL_RECURSO[recurso] if recurso else LABEL_MODULO[modulo],
        "acciones_aplicables": list(aplicables),
    }
    for accion in ACCIONES:
        if accion not in aplicables:
            nodo[f"puede_{accion}"] = None  # no aplica: la pantalla muestra "—"
            continue
        heredado = es_admin or _puede(filas_rol, modulo.value, recurso_valor, accion)
        if filas_usuario is None:
            nodo[f"puede_{accion}"] = heredado
            continue
        fila_propia = filas_usuario.get((modulo.value, recurso_valor))
        override = bool(fila_propia and fila_propia.puede(accion))
        nodo[f"heredado_{accion}"] = heredado
        nodo[f"override_{accion}"] = override
        nodo[f"puede_{accion}"] = heredado or _puede(filas_usuario, modulo.value, recurso_valor, accion)
    return nodo


def _arbol(filas_rol: dict, filas_usuario: dict | None, es_admin: bool) -> dict:
    modulos = []
    for modulo in Modulo:
        nodo = _nodo(modulo, None, filas_rol, filas_usuario, es_admin)
        nodo["recursos"] = [_nodo(modulo, r, filas_rol, filas_usuario, es_admin) for r in recursos_de_modulo(modulo)]
        modulos.append(nodo)
    return {"modulos": modulos}


def arbol_de_rol(db, rol) -> dict:
    return _arbol(_filas_de_rol(db, rol.id), None, rol.nombre == ROL_ADMIN)


def arbol_de_usuario(db, usuario) -> dict:
    return _arbol(_filas_de_rol(db, usuario.rol_id), _filas_de_usuario(db, usuario.id), usuario.es_admin)


def _destinos_validos(entradas) -> list[tuple]:
    try:
        return [(validar_destino(e.modulo, e.recurso), e) for e in entradas]
    except ValueError as exc:
        raise DatoInvalido(str(exc)) from exc


def actualizar_permisos_rol(db, autor, rol, entradas, ip) -> None:
    if rol.nombre == ROL_ADMIN:
        raise ReglaDeNegocio("Los permisos del Admin no se editan: tiene acceso total.")
    validas = _destinos_validos(entradas)
    filas = _filas_de_rol(db, rol.id)
    antes = _snapshot_filas(filas)
    for (modulo, recurso), entrada in validas:
        clave = (modulo.value, recurso.value if recurso else None)
        fila = filas.get(clave)
        if fila is None:
            fila = RolPermiso(rol_id=rol.id, modulo=clave[0], recurso=clave[1])
            db.add(fila)
            filas[clave] = fila
        aplicables = acciones_aplicables(modulo, recurso)
        for accion in ACCIONES:  # las que no aplican se guardan FALSE
            setattr(fila, f"puede_{accion}", accion in aplicables and getattr(entrada, f"puede_{accion}"))
    db.flush()
    registrar_auditoria(
        db, accion="rol.permisos_actualizar", entidad="rol", entidad_id=rol.id,
        usuario_id=autor.id if autor else None, ip_origen=ip,
        estado_anterior={"permisos": antes}, estado_nuevo={"permisos": _snapshot_filas(filas)},
    )


def _borrar_overrides_vacios(db, filas: dict) -> None:
    for clave, fila in list(filas.items()):
        if not any(fila.puede(a) for a in ACCIONES):
            db.delete(fila)
            del filas[clave]
    db.flush()


def actualizar_permisos_usuario(db, autor, usuario, entradas, ip) -> None:
    """Overrides aditivos: solo se guardan las acciones marcadas."""
    validas = _destinos_validos(entradas)
    filas = _filas_de_usuario(db, usuario.id)
    antes = _snapshot_filas(filas)
    for (modulo, recurso), entrada in validas:
        clave = (modulo.value, recurso.value if recurso else None)
        fila = filas.get(clave)
        if fila is None:
            fila = UsuarioPermiso(usuario_id=usuario.id, modulo=clave[0], recurso=clave[1])
            db.add(fila)
            filas[clave] = fila
        aplicables = acciones_aplicables(modulo, recurso)
        for accion in ACCIONES:
            setattr(fila, f"puede_{accion}", accion in aplicables and getattr(entrada, f"puede_{accion}"))
    db.flush()
    _borrar_overrides_vacios(db, filas)
    registrar_auditoria(
        db, accion="usuario.permisos_actualizar", entidad="usuario", entidad_id=usuario.id,
        usuario_id=autor.id if autor else None, ip_origen=ip,
        estado_anterior={"permisos": antes}, estado_nuevo={"permisos": _snapshot_filas(filas)},
    )


def _heredado(acceso, filas_rol: dict, es_admin: bool) -> bool:
    recurso = acceso.recurso.value if acceso.recurso else None
    return es_admin or _puede(filas_rol, acceso.modulo.value, recurso, acceso.accion)


def accesos_de_rol(db, rol) -> list[dict]:
    filas = _filas_de_rol(db, rol.id)
    es_admin = rol.nombre == ROL_ADMIN
    resultado = []
    for acceso in catalogo_accesos():
        heredado = _heredado(acceso, filas, es_admin)
        resultado.append({"clave": acceso.clave, "label": acceso.label, "heredado": heredado, "override": False, "permitido": heredado})
    return resultado


def accesos_de_usuario(db, usuario) -> list[dict]:
    filas_rol = _filas_de_rol(db, usuario.rol_id)
    filas_usuario = _filas_de_usuario(db, usuario.id)
    resultado = []
    for acceso in catalogo_accesos():
        recurso = acceso.recurso.value if acceso.recurso else None
        heredado = _heredado(acceso, filas_rol, usuario.es_admin)
        propia = filas_usuario.get((acceso.modulo.value, recurso))
        override = bool(propia and propia.puede(acceso.accion))
        permitido = heredado or _puede(filas_usuario, acceso.modulo.value, recurso, acceso.accion)
        resultado.append({"clave": acceso.clave, "label": acceso.label, "heredado": heredado, "override": override, "permitido": permitido})
    return resultado


def _claves_override(filas: dict) -> list[str]:
    claves = []
    for acceso in catalogo_accesos():
        fila = filas.get((acceso.modulo.value, acceso.recurso.value if acceso.recurso else None))
        if fila is not None and fila.puede(acceso.accion):
            claves.append(acceso.clave)
    return claves


def actualizar_accesos_usuario(db, autor, usuario, claves: list[str], ip) -> None:
    """Solo toca la acción de cada acceso del catálogo; lo heredado del rol no
    se persiste como override."""
    desconocidas = [c for c in claves if acceso_por_clave(c) is None]
    if desconocidas:
        raise DatoInvalido(f"Accesos desconocidos: {', '.join(desconocidas)}")
    marcadas = set(claves)
    filas_rol = _filas_de_rol(db, usuario.rol_id)
    filas = _filas_de_usuario(db, usuario.id)
    antes = _claves_override(filas)
    for acceso in catalogo_accesos():
        if _heredado(acceso, filas_rol, usuario.es_admin):
            continue
        clave = (acceso.modulo.value, acceso.recurso.value if acceso.recurso else None)
        fila = filas.get(clave)
        deseado = acceso.clave in marcadas
        if fila is None:
            if not deseado:
                continue
            fila = UsuarioPermiso(usuario_id=usuario.id, modulo=clave[0], recurso=clave[1])
            db.add(fila)
            filas[clave] = fila
        setattr(fila, f"puede_{acceso.accion}", deseado)
    db.flush()
    _borrar_overrides_vacios(db, filas)
    registrar_auditoria(
        db, accion="usuario.accesos_actualizar", entidad="usuario", entidad_id=usuario.id,
        usuario_id=autor.id if autor else None, ip_origen=ip,
        estado_anterior={"accesos": antes}, estado_nuevo={"accesos": _claves_override(filas)},
    )
```

`backend/app/services/roles.py`:
```python
"""Roles: los de sistema (admin/supervisor/vendedor) no se borran ni renombran."""
from sqlalchemy import func, select

from app.core.auditoria import registrar_auditoria, snapshot
from app.core.errores import DatoInvalido, NoEncontrado, ReglaDeNegocio
from app.core.utils import normalizar_texto
from app.models import Rol, Usuario
from app.services.permisos import crear_permisos_vacios


def obtener_rol(db, rol_id: int) -> Rol:
    rol = db.get(Rol, rol_id)
    if rol is None:
        raise NoEncontrado("Rol no encontrado")
    return rol


def cantidad_usuarios(db, rol_id: int, solo_activos: bool = False) -> int:
    condiciones = [Usuario.rol_id == rol_id]
    if solo_activos:
        condiciones.append(Usuario.activo.is_(True))
    return db.scalar(select(func.count()).select_from(Usuario).where(*condiciones))


def listar_roles(db, *, nombre: str | None = None, activo: bool | None = None,
                 es_sistema: bool | None = None) -> list[tuple[Rol, int]]:
    cantidad = (
        select(func.count(Usuario.id)).where(Usuario.rol_id == Rol.id).correlate(Rol).scalar_subquery()
    )
    consulta = select(Rol, cantidad).order_by(Rol.es_sistema.desc(), func.lower(Rol.nombre))
    if nombre:
        consulta = consulta.where(Rol.nombre.ilike(f"%{nombre}%"))
    if activo is not None:
        consulta = consulta.where(Rol.activo.is_(activo))
    if es_sistema is not None:
        consulta = consulta.where(Rol.es_sistema.is_(es_sistema))
    return [(rol, total) for rol, total in db.execute(consulta).all()]


def _validar_nombre_libre(db, nombre: str, excepto_id: int | None = None) -> str:
    limpio = normalizar_texto(nombre)
    if not limpio:
        raise DatoInvalido("El nombre del rol es obligatorio")
    condiciones = [func.lower(Rol.nombre) == limpio.lower()]
    if excepto_id is not None:
        condiciones.append(Rol.id != excepto_id)
    if db.scalar(select(Rol.id).where(*condiciones)) is not None:
        raise ReglaDeNegocio(f"Ya existe un rol llamado '{limpio}'")
    return limpio


def crear_rol(db, autor, nombre: str, descripcion: str | None, ip) -> Rol:
    rol = Rol(nombre=_validar_nombre_libre(db, nombre), descripcion=normalizar_texto(descripcion), es_sistema=False, activo=True)
    db.add(rol)
    db.flush()
    crear_permisos_vacios(db, rol)
    registrar_auditoria(db, accion="rol.crear", entidad="rol", entidad_id=rol.id, usuario_id=autor.id, estado_nuevo=rol, ip_origen=ip)
    return rol


def editar_rol(db, autor, rol: Rol, nombre: str, descripcion: str | None, ip) -> Rol:
    antes = snapshot(rol)
    nombre_limpio = normalizar_texto(nombre)
    if rol.es_sistema and nombre_limpio != rol.nombre:
        raise ReglaDeNegocio("Los roles del sistema no se renombran")
    if not rol.es_sistema:
        rol.nombre = _validar_nombre_libre(db, nombre, excepto_id=rol.id)
    rol.descripcion = normalizar_texto(descripcion)
    db.flush()
    registrar_auditoria(db, accion="rol.editar", entidad="rol", entidad_id=rol.id, usuario_id=autor.id,
                        estado_anterior=antes, estado_nuevo=rol, ip_origen=ip)
    return rol


def cambiar_estado_rol(db, autor, rol: Rol, activo: bool, ip) -> Rol:
    if not activo:
        activos = cantidad_usuarios(db, rol.id, solo_activos=True)
        if activos:
            raise ReglaDeNegocio(
                f"El rol tiene {activos} usuario(s) activo(s): desactivarlos o reasignarlos antes de desactivar el rol."
            )
    antes = snapshot(rol)
    rol.activo = activo
    db.flush()
    registrar_auditoria(db, accion="rol.activar" if activo else "rol.desactivar", entidad="rol", entidad_id=rol.id,
                        usuario_id=autor.id, estado_anterior=antes, estado_nuevo=rol, ip_origen=ip)
    return rol


def eliminar_rol(db, autor, rol: Rol, ip) -> None:
    if rol.es_sistema:
        raise ReglaDeNegocio("Los roles del sistema no se eliminan")
    if cantidad_usuarios(db, rol.id):
        raise ReglaDeNegocio("El rol tiene usuarios asociados: reasignarlos antes de eliminarlo")
    antes = snapshot(rol)
    db.delete(rol)
    db.flush()
    registrar_auditoria(db, accion="rol.eliminar", entidad="rol", entidad_id=antes["id"], usuario_id=autor.id,
                        estado_anterior=antes, ip_origen=ip)
```

- [ ] **Step 5: Router**

`backend/app/api/v1/roles.py`:
```python
"""Roles y su árbol de permisos (solo Admin)."""
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.seguridad import requiere_admin
from app.core.utils import ip_de_request
from app.models import Usuario
from app.schemas.permisos import ActualizarPermisos, ArbolPermisos
from app.schemas.roles import RolCrear, RolEditar, RolEstado, RolResponse
from app.services import permisos, roles

router = APIRouter(prefix="/roles", tags=["roles"])


def _respuesta(db, rol) -> RolResponse:
    return RolResponse.desde(rol, roles.cantidad_usuarios(db, rol.id))


@router.get("", response_model=list[RolResponse])
def listar(nombre: str | None = None, activo: bool | None = None, es_sistema: bool | None = None,
           db: Session = Depends(get_db), _: Usuario = Depends(requiere_admin)):
    return [RolResponse.desde(rol, total) for rol, total in roles.listar_roles(db, nombre=nombre, activo=activo, es_sistema=es_sistema)]


@router.post("", response_model=RolResponse, status_code=201)
def crear(datos: RolCrear, request: Request, db: Session = Depends(get_db), autor: Usuario = Depends(requiere_admin)):
    rol = roles.crear_rol(db, autor, datos.nombre, datos.descripcion, ip_de_request(request))
    db.commit()
    return _respuesta(db, rol)


@router.put("/{rol_id}", response_model=RolResponse)
def editar(rol_id: int, datos: RolEditar, request: Request, db: Session = Depends(get_db),
           autor: Usuario = Depends(requiere_admin)):
    rol = roles.editar_rol(db, autor, roles.obtener_rol(db, rol_id), datos.nombre, datos.descripcion, ip_de_request(request))
    db.commit()
    return _respuesta(db, rol)


@router.patch("/{rol_id}/estado", response_model=RolResponse)
def cambiar_estado(rol_id: int, datos: RolEstado, request: Request, db: Session = Depends(get_db),
                   autor: Usuario = Depends(requiere_admin)):
    rol = roles.cambiar_estado_rol(db, autor, roles.obtener_rol(db, rol_id), datos.activo, ip_de_request(request))
    db.commit()
    return _respuesta(db, rol)


@router.delete("/{rol_id}", status_code=204)
def eliminar(rol_id: int, request: Request, db: Session = Depends(get_db), autor: Usuario = Depends(requiere_admin)):
    roles.eliminar_rol(db, autor, roles.obtener_rol(db, rol_id), ip_de_request(request))
    db.commit()
    return Response(status_code=204)


@router.get("/{rol_id}/permisos", response_model=ArbolPermisos)
def ver_permisos(rol_id: int, db: Session = Depends(get_db), _: Usuario = Depends(requiere_admin)):
    return permisos.arbol_de_rol(db, roles.obtener_rol(db, rol_id))


@router.put("/{rol_id}/permisos", response_model=ArbolPermisos)
def guardar_permisos(rol_id: int, datos: ActualizarPermisos, request: Request, db: Session = Depends(get_db),
                     autor: Usuario = Depends(requiere_admin)):
    rol = roles.obtener_rol(db, rol_id)
    permisos.actualizar_permisos_rol(db, autor, rol, datos.permisos, ip_de_request(request))
    db.commit()
    return permisos.arbol_de_rol(db, rol)
```


En `backend/app/api/v1/__init__.py`, incluir `roles.router`.

- [ ] **Step 6: Correr y ver que pasa**

Run: `docker compose exec backend pytest tests/test_permisos_service.py tests/test_roles_api.py -v` → PASS; luego suite completa.

- [ ] **Step 7: Commit** — `feat(auth): árboles de permisos, accesos y ABM de roles`.

---

### Task 8: Usuarios (service y endpoints)

**Files:**
- Create: `backend/app/schemas/usuarios.py`, `backend/app/services/usuarios.py`, `backend/app/api/v1/usuarios.py`
- Modify: `backend/app/api/v1/__init__.py`
- Test: `backend/tests/test_usuarios_api.py`

**Interfaces:**
- Consumes: `Password`, services `auth` / `permisos` / `roles`, `requiere_permiso`, `RespuestaPaginada`, `sin_tildes_sql`, `sin_tildes`, `normalizar_texto`, `snapshot`.
- Produces (`services/usuarios.py`): `obtener_usuario(db, id)`, `validar_puede_gestionar(autor, rol_objetivo)`, `roles_asignables(db, autor) -> list[Rol]`, `listar_usuarios(db, *, nombre, username, email, rol_id, activo, pagina, tamano) -> tuple[list[Usuario], int]`, `crear_usuario(db, autor, datos, ip) -> Usuario`, `editar_usuario(db, autor, usuario, datos, ip) -> Usuario`, `cambiar_estado_usuario(db, autor, usuario, activo, ip) -> Usuario`, `historial_de_usuario(db, usuario_id, *, desde, hasta, resultado, pagina, tamano) -> tuple[list[HistorialAcceso], int]`; `TAMANO_MAXIMO = 100`.
- Produces (schemas): `normalizar_celular(v)`, `UsuarioCrear`, `UsuarioEditar` (extra prohibido: `username` no se edita), `UsuarioEstado`, `UsuarioResponse` (`UsuarioResponse.desde(u)`), `RolAsignable`, `HistorialAccesoResponse`.
- Endpoints `/api/v1/usuarios` según el spec (sin clave especial).

- [ ] **Step 1: Tests que fallan**

`backend/tests/test_usuarios_api.py`:
```python
from sqlalchemy import select

from app.models import Auditoria, Rol, Sesion, Usuario
from app.services import auth

URL = "/api/v1/usuarios"


def _rol_id(db, nombre):
    return db.scalar(select(Rol.id).where(Rol.nombre == nombre))


def _alta(**extra):
    datos = {"username": "Nuevo.Vendedor", "nombre": "Nuevo Vendedor", "password": "Clave1234"}
    datos.update(extra)
    return datos


def test_admin_crea_vendedor(client, crear_usuario, headers_de, db):
    h = headers_de(crear_usuario("admin"))
    r = client.post(URL, json=_alta(rol_id=_rol_id(db, "vendedor"), celular="+54 9 351-210-8190", email="Nuevo@Example.com"), headers=h)
    assert r.status_code == 201
    u = r.json()
    assert u["username"] == "nuevo.vendedor" and u["rol"] == "vendedor"
    assert u["celular"] == "+5493512108190" and u["email"] == "nuevo@example.com"
    assert u["ultimo_acceso"] is None and "password_hash" not in u
    registro = db.scalar(select(Auditoria).where(Auditoria.accion == "usuario.crear", Auditoria.entidad_id == u["id"]))
    assert "password_hash" not in registro.estado_nuevo


def test_validaciones_del_alta(client, crear_usuario, headers_de, db):
    h = headers_de(crear_usuario("admin"))
    vendedor = _rol_id(db, "vendedor")
    assert client.post(URL, json=_alta(rol_id=_rol_id(db, "admin")), headers=h).status_code == 409
    assert client.post(URL, json=_alta(rol_id=vendedor), headers=h).status_code == 201
    assert client.post(URL, json=_alta(rol_id=vendedor), headers=h).status_code == 409  # username repetido
    assert client.post(URL, json=_alta(rol_id=vendedor, username="otro", email="a@b.com"), headers=h).status_code == 201
    assert client.post(URL, json=_alta(rol_id=vendedor, username="otro2", email="A@B.com"), headers=h).status_code == 409
    assert client.post(URL, json=_alta(rol_id=vendedor, username="x3", celular="12ab"), headers=h).status_code == 422
    assert client.post(URL, json=_alta(rol_id=vendedor, username="ab"), headers=h).status_code == 422


def test_supervisor_solo_gestiona_vendedores(client, crear_usuario, headers_de, db):
    h = headers_de(crear_usuario("supervisor"))
    assert client.post(URL, json=_alta(rol_id=_rol_id(db, "vendedor")), headers=h).status_code == 201
    assert client.post(URL, json=_alta(username="sup2", rol_id=_rol_id(db, "supervisor")), headers=h).status_code == 403
    otro_supervisor = crear_usuario("supervisor")
    assert client.put(f"{URL}/{otro_supervisor.id}", json={"nombre": "X"}, headers=h).status_code == 403
    asignables = [r["nombre"] for r in client.get(f"{URL}/roles-asignables", headers=h).json()]
    assert asignables == ["vendedor"]


def test_vendedor_no_gestiona_usuarios(client, crear_usuario, headers_de, db):
    h = headers_de(crear_usuario("vendedor"))
    assert client.get(URL, headers=h).status_code == 403
    assert client.post(URL, json=_alta(rol_id=_rol_id(db, "vendedor")), headers=h).status_code == 403


def test_edicion(client, crear_usuario, headers_de, db):
    h = headers_de(crear_usuario("admin"))
    u = crear_usuario("vendedor", celular="3511111111", email="viejo@example.com")
    assert client.put(f"{URL}/{u.id}", json={"username": "otro"}, headers=h).status_code == 422
    r = client.put(f"{URL}/{u.id}", json={"nombre": "Nombre Nuevo", "celular": None}, headers=h)
    assert r.status_code == 200
    assert r.json()["nombre"] == "Nombre Nuevo" and r.json()["celular"] is None
    assert r.json()["email"] == "viejo@example.com"  # no enviado: se conserva
    assert db.scalar(select(Auditoria).where(Auditoria.accion == "usuario.editar", Auditoria.entidad_id == u.id))


def test_editar_password_fuerza_cambio_y_revoca_sesiones(client, crear_usuario, headers_de, db):
    h = headers_de(crear_usuario("admin"))
    u = crear_usuario("vendedor")
    _, refresh, _ = auth.generar_tokens(db, u, None)
    r = client.put(f"{URL}/{u.id}", json={"password": "Reseteada1"}, headers=h)
    assert r.status_code == 200 and r.json()["ultimo_acceso"] is None
    assert db.scalar(select(Sesion.revocada).where(Sesion.usuario_id == u.id))


def test_no_se_cambia_el_rol_del_admin_ni_se_asigna_admin(client, crear_usuario, headers_de, db):
    admin = crear_usuario("admin")
    h = headers_de(admin)
    otro_admin = db.scalar(select(Usuario).where(Usuario.username == "admin"))
    assert client.put(f"{URL}/{otro_admin.id}", json={"rol_id": _rol_id(db, "vendedor")}, headers=h).status_code == 409
    vendedor = crear_usuario("vendedor")
    assert client.put(f"{URL}/{vendedor.id}", json={"rol_id": _rol_id(db, "admin")}, headers=h).status_code == 409


def test_estado(client, crear_usuario, headers_de, db):
    admin = crear_usuario("admin")
    h = headers_de(admin)
    assert client.patch(f"{URL}/{admin.id}/estado", json={"activo": False}, headers=h).status_code == 409
    seed_admin = db.scalar(select(Usuario).where(Usuario.username == "admin"))
    assert client.patch(f"{URL}/{seed_admin.id}/estado", json={"activo": False}, headers=h).status_code == 409
    vendedor = crear_usuario("vendedor")
    auth.generar_tokens(db, vendedor, None)
    r = client.patch(f"{URL}/{vendedor.id}/estado", json={"activo": False}, headers=h)
    assert r.status_code == 200 and r.json()["activo"] is False
    assert db.scalar(select(Sesion.revocada).where(Sesion.usuario_id == vendedor.id))


def test_listado_con_filtros_y_paginacion(client, crear_usuario, headers_de, db):
    h = headers_de(crear_usuario("admin"))
    crear_usuario("vendedor", nombre="José Gómez")
    crear_usuario("vendedor", nombre="Josefina Díaz", activo=False)
    r = client.get(URL, params={"nombre": "jose"}, headers=h).json()
    assert r["total"] == 2 and r["tamano"] == 10
    r = client.get(URL, params={"nombre": "jose", "activo": True}, headers=h).json()
    assert [u["nombre"] for u in r["resultados"]] == ["José Gómez"]
    r = client.get(URL, params={"nombre": "jose", "tamano": 1, "pagina": 2}, headers=h).json()
    assert r["total"] == 2 and len(r["resultados"]) == 1


def test_historial_de_accesos(client, crear_usuario, headers_de):
    h = headers_de(crear_usuario("admin"))
    u = crear_usuario("vendedor", username="histo", password="Clave1234")
    client.post("/api/v1/auth/login", json={"username": "histo", "password": "mala"})
    client.post("/api/v1/auth/login", json={"username": "histo", "password": "Clave1234"})
    r = client.get(f"{URL}/{u.id}/historial", headers=h).json()
    assert r["total"] == 2 and r["resultados"][0]["resultado"] == "exitoso"
    r = client.get(f"{URL}/{u.id}/historial", params={"resultado": "fallido"}, headers=h).json()
    assert r["total"] == 1 and r["resultados"][0]["detalle"] == "Contraseña incorrecta"


def test_accesos_y_permisos_de_usuario(client, crear_usuario, headers_de, db):
    h = headers_de(crear_usuario("admin"))
    vendedor = crear_usuario("vendedor")
    base = client.get(f"{URL}/accesos", params={"rol_id": _rol_id(db, "vendedor")}, headers=h).json()
    assert next(a for a in base if a["clave"] == "stock:stock.baja:crear")["heredado"]
    r = client.put(f"{URL}/{vendedor.id}/accesos", json={"accesos": ["caja:caja.retiro:crear"]}, headers=h)
    assert r.status_code == 200
    retiro = next(a for a in r.json() if a["clave"] == "caja:caja.retiro:crear")
    assert retiro["override"] and retiro["permitido"]
    arbol = client.get(f"{URL}/{vendedor.id}/permisos", headers=h).json()
    caja = next(n for n in arbol["modulos"] if n["modulo"] == "caja")
    nodo = next(r for r in caja["recursos"] if r["recurso"] == "caja.retiro")
    assert nodo["override_crear"] is True and nodo["heredado_crear"] is False
    r = client.put(f"{URL}/{vendedor.id}/permisos", json={"permisos": []}, headers=h)
    assert r.status_code == 200


def test_usuario_inexistente(client, crear_usuario, headers_de):
    h = headers_de(crear_usuario("admin"))
    assert client.get(f"{URL}/999999", headers=h).status_code == 404
```

- [ ] **Step 2: Correr y ver que falla**

Run: `docker compose exec backend pytest tests/test_usuarios_api.py -v` → FAIL (404 en `/api/v1/usuarios`).

- [ ] **Step 3: Schemas**

`backend/app/schemas/usuarios.py`:
```python
import re
from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, EmailStr, Field

from app.models import ResultadoAcceso
from app.schemas.auth import Password


def normalizar_celular(valor):
    """"+54 9 351-210-8190" → "+5493512108190". Vacío → None."""
    if valor is None:
        return None
    limpio = re.sub(r"[\s\-().]", "", str(valor))
    if not limpio:
        return None
    if not re.fullmatch(r"\+?\d{6,19}", limpio):
        raise ValueError("Celular inválido: solo dígitos (de 6 a 19), con + opcional")
    return limpio


Celular = Annotated[str | None, BeforeValidator(normalizar_celular)]


class UsuarioCrear(BaseModel):
    username: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9._-]+$")
    nombre: str = Field(min_length=1, max_length=150)
    password: Password
    rol_id: int
    email: EmailStr | None = None
    fecha_nacimiento: date | None = None
    celular: Celular = None


class UsuarioEditar(BaseModel):
    """Todos opcionales. Se distingue "no enviado" de "enviado en null"
    (model_fields_set). El username no se edita (extra prohibido)."""

    model_config = ConfigDict(extra="forbid")

    nombre: str | None = Field(default=None, min_length=1, max_length=150)
    rol_id: int | None = None
    email: EmailStr | None = None
    fecha_nacimiento: date | None = None
    celular: Celular = None
    password: Password | None = None


class UsuarioEstado(BaseModel):
    activo: bool


class UsuarioResponse(BaseModel):
    id: int
    username: str
    email: str | None
    nombre: str
    rol_id: int
    rol: str
    activo: bool
    fecha_nacimiento: date | None
    celular: str | None
    created_at: datetime
    updated_at: datetime
    ultimo_acceso: datetime | None

    @classmethod
    def desde(cls, usuario) -> "UsuarioResponse":
        return cls(
            id=usuario.id, username=usuario.username, email=usuario.email, nombre=usuario.nombre,
            rol_id=usuario.rol_id, rol=usuario.rol.nombre, activo=usuario.activo,
            fecha_nacimiento=usuario.fecha_nacimiento, celular=usuario.celular,
            created_at=usuario.created_at, updated_at=usuario.updated_at, ultimo_acceso=usuario.ultimo_acceso,
        )


class RolAsignable(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    descripcion: str | None


class HistorialAccesoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    timestamp: datetime
    ip_origen: str | None
    resultado: ResultadoAcceso
    detalle: str | None
```

- [ ] **Step 4: Service**

`backend/app/services/usuarios.py`:
```python
"""Usuarios: alta, edición, estado e historial. Admin gestiona a todos; el
resto de los que tienen permiso sobre Usuarios, solo a vendedores."""
from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select

from app.core.auditoria import registrar_auditoria, snapshot
from app.core.errores import DatoInvalido, NoEncontrado, ReglaDeNegocio, SinPermiso
from app.core.permisos import ROL_ADMIN, ROL_VENDEDOR
from app.core.utils import normalizar_texto, sin_tildes, sin_tildes_sql
from app.models import HistorialAcceso, ResultadoAcceso, Rol, Usuario
from app.services import auth

TAMANO_MAXIMO = 100


def obtener_usuario(db, usuario_id: int) -> Usuario:
    usuario = db.get(Usuario, usuario_id)
    if usuario is None:
        raise NoEncontrado("Usuario no encontrado")
    return usuario


def validar_puede_gestionar(autor: Usuario, rol_objetivo: Rol) -> None:
    if autor.es_admin:
        return
    if rol_objetivo.nombre != ROL_VENDEDOR:
        raise SinPermiso("Solo podés gestionar usuarios con rol vendedor")


def roles_asignables(db, autor: Usuario) -> list[Rol]:
    consulta = select(Rol).where(Rol.activo.is_(True), Rol.nombre != ROL_ADMIN).order_by(func.lower(Rol.nombre))
    if not autor.es_admin:
        consulta = consulta.where(Rol.nombre == ROL_VENDEDOR)
    return list(db.scalars(consulta).all())


def _rol_asignable(db, autor: Usuario, rol_id: int) -> Rol:
    rol = db.get(Rol, rol_id)
    if rol is None or not rol.activo:
        raise ReglaDeNegocio("El rol elegido no existe o está inactivo")
    if rol.nombre == ROL_ADMIN:
        raise ReglaDeNegocio("No se puede asignar el rol Admin")
    validar_puede_gestionar(autor, rol)
    return rol


def _paginar(pagina: int, tamano: int) -> tuple[int, int]:
    return max(1, pagina), max(1, min(tamano, TAMANO_MAXIMO))


def listar_usuarios(db, *, nombre=None, username=None, email=None, rol_id=None, activo=None,
                    pagina: int = 1, tamano: int = 10) -> tuple[list[Usuario], int]:
    condiciones = []
    if nombre:
        condiciones.append(sin_tildes_sql(Usuario.nombre).ilike(f"%{sin_tildes(nombre)}%"))
    if username:
        condiciones.append(Usuario.username.ilike(f"%{username}%"))
    if email:
        condiciones.append(Usuario.email.ilike(f"%{email}%"))
    if rol_id is not None:
        condiciones.append(Usuario.rol_id == rol_id)
    if activo is not None:
        condiciones.append(Usuario.activo.is_(activo))
    pagina, tamano = _paginar(pagina, tamano)
    total = db.scalar(select(func.count()).select_from(Usuario).where(*condiciones))
    usuarios = db.scalars(
        select(Usuario).where(*condiciones).order_by(func.lower(Usuario.nombre), Usuario.id)
        .offset((pagina - 1) * tamano).limit(tamano)
    ).all()
    return list(usuarios), total


def _validar_username_libre(db, username: str) -> str:
    username = username.strip().lower()
    if db.scalar(select(Usuario.id).where(Usuario.username == username)) is not None:
        raise ReglaDeNegocio(f"El usuario '{username}' ya existe")
    return username


def _validar_email_libre(db, email: str | None, excepto_id: int | None = None) -> str | None:
    if not email:
        return None
    email = email.strip().lower()
    condiciones = [func.lower(Usuario.email) == email]
    if excepto_id is not None:
        condiciones.append(Usuario.id != excepto_id)
    if db.scalar(select(Usuario.id).where(*condiciones)) is not None:
        raise ReglaDeNegocio("El email ya está cargado en otro usuario")
    return email


def _nombre_obligatorio(nombre: str | None) -> str:
    limpio = normalizar_texto(nombre)
    if not limpio:
        raise DatoInvalido("El nombre es obligatorio")
    return limpio


def crear_usuario(db, autor: Usuario, datos, ip) -> Usuario:
    rol = _rol_asignable(db, autor, datos.rol_id)
    usuario = Usuario(
        username=_validar_username_libre(db, datos.username),
        nombre=_nombre_obligatorio(datos.nombre),
        password_hash=auth.hash_password(datos.password),
        rol_id=rol.id,
        email=_validar_email_libre(db, datos.email),
        fecha_nacimiento=datos.fecha_nacimiento,
        celular=datos.celular,
        activo=True,
        ultimo_acceso=None,  # obliga a cambiar la contraseña en el primer ingreso
    )
    db.add(usuario)
    db.flush()
    db.refresh(usuario)
    registrar_auditoria(db, accion="usuario.crear", entidad="usuario", entidad_id=usuario.id,
                        usuario_id=autor.id, estado_nuevo=usuario, ip_origen=ip)
    return usuario


def editar_usuario(db, autor: Usuario, usuario: Usuario, datos, ip) -> Usuario:
    validar_puede_gestionar(autor, usuario.rol)
    antes = snapshot(usuario)
    enviados = datos.model_fields_set
    if "rol_id" in enviados and datos.rol_id is not None and datos.rol_id != usuario.rol_id:
        if usuario.es_admin:
            raise ReglaDeNegocio("No se puede cambiar el rol del Admin")
        usuario.rol_id = _rol_asignable(db, autor, datos.rol_id).id
    if "nombre" in enviados:
        usuario.nombre = _nombre_obligatorio(datos.nombre)
    if "email" in enviados:
        usuario.email = _validar_email_libre(db, datos.email, excepto_id=usuario.id)
    for campo in ("fecha_nacimiento", "celular"):
        if campo in enviados:
            setattr(usuario, campo, getattr(datos, campo))
    db.flush()
    if "password" in enviados and datos.password:
        auth.cambiar_password(db, usuario, datos.password, autor_id=autor.id, ip=ip, debe_cambiarla=True)
    db.refresh(usuario)
    registrar_auditoria(db, accion="usuario.editar", entidad="usuario", entidad_id=usuario.id,
                        usuario_id=autor.id, estado_anterior=antes, estado_nuevo=usuario, ip_origen=ip)
    return usuario


def cambiar_estado_usuario(db, autor: Usuario, usuario: Usuario, activo: bool, ip) -> Usuario:
    validar_puede_gestionar(autor, usuario.rol)
    if not activo:
        if usuario.id == autor.id:
            raise ReglaDeNegocio("No podés desactivarte a vos mismo")
        if usuario.es_admin:
            raise ReglaDeNegocio("El Admin no se puede desactivar")
    antes = snapshot(usuario)
    usuario.activo = activo
    db.flush()
    if not activo:
        auth.revocar_sesiones_de_usuario(db, usuario.id)
    registrar_auditoria(db, accion="usuario.activar" if activo else "usuario.desactivar", entidad="usuario",
                        entidad_id=usuario.id, usuario_id=autor.id, estado_anterior=antes, estado_nuevo=usuario, ip_origen=ip)
    return usuario


def historial_de_usuario(db, usuario_id: int, *, desde: date | None = None, hasta: date | None = None,
                         resultado: ResultadoAcceso | None = None, pagina: int = 1,
                         tamano: int = 10) -> tuple[list[HistorialAcceso], int]:
    condiciones = [HistorialAcceso.usuario_id == usuario_id]
    if desde:
        condiciones.append(HistorialAcceso.timestamp >= datetime.combine(desde, time.min))
    if hasta:
        condiciones.append(HistorialAcceso.timestamp < datetime.combine(hasta + timedelta(days=1), time.min))
    if resultado is not None:
        condiciones.append(HistorialAcceso.resultado == resultado)
    pagina, tamano = _paginar(pagina, tamano)
    total = db.scalar(select(func.count()).select_from(HistorialAcceso).where(*condiciones))
    filas = db.scalars(
        select(HistorialAcceso).where(*condiciones)
        .order_by(HistorialAcceso.timestamp.desc(), HistorialAcceso.id.desc())
        .offset((pagina - 1) * tamano).limit(tamano)
    ).all()
    return list(filas), total
```

- [ ] **Step 5: Router**

`backend/app/api/v1/usuarios.py`:
```python
"""Usuarios. Las rutas fijas van antes de /{usuario_id}; toda gestión sobre un
usuario pasa por validar_puede_gestionar."""
from datetime import date

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.permisos import Modulo
from app.core.seguridad import requiere_permiso
from app.core.utils import ip_de_request
from app.models import ResultadoAcceso, Usuario
from app.schemas.comunes import RespuestaPaginada
from app.schemas.permisos import AccesoResponse, ActualizarAccesos, ActualizarPermisos, ArbolPermisos
from app.schemas.usuarios import (
    HistorialAccesoResponse,
    RolAsignable,
    UsuarioCrear,
    UsuarioEditar,
    UsuarioEstado,
    UsuarioResponse,
)
from app.services import permisos, roles, usuarios
from app.services.usuarios import TAMANO_MAXIMO

router = APIRouter(prefix="/usuarios", tags=["usuarios"])

puede_ver = requiere_permiso(Modulo.USUARIOS, "ver")
puede_crear = requiere_permiso(Modulo.USUARIOS, "crear")
puede_editar = requiere_permiso(Modulo.USUARIOS, "editar")


@router.get("", response_model=RespuestaPaginada[UsuarioResponse])
def listar(nombre: str | None = None, username: str | None = None, email: str | None = None,
           rol_id: int | None = None, activo: bool | None = None, pagina: int = Query(1, ge=1),
           tamano: int = Query(10, ge=1, le=TAMANO_MAXIMO), db: Session = Depends(get_db),
           _: Usuario = Depends(puede_ver)):
    items, total = usuarios.listar_usuarios(db, nombre=nombre, username=username, email=email, rol_id=rol_id,
                                            activo=activo, pagina=pagina, tamano=tamano)
    return RespuestaPaginada(total=total, pagina=pagina, tamano=tamano,
                             resultados=[UsuarioResponse.desde(u) for u in items])


@router.get("/roles-asignables", response_model=list[RolAsignable])
def roles_asignables(db: Session = Depends(get_db), autor: Usuario = Depends(puede_ver)):
    return usuarios.roles_asignables(db, autor)


@router.get("/accesos", response_model=list[AccesoResponse])
def accesos_de_rol(rol_id: int, db: Session = Depends(get_db), _: Usuario = Depends(puede_ver)):
    return permisos.accesos_de_rol(db, roles.obtener_rol(db, rol_id))


@router.get("/{usuario_id}", response_model=UsuarioResponse)
def detalle(usuario_id: int, db: Session = Depends(get_db), _: Usuario = Depends(puede_ver)):
    return UsuarioResponse.desde(usuarios.obtener_usuario(db, usuario_id))


@router.post("", response_model=UsuarioResponse, status_code=201)
def crear(datos: UsuarioCrear, request: Request, db: Session = Depends(get_db), autor: Usuario = Depends(puede_crear)):
    usuario = usuarios.crear_usuario(db, autor, datos, ip_de_request(request))
    db.commit()
    return UsuarioResponse.desde(usuario)


@router.put("/{usuario_id}", response_model=UsuarioResponse)
def editar(usuario_id: int, datos: UsuarioEditar, request: Request, db: Session = Depends(get_db),
           autor: Usuario = Depends(puede_editar)):
    usuario = usuarios.editar_usuario(db, autor, usuarios.obtener_usuario(db, usuario_id), datos, ip_de_request(request))
    db.commit()
    return UsuarioResponse.desde(usuario)


@router.patch("/{usuario_id}/estado", response_model=UsuarioResponse)
def cambiar_estado(usuario_id: int, datos: UsuarioEstado, request: Request, db: Session = Depends(get_db),
                   autor: Usuario = Depends(puede_editar)):
    usuario = usuarios.cambiar_estado_usuario(db, autor, usuarios.obtener_usuario(db, usuario_id), datos.activo,
                                              ip_de_request(request))
    db.commit()
    return UsuarioResponse.desde(usuario)


@router.get("/{usuario_id}/accesos", response_model=list[AccesoResponse])
def accesos(usuario_id: int, db: Session = Depends(get_db), _: Usuario = Depends(puede_ver)):
    return permisos.accesos_de_usuario(db, usuarios.obtener_usuario(db, usuario_id))


@router.put("/{usuario_id}/accesos", response_model=list[AccesoResponse])
def guardar_accesos(usuario_id: int, datos: ActualizarAccesos, request: Request, db: Session = Depends(get_db),
                    autor: Usuario = Depends(puede_editar)):
    usuario = usuarios.obtener_usuario(db, usuario_id)
    usuarios.validar_puede_gestionar(autor, usuario.rol)
    permisos.actualizar_accesos_usuario(db, autor, usuario, datos.accesos, ip_de_request(request))
    db.commit()
    return permisos.accesos_de_usuario(db, usuario)


@router.get("/{usuario_id}/permisos", response_model=ArbolPermisos)
def ver_permisos(usuario_id: int, db: Session = Depends(get_db), _: Usuario = Depends(puede_ver)):
    return permisos.arbol_de_usuario(db, usuarios.obtener_usuario(db, usuario_id))


@router.put("/{usuario_id}/permisos", response_model=ArbolPermisos)
def guardar_permisos(usuario_id: int, datos: ActualizarPermisos, request: Request, db: Session = Depends(get_db),
                     autor: Usuario = Depends(puede_editar)):
    usuario = usuarios.obtener_usuario(db, usuario_id)
    usuarios.validar_puede_gestionar(autor, usuario.rol)
    permisos.actualizar_permisos_usuario(db, autor, usuario, datos.permisos, ip_de_request(request))
    db.commit()
    return permisos.arbol_de_usuario(db, usuario)


@router.get("/{usuario_id}/historial", response_model=RespuestaPaginada[HistorialAccesoResponse])
def historial(usuario_id: int, desde: date | None = None, hasta: date | None = None,
              resultado: ResultadoAcceso | None = None, pagina: int = Query(1, ge=1),
              tamano: int = Query(10, ge=1, le=TAMANO_MAXIMO), db: Session = Depends(get_db),
              _: Usuario = Depends(puede_ver)):
    usuarios.obtener_usuario(db, usuario_id)
    filas, total = usuarios.historial_de_usuario(db, usuario_id, desde=desde, hasta=hasta, resultado=resultado,
                                                 pagina=pagina, tamano=tamano)
    return RespuestaPaginada(total=total, pagina=pagina, tamano=tamano,
                             resultados=[HistorialAccesoResponse.model_validate(f) for f in filas])
```

En `backend/app/api/v1/__init__.py`, incluir `usuarios.router`.

- [ ] **Step 6: Correr y ver que pasa**

Run: `docker compose exec backend pytest tests/test_usuarios_api.py -v` → PASS; luego suite completa.

- [ ] **Step 7: Commit** — `feat(auth): ABM de usuarios, accesos, permisos individuales e historial`.

---

### Task 9: Endpoint de auditoría y README

**Files:**
- Create: `backend/app/api/v1/auditoria.py`
- Modify: `backend/app/api/v1/__init__.py`, `README.md`
- Test: `backend/tests/test_auditoria_api.py`

**Interfaces:**
- Consumes: `listar_auditoria`, `TAMANO_MAXIMO_AUDITORIA`, `AuditoriaResponse`, `RespuestaPaginada`, `requiere_permiso(Modulo.AUDITORIA, "ver")`.
- Produces: `GET /api/v1/auditoria` (filtros `usuario_id, accion, entidad, entidad_id, desde, hasta, pagina, tamano` default 50, máx 200).

- [ ] **Step 1: Test que falla**

`backend/tests/test_auditoria_api.py`:
```python
URL = "/api/v1/auditoria"


def test_admin_consulta_la_auditoria(client, crear_usuario, headers_de):
    h = headers_de(crear_usuario("admin"))
    r = client.get(URL, params={"accion": "sistema.seed"}, headers=h)
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["total"] == 1 and cuerpo["tamano"] == 50
    assert cuerpo["resultados"][0]["accion"] == "sistema.seed"


def test_solo_con_permiso_de_auditoria(client, crear_usuario, headers_de):
    assert client.get(URL, headers=headers_de(crear_usuario("supervisor"))).status_code == 403
    assert client.get(URL, headers=headers_de(crear_usuario("vendedor"))).status_code == 403
    assert client.get(URL).status_code == 401


def test_tamano_maximo(client, crear_usuario, headers_de):
    h = headers_de(crear_usuario("admin"))
    assert client.get(URL, params={"tamano": 201}, headers=h).status_code == 422


def test_login_queda_en_la_auditoria(client, crear_usuario, headers_de):
    h = headers_de(crear_usuario("admin"))
    crear_usuario(username="audit1", password="Clave1234")
    client.post("/api/v1/auth/login", json={"username": "audit1", "password": "Clave1234"})
    r = client.get(URL, params={"accion": "auth.login"}, headers=h).json()
    assert r["total"] >= 1
```

- [ ] **Step 2: Correr y ver que falla** — `docker compose exec backend pytest tests/test_auditoria_api.py -v` → FAIL (404).

- [ ] **Step 3: Implementación**

`backend/app/api/v1/auditoria.py`:
```python
"""Consulta de la auditoría (solo lectura)."""
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.permisos import Modulo
from app.core.seguridad import requiere_permiso
from app.models import Usuario
from app.schemas.auditoria import AuditoriaResponse
from app.schemas.comunes import RespuestaPaginada
from app.services.auditoria import TAMANO_MAXIMO_AUDITORIA, listar_auditoria

router = APIRouter(prefix="/auditoria", tags=["auditoria"])


@router.get("", response_model=RespuestaPaginada[AuditoriaResponse])
def listar(usuario_id: int | None = None, accion: str | None = None, entidad: str | None = None,
           entidad_id: int | None = None, desde: date | None = None, hasta: date | None = None,
           pagina: int = Query(1, ge=1), tamano: int = Query(50, ge=1, le=TAMANO_MAXIMO_AUDITORIA),
           db: Session = Depends(get_db), _: Usuario = Depends(requiere_permiso(Modulo.AUDITORIA, "ver"))):
    registros, total = listar_auditoria(db, usuario_id=usuario_id, accion=accion, entidad=entidad,
                                        entidad_id=entidad_id, desde=desde, hasta=hasta, pagina=pagina, tamano=tamano)
    return RespuestaPaginada(total=total, pagina=pagina, tamano=tamano,
                             resultados=[AuditoriaResponse.model_validate(r) for r in registros])
```

Incluir `auditoria.router` en `backend/app/api/v1/__init__.py`.

En `README.md`, reemplazar la sección "Credenciales iniciales" por:
```markdown
## Credenciales iniciales
Usuario `admin`, contraseña `Admin1234!`. En el primer ingreso el sistema obliga
a cambiarla. Los demás usuarios se crean desde Configuraciones → Usuarios (o por
la API `/api/v1/usuarios`) y también cambian su contraseña al primer ingreso.

## Recuperación de contraseña
Requiere SMTP configurado (`SMTP_*` en `.env`) y que el usuario tenga email.
El enlace del mail vence en 30 minutos y sirve una sola vez. Sin SMTP, el Admin
puede asignar una contraseña nueva editando al usuario (queda obligado a
cambiarla al ingresar).
```

- [ ] **Step 4: Verificación final del plan**

```bash
docker compose exec backend pytest -p no:warnings          # suite completa verde
docker compose restart backend && sleep 5
curl -s -X POST localhost:8000/api/v1/auth/login -H 'Content-Type: application/json' -d '{"username":"admin","password":"Admin1234!"}' | head -c 300
curl -s -o /dev/null -w "%{http_code}\n" localhost:8000/api/v1/auditoria    # 401
```

- [ ] **Step 5: Commit** — `feat(auth): consulta de auditoría y README de acceso`.
