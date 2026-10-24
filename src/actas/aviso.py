"""Aviso del grabador (lección de F0, 2026-10-24): la página de un socio conforme está en la sala, pero ningún stream casa con
su `&view`, porque el socio entró sin su enlace con `&push`. Pasado el margen, el supervisor lo publica en `/metricas` y
vmalert lo lleva a Telegram."""

import re
from collections.abc import Iterable, Mapping

MARGEN_S = 60
_STREAM_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")


def streams_validos(ids: Iterable[object], tope: int = 50) -> list[str]:
    """Los streamIDs que la página dice ver: solo cadenas con forma de streamID, sin repetir, ordenadas y como mucho `tope`
    (el ID lo elige cada cliente)."""
    return sorted({x for x in ids if isinstance(x, str) and _STREAM_ID.fullmatch(x)})[:tope]


def sin_coincidencia(vistos: Mapping[str, list[str]], segundos: float) -> list[str]:
    """Los socios conformes que, pasado el margen, no publican en la sala."""
    if segundos < MARGEN_S:
        return []
    return sorted(s for s, ids in vistos.items() if s not in ids)
