"""Supervisor del grabador y cliente de la plataforma de transcripción (ADR 0015, decisiones 1 y 6; ADR 0017, D8).

Cada vuelta (cada 5 s):
1. Si hay una grabación activa: la para si se pidió o si llegó al tope de 3 h (@a7); si no, cada minuto mira si cada socio
   conforme publica en la sala y, si no, enciende el aviso (@a25).
2. Si no la hay: atiende la reunión `pedida` más antigua, revalidando los socios conformes (@a6).
3. Envía a la plataforma las reuniones `grabada` (@a8) y consulta las `transcribiendo` hasta `listo`; con el texto guardado,
   borra su audio del tmpfs (@a10).
La purga del audio de más de 7 días y del huérfano corre al arrancar y cada hora.
"""

import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

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
        """Una reunión que figura `grabando` al arrancar perdió su grabador (reinicio del pod o del contenedor): pasa a
        `error` y su audio, si lo hay, se conserva para `actas.sh reintentar` dentro del plazo de 7 días."""
        for r in self.repo.en_estado(Estado.GRABANDO):
            self._error(r["id"], Estado.GRABANDO, "reinicio_supervisor")
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
            self._atender_pedida()
        for r in self.repo.en_estado(Estado.GRABADA):
            self._enviar(r)
        for r in self.repo.en_estado(Estado.TRANSCRIBIENDO):
            self._consultar(r)
        if self.reloj() - self.ultima_purga_s >= PURGA_S:
            self.purgar()
        self.metricas.por_estado = self.repo.cuenta_por_estado()
        self.metricas.ultimo_paso_s = self.reloj()

    def _atender_pedida(self) -> None:
        r = self.repo.siguiente(Estado.PEDIDA)
        if r is None:
            return
        try:
            peticion = validar(list(r["socios"]), r["texto_version"])
        except ConformidadNoValida:
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
        a, self.activa = self.activa, None
        try:
            completas = a.grabador.parar()
        except Exception as e:  # noqa: BLE001 — la reunión no puede quedarse «grabando»: se envía lo que haya
            self.log("la parada falló:", type(e).__name__)
            completas = False
        self.metricas.grabando = self.metricas.aviso_sin_coincidencia = 0
        self.metricas.socios_esperados = self.metricas.socios_vistos = 0
        if not completas:
            self.log("alguna descarga no terminó: se envía lo que haya")
        self.repo.mover(a.rid, Estado.GRABANDO, Estado.GRABADA, motivo=motivo, fin=True)
        self.log("grabación parada:", motivo)

    # ── Plataforma de transcripción ───────────────────────────────────────────────────────────────────────────────────

    def _enviar(self, r: dict[str, Any]) -> None:
        rid = r["id"]
        envio = self.envios.get(rid)
        if envio and self.reloj() < envio.proximo_s:
            return
        directorio = self.raiz / rid
        try:
            pistas = pistas_de(sorted(p.name for p in directorio.iterdir()) if directorio.is_dir() else [], list(r["socios"]))
        except PistasNoValidas as e:
            self.log("pistas no válidas:", e)
            self._error(rid, Estado.GRABADA, "pistas")
            return
        codigo, cuerpo = self.plataforma.crear(directorio, pistas, rid)
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
        d = self.raiz / nombre
        if not d.exists():
            return
        ficheros = [p for p in d.rglob("*") if p.is_file()]
        octetos = sum(p.stat().st_size for p in ficheros)
        shutil.rmtree(d)
        self.repo.anotar_purga(nombre if _es_reunion(nombre) else None, motivo, len(ficheros), octetos)

    def purgar(self, mtime: Callable[[Path], float] | None = None) -> None:
        """@a10: borra el audio de las reuniones transcritas, el de más de 7 días y el huérfano. Nunca el de la grabación
        activa."""
        self.ultima_purga_s = self.reloj()
        if not self.raiz.is_dir():
            return
        dirs = [d for d in self.raiz.iterdir() if d.is_dir() and not (self.activa and d.name == self.activa.rid)]
        estados = self.repo.estados_de([d.name for d in dirs])
        leer = mtime or (lambda p: p.stat().st_mtime)
        audios = [Audio(d.name, estados.get(d.name), leer(d)) for d in dirs]
        for nombre, motivo in a_borrar(audios, self.reloj()):
            self._borrar(nombre, motivo)
            self.log("audio borrado:", motivo)


def _es_reunion(nombre: str) -> bool:
    import uuid

    try:
        uuid.UUID(nombre)
    except ValueError:
        return False
    return True
