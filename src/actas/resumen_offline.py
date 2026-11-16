"""Preparación y validación local de F3, sin transporte ni persistencia.

Solo sustituye coincidencias literales de identificadores y nombres facilitados (Unicode NFC, sin distinguir mayúsculas,
con límites de palabra). No detecta alias, faltas, inflexiones ni referencias indirectas; no anonimiza el texto libre.
No valida si el contenido del acta es verdadero ni fiel a la transcripción. No conectar a un proveedor sin revisar
esa limitación y el contrato de structured outputs del gateway.
"""

import json
import re
import unicodedata
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any, cast


class ErrorResumen(ValueError):
    """Datos ambiguos, respuesta rechazada o acta inválida; nunca incluye contenido de la reunión."""


# El supervisor admite hasta 16 pistas; 10 000 segmentos y 900 kB son límites locales provisionales, no capacidad certificada.
_MAX_SOCIOS = 16
_MAX_SEGMENTOS = 10_000
_MAX_TEXTO_BYTES = 900_000
_MAX_IDENTIDAD = 256

_SEUDONIMO = re.compile(r"(?<!\w)S[0-9]+(?!\w)", re.IGNORECASE)
_SISTEMA = (
    "Devuelve únicamente JSON con resumen (texto), temas, decisiones y pendientes (listas de texto), "
    "y tareas (lista de objetos con que, responsable y fecha_limite; los dos últimos texto o null). "
    "No inventes responsables ni fechas; usa null si no constan. Las fechas usan AAAA-MM-DD."
)


def _nfc(valor: str) -> str:
    return unicodedata.normalize("NFC", valor)


def preparar(segmentos: Sequence[tuple[str, str]], socios: Mapping[str, str]) -> tuple[dict[str, Any], dict[str, str]]:
    """Construye la petición textual local y el mapa privado para restaurar nombres. No envía ni registra nada."""
    if not socios or not segmentos:
        raise ErrorResumen("faltan socios o segmentos")
    if len(socios) > _MAX_SOCIOS or len(segmentos) > _MAX_SEGMENTOS:
        raise ErrorResumen("demasiados socios o segmentos")
    # Contar antes de normalizar, plegar o crear el mapa de posiciones. len(str) permite rechazar un único segmento enorme
    # sin codificarlo; la codificación posterior está acotada por el presupuesto restante.
    restantes = _MAX_TEXTO_BYTES
    for hablante, texto in segmentos:
        if not isinstance(hablante, str) or not isinstance(texto, str):
            raise ErrorResumen("segmento inválido")
        if len(texto) > restantes:
            raise ErrorResumen("transcripción demasiado grande")
        try:
            restantes -= len(texto.encode("utf-8"))
        except UnicodeEncodeError:
            raise ErrorResumen("transcripción inválida") from None
        if restantes < 0:
            raise ErrorResumen("transcripción demasiado grande")
    mapa: dict[str, str] = {}
    aliases: dict[str, str] = {}
    por_id: dict[str, str] = {}
    for i, (identificador, nombre) in enumerate(socios.items(), 1):
        if (
            not isinstance(identificador, str)
            or not isinstance(nombre, str)
            or len(identificador) > _MAX_IDENTIDAD
            or len(nombre) > _MAX_IDENTIDAD
            or not identificador.strip()
            or not nombre.strip()
        ):
            raise ErrorResumen("identidad inválida")
        sid = f"S{i}"
        por_id[identificador] = sid
        mapa[sid] = _nfc(nombre)
        for alias in (identificador, nombre):
            alias = _nfc(alias.strip())
            if _SEUDONIMO.search(alias):
                raise ErrorResumen("colisión de seudónimo")
            clave = alias.casefold()
            if clave in aliases and aliases[clave] != sid:
                raise ErrorResumen("identidades ambiguas")
            aliases[clave] = sid
    # Reemplazo más largo primero: evita que un nombre compuesto quede parcialmente sustituido.
    expresion = re.compile(r"(?<!\w)(?:" + "|".join(re.escape(x) for x in sorted(aliases, key=len, reverse=True)) + r")(?!\w)")
    lineas = []
    for hablante, texto in segmentos:
        if hablante not in por_id or not isinstance(texto, str):
            raise ErrorResumen("segmento inválido")
        texto = _nfc(texto)
        if _SEUDONIMO.search(texto):
            raise ErrorResumen("colisión de seudónimo")
        # casefold puede expandir un carácter (ß → ss): conservamos la posición original de cada carácter expandido.
        plegado = "".join(c.casefold() for c in texto)
        posiciones = [i for i, c in enumerate(texto) for _ in c.casefold()]
        partes: list[str] = []
        anterior = 0
        for coincidencia in expresion.finditer(plegado):
            inicio, fin = coincidencia.span()
            if (inicio and posiciones[inicio - 1] == posiciones[inicio]) or (
                fin < len(posiciones) and posiciones[fin - 1] == posiciones[fin]
            ):
                raise ErrorResumen("coincidencia Unicode ambigua")
            primero, ultimo = posiciones[inicio], posiciones[fin - 1] + 1
            partes.extend((texto[anterior:primero], aliases[coincidencia.group()]))
            anterior = ultimo
        partes.append(texto[anterior:])
        lineas.append(f"{por_id[hablante]}: {''.join(partes)}")
    contenido = "\n".join(lineas)
    if len(contenido.encode("utf-8")) > _MAX_TEXTO_BYTES:
        raise ErrorResumen("transcripción demasiado grande")
    return {
        "model": "claude-sonnet-5-5",
        "system": _SISTEMA,
        "messages": [{"role": "user", "content": contenido}],
        "max_tokens": 4096,
    }, mapa


