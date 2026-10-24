"""Supervisor del grabador y cliente de la plataforma de transcripción (ADR 0015, decisiones 1 y 6; ADR 0017, D8).

Cada vuelta (cada 5 s):
1. Si hay una grabación activa: la para si se pidió o si llegó al tope de 3 h (@a7); si no, cada minuto mira si cada socio
   conforme publica en la sala y, si no, enciende el aviso (@a25).
2. Si no la hay: atiende la reunión `pedida` más antigua, revalidando los socios conformes (@a6).
3. Envía a la plataforma las reuniones `grabada` (@a8) y consulta las `transcribiendo` hasta `listo`; con el texto guardado,
   borra su audio del tmpfs (@a10).
La purga del audio de más de 7 días y del huérfano corre al arrancar y cada hora.
"""

import os
import shutil
import stat
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import psycopg

from actas.aviso import sin_coincidencia
from actas.base import Repositorio
from actas.conformidad import ConformidadNoValida, validar
from actas.estados import Estado, TransicionNoValida, motivo_parada
from actas.metricas import Metricas
from actas.pistas import Pista, PistasNoValidas, pistas_de
from actas.purga import Audio, a_borrar
from actas.registro import Registro
from actas.sondeo import PLAZO_S, espera, interpretar_creacion, interpretar_estado
from actas.transcripcion import TranscripcionNoValida, segmentos_de

VIGILANCIA_S = 60
PURGA_S = 3600


class Grabador(Protocol):
    def empezar(self) -> None: ...
    def reanudar(self) -> None: ...
    def vistos(self) -> dict[str, list[str]]: ...
    def viva(self) -> bool: ...
    def parar(self) -> bool: ...


class Cliente(Protocol):
    def crear(self, directorio: Path, pistas: list[Pista], referencia: str) -> tuple[int, Any]: ...
    def estado(self, trabajo_id: str) -> tuple[int, Any]: ...


@dataclass
class _Activa:
    rid: str
    socios: tuple[str, ...]
    grabador: Grabador
    inicio_s: float
    ultima_vigilancia_s: float
    parada: str | None = None  # motivo de una parada ya hecha cuyo cambio de estado aún no llegó a la base


@dataclass
class _Sondeo:
    intento: int
    proximo_s: float
    desde_s: float


