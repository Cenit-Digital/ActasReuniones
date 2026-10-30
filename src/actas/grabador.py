"""El grabador: una página espectadora de VDO.Ninja v30.2 por socio conforme (anexo de F0 del ADR 0015).

Cada página entra con `&scene&view=<id>&label=<id>&autorecordremote=-64&novideo&relay&tcp`: solo pide el stream de su socio,
graba solo audio (Opus) en cuanto llega el par y lo descarga como `<id>_<ms>.webm` en el directorio de la reunión, que es un
tmpfs compartido con el contenedor `chromium`. La parada es siempre ordenada (`recorder.stop()` y esperar la descarga): una
parada brusca deja un `.crdownload` parcial.

Un socio que cuelga deja su grabador huérfano (reunión del 2026-10-30): VDO.Ninja quita su par de `session.rpcs` y solo para la
grabación con `srcObject.onended`, que un MediaStream remoto de Chrome no dispara; la descarga se queda abierta. Por eso cada
página anota en `window.__grabadores` cada elemento al que VDO.Ninja da un `recorder` (GRABADORES_JS), la vigilancia para los
que llevan dos vueltas sin par (HUERFANOS_JS) y la parada para todos los anotados. Lo que aun así quede a medias se rescata al
parar: el `.crdownload` de StreamSaver es un webm válido hasta el último trozo escrito.
"""

import json
import os
import time
import urllib.parse
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from actas.aviso import streams_validos
from actas.cdp import Cdp, Evento
from actas.enlaces import BASE, SAL_SITIO
from actas.registro import Registro
from actas.salas import ClaveNoValida, SalaNoDisponible, descifrar

ESPERA_DESCARGAS_S = 45
EBML = bytes.fromhex("1a45dfa3")  # la cabecera de todo webm (Matroska)
A_MEDIAS = ".crdownload"

# Anota los streamIDs que anuncia la sala (lista al entrar y videoaddedtoroom después) para el aviso del grabador.
VISTOS_JS = """(() => {
  window.__vistos = window.__vistos || [];
  const anotar = (id) => {
    if (typeof id === 'string' && /^[A-Za-z0-9_-]{1,64}$/.test(id) && !window.__vistos.includes(id)
        && window.__vistos.length < 50) window.__vistos.push(id);
  };
  const WS = window.WebSocket;
  window.WebSocket = function (...a) {
    const ws = new WS(...a);
    ws.addEventListener('message', (e) => {
      try {
        const m = JSON.parse(e.data);
        if (m.request === 'listing' && Array.isArray(m.list)) m.list.forEach(x => anotar(x && x.streamID));
        if (m.request === 'videoaddedtoroom') anotar(m.streamID);
      } catch (err) {}
    });
    return ws;
  };
  window.WebSocket.prototype = WS.prototype;
  Object.assign(window.WebSocket, {CONNECTING: 0, OPEN: 1, CLOSING: 2, CLOSED: 3});
})()"""

# Sin la sal de la contraseña (session.desaltStreamID): el sufijo deriva de la contraseña y no debe llegar a ningún sitio.
VISTOS_SIN_SAL_JS = """JSON.stringify((typeof session === 'undefined' || !session.desaltStreamID) ? [] :
  [...new Set((window.__vistos || []).map(s => session.desaltStreamID(s)).filter(s => typeof s === 'string'))])"""

# Anota cada elemento al que VDO.Ninja da un `recorder` (recordLocalVideo hace `video.recorder = {}`). Sin tocar nada más: tras
# la primera asignación el elemento tiene su propia propiedad, así que `delete video.recorder` y una grabación nueva (que vuelve
# a pasar por el setter) se comportan como sin el script.
GRABADORES_JS = """(() => {
  window.__grabadores = window.__grabadores || new Set();
  Object.defineProperty(HTMLMediaElement.prototype, 'recorder', {
    configurable: true,
    get() { return undefined; },
    set(valor) {
      window.__grabadores.add(this);
      Object.defineProperty(this, 'recorder', {value: valor, writable: true, configurable: true, enumerable: true});
    },
  });
})()"""

