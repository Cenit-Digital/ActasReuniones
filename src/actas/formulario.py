"""El formulario «Grabar» del panel (@a29) y quién lo envía.

- Socios: solo los conocidos (fichero JSON montado desde un ConfigMap de KubernetesInfrastructure), y además lo que ya exige
  `conformidad.validar` para `actas.sh` (al menos uno, streamID válido, tope de 16).
- Versión del texto informativo: la de un texto empaquetado (`textos/informativo-<versión>.md`), con el formato de la base.
- Usuario: el que Traefik pone en `X-Actas-Usuario` tras el BasicAuth (`headerField`); se guarda en `reuniones.pedido_por`, con
  el mismo formato que su CHECK (migración 0002).
"""

import json
import re
from collections.abc import Collection, Sequence

from actas.conformidad import STREAM_ID, TOPE_SOCIOS, ConformidadNoValida, Peticion, validar

_USUARIO = re.compile(r"[A-Za-z0-9._@-]{1,64}")
_FICHERO_TEXTO = re.compile(r"informativo-([A-Za-z0-9._-]{1,40})\.md")
TOPE_NOMBRE = 64


class FormularioNoValido(ConformidadNoValida):
    """400 y ninguna fila nueva."""


class SociosNoValidos(ValueError):
    """El fichero de socios conocidos no es válido: el panel no arranca."""


def validar_grabar(socios: Sequence[str], version: str, conocidos: Collection[str], versiones: Collection[str]) -> Peticion:
    peticion = validar(list(socios), version)
    if any(s not in conocidos for s in peticion.socios):
        raise FormularioNoValido("solo se graba a los socios conocidos")
    if peticion.version not in versiones:
        raise FormularioNoValido("la versión no es la de un texto informativo del panel")
    return peticion


def usuario(valor: str | None) -> str | None:
    return valor if valor is not None and _USUARIO.fullmatch(valor) else None


def socios_conocidos(texto: str) -> dict[str, str]:
    """`[{"id": "pablo", "nombre": "Pablo"}, …]` → {streamID: nombre visible}, en el orden del fichero."""
    try:
        datos = json.loads(texto)
    except json.JSONDecodeError as e:
        raise SociosNoValidos("el fichero de socios no es JSON") from e
    if not isinstance(datos, list) or not 1 <= len(datos) <= TOPE_SOCIOS:
        raise SociosNoValidos(f"una lista de 1 a {TOPE_SOCIOS} socios")
    socios: dict[str, str] = {}
    for d in datos:
        sid = d.get("id") if isinstance(d, dict) else None
        nombre = d.get("nombre") if isinstance(d, dict) else None
        if not isinstance(sid, str) or not STREAM_ID.fullmatch(sid) or sid in socios:
            raise SociosNoValidos("cada socio con un streamID distinto, alfanumérico en minúscula")
        if not isinstance(nombre, str) or not nombre.strip() or len(nombre) > TOPE_NOMBRE:
            raise SociosNoValidos(f"cada socio con un nombre de 1 a {TOPE_NOMBRE} caracteres")
        socios[sid] = nombre
    return socios


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
