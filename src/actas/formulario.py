"""El formulario «Grabar» del panel (@a29) y quién lo envía.

- Socios: solo los activos de la tabla `socios` (V2 de KubernetesInfrastructure#298; antes, un ConfigMap), y además lo que ya
  exige `conformidad.validar` para `actas.sh` (al menos uno, streamID válido, tope de 16). Su alta, con `validar_socio` (@a47).
- Versión del texto informativo: la de un texto empaquetado (`textos/informativo-<versión>.md`), con el formato de la base.
- Usuario: el que Traefik pone en `X-Actas-Usuario` tras el BasicAuth (`headerField`); se guarda en `reuniones.pedido_por`, con
  el mismo formato que su CHECK (migración 0002).
"""

import re
from collections.abc import Collection, Sequence
from dataclasses import dataclass

from actas.conformidad import STREAM_ID, ConformidadNoValida, Peticion, validar

_USUARIO = re.compile(r"[A-Za-z0-9._@-]{1,64}")
_FICHERO_TEXTO = re.compile(r"informativo-([A-Za-z0-9._-]{1,40})\.md")
TOPE_NOMBRE = 64
TOPE_CORREO = 254
_CORREO = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")


class FormularioNoValido(ConformidadNoValida):
    """400 y ninguna fila nueva."""


def validar_grabar(socios: Sequence[str], version: str, conocidos: Collection[str], versiones: Collection[str]) -> Peticion:
    peticion = validar(list(socios), version)
    if any(s not in conocidos for s in peticion.socios):
        raise FormularioNoValido("solo se graba a los socios conocidos")
    if peticion.version not in versiones:
        raise FormularioNoValido("la versión no es la de un texto informativo del panel")
    return peticion


def usuario(valor: str | None) -> str | None:
    return valor if valor is not None and _USUARIO.fullmatch(valor) else None


@dataclass(frozen=True)
class Socio:
    push: str
    nombre: str
    correo: str | None


def validar_socio(push: str, nombre: str, correo: str) -> Socio:
    """Alta de un socio desde «Salas y socios» (@a47). El `push` es su streamID en VDO.Ninja y en `reuniones.socios`."""
    push, nombre, correo = push.strip(), nombre.strip(), correo.strip()
    if "-" in push:
        raise FormularioNoValido("el identificador va sin guiones: VDO.Ninja los cambia por «_» (lección de F0)")
    if not STREAM_ID.fullmatch(push):
        raise FormularioNoValido("el identificador, de 1 a 32 letras minúsculas o números")
    if not 1 <= len(nombre) <= TOPE_NOMBRE or _CONTROL.search(nombre):
        raise FormularioNoValido(f"el nombre, de 1 a {TOPE_NOMBRE} caracteres y sin saltos de línea")
    if correo and (len(correo) > TOPE_CORREO or not _CORREO.fullmatch(correo)):
        raise FormularioNoValido("el correo no es válido")
    return Socio(push, nombre, correo or None)


class TextoNoValido(ValueError):
    """No se sabe qué texto informativo mostrar: el panel no arranca."""


def version_vigente(textos: Collection[str], pedida: str | None) -> str:
    """La versión que muestra «Grabar»: la configurada (ACTAS_TEXTO_VERSION) o, si no hay, la única empaquetada. Nunca se elige
    por orden alfabético («v10» < «v9»)."""
    if pedida:
        if pedida not in textos:
            raise TextoNoValido("la versión configurada no es la de ningún texto empaquetado")
        return pedida
    if len(textos) != 1:
        raise TextoNoValido("hay varios textos informativos: configura ACTAS_TEXTO_VERSION")
    return next(iter(textos))


def version_de_fichero(nombre: str) -> str | None:
    m = _FICHERO_TEXTO.fullmatch(nombre)
    return m.group(1) if m else None
