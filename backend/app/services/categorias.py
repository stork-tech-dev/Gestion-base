"""Árbol de categorías (hasta NIVEL_MAXIMO niveles). La tabla es chica: el árbol
se arma en memoria con una sola query."""
from sqlalchemy import func, select, text

from app.core.auditoria import registrar_auditoria, snapshot
from app.core.errores import DatoInvalido, NoEncontrado, ReglaDeNegocio
from app.core.utils import filtro_texto, normalizar_texto, sin_tildes, sin_tildes_sql
from app.models import NIVEL_MAXIMO, Categoria, Producto

MENSAJE_NIVELES = f"Se permiten hasta {NIVEL_MAXIMO} niveles de categorías."
MENSAJE_CICLO = "El árbol de categorías tiene un ciclo; revisá los movimientos recientes."

# Advisory lock de TRANSACCIÓN para serializar mover_categoria. Un lock de fila
# (SELECT ... FOR UPDATE sobre `categoria`) no alcanza: el ciclo se forma entre
# dos filas distintas (mover A bajo B y, a la vez, B bajo A) que read committed
# deja pasar porque cada movimiento solo toca su propia fila y las de su rama,
# nunca la del otro. Un único lock global por clave fija hace que el segundo
# movimiento espere a que el primero termine su transacción (se libera solo).
CLAVE_LOCK_MOVER = 913_204_711


def obtener_categoria(db, categoria_id: int) -> Categoria:
    categoria = db.get(Categoria, categoria_id)
    if categoria is None:
        raise NoEncontrado("Categoría no encontrada")
    return categoria


def _todas(db) -> list[Categoria]:
    return list(db.scalars(select(Categoria).order_by(Categoria.nivel, Categoria.orden, func.lower(Categoria.nombre))).all())


def listar_categorias(db, *, nombre=None, nivel=None, parent_id=None) -> list[Categoria]:
    condiciones = []
    if nombre:
        condiciones.append(filtro_texto(Categoria.nombre, nombre))
    if nivel is not None:
        condiciones.append(Categoria.nivel == nivel)
    if parent_id is not None:
        condiciones.append(Categoria.parent_id == parent_id)
    consulta = select(Categoria).where(*condiciones).order_by(Categoria.nivel, Categoria.orden, func.lower(Categoria.nombre))
    return list(db.scalars(consulta).all())


def arbol(db) -> list[dict]:
    nodos = {c.id: {"id": c.id, "nombre": c.nombre, "nivel": c.nivel, "parent_id": c.parent_id,
                    "orden": c.orden, "hijos": []} for c in _todas(db)}
    raices = []
    for nodo in nodos.values():          # _todas viene ordenada: los hijos quedan en orden
        (nodos[nodo["parent_id"]]["hijos"] if nodo["parent_id"] else raices).append(nodo)
    return raices


def _hijos_por_padre(categorias) -> dict:
    hijos: dict[int | None, list[Categoria]] = {}
    for c in categorias:
        hijos.setdefault(c.parent_id, []).append(c)
    return hijos


def rama_de_ids(db, categoria_id: int) -> list[int]:
    """La categoría y todos sus descendientes (los filtros por categoría son por rama).

    Defensa en profundidad: si el árbol tiene un ciclo (no debería, el lock de
    mover_categoria lo evita) se corta con ReglaDeNegocio en vez de colgarse."""
    hijos = _hijos_por_padre(_todas(db))
    ids, vistos, pendientes = [], set(), [categoria_id]
    while pendientes:
        actual = pendientes.pop()
        if actual in vistos:
            raise ReglaDeNegocio(MENSAJE_CICLO)
        vistos.add(actual)
        ids.append(actual)
        pendientes.extend(h.id for h in hijos.get(actual, []))
    return ids


def caminos(db) -> dict[int, str]:
    """{id: "Ropa > Remeras > Lisas"} de todas las categorías.

    Defensa en profundidad: corta con ReglaDeNegocio si detecta un ciclo al
    subir por los padres, en vez de colgarse (ver rama_de_ids)."""
    por_id = {c.id: c for c in _todas(db)}
    resultado = {}
    for c in por_id.values():
        nombres, vistos, actual = [], set(), c
        while actual is not None:
            if actual.id in vistos:
                raise ReglaDeNegocio(MENSAJE_CICLO)
            vistos.add(actual.id)
            nombres.append(actual.nombre)
            actual = por_id.get(actual.parent_id)
        resultado[c.id] = " > ".join(reversed(nombres))
    return resultado


def es_hoja(db, categoria_id: int) -> bool:
    return db.scalar(select(Categoria.id).where(Categoria.parent_id == categoria_id).limit(1)) is None