class Supervisor:
    def __init__(
        self,
        repo: Repositorio,
        plataforma: Cliente,
        nueva_grabacion: Callable[[tuple[str, ...], Path], Grabador],
        raiz: Path,
        registro: Registro,
        metricas: Metricas,
        reloj: Callable[[], float] = time.time,
    ) -> None:
        self.repo, self.plataforma, self.nueva_grabacion = repo, plataforma, nueva_grabacion
        self.raiz, self.log, self.metricas, self.reloj = raiz, registro, metricas, reloj
        self.activa: _Activa | None = None
        self.envios: dict[str, _Sondeo] = {}
        self.sondeos: dict[str, _Sondeo] = {}
        self.ultima_purga_s = 0.0

    # ── Arranque y parada del proceso ─────────────────────────────────────────────────────────────────────────────────

    def arrancar(self) -> None:
        """Una reunión que figura `grabando` al arrancar perdió su supervisor (reinicio del contenedor o del pod). Si Chromium
        sigue vivo con sus páginas, se paran de forma ordenada para no perder lo grabado; en todo caso pasa a `grabada` con el
        motivo `reinicio_supervisor` y se envía lo que haya (sin nada, acaba en `error: pistas`)."""
        for r in self.repo.en_estado(Estado.GRABANDO):
            grabador = self.nueva_grabacion(tuple(r["socios"]), self.raiz / r["id"])
            try:
                grabador.reanudar()
                grabador.parar()
            except Exception as e:  # noqa: BLE001 — Chromium también se reinició: no hay nada que rescatar
                self.log("no se pudo retomar la grabación:", type(e).__name__)
            self.repo.mover(r["id"], Estado.GRABANDO, Estado.GRABADA, motivo="reinicio_supervisor", fin=True)
            self.metricas.sumar("errores_total")  # la grabación se cortó a mitad: que avise
        self.purgar()

    def terminar(self) -> None:
        """SIGTERM: parada ordenada de la grabación activa, para no perder lo grabado."""
        if self.activa:
            self._parar("terminado")

    # ── Una vuelta ────────────────────────────────────────────────────────────────────────────────────────────────────

    def paso(self) -> None:
        if self.activa:
            self._vigilar()
        else:
            self._recuperar_huerfanas()
            self._atender_pedida()
        for r in self.repo.en_estado(Estado.GRABADA):
            self._a_salvo(self._enviar, r, Estado.GRABADA)
        for r in self.repo.en_estado(Estado.TRANSCRIBIENDO):
            self._a_salvo(self._consultar, r, Estado.TRANSCRIBIENDO)
        if self.reloj() - self.ultima_purga_s >= PURGA_S:
            self.purgar()
        self.metricas.por_estado = self.repo.cuenta_por_estado()
        self.metricas.grabaciones_bytes = self._ocupacion()
        self.metricas.ultimo_paso_s = self.reloj()

    def _a_salvo(self, etapa: Callable[[dict[str, Any]], None], r: dict[str, Any], estado: Estado) -> None:
        """Un fallo inesperado con una reunión (una respuesta con forma rara, un dato que la base no admite) la lleva a
        `error` en lugar de tumbar la vuelta entera: si no, se repetiría en cada vuelta y la sonda reiniciaría el contenedor."""
        try:
            etapa(r)
        except psycopg.OperationalError:
            raise  # la base caída un momento: la vuelta siguiente lo reintenta tal cual (sin perder el texto ni el trabajo)
        except Exception as e:  # noqa: BLE001
            self.log("fallo inesperado con una reunión:", type(e).__name__)
            self.envios.pop(r["id"], None)
            self.sondeos.pop(r["id"], None)
            self._error(r["id"], estado, "interno")

    def _recuperar_huerfanas(self) -> None:
        """Sin grabación activa no puede haber ninguna fila `grabando` (p. ej., un error al empezar que no llegó a la base):
        pasa a `grabada` y se envía lo que haya. Sin esto, el índice de una sola grabación activa bloquearía las siguientes."""
        for r in self.repo.en_estado(Estado.GRABANDO):
            self.repo.mover(r["id"], Estado.GRABANDO, Estado.GRABADA, motivo="sin_grabador", fin=True)
            self.metricas.sumar("errores_total")
            self.log("reunión sin grabador recuperada")

    def _atender_pedida(self) -> None:
        r = self.repo.siguiente(Estado.PEDIDA)
        if r is None:
            return
        try:
            peticion = validar(list(r["socios"]), r["texto_version"])
        except ConformidadNoValida:
            self._error(r["id"], Estado.PEDIDA, "conformidad")
            return
        # @a6: cada socio con su fila de conformidad de esta reunión y de la misma versión del texto informativo.
        if self.repo.conformidades(r["id"]) != [(s, peticion.version) for s in peticion.socios]:
            self._error(r["id"], Estado.PEDIDA, "conformidad")
            return
        grabador = self.nueva_grabacion(peticion.socios, self.raiz / r["id"])
        try:
            self.repo.mover(r["id"], Estado.PEDIDA, Estado.GRABANDO, inicio=True)
        except TransicionNoValida:
            return
        try:
            grabador.empezar()
        except Exception as e:  # noqa: BLE001 — Chromium caído o sin respuesta: la reunión no se queda «grabando»
            self.log("no se pudo empezar a grabar:", type(e).__name__)
            self._error(r["id"], Estado.GRABANDO, "grabador")
            return
        ahora = self.reloj()
        self.activa = _Activa(r["id"], peticion.socios, grabador, ahora, ahora)
        self.metricas.grabando, self.metricas.socios_esperados = 1, len(peticion.socios)
        self.log("grabando la reunión", r["id"], "con", len(peticion.socios), "socios")

    def _vigilar(self) -> None:
        assert self.activa is not None
        a = self.activa
        if a.parada:  # la parada ya se hizo; solo falta anotarla en la base
            self._anotar_parada(a)
            return
        r = self.repo.reunion(a.rid)
        motivo = motivo_parada(a.inicio_s, self.reloj(), r["parar_pedido_en"] is not None)
        if motivo is None and not a.grabador.viva():
            # Chromium se reinició o se cayó: sus páginas ya no graban. Se envía lo que se llegó a descargar.
            motivo = "grabador_caido"
            self.metricas.sumar("errores_total")
        if motivo:
            if motivo == "tope_3h":
                self.metricas.sumar("tope_total")
            self._parar(motivo)
            return
        if self.reloj() - a.ultima_vigilancia_s >= VIGILANCIA_S:
            a.ultima_vigilancia_s = self.reloj()
            vistos = a.grabador.vistos()
            faltan = sin_coincidencia(vistos, self.reloj() - a.inicio_s)
            self.metricas.aviso_sin_coincidencia = int(bool(faltan))
            self.metricas.socios_vistos = len(a.socios) - len([s for s in a.socios if s not in vistos.get(s, [])])
            if faltan:
                # Solo el número: los IDs que publican en la sala los elige cada cliente.
                self.log(f"AVISO: {len(faltan)} socio(s) conforme(s) no publican en la sala; ¿entraron sin su enlace con &push?")

    def _parar(self, motivo: str) -> None:
        assert self.activa is not None
        a = self.activa
        try:
            completas = a.grabador.parar()
        except Exception as e:  # noqa: BLE001 — la reunión no puede quedarse «grabando»: se envía lo que haya
            self.log("la parada falló:", type(e).__name__)
            completas = False
        if not completas:
            self.log("alguna descarga no terminó: se envía lo que haya")
        a.parada = motivo
        self._anotar_parada(a)

    def _anotar_parada(self, a: _Activa) -> None:
        """Si la base falla aquí, la grabación sigue «activa» con la parada hecha y la vuelta siguiente lo reintenta."""
        assert a.parada is not None
        self.repo.mover(a.rid, Estado.GRABANDO, Estado.GRABADA, motivo=a.parada, fin=True)
        self.activa = None
        self.metricas.grabando = self.metricas.aviso_sin_coincidencia = 0
        self.metricas.socios_esperados = self.metricas.socios_vistos = 0
        self.log("grabación parada:", a.parada)

    # ── Plataforma de transcripción ───────────────────────────────────────────────────────────────────────────────────

    def _enviar(self, r: dict[str, Any]) -> None:
        rid = r["id"]
        envio = self.envios.get(rid)
        if envio and self.reloj() < envio.proximo_s:
            return
        if envio and self.reloj() - envio.desde_s >= PLAZO_S:
            self.envios.pop(rid, None)
            self._error(rid, Estado.GRABADA, "plazo_envio")
            return
        directorio = self.raiz / rid
        try:
            nombres = (
                sorted(e.name for e in os.scandir(directorio)) if directorio.is_dir() and not directorio.is_symlink() else []
            )
            pistas = pistas_de(nombres, list(r["socios"]))
        except PistasNoValidas as e:
            self.log("pistas no válidas:", e)
            self._error(rid, Estado.GRABADA, "pistas")
            return
        try:
            codigo, cuerpo = self.plataforma.crear(directorio, pistas, rid)
        except PistasNoValidas as e:  # enlaces, FIFOs o ficheros vacíos en el tmpfs: no se sube nada
            self.log("pistas no válidas:", e)
            self._error(rid, Estado.GRABADA, "pistas")
            return
        d = interpretar_creacion(codigo, cuerpo)
        if d.accion == "reintentar":
            n = envio.intento + 1 if envio else 0
            self.envios[rid] = _Sondeo(n, self.reloj() + espera(n), envio.desde_s if envio else self.reloj())
            self.log("la plataforma no respondió:", d.motivo)
            return
        self.envios.pop(rid, None)
        if d.accion == "error":
            self._error(rid, Estado.GRABADA, d.motivo or "plataforma")
            return
        self.repo.mover(rid, Estado.GRABADA, Estado.TRANSCRIBIENDO, trabajo_id=d.trabajo_id)
        self.sondeos[rid] = _Sondeo(0, self.reloj() + espera(0), self.reloj())
        self.log("enviada a la plataforma:", len(pistas), "pistas")

    def _consultar(self, r: dict[str, Any]) -> None:
        rid = r["id"]
        s = self.sondeos.setdefault(rid, _Sondeo(0, self.reloj(), self.reloj()))
        if self.reloj() < s.proximo_s:
            return
        if self.reloj() - s.desde_s >= PLAZO_S:
            self.sondeos.pop(rid, None)
            self._error(rid, Estado.TRANSCRIBIENDO, "plazo")
            return
        codigo, cuerpo = self.plataforma.estado(r["trabajo_id"])
        d = interpretar_estado(codigo, cuerpo)
        if d.accion == "seguir":
            s.intento += 1
            s.proximo_s = self.reloj() + espera(s.intento)
            return
        self.sondeos.pop(rid, None)
        if d.accion == "error":
            self._error(rid, Estado.TRANSCRIBIENDO, d.motivo or "plataforma")
            return
        try:
            segmentos = segmentos_de(cuerpo["transcripcion"], list(r["socios"]))
        except TranscripcionNoValida:
            self._error(rid, Estado.TRANSCRIBIENDO, "transcripcion")
            return
        self.repo.guardar_transcripcion(rid, segmentos)
        self.metricas.sumar("transcritas_total")
        self.log("transcrita:", len(segmentos), "segmentos")
        self._borrar(rid, "transcrita")

    # ── Errores y purga ───────────────────────────────────────────────────────────────────────────────────────────────

    def _error(self, rid: str, desde: Estado, motivo: str) -> None:
        try:
            self.repo.mover(rid, desde, Estado.ERROR, motivo=motivo)
        except TransicionNoValida:
            return
        self.metricas.sumar("errores_total")
        self.log("reunión en error:", motivo)

    def _borrar(self, nombre: str, motivo: str) -> None:
        """Borra una entrada del tmpfs sin seguir enlaces: un enlace se quita, no se recorre su destino."""
        d = self.raiz / nombre
        try:
            st = os.lstat(d)
        except FileNotFoundError:
            return
        ficheros = octetos = 0
        if stat.S_ISDIR(st.st_mode):
            for raiz, dirs, archivos in os.walk(d, followlinks=False):
                for a in archivos + [x for x in dirs if os.path.islink(os.path.join(raiz, x))]:
                    ficheros += 1
                    octetos += os.lstat(os.path.join(raiz, a)).st_size
            shutil.rmtree(d)  # rmtree no sigue los enlaces de dentro (los quita)
        else:
            ficheros, octetos = 1, st.st_size
            d.unlink()
        self.repo.anotar_purga(nombre if _es_reunion(nombre) else None, motivo, ficheros, octetos)

    def _ocupacion(self) -> int:
        """Bytes en el tmpfs, sin seguir enlaces: si se acerca al sizeLimit, el kubelet desalojaría el pod y la grabación."""
        total = 0
        if self.raiz.is_dir():
            for raiz, _, archivos in os.walk(self.raiz, followlinks=False):
                for a in archivos:
                    try:
                        total += os.lstat(os.path.join(raiz, a)).st_size
                    except OSError:
                        pass
        return total

    def purgar(self, mtime: Callable[[Path], float] | None = None) -> None:
        """@a10: borra el audio de las reuniones transcritas, el de más de 7 días (contados desde la base) y lo que no es de
        ninguna reunión. Nunca el de la grabación activa. Un elemento que falla no impide purgar los demás."""
        self.ultima_purga_s = self.reloj()
        if not self.raiz.is_dir():
            return
        entradas = [e for e in os.scandir(self.raiz) if not (self.activa and e.name == self.activa.rid)]
        estados = self.repo.estados_de([e.name for e in entradas])
        leer = mtime or (lambda p: os.lstat(p).st_mtime)
        audios = []
        for e in entradas:
            conocida = estados.get(e.name) if e.is_dir(follow_symlinks=False) else None
            if conocida:
                audios.append(Audio(e.name, conocida[0], conocida[1]))
            else:
                audios.append(Audio(e.name, None, leer(Path(e.path))))
        for nombre, motivo in a_borrar(audios, self.reloj()):
            try:
                self._borrar(nombre, motivo)
                self.log("audio borrado:", motivo)
            except Exception as ex:  # noqa: BLE001
                self.log("no se pudo borrar una entrada del tmpfs:", type(ex).__name__)


def _es_reunion(nombre: str) -> bool:
    import uuid

    try:
        uuid.UUID(nombre)
    except ValueError:
        return False
    return True
