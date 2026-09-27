from decimal import Decimal

import pytest
from sqlalchemy import select, text

from app.core.errores import DatoInvalido, NoEncontrado, ReglaDeNegocio
from app.models import Auditoria, Categoria, Moneda, Producto, Proveedor
from app.schemas.categorias import CategoriaCrear, CategoriaEditar
from app.services import categorias as servicio


@pytest.fixture
def admin(crear_usuario):
    return crear_usuario("admin")


def _crear(db, autor, nombre, parent=None, orden=0):
    return servicio.crear_categoria(
        db, autor, CategoriaCrear(nombre=nombre, parent_id=parent.id if parent else None, orden=orden), None
    )


def _cadena(db, autor, niveles):
    actual = None
    creadas = []
    for i in range(niveles):
        actual = _crear(db, autor, f"Nivel {i + 1}", actual)
        creadas.append(actual)
    return creadas


def test_niveles_y_auditoria(db, admin):
    ropa = _crear(db, admin, "  Ropa  ")
    remeras = _crear(db, admin, "Remeras", ropa)
    assert (ropa.nombre, ropa.nivel, ropa.parent_id) == ("Ropa", 1, None)
    assert (remeras.nivel, remeras.parent_id) == (2, ropa.id)
    assert db.scalar(select(Auditoria).where(Auditoria.accion == "categoria.crear", Auditoria.entidad_id == remeras.id))


def test_maximo_cinco_niveles(db, admin):
    cadena = _cadena(db, admin, 5)
    with pytest.raises(ReglaDeNegocio) as error:
        _crear(db, admin, "Sexto", cadena[-1])
    assert "5 niveles" in error.value.mensaje


def test_padre_inexistente(db, admin):
    with pytest.raises(NoEncontrado):
        servicio.crear_categoria(db, admin, CategoriaCrear(nombre="X", parent_id=999999), None)


def test_nombre_unico_entre_hermanas(db, admin):
    ropa = _crear(db, admin, "Ropa")
    _crear(db, admin, "Remeras", ropa)
    with pytest.raises(ReglaDeNegocio):
        _crear(db, admin, "remeras", ropa)
    otra = _crear(db, admin, "Calzado")
    _crear(db, admin, "Remeras", otra)          # otro padre: se puede
    with pytest.raises(ReglaDeNegocio):
        _crear(db, admin, "ROPA")               # raíces también son hermanas


def test_editar(db, admin):
    ropa = _crear(db, admin, "Ropa")
    _crear(db, admin, "Calzado")
    servicio.editar_categoria(db, admin, ropa, CategoriaEditar(nombre="Indumentaria", orden=3), None)
    assert (ropa.nombre, ropa.orden) == ("Indumentaria", 3)
    with pytest.raises(ReglaDeNegocio):
        servicio.editar_categoria(db, admin, ropa, CategoriaEditar(nombre="calzado", orden=0), None)
    assert ropa.nombre == "Indumentaria"        # validar antes de modificar


def test_mover_actualiza_niveles_de_la_rama(db, admin):
    a = _crear(db, admin, "A")
    b = _crear(db, admin, "B")
    b1 = _crear(db, admin, "B1", b)
    b2 = _crear(db, admin, "B2", b1)
    servicio.mover_categoria(db, admin, b, a.id, None)
    assert (b.nivel, b1.nivel, b2.nivel) == (2, 3, 4)
    servicio.mover_categoria(db, admin, b, None, None)
    assert (b.nivel, b1.nivel, b2.nivel, b.parent_id) == (1, 2, 3, None)
    assert db.scalar(select(Auditoria).where(Auditoria.accion == "categoria.mover", Auditoria.entidad_id == b.id))


def test_mover_prohibido(db, admin):
    cadena = _cadena(db, admin, 4)       # niveles 1..4
    otra = _crear(db, admin, "Otra")
    otra_hija = _crear(db, admin, "Hija", otra)
    with pytest.raises(ReglaDeNegocio):
        servicio.mover_categoria(db, admin, cadena[0], cadena[0].id, None)      # a sí misma
    with pytest.raises(ReglaDeNegocio):
        servicio.mover_categoria(db, admin, cadena[0], cadena[2].id, None)      # dentro de su rama
    with pytest.raises(ReglaDeNegocio) as error:
        servicio.mover_categoria(db, admin, cadena[0], otra_hija.id, None)      # rama de 4 bajo nivel 2 → 6
    assert "5 niveles" in error.value.mensaje
    assert cadena[0].parent_id is None and cadena[0].nivel == 1