def _nombre_libre(db, nombre: str, parent_id: int | None, excepto_id: int | None = None) -> str:
    limpio = normalizar_texto(nombre)
    if not limpio:
        raise DatoInvalido("El nombre es obligatorio")
    condiciones = [
        func.lower(sin_tildes_sql(Categoria.nombre)) == sin_tildes(limpio).lower(),
        Categoria.parent_id.is_(None) if parent_id is None else Categoria.parent_id == parent_id,
    ]
    if excepto_id is not None:
        condiciones.append(Categoria.id != excepto_id)
    existente = db.scalar(select(Categoria).where(*condiciones))
    if existente is not None:
        raise ReglaDeNegocio(f"Ya existe la categoría '{existente.nombre}' en ese nivel.")
    return limpio


def _profundidad_de_rama(db, categoria: Categoria, rama: list[int]) -> int:
    """Niveles que ocupa la rama (ya calculada por el llamador) contando la
    propia categoría (1 si es hoja)."""
    maximo = db.scalar(select(func.max(Categoria.nivel)).where(Categoria.id.in_(rama)))
    return maximo - categoria.nivel + 1


def crear_categoria(db, autor, datos, ip) -> Categoria:
    nivel = 1
    if datos.parent_id is not None:
        padre = obtener_categoria(db, datos.parent_id)
        nivel = padre.nivel + 1
        if nivel > NIVEL_MAXIMO:
            raise ReglaDeNegocio(MENSAJE_NIVELES)
    categoria = Categoria(nombre=_nombre_libre(db, datos.nombre, datos.parent_id), nivel=nivel,
                          parent_id=datos.parent_id, orden=datos.orden)
    db.add(categoria)
    db.flush()
    db.refresh(categoria)
    registrar_auditoria(db, accion="categoria.crear", entidad="categoria", entidad_id=categoria.id,
                        usuario_id=autor.id, estado_nuevo=categoria, ip_origen=ip)
    return categoria


def editar_categoria(db, autor, categoria: Categoria, datos, ip) -> Categoria:
    antes = snapshot(categoria)
    nombre = _nombre_libre(db, datos.nombre, categoria.parent_id, excepto_id=categoria.id)
    categoria.nombre = nombre
    categoria.orden = datos.orden
    db.flush()
    db.refresh(categoria)
    registrar_auditoria(db, accion="categoria.editar", entidad="categoria", entidad_id=categoria.id,
                        usuario_id=autor.id, estado_anterior=antes, estado_nuevo=categoria, ip_origen=ip)
    return categoria


def mover_categoria(db, autor, categoria: Categoria, nuevo_parent_id: int | None, ip) -> Categoria:
    # Serializa los movimientos: mientras dure la transacción, ningún otro
    # mover_categoria puede leer el árbol hasta que esta termine (ver
    # CLAVE_LOCK_MOVER). Releer la categoría después del lock por si quedó
    # bloqueada esperando y otra transacción ya la movió mientras tanto.
    db.execute(text("SELECT pg_advisory_xact_lock(:clave)"), {"clave": CLAVE_LOCK_MOVER})
    db.refresh(categoria)
    rama = rama_de_ids(db, categoria.id)
    nuevo_nivel = 1
    if nuevo_parent_id is not None:
        if nuevo_parent_id in rama:
            raise ReglaDeNegocio("Una categoría no puede moverse dentro de sí misma ni de su rama.")
        nuevo_nivel = obtener_categoria(db, nuevo_parent_id).nivel + 1
    if nuevo_nivel + _profundidad_de_rama(db, categoria, rama) - 1 > NIVEL_MAXIMO:
        raise ReglaDeNegocio(MENSAJE_NIVELES)
    _nombre_libre(db, categoria.nombre, nuevo_parent_id, excepto_id=categoria.id)
    antes = snapshot(categoria)
    delta = nuevo_nivel - categoria.nivel
    categoria.parent_id = nuevo_parent_id
    for descendiente in db.scalars(select(Categoria).where(Categoria.id.in_(rama))).all():
        descendiente.nivel += delta
    db.flush()
    db.refresh(categoria)
    registrar_auditoria(db, accion="categoria.mover", entidad="categoria", entidad_id=categoria.id,
                        usuario_id=autor.id, estado_anterior=antes, estado_nuevo=categoria, ip_origen=ip)
    return categoria


def eliminar_categoria(db, autor, categoria: Categoria, ip) -> None:
    if not es_hoja(db, categoria.id):
        raise ReglaDeNegocio("No se puede eliminar una categoría con subcategorías.")
    if db.scalar(select(Producto.id).where(Producto.categoria_id == categoria.id).limit(1)) is not None:
        raise ReglaDeNegocio("No se puede eliminar una categoría con productos (incluidos los inactivos).")
    antes = snapshot(categoria)
    categoria_id = categoria.id
    db.delete(categoria)
    db.flush()
    registrar_auditoria(db, accion="categoria.eliminar", entidad="categoria", entidad_id=categoria_id,
                        usuario_id=autor.id, estado_anterior=antes, ip_origen=ip)
