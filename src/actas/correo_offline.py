"""Construcción local de un correo de acta; no realiza envíos ni registra contenido.

No aporta persistencia ni garantiza idempotencia: la integración de F4 debe resolver por separado los resultados SMTP inciertos.
"""

from email.message import EmailMessage
from email.policy import SMTP
from uuid import UUID


class ErrorCorreo(ValueError):
    """Entrada inválida; el error no incluye el contenido privado del acta."""


_DIRECCION = "info@cenitdigital.es"
_ORIGEN_PANEL = "https://actas.cenitdigital.es"
_MAX_ACTA_BYTES = 1_000_000


def preparar_correo(reunion_id: str, acta: str) -> bytes:
    """Devuelve un mensaje de texto sin adjuntos, con enlace al panel para la reunión indicada."""
    try:
        if not isinstance(reunion_id, str) or str(UUID(reunion_id)) != reunion_id:
            raise ValueError
    except (ValueError, AttributeError):
        raise ErrorCorreo("identificador de reunión inválido") from None

    if not isinstance(acta, str) or len(acta) > _MAX_ACTA_BYTES or not acta.strip() or "\x00" in acta:
        raise ErrorCorreo("acta inválida")
    try:
        if len(acta.encode("utf-8")) > _MAX_ACTA_BYTES:
            raise ErrorCorreo("acta demasiado grande")
    except UnicodeEncodeError:
        raise ErrorCorreo("acta inválida") from None

    mensaje = EmailMessage(policy=SMTP)
    mensaje["From"] = _DIRECCION
    mensaje["To"] = _DIRECCION
    mensaje["Subject"] = "Acta de la reunión"
    mensaje.set_content(f"{acta}\n\nTranscripción: {_ORIGEN_PANEL}/reuniones/{reunion_id}\n")
    return mensaje.as_bytes()
