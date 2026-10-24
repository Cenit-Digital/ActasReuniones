"""El grabador: una página espectadora de VDO.Ninja v30.2 por socio conforme (anexo de F0 del ADR 0015).

Cada página entra con `&scene&view=<id>&label=<id>&autorecordremote=-64&novideo&relay&tcp`: solo pide el stream de su socio,
graba solo audio (Opus) en cuanto llega el par y lo descarga como `<id>_<ms>.webm` en el directorio de la reunión, que es un
tmpfs compartido con el contenedor `chromium`. La parada es siempre ordenada (`recorder.stop()` y esperar la descarga): una
parada brusca deja un `.crdownload` parcial.
"""

import json
import os
import time
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from actas.aviso import streams_validos
from actas.cdp import Cdp, Evento
from actas.registro import Registro

BASE = "https://reuniones.cenitdigital.es/"
# session.salt del index.html de ReunionesVdoNinja: la de los enlaces de los socios. Con otra, el grabador entra en otra sala.
SAL_SITIO = "reuniones.cenitdigital.es"
ESPERA_DESCARGAS_S = 45

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

PARAR_JS = """(() => {
  let n = 0;
  for (const uuid in session.rpcs) {
    const v = session.rpcs[uuid] && session.rpcs[uuid].videoElement;
    if (v && v.recorder && v.recorder.stop) { try { v.recorder.stop(); n++; } catch (e) {} }
  }
  return n;
})()"""


@dataclass(frozen=True)
class Sala:
    nombre: str
    clave: str
    salt: str = SAL_SITIO
    base: str = BASE

    @classmethod
    def del_entorno(cls) -> "Sala":
        sala = cls(os.environ["SALA"], os.environ["CLAVE"], os.environ.get("SALT") or SAL_SITIO)
        if not sala.clave:
            raise ValueError("CLAVE vacía: la sala quedaría con la contraseña pública del sitio")
        return sala

    def url(self, socio: str) -> str:
        """URL de la página espectadora de `socio`. Lleva la contraseña: nunca se registra sin redactar."""
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


@dataclass
class Grabacion:
    cdp: Cdp
    sala: Sala
    socios: tuple[str, ...]
    destino: Path
    registro: Registro
    paginas: dict[str, tuple[str, str]] = field(default_factory=dict)
    descargas: dict[str, str] = field(default_factory=dict)

    def empezar(self) -> None:
        self.destino.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.cdp.manejadores.append(self._al_evento)
        self.cdp.enviar(
            "Browser.setDownloadBehavior", {"behavior": "allow", "downloadPath": str(self.destino), "eventsEnabled": True}
        )
        for s in self.socios:
            self.paginas[s] = self.cdp.pagina(self.sala.url(s), antes=(VISTOS_JS,), nombre=s)
            self.registro("espectador de", s)

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

    def parar(self) -> bool:
        """Parada ordenada. True si todas las descargas terminaron (`completed`)."""
        for s, (_, ses) in self.paginas.items():
            try:
                self.registro(s, "grabaciones paradas:", self.cdp.evaluar(ses, PARAR_JS, espera=5))
            except Exception as e:  # noqa: BLE001
                self.registro("parar", s, type(e).__name__)
        limite = time.monotonic() + ESPERA_DESCARGAS_S
        while time.monotonic() < limite and "empezada" in self.descargas.values():
            time.sleep(1)
        for t, _ in self.paginas.values():
            self.cdp.cerrar_pagina(t)
        if self._al_evento in self.cdp.manejadores:
            self.cdp.manejadores.remove(self._al_evento)
        return all(v == "completed" for v in self.descargas.values())
