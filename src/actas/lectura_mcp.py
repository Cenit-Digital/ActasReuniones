"""Lo que el MCP de solo lectura deja salir de las actas (ADR 0004).

Las consultas son las del panel (`Repositorio.ultimas`, `detalle`, `buscar` y `socios`); aquí solo se decide qué campos salen.
Cada DTO se construye campo a campo (lista blanca). Nunca salen el `push` de un socio (es su clave de la sala de VDO.Ninja), su
correo, la sala, el trabajo de transcripción ni nada del grabador. Los nombres de los socios se dejan; todo texto libre pasa por
`enmascarar` (correos fuera, teléfonos con los 3 últimos dígitos). Una reunión en la papelera no se lee: el panel tampoco
enseña lo que dijeron.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from actas import busqueda, presentacion
from actas.base import es_uuid
from actas.enmascarar import coincidencia_limpia, enmascarar
from actas.estados import Estado

Fila = dict[str, Any]

MAX_REUNIONES = 25
MAX_BUSQUEDA = 20
MAX_SEGMENTOS = 200
MAX_CARACTERES = 20_000
MAX_TEXTO = 2_000
MAX_TITULO = 200
MAX_MOTIVO = 200
MAX_PAGINA = 10_000
DESCONOCIDO = "Socio"

_ESTADOS = frozenset(e.value for e in Estado)
_ANO = re.compile(r"(?<!\d)(?:19|20)\d{2}(?!\d)")
_ORACULO = re.compile(r"@|arroba|\d(?:[\s.\-/]{0,3}\d){2,}", re.IGNORECASE)


class NoEncontrada(Exception):
    """La reunión no existe o está en la papelera."""


class ConsultaNoValida(Exception):
    """Un argumento fuera de las reglas; el mensaje es fijo y se enseña al agente."""


def _fecha(valor: Any) -> str | None:
    return valor.isoformat() if valor is not None else None


def _socios(ids: Any, conocidos: Mapping[str, str]) -> list[str]:
    return [enmascarar(conocidos.get(s, DESCONOCIDO), 64) for s in ids or []]


def reunion_mcp(r: Mapping[str, Any], conocidos: Mapping[str, str]) -> Fila:
    motivo = r.get("motivo")
    return {
        "id": str(r["id"]),
        "titulo": enmascarar(r.get("titulo") or f"Reunión del {r['creado_en']:%Y-%m-%d %H:%M}", MAX_TITULO),
        "estado": r["estado"],
        "creada_en": _fecha(r.get("creado_en")),
        "programada_para": _fecha(r.get("programada_para")),
        "inicio": _fecha(r.get("inicio")),
        "fin": _fecha(r.get("fin")),
        "duracion": presentacion.duracion(r.get("inicio"), r.get("fin")),
        "socios": _socios(r.get("socios"), conocidos),
        "motivo": enmascarar(str(motivo), MAX_MOTIVO) if motivo else None,
    }


def _tope(valor: int) -> int:
    return min(max(valor, 1), MAX_PAGINA)


def listar_reuniones(repo: Any, estado: str | None, pagina: int) -> Fila:
    """Las últimas reuniones (el panel enseña 100): `pagina` de 25 sobre ellas."""
    if estado is not None and estado not in _ESTADOS:
        raise ConsultaNoValida("Estado no válido")
    conocidos = {s["push"]: s["nombre"] for s in repo.socios()}
    todas = [r for r in repo.ultimas(100) if estado is None or r["estado"] == estado]
    pagina = _tope(pagina)
    desde = (pagina - 1) * MAX_REUNIONES
    return {
        "total": len(todas),
        "pagina": pagina,
        "reuniones": [reunion_mcp(r, conocidos) for r in todas[desde : desde + MAX_REUNIONES]],
    }


def leer_acta(repo: Any, reunion_id: str, desde: int) -> Fila:
    """Una página de la transcripción: hasta `MAX_SEGMENTOS` o `MAX_CARACTERES` de texto, lo que ocurra antes; `siguiente`
    es el `desde` de la página siguiente (null en la última) y un segmento nunca se parte."""
    if not es_uuid(reunion_id):
        raise ConsultaNoValida("Identificador de reunión no válido")
    try:
        r, _conformidades, segmentos = repo.detalle(str(reunion_id))
    except KeyError:
        raise NoEncontrada from None
    if r.get("papelera_en") is not None:
        raise NoEncontrada
    conocidos = {s["push"]: s["nombre"] for s in repo.socios()}
    desde = max(desde, 0)
    salida: list[Fila] = []
    caracteres = 0
    for hablante, inicio, fin, texto in segmentos[desde : desde + MAX_SEGMENTOS]:
        limpio = enmascarar(texto, MAX_TEXTO)
        if salida and caracteres + len(limpio) > MAX_CARACTERES:
            break
        caracteres += len(limpio)
        salida.append(
            {
                "tiempo": presentacion.hhmmss(inicio),
                "inicio_ms": inicio,
                "fin_ms": fin,
                "hablante": enmascarar(conocidos.get(hablante, DESCONOCIDO), 64),
                "texto": limpio,
            }
        )
    fin_pagina = desde + len(salida)
    return {
        "reunion": reunion_mcp(r, conocidos),
        "total_segmentos": len(segmentos),
        "desde": desde,
        "segmentos": salida,
        "siguiente": fin_pagina if fin_pagina < len(segmentos) else None,
    }


def _limpiar(fragmento: str) -> str:
    """El fragmento de `ts_headline` (con sus centinelas y los `<`, `>`, `&` cambiados, busqueda.py) a texto plano enmascarado."""
    texto = fragmento.translate(dict.fromkeys(map(ord, busqueda.INICIO + busqueda.FIN)))
    for original, sustituto in busqueda.SUSTITUTOS.items():
        texto = texto.replace(sustituto, original)
    return coincidencia_limpia(texto, MAX_TEXTO)


def buscar_en_actas(repo: Any, consulta: str) -> Fila:
    q = busqueda.normalizar(consulta)
    if q is None:
        raise ConsultaNoValida("La consulta no puede estar vacía")
    if _ORACULO.search(_ANO.sub("", q)):
        raise ConsultaNoValida("La búsqueda no admite correos ni números de más de dos cifras (salvo años)")
    conocidos = {s["push"]: s["nombre"] for s in repo.socios()}
    filas = repo.buscar(q, MAX_BUSQUEDA, busqueda.QUITAR, busqueda.PONER, busqueda.OPCIONES)
    return {
        "total": len(filas),
        "resultados": [
            {
                "reunion_id": str(h["reunion_id"]),
                "creada_en": _fecha(h["creado_en"]),
                "hablante": enmascarar(conocidos.get(h["hablante"], DESCONOCIDO), 64),
                "tiempo": presentacion.hhmmss(h["inicio_ms"]),
                "fragmento": _limpiar(h["fragmento"]),
            }
            for h in filas
        ],
    }
