"""Proceso del supervisor: `python -m actas`. Configuración por entorno (KubernetesInfrastructure, kubernetes/apps/actas):

ACTAS_DSN                  libpq del rol actas_app (la contraseña en PGPASSWORD)
ACTAS_DSN_MIGRACIONES      libpq del rol actas_owner, solo para migrar al arrancar (contraseña en ACTAS_MIGRACIONES_PASSWORD)
ACTAS_TOKEN_FICHERO        fichero con el token de servicio de la plataforma (Secret montado solo en este contenedor)
ACTAS_PLATAFORMA           http://transcribir-api.transcribir.svc.cluster.local:8081
ACTAS_CDP                  http://127.0.0.1:9222 (el Chromium del contenedor `chromium`)
ACTAS_GRABACIONES          /grabaciones (tmpfs compartido con `chromium`)
ACTAS_PUERTO_METRICAS      9101
SALA, CLAVE, SALT          la sala (Secret cifrado con SOPS)
"""

import os
import signal
import threading
from pathlib import Path

from actas import base
from actas.cdp import Cdp
from actas.grabador import Grabacion, Sala
from actas.metricas import Metricas, servir
from actas.plataforma import Plataforma
from actas.registro import Registro
from actas.supervisor import Supervisor

VUELTA_S = 5


class _GrabacionConCdp:
    """Una conexión CDP por grabación: se abre al empezar y se cierra al parar."""

    def __init__(self, cdp_url: str, sala: Sala, socios: tuple[str, ...], destino: Path, registro: Registro) -> None:
        self._args = (cdp_url, sala, socios, destino, registro)
        self._g: Grabacion | None = None

    def empezar(self) -> None:
        cdp_url, sala, socios, destino, registro = self._args
        self._g = Grabacion(Cdp(cdp_url, registro), sala, socios, destino, registro)
        self._g.empezar()

    def vistos(self) -> dict[str, list[str]]:
        assert self._g is not None
        return self._g.vistos()

    def viva(self) -> bool:
        return self._g is not None and self._g.cdp.vivo

    def parar(self) -> bool:
        assert self._g is not None
        try:
            return self._g.parar()
        finally:
            self._g.cdp.cerrar()


def cerrar_paginas_de_sala(cdp_url: str, sala: Sala, registro: Registro) -> None:
    """Al arrancar: cierra las páginas de la sala que quedaran abiertas de un supervisor anterior (seguirían grabando)."""
    try:
        cdp = Cdp(cdp_url, registro)
    except Exception as e:  # noqa: BLE001 — Chromium aún arrancando: no hay páginas que cerrar
        registro("Chromium aún no responde:", type(e).__name__)
        return
    try:
        for t in cdp.enviar("Target.getTargets")["targetInfos"]:
            if t.get("type") == "page" and str(t.get("url", "")).startswith(sala.base):
                cdp.cerrar_pagina(t["targetId"])
                registro("cerrada una página de un supervisor anterior")
    finally:
        cdp.cerrar()


def main() -> None:
    e = os.environ
    token = Path(e["ACTAS_TOKEN_FICHERO"]).read_text(encoding="utf-8").strip()
    sala = Sala.del_entorno()
    registro = Registro([sala.clave, token, e.get("PGPASSWORD", ""), e.get("ACTAS_MIGRACIONES_PASSWORD", "")])
    aplicadas = base.migrar(f"{e['ACTAS_DSN_MIGRACIONES']} password={e['ACTAS_MIGRACIONES_PASSWORD']}")
    registro("migraciones aplicadas:", ", ".join(aplicadas) or "ninguna")
    metricas = Metricas()
    servir(metricas, int(e.get("ACTAS_PUERTO_METRICAS", "9101")))
    cdp_url = e.get("ACTAS_CDP", "http://127.0.0.1:9222")
    cerrar_paginas_de_sala(cdp_url, sala, registro)
    sup = Supervisor(
        repo=base.Repositorio(e["ACTAS_DSN"]),
        plataforma=Plataforma(e["ACTAS_PLATAFORMA"], token),
        nueva_grabacion=lambda socios, destino: _GrabacionConCdp(cdp_url, sala, socios, destino, registro),
        raiz=Path(e.get("ACTAS_GRABACIONES", "/grabaciones")),
        registro=registro,
        metricas=metricas,
    )
    fin = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: fin.set())
    signal.signal(signal.SIGINT, lambda *_: fin.set())
    sup.arrancar()
    registro("supervisor en marcha")
    while not fin.is_set():
        try:
            sup.paso()
        except Exception as ex:  # noqa: BLE001 — la base o la plataforma caídas un momento no paran el supervisor
            registro("vuelta fallida:", type(ex).__name__)
        fin.wait(VUELTA_S)
    sup.terminar()
    registro("supervisor parado")


if __name__ == "__main__":
    main()