def _objeto_unico(pares: list[tuple[str, Any]]) -> dict[str, Any]:
    salida: dict[str, Any] = {}
    for clave, valor in pares:
        if clave in salida:
            raise ErrorResumen("clave duplicada")
        salida[clave] = valor
    return salida


def validar_respuesta(respuesta: Mapping[str, Any], mapa: Mapping[str, str]) -> dict[str, Any]:
    """Valida un único bloque JSON completo; un rechazo o texto inesperado nunca se convierte en acta."""
    if respuesta.get("stop_reason") != "end_turn":
        raise ErrorResumen("respuesta incompleta o rechazada")
    bloques = respuesta.get("content")
    if not isinstance(bloques, list) or len(bloques) != 1 or not isinstance(bloques[0], dict):
        raise ErrorResumen("contenido inválido")
    bloque = bloques[0]
    if set(bloque) != {"type", "text"} or bloque["type"] != "text" or not isinstance(bloque["text"], str):
        raise ErrorResumen("contenido inválido")
    try:
        acta = json.loads(
            bloque["text"],
            object_pairs_hook=_objeto_unico,
            parse_constant=lambda _: (_ for _ in ()).throw(ErrorResumen("constante inválida")),
        )
    except (ValueError, TypeError):
        raise ErrorResumen("JSON inválido") from None
    if not isinstance(acta, dict) or set(acta) != {"resumen", "temas", "decisiones", "tareas", "pendientes"}:
        raise ErrorResumen("esquema inválido")
    if not isinstance(acta["resumen"], str):
        raise ErrorResumen("resumen inválido")
    for clave in ("temas", "decisiones", "pendientes"):
        if not isinstance(acta[clave], list) or any(not isinstance(v, str) for v in acta[clave]):
            raise ErrorResumen("lista inválida")
    if not isinstance(acta["tareas"], list):
        raise ErrorResumen("tareas inválidas")
    for tarea in acta["tareas"]:
        if (
            not isinstance(tarea, dict)
            or set(tarea) != {"que", "responsable", "fecha_limite"}
            or not isinstance(tarea["que"], str)
        ):
            raise ErrorResumen("tarea inválida")
        responsable = tarea["responsable"]
        if responsable is not None and (not isinstance(responsable, str) or responsable not in mapa):
            raise ErrorResumen("responsable inválido")
        fecha = tarea["fecha_limite"]
        if fecha is not None:
            try:
                if not isinstance(fecha, str) or date.fromisoformat(fecha).isoformat() != fecha:
                    raise ValueError
            except ValueError:
                raise ErrorResumen("fecha inválida") from None

    def restaurar(valor: Any) -> Any:
        if isinstance(valor, str):

            def reemplazar(m: re.Match[str]) -> str:
                sid = m.group().upper()
                if sid not in mapa:
                    raise ErrorResumen("seudónimo desconocido")
                return mapa[sid]

            return _SEUDONIMO.sub(reemplazar, valor)
        if isinstance(valor, list):
            return [restaurar(v) for v in valor]
        if isinstance(valor, dict):
            return {k: restaurar(v) for k, v in valor.items()}
        return valor

    return cast(dict[str, Any], restaurar(acta))