def test_eliminar(db, admin):
    ropa = _crear(db, admin, "Ropa")
    remeras = _crear(db, admin, "Remeras", ropa)
    with pytest.raises(ReglaDeNegocio):
        servicio.eliminar_categoria(db, admin, ropa, None)          # tiene subcategorías
    proveedor = Proveedor(nombre="Prov cat", moneda=Moneda.ARS)
    db.add(proveedor)
    db.flush()
    db.add(Producto(sku="ZZ001", verificador="0", descripcion="Remera", categoria_id=remeras.id,
                    proveedor_id=proveedor.id, costo=Decimal("1"), margen=Decimal("0"), precio_venta=Decimal("1")))
    db.flush()
    with pytest.raises(ReglaDeNegocio):
        servicio.eliminar_categoria(db, admin, remeras, None)       # tiene productos
    calzado = _crear(db, admin, "Calzado")
    servicio.eliminar_categoria(db, admin, calzado, None)
    assert db.get(Categoria, calzado.id) is None
    assert db.scalar(select(Auditoria).where(Auditoria.accion == "categoria.eliminar", Auditoria.entidad_id == calzado.id))


def test_arbol_rama_caminos_y_hoja(db, admin):
    ropa = _crear(db, admin, "Ropa", orden=2)
    calzado = _crear(db, admin, "Calzado", orden=1)
    remeras = _crear(db, admin, "Remeras", ropa)
    lisas = _crear(db, admin, "Lisas", remeras)
    arbol = servicio.arbol(db)
    nombres = [n["nombre"] for n in arbol]
    assert nombres.index("Calzado") < nombres.index("Ropa")          # por orden
    nodo_ropa = next(n for n in arbol if n["id"] == ropa.id)
    assert nodo_ropa["hijos"][0]["hijos"][0]["nombre"] == "Lisas"
    assert set(servicio.rama_de_ids(db, ropa.id)) == {ropa.id, remeras.id, lisas.id}
    assert servicio.rama_de_ids(db, calzado.id) == [calzado.id]
    assert servicio.caminos(db)[lisas.id] == "Ropa > Remeras > Lisas"
    assert servicio.es_hoja(db, lisas.id) and not servicio.es_hoja(db, ropa.id)


def test_listar_con_filtros(db, admin):
    ropa = _crear(db, admin, "Ropa")
    _crear(db, admin, "Remeras estampadas", ropa)
    _crear(db, admin, "Calzado")
    assert [c.nombre for c in servicio.listar_categorias(db, nombre="ESTAMPADAS")] == ["Remeras estampadas"]
    assert {c.nombre for c in servicio.listar_categorias(db, nivel=1)} >= {"Ropa", "Calzado"}
    assert [c.nombre for c in servicio.listar_categorias(db, parent_id=ropa.id)] == ["Remeras estampadas"]


def test_nombre_vacio(db, admin):
    with pytest.raises(DatoInvalido):
        _crear(db, admin, "   ")


def test_ciclo_no_cuelga(db, admin):
    """rama_de_ids y caminos no deben colgarse si el árbol tiene un ciclo
    (defensa en profundidad; en circunstancias normales el lock de
    mover_categoria lo evita). El ciclo se arma a mano por SQL: A bajo B y B
    bajo A, ambos en nivel 2 para no violar el CHECK nivel>1 <-> parent_id
    NOT NULL."""
    raiz = _crear(db, admin, "Raiz")
    a = _crear(db, admin, "A", raiz)
    b = _crear(db, admin, "B", raiz)
    db.execute(text("UPDATE categorias SET parent_id = :padre WHERE id = :hijo"), {"padre": b.id, "hijo": a.id})
    db.execute(text("UPDATE categorias SET parent_id = :padre WHERE id = :hijo"), {"padre": a.id, "hijo": b.id})
    db.expire_all()  # los objetos a/b quedan en la identity map con el parent_id viejo
    with pytest.raises(ReglaDeNegocio) as error:
        servicio.rama_de_ids(db, a.id)
    assert "ciclo" in error.value.mensaje
    with pytest.raises(ReglaDeNegocio) as error:
        servicio.caminos(db)
    assert "ciclo" in error.value.mensaje


def test_mover_sigue_funcionando_con_el_lock(db, admin):
    """mover_categoria toma un advisory lock de transacción antes de leer el
    árbol; esto no debe romper el uso normal (mismo lock, misma transacción,
    dos movimientos seguidos)."""
    ropa = _crear(db, admin, "Ropa")
    calzado = _crear(db, admin, "Calzado")
    remeras = _crear(db, admin, "Remeras", ropa)
    servicio.mover_categoria(db, admin, remeras, calzado.id, None)
    assert (remeras.parent_id, remeras.nivel) == (calzado.id, 2)
    servicio.mover_categoria(db, admin, remeras, None, None)
    assert (remeras.parent_id, remeras.nivel) == (None, 1)
