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
import sys
import threading
from pathlib import Path

from actas import base
from actas.cdp import Cdp, esperar_chromium
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
        try:
            self._g.empezar()
        except Exception:
            self._g.cdp.cerrar()
            raise

    def reanudar(self) -> None:
        cdp_url, sala, socios, destino, registro = self._args
        self._g = Grabacion(Cdp(cdp_url, registro), sala, socios, destino, registro)
        self._g.reanudar()

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
    """Al arrancar, tras el rescate: cierra las páginas de la sala que aún queden abiertas (seguirían grabando) y deniega las
    descargas hasta la próxima grabación."""
    cdp = Cdp(cdp_url, registro)  # sin Chromium no se sigue: podría haber páginas grabando sin control
    try:
        for t in cdp.enviar("Target.getTargets")["targetInfos"]:
            if t.get("type") == "page" and str(t.get("url", "")).startswith(sala.base):
                cdp.cerrar_pagina(t["targetId"])
                registro("cerrada una página de un supervisor anterior")
        cdp.enviar("Browser.setDownloadBehavior", {"behavior": "deny"})
    finally:
        cdp.cerrar()


def main() -> None:
    e = os.environ
    token = Path(e["ACTAS_TOKEN_FICHERO"]).read_text(encoding="utf-8").strip()
    sala = Sala.del_entorno()
    registro = Registro([sala.clave, token, e.get("PGPASSWORD", ""), e.get("ACTAS_MIGRACIONES_PASSWORD", "")])
    aplicadas = base.migrar(e["ACTAS_DSN_MIGRACIONES"], password=e["ACTAS_MIGRACIONES_PASSWORD"])
    registro("migraciones aplicadas:", ", ".join(aplicadas) or "ninguna")
    metricas = Metricas()
    servir(metricas, int(e.get("ACTAS_PUERTO_METRICAS", "9101")))
    cdp_url = e.get("ACTAS_CDP", "http://127.0.0.1:9222")
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
    # Antes de atender nada: Chromium tiene que responder para rescatar la grabación en curso y cerrar lo que sobre (si no
    # responde en 5 min, el proceso sale y el contenedor se reinicia; avisa ActasSupervisorParado).
    esperar_chromium(cdp_url)
    sup.arrancar()  # rescata la grabación en curso, si la había, antes de cerrar lo que sobre
    cerrar_paginas_de_sala(cdp_url, sala, registro)
    registro("supervisor en marcha")
    while not fin.is_set():
        try:
            sup.paso()
        except Exception as ex:  # noqa: BLE001 — la base o la plataforma caídas un momento no paran el supervisor
            registro("vuelta fallida:", type(ex).__name__)
        fin.wait(VUELTA_S)
    sup.terminar()
    registro("supervisor parado")


def principal() -> None:
    """Sin trazas: un error al arrancar (p. ej., de la base) puede llevar datos de conexión en su mensaje."""
    try:
        main()
    except Exception as e:  # noqa: BLE001
        print(f"el supervisor no pudo arrancar: {type(e).__name__}", file=sys.stderr, flush=True)
        sys.exit(1)


if __name__ == "__main__":
    principal()
