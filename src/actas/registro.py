"""Registro del supervisor sin secretos (@a11): la contraseña de la sala va en la URL de cada página y el token en cada
petición a la plataforma. Desde V2 cada reunión tiene su sala: su contraseña se añade al descifrarla (`ocultar`)."""

import re
import sys
import time
import urllib.parse
from collections.abc import Iterable


def redactar(texto: str, secretos: Iterable[str]) -> str:
    formas = set()
    for s in secretos:
        if s.strip():
            formas |= {s, urllib.parse.quote(s, safe=""), urllib.parse.quote_plus(s, safe="")}
    for f in sorted(formas, key=len, reverse=True):
        texto = texto.replace(f, "***")
    return texto


_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")


class Registro:
    def __init__(self, secretos: Iterable[str] = ()) -> None:
        self.secretos = list(secretos)

    def ocultar(self, secreto: str) -> None:
        """Un secreto que se conoce después de arrancar (la contraseña de cada sala, V2)."""
        if secreto not in self.secretos:
            self.secretos.append(secreto)

    def __call__(self, *partes: object) -> None:
        # Sin caracteres de control: parte del texto llega de Chromium y no debe poder falsificar líneas del registro.
        linea = _CONTROL.sub(" ", " ".join(str(p) for p in partes))
        print(
            time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            redactar(linea, self.secretos),
            file=sys.stderr,
            flush=True,
        )