# Los elementos que se graban: los anotados y, para las páginas retomadas sin el script, los de session.rpcs.
_GRABADOS_JS = """const grabados = () => {
    const vs = new Set(window.__grabadores || []);
    const rpcs = (typeof session === 'undefined' || !session.rpcs) ? {} : session.rpcs;
    for (const u in rpcs) { const v = rpcs[u] && rpcs[u].videoElement; if (v) vs.add(v); }
    return vs;
  };
  const activo = (v) => v.recorder && v.recorder.stop && !v.recorder.closing;"""

PARAR_JS = (
    """(() => {
  """
    + _GRABADOS_JS
    + """
  let n = 0;
  for (const v of grabados()) { if (activo(v)) { try { v.recorder.stop(); n++; } catch (e) {} } }
  return n;
})()"""
)

# Para el grabador que lleva dos vigilancias sin par en session.rpcs (el socio colgó): así su descarga termina entera. Si el
# socio vuelve, VDO.Ninja graba en otro `<id>_<ms>.webm`. Devuelve cuántos siguen grabando y cuántos se pararon.
HUERFANOS_JS = (
    """(() => {
  """
    + _GRABADOS_JS
    + """
  const rpcs = (typeof session === 'undefined' || !session.rpcs) ? {} : session.rpcs;
  const conPar = new Set(Object.values(rpcs).map(r => r && r.videoElement).filter(Boolean));
  let grabando = 0, parados = 0;
  for (const v of grabados()) {
    if (!activo(v)) continue;
    if (conPar.has(v)) { v.__huerfano = 0; grabando++; continue; }
    v.__huerfano = (v.__huerfano || 0) + 1;
    if (v.__huerfano < 2) { grabando++; continue; }
    try { v.recorder.stop(); parados++; } catch (e) {}
  }
  return {grabando, parados};
})()"""
)


@dataclass(frozen=True)
class Sala:
    nombre: str
    clave: str
    salt: str = SAL_SITIO
    base: str = BASE

    def url(self, socio: str) -> str:
        """URL de la página espectadora de `socio`. Lleva la contraseña: nunca se registra sin redactar."""
        if not self.nombre or not self.clave:
            raise ValueError("sala sin room o sin contraseña: sería la sala pública del sitio")
        params: list[tuple[str, str | None]] = [
            ("room", self.nombre),
            ("password", self.clave),
            ("salt", self.salt),
            ("relay", None),
            ("tcp", None),
            ("cleanoutput", None),
            ("scene", None),
            ("view", socio),
            ("label", socio),
            ("autorecordremote", "-64"),
            ("novideo", None),
        ]
        return self.base + "?" + "&".join(k if v is None else f"{k}={urllib.parse.quote(v, safe='')}" for k, v in params)


# Solo para retomar al arrancar una grabación sin sala (pedida antes de V2): `reanudar` y `parar` usan la base de las URL, no
# el room ni la contraseña.
SALA_RESCATE = Sala("", "")


def sala_de_reunion(
    r: Mapping[str, Any], cifrada_de: Callable[[str], tuple[str, bytes] | None], maestra: bytes, registro: Registro
) -> Sala:
    """La sala de la reunión (@a46), con su contraseña descifrada y oculta en el registro desde ese momento. Sin sala o sin
    poder descifrarla, SalaNoDisponible: nunca se cae en otra sala (el `envFrom` `actas-sala` de antes de V2)."""
    sid = r.get("sala_id")
    datos = cifrada_de(str(sid)) if sid else None
    if datos is None:
        raise SalaNoDisponible("la reunión no tiene sala")
    room, cifrada = datos
    try:
        clave = descifrar(maestra, room, cifrada)
    except ClaveNoValida:
        raise SalaNoDisponible("la contraseña de la sala no se puede descifrar") from None
    registro.ocultar(clave)
    return Sala(room, clave)


