"""«Compartir» con los socios, nivel 1 (@a58; ADR 0023 de KubernetesInfrastructure, decisión 8): el panel prepara el texto y Pablo
lo manda por su propio canal, copiándolo o con un `mailto:`. Nada sale de NetBird desde el panel.

Cada socio recibe su mensaje: el enlace a la sala lleva su `push` (`enlaces.enlace`), así que uno solo para varios no valdría.
**La contraseña de la sala no se comparte desde aquí** (decisión de Pablo del 2026-10-27): ni es una opción de `QUE` ni un
argumento de `preparar`, así que el enlace y la contraseña no pueden ir en el mismo mensaje. Se copia, con su confirmación y su
rastro (`clave_vista`, @a45), desde la página de la sala.
"""

import urllib.parse
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass

from actas.presentacion import hhmmss

QUE = {"transcripcion": "Transcripción", "enlace_sala": "Enlace de la sala"}
# RFC 6068 no fija un tope para la URL, pero los clientes de correo cortan o rechazan las muy largas. 2000 caracteres es un tope
# prudente elegido aquí: por encima, el `mailto:` va sin la transcripción y el mensaje dice que va en el fichero adjunto (el .txt
# del panel), porque un `mailto:` no puede adjuntar ficheros.
MAILTO_MAX = 2000
_ADJUNTA = "La transcripción va en el fichero adjunto."


class CompartirNoValido(ValueError):
    pass


@dataclass(frozen=True)
class Destinatario:
    push: str
    nombre: str
    correo: str | None


@dataclass(frozen=True)
class Mensaje:
    destinatario: Destinatario
    asunto: str
    texto: str
    mailto: str
    mailto_completo: bool  # False: el `mailto:` va sin la transcripción, que se adjunta


def texto_transcripcion(segmentos: Iterable[tuple[str, int, int, str]], nombres: Mapping[str, str]) -> str:
    """Una línea por segmento: `[hh:mm:ss] Nombre: texto` (el identificador si el hablante no es un socio conocido)."""
    return "\n".join(f"[{hhmmss(ini)}] {nombres.get(h, h)}: {t}" for h, ini, _fin, t in segmentos)


def elegir(
    que: Iterable[str], socios: Iterable[str], que_ofrecido: Collection[str], socios_ofrecidos: Collection[str]
) -> tuple[set[str], list[str]]:
    """Lo marcado en el formulario, validado contra lo que la página ofrece; sin repetidos y con los socios en su orden."""
    elegido = set(que)
    if not elegido or not elegido.issubset(QUE):
        raise CompartirNoValido("elige qué quieres compartir")
    if "enlace_sala" in elegido and "enlace_sala" not in que_ofrecido:
        raise CompartirNoValido("esta reunión no tiene una sala cuyo enlace compartir")
    if "transcripcion" in elegido and "transcripcion" not in que_ofrecido:
        raise CompartirNoValido("esta reunión aún no tiene transcripción")
    elegidos = list(dict.fromkeys(socios))
    if not elegidos:
        raise CompartirNoValido("elige a quién se lo mandas")
    if any(s not in socios_ofrecidos for s in elegidos):
        raise CompartirNoValido("ese socio no es de esta reunión")
    return elegido, elegidos


def mailto(correo: str | None, asunto: str, cuerpo: str) -> str:
    """RFC 6068: todo en «percent-encoding» (el espacio, %20: un «+» sería literal) y los saltos de línea como CRLF."""
    destino = urllib.parse.quote(correo, safe="@") if correo else ""
    cuerpo = cuerpo.replace("\r\n", "\n").replace("\n", "\r\n")
    return f"mailto:{destino}?subject={urllib.parse.quote(asunto, safe='')}&body={urllib.parse.quote(cuerpo, safe='')}"


def _asunto(fecha: str, que: Collection[str]) -> str:
    if que >= {"transcripcion", "enlace_sala"}:
        return f"Reunión del {fecha}: transcripción y enlace a la sala"
    if "transcripcion" in que:
        return f"Transcripción de la reunión del {fecha}"
    return "Tu enlace a la sala de las reuniones"


def _texto(nombre: str, fecha: str, transcripcion: str | None, enlace: str | None) -> str:
    partes = [f"Hola, {nombre}:"]
    if transcripcion is not None:
        partes += [f"Te paso la transcripción de la reunión de socios del {fecha}.", transcripcion]
        partes.append("Si quieres que se corrija o se borre algo tuyo, dímelo.")
    if enlace is not None:
        partes += ["Tu enlace para entrar en la sala de las reuniones (es solo tuyo):\n" + enlace]
        partes.append("La contraseña de la sala te llega por otro canal.")
    return "\n\n".join(partes)


def preparar(
    fecha: str,
    que: Collection[str],
    destinatarios: Sequence[Destinatario],
    transcripcion: str | None,
    enlaces: Mapping[str, str],
) -> list[Mensaje]:
    """Un mensaje por destinatario. `transcripcion`: el texto de `texto_transcripcion`; `enlaces`: {push: enlace a la sala}."""
    asunto = _asunto(fecha, que)
    mensajes = []
    for d in destinatarios:
        texto_t = transcripcion if "transcripcion" in que else None
        enlace = enlaces[d.push] if "enlace_sala" in que else None
        texto = _texto(d.nombre, fecha, texto_t, enlace)
        url = mailto(d.correo, asunto, texto)
        completo = len(url) <= MAILTO_MAX
        if not completo and texto_t is not None:
            url = mailto(d.correo, asunto, _texto(d.nombre, fecha, _ADJUNTA, enlace))
        mensajes.append(Mensaje(d, asunto, texto, url, completo))
    return mensajes
