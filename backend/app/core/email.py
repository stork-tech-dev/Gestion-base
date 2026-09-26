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
