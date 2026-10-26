"""Formato de lo que muestra el panel: tiempos de la transcripción en `hh:mm:ss`, duración de la grabación y los socios por su
nombre visible (el streamID si no es un socio conocido)."""

from collections.abc import Iterable, Mapping
from datetime import datetime, timedelta

SIN_DATO = "—"
_MS = timedelta(milliseconds=1)


def hhmmss(ms: int) -> str:
    if ms < 0:
        raise ValueError("un tiempo no es negativo")
    s = ms // 1000
    return f"{s // 3600:02d}:{s // 60 % 60:02d}:{s % 60:02d}"


def duracion(inicio: datetime | None, fin: datetime | None) -> str:
    if inicio is None or fin is None or fin < inicio:
        return SIN_DATO
    return hhmmss((fin - inicio) // _MS)


def nombres(socios: Iterable[str], conocidos: Mapping[str, str]) -> str:
    return ", ".join(conocidos.get(s, s) for s in socios)

