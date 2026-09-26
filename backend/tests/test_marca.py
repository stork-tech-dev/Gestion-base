from app.core import templates as modulo_templates


def _render_marca():
    plantilla = modulo_templates.templates.env.from_string(
        '{% from "components/marca.html" import marca %}{{ marca("w-full") }}'
    )
    return plantilla.render()


def test_marca_sin_logo_muestra_el_nombre(monkeypatch, tmp_path):
    monkeypatch.setattr(modulo_templates, "STATIC_DIR", tmp_path)
    html = _render_marca()
    assert modulo_templates.templates.env.globals["APP_NAME"] in html
    assert "<img" not in html


def test_marca_con_logo_muestra_la_imagen_versionada(monkeypatch, tmp_path):
    (tmp_path / "img").mkdir()
    (tmp_path / "img" / "logo.svg").write_text("<svg/>", encoding="utf-8")
    monkeypatch.setattr(modulo_templates, "STATIC_DIR", tmp_path)
    html = _render_marca()
    assert '<img src="/static/img/logo.svg?v=' in html
    assert 'class="w-full"' in html


def test_estatico_versiona_y_tolera_inexistentes():
    assert modulo_templates.estatico("/js/app.js").startswith("/static/js/app.js?v=")
    assert modulo_templates.estatico("no/existe.css") == "/static/no/existe.css"


def test_filtro_js_escapa_para_atributos():
    salida = modulo_templates.templates.env.from_string("{{ valor|js }}").render(valor='Dijo "hola" & <chau>')
    assert '"' not in salida and "<" not in salida
    assert "&#34;" in salida
