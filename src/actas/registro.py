"""Registro del supervisor sin secretos (@a11): la contraseña de la sala va en la URL de cada página y el token en cada
petición a la plataforma."""

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


class Registro:
    def __init__(self, secretos: Iterable[str] = ()) -> None:
        self.secretos = list(secretos)

    def __call__(self, *partes: object) -> None:
        linea = " ".join(str(p) for p in partes)
        print(
            time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            redactar(linea, self.secretos),
            file=sys.stderr,
            flush=True,
        )
