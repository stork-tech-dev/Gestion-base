import pytest

from app.core.templates import templates


def render(fuente: str, **contexto) -> str:
    return templates.env.from_string(fuente).render(**contexto)


def test_badge_y_estado_texto():
    html = render('{% from "components/badge.html" import badge, estado_texto %}{{ badge("Activo", "exito") }}{{ estado_texto("Pendiente", "peligro") }}{{ badge("X", "inventada") }}')
    assert "bg-success/15" in html and "Activo" in html
    assert "text-danger" in html and "Pendiente" in html
    assert "bg-surface-alt" in html  # variante desconocida → neutro


def test_botones_accion_volver_y_acciones():
    html = render(
        '{% from "components/botones.html" import accion, acciones, volver %}'
        '{% call acciones() %}{{ accion("ver", atributos=\'@click="ver(fila)"\') }}{{ accion("borrar") }}{% endcall %}'
        '{{ accion("editar", href="/x/1") }}{{ volver("/configuracion", "Configuraciones") }}'
    )
    assert 'aria-label="Ver"' in html and '@click="ver(fila)"' in html
    assert 'aria-label="Borrar"' in html and "hover:text-danger" in html
    assert '<a href="/x/1"' in html and 'aria-label="Editar"' in html
    assert 'href="/configuracion"' in html and "Configuraciones" in html
    assert "justify-end" in html


def test_encabezado_con_y_sin_acciones():
    sin = render('{% from "components/encabezado.html" import encabezado %}{{ encabezado("Usuarios") }}')
    con = render('{% from "components/encabezado.html" import encabezado %}{% call encabezado("Usuarios", "/configuracion", "Configuraciones") %}<button>+ Crear nuevo</button>{% endcall %}')
    assert "<h1" in sin and "Usuarios" in sin and "flex-wrap" not in sin
    assert "+ Crear nuevo" in con and 'href="/configuracion"' in con


def test_form_field_macros():
    html = render(
        '{% from "components/form_field.html" import campo, campo_select, campo_booleano, campo_rango, boton %}'
        '{{ campo("nombre", "Nombre", modelo="form.nombre", requerido=True, error="errores.nombre") }}'
        '{{ campo_select("rol", "Rol", [(1, "Admin"), (2, "Vendedor")], modelo="form.rol_id") }}'
        '{{ campo_booleano("activo", "Activo", "form.activo") }}'
        '{{ campo_rango("precio", "Precio", "filtros.desde", "filtros.hasta") }}'
        '{{ boton("Guardar", tipo="submit") }}'
    )
    assert 'for="nombre"' in html and 'x-model="form.nombre"' in html and "required" in html
    assert 'text-danger">*' in html and 'x-text="errores.nombre"' in html
    assert '<option value="1">Admin</option>' in html and "Elegí una opción" in html
    assert 'type="checkbox"' in html and 'x-model="form.activo"' in html
    assert 'x-model="filtros.desde"' in html and 'x-model="filtros.hasta"' in html
    assert 'type="submit"' in html and "boton-primario" in html


def test_combobox_escapa_la_configuracion():
    html = render('{% from "components/combobox.html" import combobox %}{{ combobox("f-proveedor", "proveedores", "filtros.proveedor_id", texto="nombre", vacio="Proveedor (todos)", etiqueta="Proveedor") }}')
    assert 'x-data="combobox({ fuente: () => (proveedores), texto: &#34;nombre&#34;' in html
    assert 'x-model="filtros.proveedor_id"' in html and 'x-modelable="seleccion"' in html
    assert "Proveedor (todos)" in html and 'for="f-proveedor"' in html


def test_hub_con_y_sin_secciones():
    con = render('{% from "components/hub.html" import hub %}{{ hub(s) }}', s=[{"nombre": "Usuarios", "descripcion": "Altas", "url": "/usuarios", "title": "Ayuda"}])
    sin = render('{% from "components/hub.html" import hub %}{{ hub([]) }}')
    assert 'href="/usuarios"' in con and 'title="Ayuda"' in con and "tarjeta-enlace" in con
    assert "No tenés secciones disponibles." in sin


def test_miniatura_modal_paginacion():
    html = render(
        '{% from "components/miniatura.html" import miniatura %}{% from "components/modal.html" import modal %}'
        '{% from "components/paginacion.html" import paginacion %}'
        '{{ miniatura("fila.foto_url", "sm") }}'
        '{% call modal("Nuevo usuario", "modal-usuario", abierto="formAbierto") %}<p>cuerpo</p>{% endcall %}'
        '{{ paginacion() }}'
    )
    assert ':src="fila.foto_url"' in html and "w-10 h-10" in html
    assert 'x-show="formAbierto"' in html and '@click="formAbierto = false"' in html and "cuerpo" in html
    assert "@keydown.escape" not in html  # el modal NO se cierra con ESC
    assert "Anterior" in html and "Siguiente" in html and "pagina--; cargar()" in html


def test_switches():
    html = render(
        '{% from "components/switch_activos.html" import switch_activos %}{% from "components/switch_estado.html" import switch_estado %}'
        '{{ switch_activos("soloActivos", "cargar()") }}{{ switch_estado("activos", "", "sw-estado") }}'
    )
    assert 'role="switch"' in html and '@click="soloActivos = !soloActivos; cargar()"' in html
    assert "Solo activos" in html
    assert "activos ? " in html and "Inactivos" in html and 'id="sw-estado"' in html


def test_barra_filtros_y_tabla():
    html = render(
        '{% from "components/table.html" import barra_filtros, tabla %}{% from "components/botones.html" import accion %}'
        '{% call barra_filtros(buscar="buscar()", extras="<span>EXTRA</span>"|safe) %}<input id="f">{% endcall %}'
        '{% call tabla(cols, cargando="cargando") %}{{ accion("ver") }}{% endcall %}'
        '{{ tabla(cols) }}',
        cols=[{"titulo": "Nombre", "expr": "fila.nombre"}, {"titulo": "Estado", "expr": "fila.estado_html", "html": True, "clase": "text-right"}],
    )
    assert "registros encontrados" in html and 'x-text="total"' in html
    assert '@click="buscar()"' in html and "Limpiar filtros" in html and "EXTRA" in html
    assert 'x-for="fila in filas"' in html and ':key="fila.id"' in html
    assert 'x-text="fila.nombre"' in html and 'x-html="fila.estado_html"' in html
    assert 'colspan="3"' in html and 'colspan="2"' in html  # con y sin columna de acciones
    assert "Cargando…" in html and "No se encontraron registros." in html


@pytest.mark.parametrize(
    "archivo",
    ["badge", "botones", "combobox", "encabezado", "form_field", "hub", "icons", "marca", "miniatura",
     "modal", "modal_confirmacion", "paginacion", "switch_activos", "switch_estado", "table", "toast", "_sidebar_item"],
)
def test_todos_los_componentes_compilan(archivo):
    templates.env.get_template(f"components/{archivo}.html")
