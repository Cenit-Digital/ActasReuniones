"""`/mcp`: servidor MCP de solo lectura de las actas para el agente Hermes (ADR 0004).

Streamable HTTP sin estado y con respuesta JSON, en su propio puerto (8081, `ACTAS_MCP_PUERTO`): el del panel (8080) es el
de Traefik y exige su secreto y su usuario; este solo lo alcanzan, por NetworkPolicy, los pods de Hermes. Tres herramientas,
todas con `readOnlyHint`, sobre las mismas consultas del panel (`actas.lectura_mcp`). Sin escrituras, sin audio y sin sala ni
claves.

El logger del SDK sube a WARNING: registra cada petición y las búsquedas son texto de la persona.
"""

import asyncio
import contextlib
import json
import logging
import time
from collections.abc import AsyncIterator, Callable
from typing import Any

import anyio
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.streamable_http_manager import StreamableHTTPASGIApp
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from starlette.applications import Starlette
from starlette.routing import Route

from actas import lectura_mcp as lectura
from actas.base import Repositorio
from actas.mcp_guarda import GuardaMcp

log = logging.getLogger("actas.mcp")

MAX_CUERPO = 64 * 1024
SOLO_LECTURA = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False)


# `Repositorio` abre una conexión por operación y el rol del panel tiene su CONNECTION LIMIT: el MCP no hace más de dos llamadas
# a la vez (cada una, entre 2 y 3 conexiones seguidas).
LIMITE_LLAMADAS = 2


async def _ejecutar(repo: Repositorio, herramienta: str, consulta: Callable[[Repositorio], dict[str, Any]]) -> str:
    """Ejecuta la consulta, la audita y devuelve JSON. Cualquier fallo es un error genérico (el mensaje de PostgreSQL puede llevar
    texto de una reunión). Si no se puede auditar, no sale ningún dato."""
    inicio = time.perf_counter()
    mensaje: str | None = None
    datos: dict[str, Any] = {}
    try:
        datos = await asyncio.to_thread(consulta, repo)
        resultado = "ok"
    except lectura.NoEncontrada:
        resultado, mensaje = "error", "Reunión no encontrada"
    except lectura.ConsultaNoValida as exc:  # mensajes fijos
        resultado, mensaje = "error", str(exc)
    except Exception as exc:  # noqa: BLE001 — solo el tipo, nunca el mensaje
        log.error("herramienta %s: %s", herramienta, type(exc).__name__)
        resultado, mensaje = "error", "Error interno"
    ms = round((time.perf_counter() - inicio) * 1000)
    try:
        await asyncio.to_thread(repo.auditar_mcp, herramienta, resultado, ms)
    except Exception as exc:  # noqa: BLE001
        log.error("auditoría de %s: %s", herramienta, type(exc).__name__)
        raise ToolError("No se pudo auditar la llamada") from None
    if mensaje is not None:
        raise ToolError(mensaje)
    return json.dumps(datos, ensure_ascii=False, separators=(",", ":"), default=str)


def crear_servidor(repo: Repositorio) -> MCPServer:
    limitador: list[anyio.CapacityLimiter] = []  # uno por servidor y dentro de su bucle: se crea en la primera llamada

    async def ejecutar(herramienta: str, consulta: Callable[[Repositorio], dict[str, Any]]) -> str:
        if not limitador:
            limitador.append(anyio.CapacityLimiter(LIMITE_LLAMADAS))
        async with limitador[0]:
            return await _ejecutar(repo, herramienta, consulta)

    servidor = MCPServer(
        "actas",
        instructions=(
            "Actas de las reuniones de socios de Cenit Digital, solo lectura. Los correos no salen y de los teléfonos solo los "
            "3 últimos dígitos. Pagina `leer_acta` con `siguiente`."
        ),
    )

    @servidor.tool(
        name="listar_reuniones",
        description="Lista las últimas reuniones (más recientes primero) con su estado, socios y duración. 25 por página.",
        annotations=SOLO_LECTURA,
        structured_output=False,
    )
    async def listar_reuniones(estado: str | None = None, pagina: int = 1) -> str:
        return await ejecutar("listar_reuniones", lambda r: lectura.listar_reuniones(r, estado, pagina))

    @servidor.tool(
        name="leer_acta",
        description=(
            "Una página de la transcripción de una reunión: quién habló, cuándo y qué dijo. Si `siguiente` no es null, vuelve a "
            "llamar con `desde` = `siguiente`."
        ),
        annotations=SOLO_LECTURA,
        structured_output=False,
    )
    async def leer_acta(reunion_id: str, desde: int = 0) -> str:
        return await ejecutar("leer_acta", lambda r: lectura.leer_acta(r, reunion_id, desde))

    @servidor.tool(
        name="buscar_en_actas",
        description="Busca texto (sin distinguir tildes) en todas las transcripciones. 20 resultados como máximo.",
        annotations=SOLO_LECTURA,
        structured_output=False,
    )
    async def buscar_en_actas(consulta: str) -> str:
        return await ejecutar("buscar_en_actas", lambda r: lectura.buscar_en_actas(r, consulta))

    return servidor


def crear_app_mcp(repo: Repositorio, hosts: tuple[str, ...], token_sha256: str) -> Starlette:
    """La app del puerto del MCP (solo `POST /mcp`). Su lifespan ejecuta el gestor de sesiones del SDK: el servidor de este
    puerto se arranca con `lifespan="on"` (el del panel va apagado)."""
    logging.getLogger("mcp").setLevel(logging.WARNING)
    servidor = crear_servidor(repo)
    servidor.streamable_http_app(  # construye el gestor de sesiones; el enrutado es el nuestro
        streamable_http_path="/mcp",
        json_response=True,
        stateless_http=True,
        max_request_body_size=MAX_CUERPO,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True, allowed_hosts=list(hosts), allowed_origins=[]
        ),
    )
    gestor = servidor.session_manager
    guarda = GuardaMcp(StreamableHTTPASGIApp(gestor), hosts, token_sha256)

    @contextlib.asynccontextmanager
    async def ciclo(_: Starlette) -> AsyncIterator[None]:
        async with gestor.run():
            yield

    return Starlette(routes=[Route("/mcp", endpoint=guarda)], lifespan=ciclo)
