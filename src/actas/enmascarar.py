"""Enmascarado de datos personales del texto que sale por el MCP (lista blanca de salida, ADR 0004).

Las transcripciones nombran a terceros. Los nombres se dejan (son de los socios y de las personas de la
reunión); los correos no salen y de un teléfono solo salen los 3 últimos dígitos. Límite conocido: un
correo o un teléfono dictados en palabras («seis uno dos…») no se pueden reconocer de forma fiable y salen
tal cual.

Las expresiones son de coste lineal con textos largos: cada una empieza tras un límite (`(?<!…)`), así que
no se reintenta desde cada posición de una racha de letras o de dígitos, y todo cuantificador tiene tope.
"""

from __future__ import annotations

import re

MARCA_CORREO = "[correo]"
PREFIJO_TELEFONO = "···"
MIN_DIGITOS_TELEFONO = 9  # un teléfono español; una fecha (8 dígitos) o un año no llegan

_LOCAL = r"[\w.+\-%'!#&]"
_ARROBA = (
    r"(?:\s{0,3}[@\N{FULLWIDTH COMMERCIAL AT}\N{SMALL COMMERCIAL AT}]\s{0,3}"  # «@» y sus formas Unicode
    r"|\s{0,3}[(\[]at[)\]]\s{0,3}"
    r"|\s{1,3}arroba\b\s{0,3})"
)
_PUNTO = r"(?:\s{0,3}\.\s{0,3}|\s{0,3}[(\[]dot[)\]]\s{0,3}|\s{1,3}punto\s{1,3})"
_ETIQUETA = r"[\w\-]{1,63}"
# El dominio es opcional: un fragmento de búsqueda puede cortarse tras «arroba» o tras «@».
_CORREO = re.compile(
    rf"(?<!{_LOCAL}){_LOCAL}{{1,64}}" + _ARROBA + rf"(?:{_ETIQUETA}(?:{_PUNTO}{_ETIQUETA}){{0,8}})?",
    re.IGNORECASE | re.UNICODE,
)
# Espacios (también el duro y los finos), punto, guion, raya, barra y paréntesis.
_SEPARADOR = (
    r"[\s\N{NO-BREAK SPACE}\N{THIN SPACE}\N{NARROW NO-BREAK SPACE}.\-\N{EN DASH}\N{EM DASH}\N{NON-BREAKING HYPHEN}"
    r"\N{FIGURE DASH}\N{MINUS SIGN}_/()]"
)
# Dígitos con separadores; prefijo «+» o «00» opcional.
_TELEFONO = re.compile(r"(?<!\d)(?:\+|00)?\(?\d(?:" + _SEPARADOR + r"{0,3}\d){6,18}\)?(?!\d)")
# Cifras sueltas dictadas («6, 1, 2, 3…», como las escribe Whisper): una coma solo une cifras sueltas, para
# que una lista de importes («1500, 2000, 3000») no se tome por un teléfono.
_DICTADO = re.compile(r"(?<!\d)\d(?:[,.]?[ \N{NO-BREAK SPACE}]\d(?!\d)){8,18}")
# Grupos de tres cifras con comas o punto y coma («612, 345, 678»): solo de tres, para no tomar por teléfono una lista de
# importes o de números sueltos.
_GRUPOS = re.compile(r"(?<!\d)(?:\+|00)?\(?\d{3}(?:[,;]\s?\d{3}){2,5}\)?(?!\d)")
_RELLENO = r"[\s.,/\-\N{EN DASH}()+]"
_BORDE_INICIAL = re.compile(r"^" + _RELLENO + r"*\d[\d\s.,/\-\N{EN DASH}()+]{0,40}")
_BORDE_FINAL = re.compile(r"[\d\s.,/\-\N{EN DASH}()+]{0,40}\d" + _RELLENO + r"*$")


# Una fecha con hora suelta («2026-11-25 09», «25/11/2026 10»): suma 9 o 10 cifras y no es un teléfono.
_FECHA_Y_HORA = re.compile(r"(?:\d{4}[-/.]\d{1,2}[-/.]\d{1,2}|\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4})(?:[ \N{NO-BREAK SPACE}]\d{1,2})?")


def _telefono(m: re.Match[str]) -> str:
    digitos = re.sub(r"\D", "", m.group(0))
    if len(digitos) < MIN_DIGITOS_TELEFONO or _FECHA_Y_HORA.fullmatch(m.group(0)):
        return m.group(0)
    return f"{PREFIJO_TELEFONO}{digitos[-3:]}"


def enmascarar(texto: str, maximo: int | None = None) -> str:
    """Correos fuera y teléfonos a sus 3 últimos dígitos; con `maximo`, recorta el resultado."""
    salida = _CORREO.sub(MARCA_CORREO, texto)
    salida = _DICTADO.sub(_telefono, _GRUPOS.sub(_telefono, _TELEFONO.sub(_telefono, salida)))
    if maximo is not None and len(salida) > maximo:
        salida = salida[:maximo] + "…"
    return salida


def recortar_bordes(texto: str, maximo: int | None = None) -> str:
    """Un fragmento de búsqueda ya en texto plano, enmascarado.

    `ts_headline` corta por palabras: un número cortado en el borde («345 678 …») ya no llega a 9 cifras y no se
    reconocería. Lo que queda de cifras en los bordes, tras enmascarar lo completo, se descarta."""
    texto = enmascarar(texto)
    texto = _BORDE_INICIAL.sub("… ", texto, count=1) if _BORDE_INICIAL.match(texto) else texto
    texto = _BORDE_FINAL.sub(" …", texto, count=1) if _BORDE_FINAL.search(texto) else texto
    if maximo is not None and len(texto) > maximo:
        texto = texto[:maximo] + "…"
    return texto
