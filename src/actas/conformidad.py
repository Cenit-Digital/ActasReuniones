"""Petición de grabar: solo los socios conformes en esta reunión, con la versión del texto informativo (ADR 0015, RGPD 2)."""

import re
from dataclasses import dataclass

TOPE_SOCIOS = 16
# Alfanuméricos en minúscula: VDO.Ninja convierte «-» en «_» y el ID acaba en nombres de fichero (anexo de F0).
STREAM_ID = re.compile(r"[a-z0-9]{1,32}")
_VERSION = re.compile(r"[A-Za-z0-9._-]{1,40}")


class ConformidadNoValida(ValueError):
    """La petición se rechaza y el supervisor no abre ninguna página."""


@dataclass(frozen=True)
class Peticion:
    socios: tuple[str, ...]
    version: str


def validar(socios: list[str], version: str) -> Peticion:
    if not socios:
        raise ConformidadNoValida("ningún socio conforme: no se graba")
    for s in socios:
        if not STREAM_ID.fullmatch(s):
            raise ConformidadNoValida("streamID no válido: alfanumérico en minúscula, como mucho 32 caracteres")
    unicos = tuple(sorted(set(socios)))
    if len(unicos) > TOPE_SOCIOS:
        raise ConformidadNoValida(f"como mucho {TOPE_SOCIOS} socios")
    if not _VERSION.fullmatch(version):
        raise ConformidadNoValida("versión del texto informativo obligatoria (letras, números, «.», «_» o «-»)")
    return Peticion(unicos, version)
