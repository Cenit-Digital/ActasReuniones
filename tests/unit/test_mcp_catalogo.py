"""MCP-first (arnés v0.6.0): catalogo.json da la capa de cada herramienta, con el formato de la centralita del Nodo."""

import json
from pathlib import Path
from typing import Any

import anyio
from test_mcp_lectura import Repo

from actas.mcp_servidor import crear_servidor

CATALOGO = Path(__file__).resolve().parents[2] / "src" / "actas" / "catalogo.json"


def test_catalogo_de_capas_coincide_con_tools_list() -> None:
    """Falla si el servidor anuncia una herramienta que no está en el catálogo (o al revés), si una capa no es
    L, E ni ⚠ (las ✕ no se anuncian) o si `readOnlyHint` no coincide con «es L»."""
    catalogo = json.loads(CATALOGO.read_text(encoding="utf-8"))
    servidor = crear_servidor(Repo())  # type: ignore[arg-type]

    async def herramientas() -> list[Any]:
        return list(await servidor.list_tools())

    anunciadas = anyio.run(herramientas)
    assert {t.name for t in anunciadas} == set(catalogo)
    for t in anunciadas:
        capa = catalogo[t.name]
        assert capa in {"L", "E", "⚠"}, (t.name, capa)
        solo_lectura = bool(t.annotations and t.annotations.read_only_hint)
        assert solo_lectura == (capa == "L"), t.name
