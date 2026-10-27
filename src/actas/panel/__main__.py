"""Proceso del panel: `python -m actas.panel`. Configuración por entorno (KubernetesInfrastructure, kubernetes/apps/actas):

ACTAS_DSN                 libpq del rol actas_panel (la contraseña en PGPASSWORD); las fechas, en hora de Madrid
ACTAS_SOCIOS_FICHERO      JSON con los socios conocidos, [{"id": "pablo", "nombre": "Pablo"}, …] (ConfigMap montado)
ACTAS_TEXTO_VERSION       la versión del texto informativo de «Grabar»; obligatoria si la imagen trae más de uno
ACTAS_SECRETO_PROXY_FICHERO  fichero con el secreto que la ruta de Traefik añade en X-Actas-Proxy (Secret cifrado con SOPS)
ACTAS_ORIGEN              el origen del panel para la defensa CSRF (por defecto https://actas.cenitdigital.es)
ACTAS_PANEL_PUERTO        8080
ACTAS_PANEL_CONCURRENCIA  16 peticiones en curso a la vez, sin contar /salud (503 por encima; las cuenta el panel, no uvicorn)
ACTAS_PANEL_CONEXIONES    4 consultas a la base a la vez, una conexión cada una: por debajo del CONNECTION LIMIT de actas_panel

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
from actas.formulario import socios_conocidos, version_vigente
from actas.panel import cargar_textos, crear_app
from actas.registro import Registro

ORIGEN = "https://actas.cenitdigital.es"
# Fechas en hora de Madrid y ninguna consulta de más de 5 s (una búsqueda solo negativa recorre todos los segmentos).
AJUSTES = {"TimeZone": "Europe/Madrid", "statement_timeout": "5s"}


def preparar(e: Mapping[str, str]) -> tuple[ASGIApp, Registro]:
    secreto = Path(e["ACTAS_SECRETO_PROXY_FICHERO"]).read_text(encoding="utf-8").strip()
    if not secreto:
        raise ValueError("secreto del proxy vacío")
    registro = Registro([e.get("PGPASSWORD", ""), secreto])
    socios = socios_conocidos(Path(e["ACTAS_SOCIOS_FICHERO"]).read_text(encoding="utf-8"))
    textos = cargar_textos()
    vigente = version_vigente(textos, e.get("ACTAS_TEXTO_VERSION"))
    repo = Repositorio(e["ACTAS_DSN"], ajustes=AJUSTES)
    conexiones = int(e.get("ACTAS_PANEL_CONEXIONES", "4"))
    concurrencia = int(e.get("ACTAS_PANEL_CONCURRENCIA", "16"))
    origen = e.get("ACTAS_ORIGEN", ORIGEN)
    app = crear_app(repo, socios, textos, vigente, origen, secreto, registro, conexiones, concurrencia)
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
