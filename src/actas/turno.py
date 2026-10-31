"""Un solo supervisor a la vez, también mientras un pod drena: candado consultivo de PostgreSQL.

`Recreate` solo espera al pod viejo en un despliegue o un `rollout restart`. Con `kubectl delete pod` (o un desalojo) el
ReplicaSet crea el sustituto en el acto, sin esperar a que el viejo termine (`podReplacementPolicy` no existe en el
Deployment de k3s v1.36). Sin este candado, el supervisor nuevo se apropiaría en `arrancar()` de la reunión que el viejo sigue
grabando mientras drena (la pasaría a `grabada` sin pistas en su tmpfs) y empezaría las siguientes: dos grabadores.

El supervisor toma el candado antes de tocar nada y lo conserva con su propia conexión mientras vive; al salir el proceso, la
base lo suelta. Esperando, sigue vivo para las sondas (`ultimo_paso_s`) y, si su propio pod empieza a pararse, da el drenaje
por hecho: no tiene nada que drenar. La base suelta el candado si se cae su conexión (un reinicio de PostgreSQL, un corte):
`conservar()`, en cada vuelta, lo comprueba y lo vuelve a tomar; si otro supervisor lo tiene ya, este deja de empezar
grabaciones (drena) y sale en cuanto no tiene nada que enviar.
"""

import threading
import time
from collections.abc import Callable
from typing import Any

import psycopg

from actas.drenaje import Drenaje
from actas.metricas import Metricas
from actas.registro import Registro

CLAVE = 0x6163746173  # «actas»: los candados consultivos son por base de datos
ESPERA_S = 5


def esperar_turno(
    conectar: Callable[[], psycopg.Connection[Any]],
    drenaje: Drenaje,
    metricas: Metricas,
    registro: Registro,
    fin: threading.Event,
    reloj: Callable[[], float] = time.time,
    clave: int = CLAVE,
) -> psycopg.Connection[Any] | None:
    """La conexión que tiene el candado (hay que conservarla mientras viva el proceso), o None si hay que salir."""
    c = conectar()
    avisado = False
    while not c.execute("SELECT pg_try_advisory_lock(%s)", (clave,)).fetchone()[0]:  # type: ignore[index]
        if not avisado:
            registro("otro supervisor sigue en marcha (su pod se está parando): se espera a que termine")
            avisado = True
        if drenaje.pedido():  # este pod también se para: no hay nada que drenar
            drenaje.anotar_hecho()
            c.close()
            return None
        metricas.ultimo_paso_s = reloj()  # esperando, no colgado: que la sonda de vida no lo reinicie
        if fin.wait(ESPERA_S):
            c.close()
            return None
    if avisado:
        registro("el supervisor anterior terminó: este toma el relevo")
    return c


class Turno:
    """El candado del supervisor en marcha: hay que conservarlo (y comprobarlo) mientras viva el proceso."""

    def __init__(
        self, conectar: Callable[[], psycopg.Connection[Any]], c: psycopg.Connection[Any], registro: Registro, clave: int = CLAVE
    ) -> None:
        self._conectar, self._c, self.log, self._clave = conectar, c, registro, clave
        self.perdido = False

    def conservar(self) -> bool:
        """True si este proceso sigue teniendo el candado. Si su conexión se cayó, reconecta y lo vuelve a pedir; perdido una
        vez, no se reintenta: el proceso drena y sale, y al arrancar de nuevo espera su turno."""
        if self.perdido:
            return False
        try:
            self._c.execute("SELECT 1")
            return True
        except psycopg.Error:
            pass
        try:
            self._c.close()
            self._c = self._conectar()
            if self._c.execute("SELECT pg_try_advisory_lock(%s)", (self._clave,)).fetchone()[0]:  # type: ignore[index]
                self.log("candado del supervisor recuperado tras perder su conexión")
                return True
        except psycopg.Error:
            return True  # la base sigue caída: se reintenta en la vuelta siguiente
        self.perdido = True
        self.log("AVISO: otro supervisor tiene el candado: este no empieza nada nuevo y sale al acabar lo suyo")
        return False

    def soltar(self) -> None:
        self._c.close()
