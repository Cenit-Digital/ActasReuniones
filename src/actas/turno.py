"""Un solo supervisor a la vez, también mientras un pod drena: candado consultivo de PostgreSQL.

`Recreate` solo espera al pod viejo en un despliegue o un `rollout restart`. Con `kubectl delete pod` (o un desalojo) el
ReplicaSet crea el sustituto en el acto, sin esperar a que el viejo termine (`podReplacementPolicy` no existe en el
Deployment de k3s v1.36). Sin este candado, el supervisor nuevo se apropiaría en `arrancar()` de la reunión que el viejo sigue
grabando mientras drena (la pasaría a `grabada` sin pistas en su tmpfs) y empezaría las siguientes: dos grabadores.

El supervisor toma el candado antes de tocar nada y lo conserva con su propia conexión mientras vive; al salir el proceso, la
base lo suelta. Esperando, sigue vivo para las sondas (`ultimo_paso_s`) y, si su propio pod empieza a pararse, da el drenaje
por hecho: no tiene nada que drenar. Si la conexión del candado se cayera (un reinicio de la base), otro supervisor que
esperase podría tomarlo; con un solo pod eso solo pasa a la vez que un drenaje.
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
