"""Registro del supervisor sin secretos (@a11): la contraseña de la sala va en la URL de cada página y el token en cada
petición a la plataforma."""

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

    def __call__(self, *partes: object) -> None:
        # Sin caracteres de control: parte del texto llega de Chromium y no debe poder falsificar líneas del registro.
        linea = _CONTROL.sub(" ", " ".join(str(p) for p in partes))
        print(
            time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            redactar(linea, self.secretos),
            file=sys.stderr,
            flush=True,
        )
