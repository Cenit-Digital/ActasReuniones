"""«Copiar diagnóstico para Claude» (@a60; ADR 0023 de KubernetesInfrastructure, decisión 9, parte a): un bloque en Markdown que
Pablo pega en su propio Claude Code o en claude.ai. Es uso ordinario de su suscripción: el panel no llama a nadie.

Sale de Cenit hacia un tercero, así que se construye con una lista blanca y no tachando: el estado, el motivo, el diagnóstico
del panel (`diagnostico.py`), las líneas del historial de eventos (sus detalles ya son de la lista blanca de la migración 0005),
las comprobaciones del latido y las versiones. Los socios van como S1, S2… en el orden de la reunión, y los usuarios del panel
como U1, U2… Nunca lleva la sala (ni su nombre, ni `room`, ni `hash`, ni la contraseña), enlaces, correos ni el texto de los
segmentos. Por si un nombre llegara como código (el motivo o un valor libre de un evento), cada valor que sea entero un nombre
o un identificador conocido se cambia por su seudónimo antes de escribir la línea: se comparan valores, no se busca en el texto,
que con códigos de socio cortos (`a`, `de`) o nombres corrientes («Error») estropearía el diagnóstico (hallazgo de la revisión de
seguridad). Y cada URL de todo el bloque, comprobaciones incluidas, por «[enlace]».
"""

import re
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from typing import Any

from actas.diagnostico import Diagnostico, linea_evento

_URL = re.compile(r"https?://\S+")
# Claves de `eventos.detalle` cuyos valores son de un vocabulario fijo del supervisor (estados y acciones): un socio que se
# llamara «Error» no puede cambiar `hasta: error`.
_VOCABULARIO_FIJO = frozenset({"desde", "hasta", "accion"})


def _hora(m: datetime) -> str:
    return m.strftime("%Y-%m-%d %H:%M:%S")


class _Seudonimos:
    def __init__(self, prefijo: str, conocidos: Iterable[str] = ()) -> None:
        self.prefijo = prefijo
        self.de: dict[str, str] = {}
        for c in conocidos:
            self(c)

    def __call__(self, nombre: str) -> str:
        return self.de.setdefault(nombre, f"{self.prefijo}{len(self.de) + 1}")


def _historial(r: Mapping[str, Any], eventos: Sequence[Mapping[str, Any]], usuario: _Seudonimos, valor: Any) -> list[str]:
    """Las mismas líneas que el historial del panel, con los usuarios ya cambiados y cada valor pasado por `valor`."""
    pedido_por = r.get("pedido_por")
    lineas: list[tuple[datetime, str]] = [(r["creado_en"], f"Pedida por {usuario(pedido_por) if pedido_por else 'actas.sh'}")]
    if r.get("parar_pedido_en"):
        lineas.append((r["parar_pedido_en"], "Parada pedida"))
    if r.get("reintento_pedido_en"):
        quien = r.get("reintento_pedido_por")
        lineas.append((r["reintento_pedido_en"], f"Reintento pedido por {usuario(quien) if quien else 'alguien'}: pendiente"))
    for e in eventos:
        detalle = {k: v if k in _VOCABULARIO_FIJO else valor(v) for k, v in e["detalle"].items()}
        if e["detalle"].get("usuario"):
            detalle["usuario"] = usuario(str(e["detalle"]["usuario"]))
        texto, nivel = linea_evento(e["tipo"], detalle)
        lineas.append((e["momento"], f"{texto} [{nivel}]"))
    if not eventos:
        if r.get("inicio"):
            lineas.append((r["inicio"], "Empezó a grabar"))
        if r.get("fin"):
            lineas.append((r["fin"], "Terminó la grabación"))
    lineas.sort(key=lambda x: x[0])
    return [f"- {_hora(m)} · {texto}" for m, texto in lineas]


def bloque(
    r: Mapping[str, Any],
    conformidades: Sequence[tuple[str, str]],
    eventos: Sequence[Mapping[str, Any]],
    diagnostico: Diagnostico,
    comprobaciones: Sequence[tuple[str, str]],
    nombres: Mapping[str, str],
) -> str:
    """`r`: la fila de la reunión; `conformidades`: (push, versión del texto); `comprobaciones`: las de
    `diagnostico.comprobaciones`; `nombres`: {push: nombre} de todos los socios, solo para cambiarlos si se colaran."""
    socio = _Seudonimos("S", r.get("socios") or [])
    usuario = _Seudonimos("U")
    for p in nombres:
        socio(p)
    # {valor en minúsculas: seudónimo}: los identificadores y los nombres de los socios (un socio gana a un usuario homónimo).
    conocidos = {**{p.lower(): s for p, s in socio.de.items()}, **{n.lower(): socio(p) for p, n in nombres.items() if n}}

    def valor(v: Any) -> Any:
        if isinstance(v, str):
            return conocidos.get(v.lower()) or usuario.de.get(v) or v
        return v

    historial = _historial(r, eventos, usuario, valor)
    motivo = r.get("motivo")
    titulo = diagnostico.titulo
    if motivo and valor(motivo) != motivo:  # un motivo desconocido sale tal cual en el título: «Error «x»»
        titulo = titulo.replace(f"«{motivo}»", f"«{valor(motivo)}»")
    socios = [socio(s) for s in r.get("socios") or []]
    lineas_reunion = [
        f"- Id: {str(r['id'])[:8]}",
        f"- Estado: {r['estado']} · motivo `{valor(motivo) if motivo else 'sin motivo'}`",
        f"- Socios: {', '.join(socios) or 'ninguno'}",
        f"- Conformidades: {', '.join(f'{socio(s)} (texto {v})' for s, v in conformidades) or 'ninguna'}",
    ]
    partes = [
        "# Diagnóstico de una reunión del sistema de actas de Cenit Digital",
        "Contexto: un supervisor en Python graba las reuniones de socios con un Chromium sin cabeza (páginas de VDO.Ninja "
        "por CDP), envía las pistas a una plataforma de transcripción propia y guarda el texto en PostgreSQL. Los socios van "
        "como S1, S2… y los usuarios del panel como U1, U2…; no se incluyen contraseñas, enlaces ni texto de la reunión. "
        "«Abajo» y los botones que cita el diagnóstico son los de la ficha de la reunión en el panel.",
        "## Reunión\n" + "\n".join(lineas_reunion),
        f"## Diagnóstico del panel\n- {titulo}\n- Qué pasó: {diagnostico.que_paso}\n- Qué hacer: {diagnostico.que_hacer}",
        "## Historial\n" + "\n".join(historial) + ("\n- (reunión anterior al historial: sin eventos)" if not eventos else ""),
        "## Comprobaciones y versiones\n" + "\n".join(f"- {t} [{nivel}]" for t, nivel in comprobaciones),
        "¿Qué crees que pasó y qué harías?",
    ]
    return _URL.sub("[enlace]", "\n\n".join(partes)) + "\n"
