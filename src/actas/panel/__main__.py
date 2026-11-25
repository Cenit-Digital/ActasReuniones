"""Proceso del panel: `python -m actas.panel`. Configuración por entorno (KubernetesInfrastructure, kubernetes/apps/actas):

ACTAS_DSN                 libpq del rol actas_panel (la contraseña en PGPASSWORD); las fechas, en hora de Madrid
ACTAS_SALAS_CLAVE_FICHERO fichero con la clave de las contraseñas de las salas, 32 bytes en base64 (Secret `actas-salas-clave`,
                          SOPS). Los socios están en la base desde V2 (KubernetesInfrastructure#298): ACTAS_SOCIOS_FICHERO ya
                          no se lee.
ACTAS_TEXTO_VERSION       la versión del texto informativo de «Grabar»; obligatoria si la imagen trae más de uno
ACTAS_SECRETO_PROXY_FICHERO  fichero con el secreto que la ruta de Traefik añade en X-Actas-Proxy (Secret cifrado con SOPS)
ACTAS_ORIGEN              el origen del panel para la defensa CSRF (por defecto https://actas.cenitdigital.es)
ACTAS_PANEL_PUERTO        8080
ACTAS_PANEL_CONCURRENCIA  16 peticiones en curso a la vez, sin contar /salud (503 por encima; las cuenta el panel, no uvicorn)
ACTAS_MCP_TOKEN_SHA256    SHA-256 (hexadecimal) del Bearer del MCP de solo lectura (ADR 0004); lo emite `actas.mcp_token`
ACTAS_MCP_HOSTS           los Host admitidos en el MCP, con puerto, separados por comas. Sin el hash o sin los hosts, no hay MCP
ACTAS_MCP_PUERTO          8081, el del MCP (el 8080 es el de Traefik y no lo sirve)
ACTAS_PANEL_CONEXIONES    4 consultas a la base a la vez, una conexión cada una: por debajo del CONNECTION LIMIT de actas_panel

uvicorn 0.54.0, docs/settings.md: `--no-access-log` («Disable access log only»), `--no-server-header`, `--no-proxy-headers` (el
panel no usa la IP de origen) y `--limit-concurrency` («Maximum number of concurrent connections or tasks to allow, before
issuing HTTP 503 responses»), aquí con sus equivalentes de `uvicorn.Config`.
"""

import asyncio
import contextlib
import os
import signal
import sys
from collections.abc import Generator, Mapping, Sequence
from pathlib import Path
from typing import Any

import uvicorn
from starlette.types import ASGIApp

from actas.base import Repositorio
from actas.formulario import version_vigente
from actas.mcp_servidor import crear_app_mcp
from actas.panel import cargar_textos, crear_app
from actas.registro import Registro
from actas.salas import clave_maestra

ORIGEN = "https://actas.cenitdigital.es"
# Fechas en hora de Madrid y ninguna consulta de más de 5 s (una búsqueda solo negativa recorre todos los segmentos).
AJUSTES = {"TimeZone": "Europe/Madrid", "statement_timeout": "5s"}


def preparar(e: Mapping[str, str]) -> tuple[ASGIApp, Registro]:
    secreto = Path(e["ACTAS_SECRETO_PROXY_FICHERO"]).read_text(encoding="utf-8").strip()
    if not secreto:
        raise ValueError("secreto del proxy vacío")
    texto_maestra = Path(e["ACTAS_SALAS_CLAVE_FICHERO"]).read_text(encoding="utf-8")
    maestra = clave_maestra(texto_maestra)
    registro = Registro([e.get("PGPASSWORD", ""), secreto, texto_maestra.strip()])
    textos = cargar_textos()
    vigente = version_vigente(textos, e.get("ACTAS_TEXTO_VERSION"))
    repo = Repositorio(e["ACTAS_DSN"], ajustes=AJUSTES)
    conexiones = int(e.get("ACTAS_PANEL_CONEXIONES", "4"))
    concurrencia = int(e.get("ACTAS_PANEL_CONCURRENCIA", "16"))
    origen = e.get("ACTAS_ORIGEN", ORIGEN)
    app = crear_app(repo, maestra, textos, vigente, origen, secreto, registro, conexiones, concurrencia)
    return app, registro


def configuracion(app: Any, e: Mapping[str, str]) -> uvicorn.Config:
    return uvicorn.Config(
        app,
        host="0.0.0.0",  # noqa: S104 — dentro del pod; la NetworkPolicy solo deja entrar a Traefik
        port=int(e.get("ACTAS_PANEL_PUERTO", "8080")),
        access_log=False,
        server_header=False,
        proxy_headers=False,
        # Sin `limit_concurrency`: cuenta las conexiones keep-alive ociosas y dejaba sin respuesta a la sonda de vida. El tope de
        # peticiones lo pone el panel (actas.panel._Guardia), sin contar /salud.
        lifespan="off",
    )


class Servidor(uvicorn.Server):
    """uvicorn instala sus manejadores de señales al servir y el segundo pisaría al primero: aquí no los instala nadie y un único
    manejador de SIGTERM y SIGINT (`servir`) pide la parada ordenada a los dos."""

    @contextlib.contextmanager
    def capture_signals(self) -> Generator[None, None, None]:
        yield


def servidor_mcp(e: Mapping[str, str]) -> Servidor | None:
    """El servidor del puerto del MCP, o None sin hash o sin hosts. Va aparte del panel y sin su guardia (Traefik no llega)."""
    sha = (e.get("ACTAS_MCP_TOKEN_SHA256") or "").strip().lower()
    hosts = tuple(h.strip().lower() for h in (e.get("ACTAS_MCP_HOSTS") or "").split(",") if h.strip())
    if not sha or not hosts:
        return None
    return Servidor(
        uvicorn.Config(
            crear_app_mcp(Repositorio(e["ACTAS_DSN"], ajustes=AJUSTES), hosts, sha),
            host="0.0.0.0",  # noqa: S104 — dentro del pod; la NetworkPolicy solo deja entrar a Hermes
            port=int(e.get("ACTAS_MCP_PUERTO", "8081")),
            access_log=False,
            server_header=False,
            proxy_headers=False,
            lifespan="on",  # ejecuta el gestor de sesiones del SDK
            log_config=None,
        )
    )


async def servir(servidores: Sequence[Servidor]) -> None:
    """Los servidores en un mismo bucle: SIGTERM los para a todos y si uno acaba (o falla), para a los demás."""
    bucle = asyncio.get_running_loop()

    def parar() -> None:
        for servidor in servidores:
            servidor.should_exit = True

    for senal in (signal.SIGTERM, signal.SIGINT):
        bucle.add_signal_handler(senal, parar)

    async def uno(servidor: Servidor) -> None:
        try:
            await servidor.serve()
        finally:
            parar()

    resultados = await asyncio.gather(*(uno(s) for s in servidores), return_exceptions=True)
    for r in resultados:
        if isinstance(r, BaseException):
            raise r


def main() -> None:
    app, registro = preparar(os.environ)
    registro("panel en marcha")
    servidores = [Servidor(configuracion(app, os.environ))]
    mcp = servidor_mcp(os.environ)
    if mcp is not None:
        servidores.append(mcp)
        registro("mcp activado")
    asyncio.run(servir(servidores))


def principal() -> None:
    """Sin trazas: un error al arrancar puede llevar datos de conexión en su mensaje."""
    try:
        main()
    except Exception as e:  # noqa: BLE001
        print(f"el panel no pudo arrancar: {type(e).__name__}", file=sys.stderr, flush=True)
        sys.exit(1)


if __name__ == "__main__":
    principal()
