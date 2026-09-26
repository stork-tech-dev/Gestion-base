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
