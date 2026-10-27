"""Reuniones programadas (V3 de KubernetesInfrastructure#298, ADR 0023 decisión 5): el formulario de programar del panel, cuándo
empieza una reunión `programada` (@a48) y la fecha de la siguiente de una serie (@a53).

- Las horas se escriben y se repiten en la de Madrid: una reunión semanal de las 17:30 sigue a las 17:30 tras el cambio de hora.
  Una hora que no existe (el salto de marzo) se rechaza; una que pasa dos veces (la vuelta de octubre) es la primera (`fold=0`,
  PEP 495). Las fechas salen siempre en UTC.
- «Cada mes» va el mismo día y, si el mes no lo tiene, su último día. El día original (`reuniones.repetir_dia`) se guarda aparte
  para no correrse: 31 de enero → 28 de febrero → 31 de marzo.
- La hora de empezar la decide el reloj de la base (el supervisor le pide el retraso de cada reunión); aquí solo se decide qué
  hacer con él.
"""

import calendar
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from actas.conformidad import Peticion
from actas.formulario import FormularioNoValido

MADRID = ZoneInfo("Europe/Madrid")
TOPES_MIN = (60, 120, 180)  # «Parar como mucho a las» del diseño; 180 es el tope de 3 h de F1 (@a7)
ESPERAS_MIN = (15, 30, 60)  # «Si no entra nadie»
REPETIR = ("no", "semanal", "mensual")
TOPE_TITULO = 120
PLAZO_MAXIMO = timedelta(days=366)  # programar como mucho a un año vista
_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")
_HORA_LOCAL = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?", re.ASCII)  # lo que envía un <input type="datetime-local">


@dataclass(frozen=True)
class Programacion:
    titulo: str | None
    sala_id: str
    para: datetime  # en UTC
    tope_min: int
    repetir: str
    espera_min: int
    socios: tuple[str, ...]
    version: str


def _es_uuid(valor: str) -> bool:
    try:
        uuid.UUID(valor)
    except ValueError:
        return False
    return True


def titulo(valor: str) -> str | None:
    valor = valor.strip()
    if not valor:
        return None
    if len(valor) > TOPE_TITULO or _CONTROL.search(valor):
        raise FormularioNoValido(f"el título, como mucho {TOPE_TITULO} caracteres y sin saltos de línea")
    return valor


def tope(valor: str) -> int:
    if valor not in {str(t) for t in TOPES_MIN}:
        raise FormularioNoValido("el tope es de 1, 2 o 3 horas")
    return int(valor)


def hora_local(valor: str) -> datetime:
    """La hora de Madrid de un <input type="datetime-local">, en UTC."""
    if not _HORA_LOCAL.fullmatch(valor):
        raise FormularioNoValido("la fecha y la hora, como AAAA-MM-DDTHH:MM")
    try:
        ingenua = datetime.fromisoformat(valor)
    except ValueError:
        raise FormularioNoValido("esa fecha no existe") from None
    local = ingenua.replace(tzinfo=MADRID)
    if local.astimezone(UTC).astimezone(MADRID).replace(tzinfo=None) != ingenua:
        raise FormularioNoValido("esa hora no existe en Madrid por el cambio de hora")
    return local.astimezone(UTC)


def validar_programacion(
    titulo_: str,
    sala_id: str,
    cuando: str,
    tope_: str,
    repetir: str,
    espera: str,
    peticion: Peticion,
    ahora: datetime,
) -> Programacion:
    """`peticion`: los socios conformes y la versión del texto, ya validados como en «Grabar» (formulario.validar_grabar)."""
    if not _es_uuid(sala_id):
        raise FormularioNoValido("elige la sala en la que se graba")
    para = hora_local(cuando)
    if para <= ahora:
        raise FormularioNoValido("la hora de empezar ya ha pasado")
    if para > ahora + PLAZO_MAXIMO:
        raise FormularioNoValido("como mucho, a un año vista")
    if repetir not in REPETIR:
        raise FormularioNoValido("repetir: no, cada semana o cada mes")
    if espera not in {str(e) for e in ESPERAS_MIN}:
        raise FormularioNoValido("la espera es de 15, 30 o 60 minutos")
    return Programacion(titulo(titulo_), sala_id, para, tope(tope_), repetir, int(espera), peticion.socios, peticion.version)


def decidir(retraso_s: float, espera_min: int) -> Literal["esperar", "empezar", "tarde"]:
    """`retraso_s`: segundos desde su hora (negativo, aún no ha llegado). Pasada su espera sin poder empezar (otra grabación en
    marcha o el supervisor parado), ya no se graba: llega tarde."""
    if retraso_s < 0:
        return "esperar"
    if retraso_s <= espera_min * 60:
        return "empezar"
    return "tarde"


def _dia_del_mes(anio: int, mes: int, dia: int) -> date:
    return date(anio, mes, min(dia, calendar.monthrange(anio, mes)[1]))


def siguiente(para: datetime, repetir: str, dia: int | None, ahora: datetime, hora: time | None = None) -> datetime | None:
    """La primera fecha de la serie posterior a `para` que aún no ha llegado (si el supervisor estuvo parado, se saltan las que
    pasaron). `dia`: el día original de una serie mensual; `hora`: la hora de Madrid original de la serie
    (`reuniones.repetir_hora`). Una que cae en el salto de marzo va a la hora siguiente (fold=0), y con la hora original la
    siguiente vuelve a la suya en vez de quedarse corrida. None si no se repite."""
    if repetir == "no":
        return None
    if repetir not in REPETIR:
        raise ValueError("repetición desconocida")
    local = para.astimezone(MADRID)
    hora = hora or local.time()
    fecha = local.date()
    dia = dia or fecha.day
    while True:
        if repetir == "semanal":
            fecha += timedelta(days=7)
        else:
            anio, mes0 = divmod(fecha.year * 12 + fecha.month, 12)  # el mes siguiente, con enero = 0
            fecha = _dia_del_mes(anio, mes0 + 1, dia)
        candidata = datetime.combine(fecha, hora, tzinfo=MADRID).astimezone(UTC)
        if candidata > ahora:
            return candidata
