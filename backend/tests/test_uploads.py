from pathlib import Path

from config import settings


def test_archivos_de_uploads_se_sirven(client):
    carpeta = Path(settings.UPLOADS_DIR) / "productos"
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / "prueba.txt").write_text("hola", encoding="utf-8")

    r = client.get("/uploads/productos/prueba.txt")
    assert r.status_code == 200
    assert r.text == "hola"


def test_uploads_inexistente_da_404(client):
    assert client.get("/uploads/no-existe.jpg").status_code == 404
