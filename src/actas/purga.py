"""Qué audio se borra del tmpfs (@a10; plazos del ADR 0015, decisión 5): el de una reunión ya transcrita, cualquiera de más
de 7 días, el que no es de ninguna reunión conocida y, desde V3, el de una reunión cancelada porque no entró nadie."""

from dataclasses import dataclass

PLAZO_AUDIO_S = 7 * 24 * 3600


@dataclass(frozen=True)
class Audio:
    reunion: str
    estado: str | None  # None: el directorio no es de ninguna reunión de la base
    mtime_s: float


def a_borrar(audios: list[Audio], ahora_s: float) -> list[tuple[str, str]]:
    """(reunión, motivo) de lo que hay que borrar."""
    borrar = []
    for a in audios:
        if a.estado is None:
            borrar.append((a.reunion, "huerfano"))
        elif a.estado == "transcrita":
            borrar.append((a.reunion, "transcrita"))
        elif a.estado == "cancelada":
            borrar.append((a.reunion, "nadie_entro"))
        elif ahora_s - a.mtime_s >= PLAZO_AUDIO_S:
            borrar.append((a.reunion, "plazo_7d"))
    return borrar
