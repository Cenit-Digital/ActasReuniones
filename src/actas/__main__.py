"""Proceso del supervisor: `python -m actas`. Configuración por entorno (KubernetesInfrastructure, kubernetes/apps/actas):

ACTAS_DSN                  libpq del rol actas_app (la contraseña en PGPASSWORD)
ACTAS_DSN_MIGRACIONES      libpq del rol actas_owner, solo para migrar al arrancar (contraseña en ACTAS_MIGRACIONES_PASSWORD)
ACTAS_TOKEN_FICHERO        fichero con el token de servicio de la plataforma (Secret montado solo en este contenedor)
ACTAS_PLATAFORMA           http://transcribir-api.transcribir.svc.cluster.local:8081
ACTAS_CDP                  http://127.0.0.1:9222 (el Chromium del contenedor `chromium`)
ACTAS_GRABACIONES          /grabaciones (tmpfs compartido con `chromium`)
ACTAS_PUERTO_METRICAS      9101
ACTAS_SALAS_CLAVE_FICHERO  fichero con la clave de las contraseñas de las salas, 32 bytes en base64 (Secret `actas-salas-clave`,
                           SOPS). Cada reunión se graba en su sala (V2 de KubernetesInfrastructure#298, @a46); `SALA`, `CLAVE` y
                           `SALT` (el `envFrom` `actas-sala` de antes) ya no se leen.
ACTAS_REVISION             el commit de la imagen (lo pone el Dockerfile al construirla): va al latido como `sha-<commit>`
"""

import os
import signal
import sys
import threading
from collections.abc import Mapping
from pathlib import Path

from actas.base import Repositorio
from actas.cdp import Cdp, esperar_chromium, version_chromium
from actas.enlaces import BASE
from actas.grabador import SALA_RESCATE, Grabacion, Sala, Vigilancia, sala_de_reunion
from actas.metricas import Metricas, servir
from actas.plataforma import Plataforma
from actas.registro import Registro
from actas.salas import clave_maestra
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
        try:
            self._g.reanudar()
        except Exception:
            self._g.cdp.cerrar()
            raise

    def vistos(self) -> dict[str, list[str]]:
        assert self._g is not None
        return self._g.vistos()

    def vigilar(self) -> dict[str, Vigilancia]:
        assert self._g is not None
        return self._g.vigilar()

    @property
    def rescatadas(self) -> int:
        return self._g.rescatadas if self._g is not None else 0

    def viva(self) -> bool:
        return self._g is not None and self._g.cdp.vivo

    def parar(self) -> bool:
        assert self._g is not None
        try:
            return self._g.parar()
        finally:
            self._g.cdp.cerrar()


def nueva_grabacion(
    cdp_url: str, sala: Sala | None, socios: tuple[str, ...], destino: Path, registro: Registro
) -> _GrabacionConCdp:
    """Sin sala (una grabación pedida antes de V2 que se retoma al arrancar), SALA_RESCATE: retomar y parar solo usan la base
    de las URL, y Sala.url se niega a abrir una página sin room ni contraseña."""
    return _GrabacionConCdp(cdp_url, sala or SALA_RESCATE, socios, destino, registro)


def cerrar_paginas_de_vdo_ninja(cdp_url: str, registro: Registro) -> None:
    """Al arrancar, tras el rescate: cierra las páginas de VDO.Ninja que aún queden abiertas, de cualquier sala (seguirían
    grabando), y deniega las descargas hasta la próxima grabación."""
    cdp = Cdp(cdp_url, registro)  # sin Chromium no se sigue: podría haber páginas grabando sin control
    try:
        for t in cdp.enviar("Target.getTargets")["targetInfos"]:
            if t.get("type") == "page" and str(t.get("url", "")).startswith(BASE):
                cdp.cerrar_pagina(t["targetId"])
                registro("cerrada una página de un supervisor anterior")
        cdp.enviar("Browser.setDownloadBehavior", {"behavior": "deny"})
    finally:
        cdp.cerrar()


def registro_del_entorno(e: Mapping[str, str], token: str, maestra: str = "") -> Registro:
    """El registro del proceso, que redacta el token, las contraseñas de la base y la clave de las salas; y `CLAVE` mientras
    el `envFrom` `actas-sala` siga en el pod (hasta el segundo PR de despliegue de V2). Las contraseñas de las salas se añaden
    al descifrarlas (grabador.sala_de_reunion)."""
    return Registro(
        [e.get("CLAVE", ""), token, e.get("PGPASSWORD", ""), e.get("ACTAS_MIGRACIONES_PASSWORD", ""), maestra.strip()]
    )


def main() -> None:
    e = os.environ
    token = Path(e["ACTAS_TOKEN_FICHERO"]).read_text(encoding="utf-8").strip()
    texto_maestra = Path(e["ACTAS_SALAS_CLAVE_FICHERO"]).read_text(encoding="utf-8")
    maestra = clave_maestra(texto_maestra)
    registro = registro_del_entorno(e, token, texto_maestra)
    # Los mismos secretos que redacta el registro, también las contraseñas de sala que añade al grabar: ningún evento los lleva
    # (@a55). La lista se comparte, no se copia.
    repo = Repositorio(e["ACTAS_DSN"], secretos=registro.secretos)
    metricas = Metricas()
    servir(metricas, int(e.get("ACTAS_PUERTO_METRICAS", "9101")))
    cdp_url = e.get("ACTAS_CDP", "http://127.0.0.1:9222")
    revision = e.get("ACTAS_REVISION", "")
    sup = Supervisor(
        repo=repo,
        plataforma=Plataforma(e["ACTAS_PLATAFORMA"], token),
        sala_de=lambda r: sala_de_reunion(r, repo.cifrada_de_sala, maestra, registro),
        nueva_grabacion=lambda sala, socios, destino: nueva_grabacion(cdp_url, sala, socios, destino, registro),
        raiz=Path(e.get("ACTAS_GRABACIONES", "/grabaciones")),
        registro=registro,
        metricas=metricas,
        chromium=lambda: version_chromium(cdp_url),
        imagen=f"sha-{revision}" if revision else "",
    )
    fin = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: fin.set())
    signal.signal(signal.SIGINT, lambda *_: fin.set())
    # Antes de atender nada: Chromium tiene que responder para rescatar la grabación en curso y cerrar lo que sobre (si no
    # responde en 5 min, el proceso sale y el contenedor se reinicia; avisa ActasSupervisorParado).
    esperar_chromium(cdp_url)
    sup.arrancar()  # rescata la grabación en curso, si la había, antes de cerrar lo que sobre
    cerrar_paginas_de_vdo_ninja(cdp_url, registro)
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
