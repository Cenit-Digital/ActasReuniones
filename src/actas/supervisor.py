"""Supervisor del grabador y cliente de la plataforma de transcripción (ADR 0015, decisiones 1 y 6; ADR 0017, D8).

Cada vuelta (cada 5 s):
1. Si hay una grabación activa: la para si se pidió o si llegó al tope de 3 h (@a7); si no, cada minuto mira si cada socio
   conforme publica en la sala y, si no, enciende el aviso (@a25).
2. Si no la hay: atiende la reunión `pedida` más antigua o, si no hay ninguna, la `programada` cuya hora llegó (@a48, V3),
   revalidando los socios conformes (@a6; en una programada, todos), en la sala de esa reunión (@a46; sin sala, `error` con el
   motivo `sala`). Una programada que pasada su espera no pudo empezar (otra grabación, el supervisor parado) pasa a `error`
   con el motivo `no_empezo`; una que empezó y en su espera no vio publicar a ningún socio conforme se para, se borra su
   audio y queda `cancelada` (`nadie_entro`). Cada grabación para en su tope (`tope_min`, como mucho 3 h).
3. Envía a la plataforma las reuniones `grabada` (@a8) y consulta las `transcribiendo` hasta `listo`; con el texto guardado,
   borra su audio del tmpfs (@a10).
4. Atiende los «Reintentar» del panel (@a57): si el audio sigue en el tmpfs, la reunión vuelve de `error` a `grabada`.
5. Crea la siguiente reunión de cada serie semanal o mensual que ya salió de `programada` (@a53), sin conformidades.
La purga del audio de más de 7 días y del huérfano corre al arrancar y cada hora; la de las reuniones (`purgar_actas`: la
papelera de más de 7 días y lo terminado hace más de 12 meses, @a51 y @a52), en la primera vuelta y una vez al día.

Cada cambio de estado deja su evento en la misma transacción (@a54, Repositorio._mover), y también las respuestas de
transcribir, el aviso de socios y la purga del audio: el historial del panel (V4 de KubernetesInfrastructure#298). Al final de
cada vuelta escribe el latido: Chromium, imagen, tmpfs, la última respuesta de transcribir y qué reuniones conservan audio.
"""

import os
import re
import shutil
import stat
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import psycopg

from actas.aviso import sin_coincidencia
from actas.base import PROGRAMADO, Repositorio
from actas.conformidad import ConformidadNoValida, validar
from actas.estados import TOPE_GRABACION_S, Estado, TransicionNoValida, motivo_parada, nadie_entro
from actas.metricas import Metricas
from actas.pistas import Pista, PistasNoValidas, pistas_de
from actas.planificador import decidir, siguiente
from actas.purga import Audio, a_borrar
from actas.registro import Registro
from actas.salas import SalaNoDisponible
from actas.sondeo import PLAZO_S, espera, interpretar_creacion, interpretar_estado
from actas.transcripcion import TranscripcionNoValida, segmentos_de

