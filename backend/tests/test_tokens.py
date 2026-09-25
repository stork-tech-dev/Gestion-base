import re
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1] / "app"
CSS = (APP_DIR / "static" / "css" / "custom.css").read_text(encoding="utf-8")
TAILWIND = (APP_DIR / "templates" / "components" / "_tailwind_config.html").read_text(encoding="utf-8")

COLORES = [
    "--color-primary", "--color-primary-hover", "--color-accent", "--color-welcome",
    "--color-bg", "--color-surface", "--color-surface-alt", "--color-border",
    "--color-text", "--color-text-muted", "--color-text-disabled", "--color-text-header",
    "--color-text-invert", "--color-input-border", "--color-danger", "--color-success",
    "--color-sidebar-bg", "--color-sidebar-text", "--color-sidebar-active", "--color-check-borde",
]
GEOMETRIA = [
    "--font-sans", "--radius-input", "--radius-pill", "--radius-search", "--sidebar-width",
    "--header-height", "--layout-max", "--alto-control", "--alto-boton", "--toque-min",
]


def _bloque(patron: str) -> str:
    """Contenido del primer bloque de nivel superior que empieza con `patron`."""
    m = re.search(rf"^{patron}\s*\{{(.*?)^\}}", CSS, re.S | re.M)
    assert m, f"no se encontró el bloque {patron}"
    return m.group(1)


def _define(bloque: str, variable: str) -> bool:
    return re.search(rf"{re.escape(variable)}\s*:", bloque) is not None


def test_root_define_todas_las_variables():
    root = _bloque(r":root")
    faltan = [v for v in COLORES + GEOMETRIA if not _define(root, v)]
    assert not faltan, f"faltan en :root: {faltan}"


def test_modo_oscuro_redefine_todos_los_colores():
    oscuro = _bloque(r"\.dark")
    faltan = [v for v in COLORES if not _define(oscuro, v)]
    assert not faltan, f"faltan en .dark: {faltan}"


def test_puntero_tactil_sube_los_controles_a_44px():
    m = re.search(r"@media\s*\(pointer:\s*coarse\)\s*\{\s*:root\s*\{([^}]*)\}", CSS)
    assert m, "falta el bloque @media (pointer: coarse) { :root { ... } }"
    for variable in ("--alto-control", "--alto-boton", "--toque-min"):
        assert re.search(rf"{variable}\s*:\s*2\.75rem", m.group(1)), variable


def test_tailwind_solo_usa_variables_existentes():
    root = _bloque(r":root")
    usadas = set(re.findall(r"var\(--([\w-]+)\)", TAILWIND)) | {
        f"color-{c}" for c in re.findall(r"c\('([\w-]+)'\)", TAILWIND)
    }
    faltan = [v for v in usadas if v.startswith(("color-", "font-", "radius-", "sidebar-", "header-", "alto-", "toque-", "layout-")) and not _define(root, f"--{v}")]
    assert not faltan, f"el config de Tailwind usa variables inexistentes: {faltan}"


def test_tailwind_reemplaza_breakpoints():
    assert "screens:" in TAILWIND
    assert "'640px'" in TAILWIND and "'1024px'" in TAILWIND and "'1280px'" in TAILWIND
    assert "md:" not in TAILWIND and "2xl:" not in TAILWIND


def test_sin_scroll_horizontal_global():
    # clip (no hidden): hidden crea un contenedor de scroll en html/body y
    # rompe `position: sticky` (ver custom.css).
    assert re.search(r"html,\s*body\s*\{[^}]*overflow-x:\s*clip", CSS)
    assert not re.search(r"html,\s*body\s*\{[^}]*overflow-x:\s*hidden", CSS)
