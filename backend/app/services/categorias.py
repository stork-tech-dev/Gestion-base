"""Árbol de categorías (hasta NIVEL_MAXIMO niveles). La tabla es chica: el árbol
se arma en memoria con una sola query."""
from sqlalchemy import func, select, text

from app.core.auditoria import registrar_auditoria, snapshot
from app.core.errores import DatoInvalido, NoEncontrado, ReglaDeNegocio
from app.core.utils import buscar_por_nombre, filtro_texto, normalizar_texto
from app.models import NIVEL_MAXIMO, Categoria, Producto

MENSAJE_NIVELES = f"Se permiten hasta {NIVEL_MAXIMO} niveles de categorías."
MENSAJE_CICLO = "El árbol de categorías tiene un ciclo; revisá los movimientos recientes."

MENSAJE_PADRE_CON_PRODUCTOS = ("La categoría tiene productos: movelos a otra categoría antes de "
                               "crearle subcategorías.")
MENSAJE_DESTINO_CON_PRODUCTOS = ("La categoría de destino tiene productos: movelos a otra categoría antes "
                                 "de moverle subcategorías.")

# Advisory lock de TRANSACCIÓN sobre todo el árbol: lo toman (exclusivo) crear,
# editar y mover categorías, y (compartido) el alta/cambio de categoría de un
# producto. Un lock de fila (SELECT ... FOR UPDATE sobre `categoria`) no
# alcanza: el ciclo se forma entre dos filas distintas (mover A bajo B y, a la
# vez, B bajo A) que read committed deja pasar porque cada movimiento solo toca
# su propia fila y las de su rama, nunca la del otro. Con un único lock global
# por clave fija, la segunda escritura espera a que la primera termine su
# transacción (se libera solo): tampoco se calculan niveles con un padre que
# se está moviendo, ni pasan dos nombres iguales (mayúsculas/tildes) a la vez,
# ni se cuela un producto en la categoría que está recibiendo subcategorías.
CLAVE_LOCK_ARBOL = 913_204_711


def bloquear_arbol(db, compartido: bool = False) -> None:
    funcion = "pg_advisory_xact_lock_shared" if compartido else "pg_advisory_xact_lock"
    db.execute(text(f"SELECT {funcion}(:clave)"), {"clave": CLAVE_LOCK_ARBOL})


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


def tiene_productos(db, categoria_id: int) -> bool:
    """¿Hay productos (incluidos los inactivos) directamente en la categoría?"""
    return db.scalar(select(Producto.id).where(Producto.categoria_id == categoria_id).limit(1)) is not None


def _condicion_padre(parent_id: int | None):
    """Condición "hija de `parent_id`" (None = primer nivel)."""
    return Categoria.parent_id.is_(None) if parent_id is None else Categoria.parent_id == parent_id


def buscar_hija(db, nombre: str | None, parent_id: int | None) -> Categoria | None:
    """Categoría con ese nombre (sin mayúsculas ni tildes) entre las hijas de
    `parent_id` (None = primer nivel)."""
    return buscar_por_nombre(db, Categoria, nombre, _condicion_padre(parent_id))


def _nombre_libre(db, nombre: str, parent_id: int | None, excepto_id: int | None = None) -> str:
    limpio = normalizar_texto(nombre)
    if not limpio:
        raise DatoInvalido("El nombre es obligatorio")
    condiciones = [_condicion_padre(parent_id)] + ([Categoria.id != excepto_id] if excepto_id is not None else [])
    existente = buscar_por_nombre(db, Categoria, limpio, *condiciones)
    if existente is not None:
        raise ReglaDeNegocio(f"Ya existe la categoría '{existente.nombre}' en ese nivel.")
    return limpio


def _profundidad_de_rama(db, categoria: Categoria, rama: list[int]) -> int:
    """Niveles que ocupa la rama (ya calculada por el llamador) contando la
    propia categoría (1 si es hoja)."""
    maximo = db.scalar(select(func.max(Categoria.nivel)).where(Categoria.id.in_(rama)))
    return maximo - categoria.nivel + 1


def crear_categoria(db, autor, datos, ip) -> Categoria:
    bloquear_arbol(db)
    nivel = 1
    if datos.parent_id is not None:
        padre = obtener_categoria(db, datos.parent_id)
        db.refresh(padre)                     # su nivel pudo cambiar mientras se esperaba el lock
        nivel = padre.nivel + 1
        if nivel > NIVEL_MAXIMO:
            raise ReglaDeNegocio(MENSAJE_NIVELES)
        # Los productos van solo en hojas: el padre dejaría de serlo.
        if tiene_productos(db, padre.id):
            raise ReglaDeNegocio(MENSAJE_PADRE_CON_PRODUCTOS)
    categoria = Categoria(nombre=_nombre_libre(db, datos.nombre, datos.parent_id), nivel=nivel,
                          parent_id=datos.parent_id, orden=datos.orden)
    db.add(categoria)
    db.flush()
    db.refresh(categoria)
    registrar_auditoria(db, accion="categoria.crear", entidad="categoria", entidad_id=categoria.id,
                        usuario_id=autor.id, estado_nuevo=categoria, ip_origen=ip)
    return categoria


def editar_categoria(db, autor, categoria: Categoria, datos, ip) -> Categoria:
    bloquear_arbol(db)
    db.refresh(categoria)                     # su padre pudo cambiar mientras se esperaba el lock
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
    # Serializa las escrituras del árbol: mientras dure la transacción, ninguna
    # otra puede leerlo hasta que esta termine (ver CLAVE_LOCK_ARBOL). Releer la
    # categoría después del lock por si quedó bloqueada esperando y otra
    # transacción ya la movió mientras tanto.
    bloquear_arbol(db)
    db.refresh(categoria)
    rama = rama_de_ids(db, categoria.id)
    nuevo_nivel = 1
    if nuevo_parent_id is not None:
        if nuevo_parent_id in rama:
            raise ReglaDeNegocio("Una categoría no puede moverse dentro de sí misma ni de su rama.")
        destino = obtener_categoria(db, nuevo_parent_id)
        db.refresh(destino)
        nuevo_nivel = destino.nivel + 1
        if tiene_productos(db, destino.id):
            raise ReglaDeNegocio(MENSAJE_DESTINO_CON_PRODUCTOS)
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
    if tiene_productos(db, categoria.id):
        raise ReglaDeNegocio("No se puede eliminar una categoría con productos (incluidos los inactivos).")
    antes = snapshot(categoria)
    categoria_id = categoria.id
    db.delete(categoria)
    db.flush()
    registrar_auditoria(db, accion="categoria.eliminar", entidad="categoria", entidad_id=categoria_id,
                        usuario_id=autor.id, estado_anterior=antes, ip_origen=ip)
