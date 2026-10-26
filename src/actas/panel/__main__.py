"""Proceso del panel: `python -m actas.panel`. Configuración por entorno (KubernetesInfrastructure, kubernetes/apps/actas):

ACTAS_DSN                 libpq del rol actas_panel (la contraseña en PGPASSWORD; PGTZ=Europe/Madrid para las fechas)
ACTAS_SOCIOS_FICHERO      JSON con los socios conocidos, [{"id": "pablo", "nombre": "Pablo"}, …] (ConfigMap montado)
ACTAS_ORIGEN              el origen del panel para la defensa CSRF (por defecto https://actas.cenitdigital.es)
ACTAS_PANEL_PUERTO        8080
ACTAS_PANEL_CONCURRENCIA  4: como mucho las conexiones que admite actas_panel (una por petición)

uvicorn 0.54.0, docs/settings.md: `--no-access-log` («Disable access log only»), `--no-server-header`, `--no-proxy-headers` (el
panel no usa la IP de origen) y `--limit-concurrency` («Maximum number of concurrent connections or tasks to allow, before
issuing HTTP 503 responses»), aquí con sus equivalentes de `uvicorn.Config`.
"""

import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import uvicorn
from starlette.types import ASGIApp

from actas.base import Repositorio
from actas.formulario import socios_conocidos
from actas.panel import cargar_textos, crear_app
from actas.registro import Registro

ORIGEN = "https://actas.cenitdigital.es"


def preparar(e: Mapping[str, str]) -> tuple[ASGIApp, Registro]:
    registro = Registro([e.get("PGPASSWORD", "")])
    socios = socios_conocidos(Path(e["ACTAS_SOCIOS_FICHERO"]).read_text(encoding="utf-8"))
    app = crear_app(Repositorio(e["ACTAS_DSN"]), socios, cargar_textos(), e.get("ACTAS_ORIGEN", ORIGEN), registro)
    return app, registro


def configuracion(app: Any, e: Mapping[str, str]) -> uvicorn.Config:
    return uvicorn.Config(
        app,
        host="0.0.0.0",  # noqa: S104 — dentro del pod; la NetworkPolicy solo deja entrar a Traefik
        port=int(e.get("ACTAS_PANEL_PUERTO", "8080")),
        access_log=False,
        server_header=False,
        proxy_headers=False,
        limit_concurrency=int(e.get("ACTAS_PANEL_CONCURRENCIA", "4")),
        lifespan="off",
    )


def main() -> None:
    app, registro = preparar(os.environ)
    registro("panel en marcha")
    uvicorn.Server(configuracion(app, os.environ)).run()


def principal() -> None:
    """Sin trazas: un error al arrancar puede llevar datos de conexión en su mensaje."""
    try:
        main()
    except Exception as e:  # noqa: BLE001
        print(f"el panel no pudo arrancar: {type(e).__name__}", file=sys.stderr, flush=True)
        sys.exit(1)


if __name__ == "__main__":
    principal()
