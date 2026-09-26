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
