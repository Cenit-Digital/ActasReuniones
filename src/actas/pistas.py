"""De los ficheros que deja VDO.Ninja v30.2 a las pistas de la petición a la plataforma de transcripción.

El grabador abre una página por socio con `&label=<id>`, así que cada grabación se llama `<id>_<ms>.webm`
(buildRecordingFilenameBase + Date.now() al empezar; anexo de F0 del ADR 0015). Un socio que se reconecta deja otro fichero.
La plataforma solo suma un desfase constante a cada pista: `desfase_ms` es la marca de cada fichero menos la menor.
"""

import re
from dataclasses import dataclass

TOPE_PISTAS = 16  # MAX_PISTAS de la API interna de la plataforma (transcribir.entradas.api.app)

# fullmatch y ASCII: «$» aceptaría un salto de línea final y «\d», dígitos de otras escrituras (el nombre lo elige Chromium).
_GRABACION = re.compile(r"(?P<socio>[a-z0-9]+)_(?P<ms>[0-9]+)\.webm", re.ASCII)
_PARTIDA = re.compile(r"[a-z0-9]+_[0-9]+\.webm_[0-9]+", re.ASCII)
_TEMPORAL = (".crdownload",)


class PistasNoValidas(ValueError):
    """Los ficheros de la reunión no se pueden enviar tal cual: la reunión pasa a `error` y el audio se conserva. `causa`: el
    código que va al historial (eventos.py), para explicar el error en el panel sin el nombre de ningún fichero."""

    def __init__(self, mensaje: str, causa: str) -> None:
        super().__init__(mensaje)
        self.causa = causa


@dataclass(frozen=True)
class Pista:
    fichero: str
    socio: str
    marca_ms: int
    desfase_ms: int


def pistas_de(ficheros: list[str], conformes: list[str]) -> list[Pista]:
    """Las pistas ordenadas por marca, con su desfase. Ignora descargas a medias y ficheros que no son grabaciones."""
    encontradas: list[tuple[int, str, str]] = []
    for nombre in ficheros:
        if nombre.endswith(_TEMPORAL) or nombre.startswith(".") or nombre.endswith((".json", ".jsonl")):
            continue
        if _PARTIDA.fullmatch(nombre):
            raise PistasNoValidas("grabación partida por VDO.Ninja: su marca no es la del trozo", "partida")
        m = _GRABACION.fullmatch(nombre)
        if m is None:
            raise PistasNoValidas("fichero que no es una grabación", "no_grabacion")
        if m["socio"] not in conformes:
            raise PistasNoValidas("pista de un socio no conforme", "no_conforme")
        encontradas.append((int(m["ms"]), m["socio"], nombre))
    if not encontradas:
        raise PistasNoValidas("ninguna pista", "ninguna_pista")
    if len(encontradas) > TOPE_PISTAS:
        raise PistasNoValidas(f"{len(encontradas)} pistas, más que las {TOPE_PISTAS} que admite la plataforma", "demasiadas")
    encontradas.sort()
    origen = encontradas[0][0]
    return [Pista(nombre, socio, ms, ms - origen) for ms, socio, nombre in encontradas]