@dataclass
class Grabacion:
    cdp: Cdp
    sala: Sala
    socios: tuple[str, ...]
    destino: Path
    registro: Registro
    paginas: dict[str, tuple[str, str]] = field(default_factory=dict)
    descargas: dict[str, str] = field(default_factory=dict)
    rescatadas: int = 0  # descargas a medias que la última parada rescató

    def _descargar_aqui(self) -> None:
        self.destino.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self._al_evento not in self.cdp.manejadores:
            self.cdp.manejadores.append(self._al_evento)
        self.cdp.enviar(
            "Browser.setDownloadBehavior", {"behavior": "allow", "downloadPath": str(self.destino), "eventsEnabled": True}
        )

    def empezar(self) -> None:
        """Una página por socio. Si una falla, se cierran las ya abiertas: no pueden quedarse grabando sin supervisor."""
        self._descargar_aqui()
        try:
            for s in self.socios:
                self.paginas[s] = self.cdp.pagina(self.sala.url(s), antes=(VISTOS_JS, GRABADORES_JS), nombre=s)
                self.registro("espectador de", s)
        except Exception:
            self._cerrar()
            raise

    def reanudar(self) -> None:
        """Tras reiniciarse el supervisor con Chromium vivo: toma las páginas de la sala que siguen grabando, para pararlas de
        forma ordenada y no perder lo grabado. La etiqueta de cada página está en su URL (`&label=<id>`)."""
        self._descargar_aqui()
        for t in self.cdp.enviar("Target.getTargets")["targetInfos"]:
            url = str(t.get("url", ""))
            if t.get("type") != "page" or not url.startswith(self.sala.base):
                continue
            socio = (urllib.parse.parse_qs(urllib.parse.urlsplit(url).query).get("label") or [""])[0]
            if socio not in self.socios or socio in self.paginas:
                self.cdp.cerrar_pagina(t["targetId"])
                continue
            ses = self.cdp.enviar("Target.attachToTarget", {"targetId": t["targetId"], "flatten": True})["sessionId"]
            self.cdp.nombres[ses] = socio
            self.paginas[socio] = (t["targetId"], ses)
        self.registro("páginas retomadas:", len(self.paginas))

    def _al_evento(self, m: Evento) -> None:
        p: dict[str, Any] = m.get("params", {})
        if m.get("method") == "Browser.downloadWillBegin":
            self.descargas[p["guid"]] = "empezada"
        elif m.get("method") == "Browser.downloadProgress" and p.get("state") != "inProgress":
            self.descargas[p["guid"]] = str(p.get("state"))
            self.registro("descarga", p.get("state"), p.get("receivedBytes"))

    def vistos(self) -> dict[str, list[str]]:
        """Qué streams ve cada página en la sala (sin sal). Una página que no responde cuenta como que no ve a nadie."""
        salida = {}
        for s, (_, ses) in self.paginas.items():
            try:
                salida[s] = streams_validos(json.loads(self.cdp.evaluar(ses, VISTOS_SIN_SAL_JS, espera=10) or "[]"))
            except Exception as e:  # noqa: BLE001
                self.registro(s, "streams de la sala:", type(e).__name__)
                salida[s] = []
        return salida

    def vigilar(self) -> dict[str, int]:
        """Cuántos grabadores siguen grabando en cada página, tras parar los huérfanos (HUERFANOS_JS). Una página que no
        responde cuenta como que no graba nada."""
        salida = {}
        for s, (_, ses) in self.paginas.items():
            try:
                r = self.cdp.evaluar(ses, HUERFANOS_JS, espera=10) or {}
                salida[s] = int(r.get("grabando", 0))
                if r.get("parados"):
                    self.registro(s, "grabaciones huérfanas paradas:", int(r["parados"]))
            except Exception as e:  # noqa: BLE001
                self.registro(s, "vigilar grabadores:", type(e).__name__)
                salida[s] = 0
        return salida

    def parar(self) -> bool:
        """Parada ordenada. True solo si hubo grabaciones y todas sus descargas terminaron (`completed`).

        VDO.Ninja graba con StreamSaver: la descarga empieza (downloadWillBegin) al empezar a grabar y termina al parar
        (downloadProgress completed). Se espera, con el plazo de ESPERA_DESCARGAS_S, a que haya al menos una descarga por
        grabación parada y a que ninguna siga a medias. Sin ninguna descarga no es un éxito."""
        paradas = 0
        for s, (_, ses) in self.paginas.items():
            try:
                n = self.cdp.evaluar(ses, PARAR_JS, espera=5)
                paradas += n if isinstance(n, int) else 0
                self.registro(s, "grabaciones paradas:", n)
            except Exception as e:  # noqa: BLE001
                self.registro("parar", s, type(e).__name__)
        limite = time.monotonic() + ESPERA_DESCARGAS_S
        while time.monotonic() < limite and (len(self.descargas) < paradas or "empezada" in self.descargas.values()):
            time.sleep(0.5)
        rescatadas = self._rescatar()
        self._cerrar()
        self._quitar_a_medias(rescatadas)
        self.rescatadas = len(rescatadas)
        return bool(self.descargas) and len(self.descargas) >= paradas and all(v == "completed" for v in self.descargas.values())

    def _rescatar(self) -> list[Path]:
        """Las descargas a medias (`<x>.webm.crdownload`) con contenido webm y sin su `<x>.webm`, enlazadas a ese nombre."""
        rescatadas: list[Path] = []
        try:
            candidatas = sorted(self.destino.glob("*.webm" + A_MEDIAS))
        except OSError:
            return rescatadas
        for p in candidatas:
            final = p.with_name(p.name.removesuffix(A_MEDIAS))
            try:
                if p.is_symlink() or not p.is_file() or final.exists() or final.is_symlink():
                    continue
                with p.open("rb") as f:
                    if f.read(len(EBML)) != EBML:
                        continue
                os.link(p, final)
                rescatadas.append(final)
            except OSError as e:
                self.registro("no se pudo rescatar una descarga a medias:", type(e).__name__)
        if rescatadas:
            self.registro("descargas a medias rescatadas:", len(rescatadas))
        return rescatadas

    def _quitar_a_medias(self, rescatadas: list[Path]) -> None:
        """Quita el nombre `.crdownload` de lo rescatado (si sigue siendo el mismo fichero): así no cuenta como perdido."""
        for final in rescatadas:
            a_medias = final.with_name(final.name + A_MEDIAS)
            try:
                if a_medias.exists() and os.path.samefile(a_medias, final):
                    a_medias.unlink()
            except OSError as e:
                self.registro("no se pudo quitar una descarga rescatada:", type(e).__name__)

    def _cerrar(self) -> None:
        """Cierra las páginas y deja de aceptar descargas: fuera de una grabación, nada escribe en /grabaciones."""
        objetivos = {t for t, _ in self.paginas.values()}
        # Chromium responde «success» a closeTarget pero no cierra una página que aún está navegando (medido con el headless
        # shell 1248): se repite hasta que ya no está, como mucho 5 s.
        limite = time.monotonic() + 5
        while objetivos and time.monotonic() < limite:
            for t in objetivos:
                self.cdp.cerrar_pagina(t)
            time.sleep(0.2)
            try:
                vivos = {t["targetId"] for t in self.cdp.enviar("Target.getTargets", espera=5)["targetInfos"]}
            except Exception:  # noqa: BLE001
                break
            objetivos &= vivos
        if objetivos:
            self.registro("páginas que no se cerraron:", len(objetivos))
        try:
            self.cdp.enviar("Browser.setDownloadBehavior", {"behavior": "deny"}, espera=10)
        except Exception as e:  # noqa: BLE001
            self.registro("no se pudieron denegar las descargas:", type(e).__name__)
        if self._al_evento in self.cdp.manejadores:
            self.cdp.manejadores.remove(self._al_evento)