VIGILANCIA_S = 60
PURGA_S = 3600
PURGA_ACTAS_S = 24 * 3600
CHROMIUM_S = 30  # cada cuánto se pregunta a Chromium su versión para el latido (una petición HTTP local con 5 s de plazo)
_VERSION = re.compile(r"[A-Za-z0-9._/:-]{1,80}", re.ASCII)  # la forma que admite el CHECK del latido


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
    completas: bool = True  # si todas las descargas terminaron al parar
    faltan: int = 0  # socios conformes que no publican, en el último aviso anotado
    tope_s: int = TOPE_GRABACION_S  # el de la reunión (V3)
    espera_s: int | None = None  # la de una programada: si en ella no publica ningún socio conforme, se cancela
    alguno_visto: bool = False  # algún socio conforme publicó en la sala en alguna vigilancia


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
        sala_de: Callable[[dict[str, Any]], Any],
        nueva_grabacion: Callable[[Any, tuple[str, ...], Path], Grabador],
        raiz: Path,
        registro: Registro,
        metricas: Metricas,
        reloj: Callable[[], float] = time.time,
        chromium: Callable[[], str] | None = None,
        imagen: str = "",
    ) -> None:
        """`chromium`: la versión del navegador (lanza si no responde); `imagen`: la de este proceso (`sha-<commit>`)."""
        self.repo, self.plataforma, self.sala_de, self.nueva_grabacion = repo, plataforma, sala_de, nueva_grabacion
        self.raiz, self.log, self.metricas, self.reloj = raiz, registro, metricas, reloj
        self.chromium, self.imagen = chromium, imagen
        self.activa: _Activa | None = None
        self.envios: dict[str, _Sondeo] = {}
        self.sondeos: dict[str, _Sondeo] = {}
        self.ultima_purga_s = 0.0
        self.ultima_purga_actas_s: float | None = None
        self.version_chromium: str | None = None
        self.ultimo_chromium_s: float | None = None
        self.transcribir: int | None = None  # código de la última respuesta de transcribir (0: sin respuesta)

    # ── Arranque y parada del proceso ─────────────────────────────────────────────────────────────────────────────────

    def arrancar(self) -> None:
        """Una reunión que figura `grabando` al arrancar perdió su supervisor (reinicio del contenedor o del pod). Si Chromium
        sigue vivo con sus páginas, se paran de forma ordenada para no perder lo grabado; en todo caso pasa a `grabada` con el
        motivo `reinicio_supervisor` y se envía lo que haya (sin nada, acaba en `error: pistas`)."""
        for r in self.repo.en_estado(Estado.GRABANDO):
            try:
                sala = self.sala_de(r)
            except SalaNoDisponible:
                sala = None  # pedida antes de V2: se retoma igual, para no perder lo grabado (la parada no usa la sala)
            try:
                grabador = self.nueva_grabacion(sala, tuple(r["socios"]), self.raiz / r["id"])
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
        vencidas = self._caducar_programadas()
        if self.activa:
            self._vigilar()
        else:
            self._recuperar_huerfanas()
            self._atender_siguiente(vencidas)
        self._crear_siguientes()
        self._atender_reintentos()
        for r in self.repo.en_estado(Estado.GRABADA):
            self._a_salvo(self._enviar, r, Estado.GRABADA)
        for r in self.repo.en_estado(Estado.TRANSCRIBIENDO):
            self._a_salvo(self._consultar, r, Estado.TRANSCRIBIENDO)
        if self.reloj() - self.ultima_purga_s >= PURGA_S:
            self.purgar()
        if self.ultima_purga_actas_s is None or self.reloj() - self.ultima_purga_actas_s >= PURGA_ACTAS_S:
            self._purgar_actas()
        self.metricas.por_estado = self.repo.cuenta_por_estado()
        self.metricas.grabaciones_bytes, con_audio = self._tmpfs()
        self.metricas.ultimo_paso_s = self.reloj()
        self._latir(con_audio)

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

    def _caducar_programadas(self) -> list[dict[str, Any]]:
        """@a48: una programada que pasada su espera no pudo empezar ya no se graba (`no_empezo`); la hora es la de la base.
        Devuelve las vencidas que siguen a tiempo, para no volver a pedirlas en la misma vuelta."""
        vencidas = self.repo.vencidas()
        for r in vencidas:
            if decidir(r["retraso_s"], r["espera_min"]) == "tarde":
                self._error(r["id"], Estado.PROGRAMADA, "no_empezo", igual=_programado(r))
        return [r for r in vencidas if decidir(r["retraso_s"], r["espera_min"]) != "tarde"]

    def _atender_siguiente(self, vencidas: list[dict[str, Any]]) -> None:
        """La `pedida` más antigua («Grabar ahora» o actas.sh) o, si no hay, la programada cuya hora llegó (@a48). Una
        programada solo se mueve si lo programado sigue como se leyó (el panel puede modificarla entretanto)."""
        r, desde = self.repo.siguiente(Estado.PEDIDA), Estado.PEDIDA
        if r is None:
            a_tiempo = [v for v in vencidas if decidir(v["retraso_s"], v["espera_min"]) == "empezar"]
            if not a_tiempo:
                return
            r, desde = a_tiempo[0], Estado.PROGRAMADA
        igual = _programado(r) if desde == Estado.PROGRAMADA else None
        try:
            peticion = validar(list(r["socios"]), r["texto_version"])
        except ConformidadNoValida:
            self._error(r["id"], desde, "conformidad", igual=igual)
            return
        # @a6: cada socio con su fila de conformidad de esta reunión y de la misma versión del texto informativo. En una
        # programada, la de todos sus socios (Pablo, 2026-10-27): la siguiente de una serie nace sin ninguna.
        if self.repo.conformidades(r["id"]) != [(s, peticion.version) for s in peticion.socios]:
            self._error(r["id"], desde, "conformidad", igual=igual)
            return
        # @a46: la sala de esta reunión, nunca la de otra. Sin sala o sin poder descifrarla, no se graba.
        try:
            sala = self.sala_de(r)
        except SalaNoDisponible as e:
            self.log("no se graba:", str(e))
            self._error(r["id"], desde, "sala", igual=igual)
            return
        grabador = self.nueva_grabacion(sala, peticion.socios, self.raiz / r["id"])
        try:
            self.repo.mover(r["id"], desde, Estado.GRABANDO, inicio=True, detalle={"socios": len(peticion.socios)}, igual=igual)
        except TransicionNoValida:
            return
        try:
            grabador.empezar()
        except Exception as e:  # noqa: BLE001 — Chromium caído o sin respuesta: la reunión no se queda «grabando»
            self.log("no se pudo empezar a grabar:", type(e).__name__)
            self._error(r["id"], Estado.GRABANDO, "grabador")
            return
        ahora = self.reloj()
        espera_s = r["espera_min"] * 60 if desde == Estado.PROGRAMADA and r.get("espera_min") else None
        self.activa = _Activa(r["id"], peticion.socios, grabador, ahora, ahora, tope_s=r["tope_min"] * 60, espera_s=espera_s)
        self.metricas.grabando, self.metricas.socios_esperados = 1, len(peticion.socios)
        self.log("grabando la reunión", r["id"], "con", len(peticion.socios), "socios")

    def _vigilar(self) -> None:
        assert self.activa is not None
        a = self.activa
        if a.parada:  # la parada ya se hizo; solo falta anotarla en la base
            self._anotar_parada(a)
            return
        r = self.repo.reunion(a.rid)
        motivo = motivo_parada(a.inicio_s, self.reloj(), r["parar_pedido_en"] is not None, a.tope_s)
        if motivo is None and not a.grabador.viva():
            # Chromium se reinició o se cayó: sus páginas ya no graban. Se envía lo que se llegó a descargar.
            motivo = "grabador_caido"
            self.metricas.sumar("errores_total")
        if motivo:
            if motivo in ("tope_3h", "tope"):
                self.metricas.sumar("tope_total")
            self._parar(motivo)
            return
        if self.reloj() - a.ultima_vigilancia_s >= VIGILANCIA_S:
            a.ultima_vigilancia_s = self.reloj()
            vistos = a.grabador.vistos()
            faltan = sin_coincidencia(vistos, self.reloj() - a.inicio_s)
            self.metricas.aviso_sin_coincidencia = int(bool(faltan))
            self.metricas.socios_vistos = len(a.socios) - len([s for s in a.socios if s not in vistos.get(s, [])])
            a.alguno_visto = a.alguno_visto or self.metricas.socios_vistos > 0
            if nadie_entro(self.reloj() - a.inicio_s, a.espera_s, a.alguno_visto):
                self.log("ningún socio conforme entró en la sala en su espera: se cancela")
                self._parar("nadie_entro")
                return
            if len(faltan) != a.faltan:
                a.faltan = len(faltan)
                self.repo.anotar_evento(a.rid, "aviso", {"faltan": a.faltan})
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
        a.parada, a.completas = motivo, bool(completas)
        self._anotar_parada(a)

    def _anotar_parada(self, a: _Activa) -> None:
        """Si la base falla aquí, la grabación sigue «activa» con la parada hecha y la vuelta siguiente lo reintenta. Si no entró
        nadie, la reunión queda cancelada y su audio (sin nadie que hablara) se borra."""
        assert a.parada is not None
        if a.parada == "nadie_entro":
            self.repo.mover(a.rid, Estado.GRABANDO, Estado.CANCELADA, motivo=a.parada, fin=True)
        else:
            self.repo.mover(a.rid, Estado.GRABANDO, Estado.GRABADA, motivo=a.parada, fin=True, detalle={"completas": a.completas})
        self.activa = None
        self.metricas.grabando = self.metricas.aviso_sin_coincidencia = 0
        self.metricas.socios_esperados = self.metricas.socios_vistos = 0
        self.log("grabación parada:", a.parada)
        if a.parada == "nadie_entro":
            try:
                self._borrar(a.rid, "nadie_entro")
            except Exception as e:  # noqa: BLE001 — la purga de cada hora borra el audio de una cancelada
                self.log("no se pudo borrar el audio de una reunión cancelada:", type(e).__name__)

    # ── Series y purga de las reuniones (V3) ──────────────────────────────────────────────────────────────────────────

    def _crear_siguientes(self) -> None:
        """@a53: la siguiente de cada serie que ya salió de `programada`, a la primera fecha que aún no ha pasado. Un fallo con
        una no impide las demás ni tumba la vuelta (se reintenta en la siguiente)."""
        ahora = datetime.fromtimestamp(self.reloj(), UTC)
        for r in self.repo.series_pendientes():
            try:
                para = siguiente(r["programada_para"], r["repetir"], r["repetir_dia"], ahora)
                if para is not None and self.repo.crear_siguiente(r, para):
                    self.log("programada la siguiente reunión de una serie")
            except psycopg.OperationalError:
                raise
            except Exception as e:  # noqa: BLE001
                self.log("no se pudo programar la siguiente de una serie:", type(e).__name__)

    def _purgar_actas(self) -> None:
        """@a51 y @a52: la papelera de más de 7 días y lo terminado hace más de 12 meses, por `purgar_actas` de la base."""
        try:
            borradas = self.repo.purgar_actas()
        except psycopg.OperationalError:
            raise  # la base caída un momento: la vuelta siguiente lo reintenta
        except Exception as e:  # noqa: BLE001 — otro fallo: se reintenta mañana, sin repetirlo en cada vuelta
            self.ultima_purga_actas_s = self.reloj()
            self.log("la purga de las reuniones falló:", type(e).__name__)
            return
        self.ultima_purga_actas_s = self.reloj()
        if borradas:
            self.log("reuniones borradas por la purga:", borradas)

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
        nombres = self._nombres(rid)
        try:
            pistas = pistas_de(nombres, list(r["socios"]))
            codigo, cuerpo = self.plataforma.crear(directorio, pistas, rid)
        except PistasNoValidas as e:  # o enlaces, FIFOs o ficheros vacíos en el tmpfs (plataforma._abrir): no se sube nada
            self.log("pistas no válidas:", e)
            self._error(rid, Estado.GRABADA, "pistas", {"causa": e.causa, "ficheros": len(nombres)})
            return
        d = interpretar_creacion(codigo, cuerpo)
        n = envio.intento + 1 if envio else 0
        if d.accion != "seguir":  # el 201 se anota después de guardar el trabajo: si fallara antes, se volvería a crear
            self._respuesta(rid, "envio", codigo, d.accion, d.motivo, n)
        if d.accion == "reintentar":
            self.envios[rid] = _Sondeo(n, self.reloj() + espera(n), envio.desde_s if envio else self.reloj())
            self.log("la plataforma no respondió:", d.motivo)
            return
        self.envios.pop(rid, None)
        if d.accion == "error":
            self._error(rid, Estado.GRABADA, d.motivo or "plataforma")
            return
        self.repo.mover(rid, Estado.GRABADA, Estado.TRANSCRIBIENDO, trabajo_id=d.trabajo_id, detalle={"pistas": len(pistas)})
        self._respuesta(rid, "envio", codigo, d.accion, d.motivo, n)
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
        if codigo != 200 or d.accion == "error":  # las consultas en curso (un 200 cada minuto) no van al historial
            self._respuesta(rid, "consulta", codigo, d.accion, d.motivo)
        else:
            self.transcribir = codigo
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

    def _respuesta(self, rid: str, tipo: str, codigo: int, accion: str, motivo: str | None, intento: int | None = None) -> None:
        """Una respuesta de transcribir: al historial de la reunión y, para el latido, como la última conocida."""
        self.transcribir = codigo
        detalle: dict[str, Any] = {"codigo": codigo, "accion": accion}
        if intento is not None:
            detalle["intento"] = intento
        if accion == "error" and motivo:
            detalle["motivo"] = motivo
        self.repo.anotar_evento(rid, tipo, detalle)

    # ── Reintentos del panel y latido ──────────────────────────────────────────────────────────────────────────────────

    def _nombres(self, rid: str) -> list[str]:
        directorio = self.raiz / rid
        if not directorio.is_dir() or directorio.is_symlink():
            return []
        return sorted(e.name for e in os.scandir(directorio))

    def _atender_reintentos(self) -> None:
        """@a57: «Reintentar» del panel. Con pistas que se pueden enviar, la reunión vuelve a `grabada` y esta misma vuelta la
        envía; si no (el audio ya se purgó, o nunca lo hubo), la petición se descarta y la reunión sigue en error."""
        for r in self.repo.reintentos_pedidos():
            try:
                self._atender_reintento(r)
            except psycopg.OperationalError:
                raise  # la base caída un momento: la petición sigue ahí y la vuelta siguiente la atiende
            except Exception as e:  # noqa: BLE001 — una petición que falla no puede repetirse en cada vuelta y parar el resto
                self.log("reintento fallido:", type(e).__name__)
                self.repo.atender_reintento(r["id"], reenviar=False, resultado="interno")

    def _atender_reintento(self, r: dict[str, Any]) -> None:
        try:
            pistas_de(self._nombres(r["id"]), list(r["socios"]))
        except PistasNoValidas as e:
            self.repo.atender_reintento(r["id"], reenviar=False, resultado=e.causa)
            self.log("reintento sin pistas que enviar:", e.causa)
            return
        self.envios.pop(r["id"], None)
        self.sondeos.pop(r["id"], None)
        self.repo.atender_reintento(r["id"], reenviar=True, resultado="reenviada")
        self.log("reintento pedido desde el panel")

    def _latir(self, con_audio: list[str]) -> None:
        """El latido del panel (@a56). Un fallo aquí no tumba la vuelta: el panel verá el latido viejo."""
        try:
            self.repo.latir(
                {
                    "chromium": self._version_chromium(),
                    "imagen": self.imagen or None,
                    "grabaciones_bytes": self.metricas.grabaciones_bytes,
                    "grabaciones_total": shutil.disk_usage(self.raiz).total if self.raiz.is_dir() else None,
                    "con_audio": con_audio,
                    "transcribir_codigo": self.transcribir,
                }
            )
        except Exception as e:  # noqa: BLE001
            self.log("latido fallido:", type(e).__name__)

    def _version_chromium(self) -> str | None:
        if self.chromium is None:
            return None
        if self.ultimo_chromium_s is None or self.reloj() - self.ultimo_chromium_s >= CHROMIUM_S:
            self.ultimo_chromium_s = self.reloj()
            try:
                version = self.chromium()
                self.version_chromium = version if _VERSION.fullmatch(version) else "desconocida"
            except Exception:  # noqa: BLE001 — no responde: el latido lo dice
                self.version_chromium = None
        return self.version_chromium

    # ── Errores y purga (sigue) ───────────────────────────────────────────────────────────────────────────────────────

    def _error(
        self,
        rid: str,
        desde: Estado,
        motivo: str,
        detalle: dict[str, Any] | None = None,
        igual: dict[str, Any] | None = None,
    ) -> None:
        try:
            self.repo.mover(rid, desde, Estado.ERROR, motivo=motivo, detalle=detalle, igual=igual)
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

    def _tmpfs(self) -> tuple[int, list[str]]:
        """Bytes en el tmpfs, sin seguir enlaces (si se acerca al sizeLimit, el kubelet desalojaría el pod y la grabación), y las
        reuniones que aún tienen alguna grabación (`.webm` no vacío) para el latido, en el mismo recorrido."""
        total, con_audio = 0, set()
        if self.raiz.is_dir():
            for raiz, _, archivos in os.walk(self.raiz, followlinks=False):
                reunion = Path(raiz).name if Path(raiz).parent == self.raiz and _es_reunion(Path(raiz).name) else None
                for a in archivos:
                    try:
                        st = os.lstat(os.path.join(raiz, a))
                    except OSError:  # la purga lo borró mientras se recorría
                        continue
                    total += st.st_size
                    if reunion and st.st_size and stat.S_ISREG(st.st_mode) and a.endswith(".webm"):
                        con_audio.add(reunion)
        return total, sorted(con_audio)

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


def _programado(r: dict[str, Any]) -> dict[str, Any]:
    return {k: r.get(k) for k in PROGRAMADO}


def _es_reunion(nombre: str) -> bool:
    import uuid

    try:
        uuid.UUID(nombre)
    except ValueError:
        return False
    return True
