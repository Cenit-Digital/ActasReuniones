"""«Copiar diagnóstico para Claude» (@a60; ADR 0023 de KubernetesInfrastructure, decisión 9, parte a): un bloque en Markdown que
Pablo pega en su propio Claude Code o en claude.ai. Es uso ordinario de su suscripción: el panel no llama a nadie.

Sale de Cenit hacia un tercero, así que se construye con una lista blanca y no tachando: el estado, el motivo, el diagnóstico
del panel (`diagnostico.py`), las líneas del historial de eventos (sus detalles ya son de la lista blanca de la migración 0005),
las comprobaciones del latido y las versiones. Los socios van como S1, S2… en el orden de la reunión, y los usuarios del panel
como U1, U2… Nunca lleva la sala (ni su nombre, ni `room`, ni `hash`, ni la contraseña), enlaces, correos ni el texto de los
segmentos. Por si un nombre llegara dentro de un código, al final se cambia cada nombre e identificador conocido por su
seudónimo y cada URL por «[enlace]».
"""

import re
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from typing import Any

from actas.diagnostico import Diagnostico, linea_evento

_URL = re.compile(r"https?://\S+")


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


def _historial(r: Mapping[str, Any], eventos: Sequence[Mapping[str, Any]], usuario: _Seudonimos) -> list[str]:
    """Las mismas líneas que el historial del panel, con los usuarios ya cambiados."""
    pedido_por = r.get("pedido_por")
    lineas: list[tuple[datetime, str]] = [(r["creado_en"], f"Pedida por {usuario(pedido_por) if pedido_por else 'actas.sh'}")]
    if r.get("parar_pedido_en"):
        lineas.append((r["parar_pedido_en"], "Parada pedida"))
    if r.get("reintento_pedido_en"):
        quien = usuario(r.get("reintento_pedido_por") or "")
        lineas.append((r["reintento_pedido_en"], f"Reintento pedido por {quien}: pendiente"))
    for e in eventos:
        detalle = dict(e["detalle"])
        if detalle.get("usuario"):
            detalle["usuario"] = usuario(str(detalle["usuario"]))
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
    historial = _historial(r, eventos, usuario)
    partes = [
        "# Diagnóstico de una reunión del sistema de actas de Cenit Digital",
        "Contexto: un supervisor en Python graba las reuniones de socios con un Chromium sin cabeza (páginas de VDO.Ninja "
        "por CDP), envía las pistas a una plataforma de transcripción propia y guarda el texto en PostgreSQL. Los socios "
        "van como S1, S2… y los usuarios del panel como U1, U2…; no se incluyen contraseñas, enlaces ni texto de la reunión.",
        "## Reunión\n"
        + "\n".join(
            [
                f"- Id: {str(r['id'])[:8]}",
                f"- Estado: {r['estado']} · motivo `{r.get('motivo') or 'sin motivo'}`",
                f"- Socios: {', '.join(socio(s) for s in r.get('socios') or []) or 'ninguno'}",
                f"- Conformidades: {', '.join(f'{socio(s)} (texto {v})' for s, v in conformidades) or 'ninguna'}",
            ]
        ),
        "## Diagnóstico del panel\n"
        + f"- {diagnostico.titulo}\n- Qué pasó: {diagnostico.que_paso}\n- Qué hacer: {diagnostico.que_hacer}",
        "## Historial\n" + "\n".join(historial) + ("\n- (reunión anterior al historial: sin eventos)" if not eventos else ""),
        "## Comprobaciones y versiones\n" + "\n".join(f"- {texto} [{nivel}]" for texto, nivel in comprobaciones),
        "¿Qué crees que pasó y qué harías?",
    ]
    texto = _URL.sub("[enlace]", "\n\n".join(partes) + "\n")
    # Red de seguridad: cada nombre e identificador conocido, por su seudónimo (los más largos primero).
    cambios = {**{n: socio(p) for p, n in nombres.items()}, **{p: socio(p) for p in nombres}, **socio.de, **usuario.de}
    for original in sorted((c for c in cambios if c), key=len, reverse=True):
        texto = re.sub(rf"(?<!\w){re.escape(original)}(?!\w)", cambios[original], texto, flags=re.IGNORECASE)
    return texto
