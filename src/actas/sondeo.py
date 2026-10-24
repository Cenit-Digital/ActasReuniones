"""Respuestas de la API interna de la plataforma de transcripción (ADR 0017, D8): `POST /api/interno/actas/trabajos` y
`GET /api/interno/actas/trabajos/{id}`. Código 0: no hubo respuesta (conexión rechazada, tiempo agotado)."""

import re
from dataclasses import dataclass
from typing import Any, Literal

ESPERA_MAX_S = 60
PLAZO_S = 12 * 3600

_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_EN_CURSO = {"recibido", "ingestando", "preparado", "en_cola", "transcribiendo", "alineando", "diarizando"}


@dataclass(frozen=True)
class Decision:
    accion: Literal["seguir", "listo", "error", "reintentar"]
    motivo: str | None = None
    trabajo_id: str | None = None


def _rechazo(codigo: int) -> str:
    return "token" if codigo == 401 else f"rechazada_{codigo}"


def interpretar_creacion(codigo: int, cuerpo: Any) -> Decision:
    if codigo == 201:
        tid = cuerpo.get("id") if isinstance(cuerpo, dict) else None
        if isinstance(tid, str) and _UUID.fullmatch(tid):
            return Decision("seguir", trabajo_id=tid)
        return Decision("error", motivo="respuesta_sin_id")
    if 400 <= codigo < 500:
        return Decision("error", motivo=_rechazo(codigo))
    return Decision("reintentar", motivo=f"http_{codigo}")


def interpretar_estado(codigo: int, cuerpo: Any) -> Decision:
    if codigo == 401:
        return Decision("error", motivo="token")
    if codigo == 404:
        return Decision("error", motivo="trabajo_no_encontrado")
    if codigo != 200:
        return Decision("seguir", motivo=f"http_{codigo}")
    estado = (cuerpo.get("trabajo") or {}).get("estado")
    if estado == "listo":
        return Decision("listo") if isinstance(cuerpo.get("transcripcion"), dict) else Decision("error", motivo="listo_sin_texto")
    if estado in ("error", "cancelado"):
        return Decision("error", motivo=f"plataforma_{estado}")
    if estado in _EN_CURSO:
        return Decision("seguir")
    return Decision("error", motivo="estado_desconocido")


def espera(intento: int) -> int:
    """Segundos hasta la siguiente consulta: 5, 10, 20, 40 y luego 60."""
    return int(min(5 * 2**intento, ESPERA_MAX_S))
