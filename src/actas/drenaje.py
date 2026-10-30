"""Parada ordenada del pod sin perder audio: `python -m actas.drenaje`, el preStop del contenedor supervisor.

El audio vive en un tmpfs (emptyDir `Memory`, ADR 0015, enmienda de F1, decisión 1) que desaparece con el pod. Un despliegue,
un `rollout restart` o un `kubectl delete pod` a mitad de una reunión la perdían: el SIGTERM paraba la grabación, pero el
proceso salía antes de subir las pistas. Ahora el kubelet ejecuta antes este preStop, que pide el drenaje con una marca en el
/tmp del contenedor y espera (dentro del terminationGracePeriodSeconds del pod) a que el supervisor lo dé por hecho:
- el supervisor sigue dando vueltas como siempre, pero ya no empieza ninguna grabación nueva;
- la grabación en curso sigue hasta que acaba sola (Parar, el tope o el grabador caído): un despliegue no corta la reunión;
- cuando no queda grabación activa ni ninguna reunión `grabada` sin enviar, anota la marca de hecho y el preStop termina.
Una vez enviada (`transcribiendo`), la plataforma tiene su copia; el pod nuevo sigue consultándola hasta `listo`.

Si el supervisor no responde en /salud (bucle colgado: es la sonda de vida la que lo mata), no hay nada que esperar y sale
enseguida, para no retrasar el reinicio. El contenedor chromium tiene su propio preStop (KubernetesInfrastructure,
kubernetes/apps/actas): sigue vivo mientras `actas_grabando` sea 1.
"""

import os
import sys
import time
import urllib.request
from collections.abc import Callable, Mapping
from pathlib import Path

ESPERA_S = 5


class Drenaje:
    """Las dos marcas, en el /tmp del contenedor supervisor (un emptyDir propio: chromium no lo ve)."""

    def __init__(self, directorio: Path) -> None:
        self._pedido = directorio / "actas-drenar"
        self._hecho = directorio / "actas-drenado"

    def pedir(self) -> None:
        self._pedido.touch()

    def pedido(self) -> bool:
        return self._pedido.exists()

    def anotar_hecho(self) -> None:
        self._hecho.touch()

    def hecho(self) -> bool:
        return self._hecho.exists()

    def limpiar(self) -> None:
        """Al arrancar el proceso: unas marcas de antes son de un reinicio del contenedor (la sonda de vida), no de una parada
        del pod (en un pod que termina, el kubelet no reinicia contenedores). Sin esto, no volvería a grabar nunca."""
        self._pedido.unlink(missing_ok=True)
        self._hecho.unlink(missing_ok=True)


def del_entorno(e: Mapping[str, str]) -> Drenaje:
    return Drenaje(Path(e.get("ACTAS_DRENAJE", "/tmp")))  # noqa: S108 (el /tmp del contenedor es un emptyDir propio)


def esperar(drenaje: Drenaje, salud: Callable[[], bool], dormir: Callable[[float], None] = time.sleep) -> str:
    """Pide el drenaje y espera a que el supervisor lo dé por hecho. Devuelve por qué terminó."""
    if not salud():
        return "sin_supervisor"
    drenaje.pedir()
    while not drenaje.hecho():
        if not salud():
            return "sin_supervisor"
        dormir(ESPERA_S)
    return "drenado"


def salud_local(puerto: int) -> Callable[[], bool]:
    def salud() -> bool:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{puerto}/salud", timeout=5) as r:  # noqa: S310 (URL fija)
                return bool(r.status == 200)
        except OSError:
            return False

    return salud


def main() -> None:
    e = os.environ
    motivo = esperar(del_entorno(e), salud_local(int(e.get("ACTAS_PUERTO_METRICAS", "9101"))))
    print(f"drenaje: {motivo}", file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
