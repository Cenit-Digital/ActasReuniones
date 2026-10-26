"""Búsqueda del panel (@a22) sobre `segmentos.tsv` con `websearch_to_tsquery('spanish', q)`, que según la documentación de
PostgreSQL 18 (textsearch-controls) «will never raise syntax errors, which makes it possible to use raw user-supplied input».

El resaltado lo calcula `ts_headline` solo para las filas que se muestran (tras el LIMIT: «can be slow»), con dos centinelas
del área de uso privado de Unicode en vez de `<b>`: su salida «is not guaranteed to be safe for direct inclusion in web pages».
La aplicación escapa primero el fragmento entero y solo después cambia los centinelas por `<mark>`. El texto original se pasa
sin centinelas, así que los únicos que llegan son los de `ts_headline`; si aun así no casan, no se marca nada.

Además, `ts_headline` borra lo que su analizador toma por etiquetas (`<script>`, medido en PostgreSQL 18.6): para que un
segmento que las dice se vea tal cual (@a22), `<`, `>` y `&` le llegan cambiados por otros tres caracteres de uso privado
(`translate(texto, QUITAR, PONER)`, que además borra los centinelas y sustitutos que trajera el texto) y vuelven, ya escapados,
al resaltar.
"""

import re

from markupsafe import Markup, escape

LIMITE = 50
TOPE_CONSULTA = 200
INICIO = "\ue000"
FIN = "\ue001"
SUSTITUTOS = {"<": "\ue002", ">": "\ue003", "&": "\ue004"}
PONER = "".join(SUSTITUTOS.values())
QUITAR = "".join(SUSTITUTOS) + PONER + INICIO + FIN
_ESCAPADOS = {v: str(escape(k)) for k, v in SUSTITUTOS.items()}
OPCIONES = f"StartSel={INICIO}, StopSel={FIN}, MaxWords=30, MinWords=10"
_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")


def sin_centinelas(texto: str) -> str:
    return texto.translate(dict.fromkeys(map(ord, PONER + INICIO + FIN)))


def normalizar(q: str | None) -> str | None:
    """La consulta tal cual la escribió la persona, sin caracteres de control y con un tope; None si no queda nada."""
    if q is None:
        return None
    limpia = " ".join(_CONTROL.sub(" ", sin_centinelas(q)).split())[:TOPE_CONSULTA].strip()
    return limpia or None


def _compensados(texto: str) -> bool:
    abierto = False
    for c in texto:
        if c == INICIO:
            if abierto:
                return False
            abierto = True
        elif c == FIN:
            if not abierto:
                return False
            abierto = False
    return not abierto


def resaltar(fragmento: str) -> Markup:
    escapado = str(escape(fragmento))
    if _compensados(escapado):
        escapado = escapado.replace(INICIO, "<mark>").replace(FIN, "</mark>")
    escapado = escapado.replace(INICIO, "").replace(FIN, "")
    for sustituto, entidad in _ESCAPADOS.items():
        escapado = escapado.replace(sustituto, entidad)
    return Markup(escapado)  # noqa: S704 — escapado antes de marcar y de devolver los sustitutos
