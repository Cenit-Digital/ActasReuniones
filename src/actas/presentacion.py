"""Formato de lo que muestra el panel: tiempos de la transcripción en `hh:mm:ss`, duración de la grabación, los socios por su
nombre visible (el streamID si no es un socio conocido) y cada estado con su texto y su glifo (@a42: no solo el color)."""

from collections.abc import Iterable, Mapping
from datetime import datetime, timedelta
from typing import NamedTuple

SIN_DATO = "—"
_MS = timedelta(milliseconds=1)


class Estado(NamedTuple):
    texto: str
    glifo: str


# Los seis de F1 (`estados.Estado`) y los dos que trae la programación (V3 de KubernetesInfrastructure#298). Los glifos los
# dibuja `plantillas/_glifos.html`.
ESTADOS = {
    "pedida": Estado("Pedida", "espera"),
    "grabando": Estado("Grabando", "punto"),
    "grabada": Estado("Grabada", "cuadrado"),
    "transcribiendo": Estado("Transcribiendo", "medio"),
    "transcrita": Estado("Transcrita", "visto"),
    "error": Estado("Error", "cruz"),
    "programada": Estado("Programada", "reloj"),
    "cancelada": Estado("Cancelada", "prohibido"),
}


def estado(valor: str) -> Estado:
    return ESTADOS.get(valor) or Estado(valor, "desconocido")


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


def bloques(texto: str) -> list[tuple[str, list[str]]]:
    """El texto informativo (`textos/*.md`, un subconjunto mínimo de Markdown) en bloques que la plantilla escapa: `# ` y `## `
    son títulos, un bloque con todas sus líneas en `- ` es una lista y lo demás, un párrafo. Sin HTML ni enlaces."""
    salida: list[tuple[str, list[str]]] = []
    for crudo in texto.split("\n\n"):
        lineas = [linea.strip() for linea in crudo.splitlines() if linea.strip()]
        if not lineas:
            continue
        if len(lineas) == 1 and lineas[0].startswith("## "):
            salida.append(("h3", [lineas[0][3:].strip()]))
        elif len(lineas) == 1 and lineas[0].startswith("# "):
            salida.append(("h2", [lineas[0][2:].strip()]))
        elif all(linea.startswith("- ") for linea in lineas):
            salida.append(("ul", [linea[2:].strip() for linea in lineas]))
        else:
            salida.append(("p", [" ".join(lineas)]))
    return salida
