"""Cliente CDP por WebSocket del Chromium del contenedor `chromium` del mismo pod (127.0.0.1:9222).

Chromium va en su propio contenedor, sin ningún Secret: el token de la plataforma y las credenciales de la base viven solo en
el contenedor del supervisor (plan de F1, KubernetesInfrastructure#223). La contraseña de la sala sí llega a Chromium, dentro
de la URL de cada página (Page.navigate): es la única forma de entrar en la sala, y nunca se registra.
"""

import json
import threading
import urllib.request
from collections.abc import Callable
from typing import Any

from websockets.exceptions import ConnectionClosed
from websockets.sync.client import ClientConnection, connect

from actas.registro import Registro

Evento = dict[str, Any]


class ChromiumNoDisponible(RuntimeError):
    pass


class Cdp:
    def __init__(self, base: str, registro: Registro) -> None:
        try:
            with urllib.request.urlopen(f"{base}/json/version", timeout=5) as r:  # noqa: S310 (solo http://127.0.0.1)
                ws = json.load(r)["webSocketDebuggerUrl"]
        except (OSError, ValueError, KeyError) as e:
            raise ChromiumNoDisponible(type(e).__name__) from e
        self._log = registro
        self._ws: ClientConnection = connect(ws, max_size=64 << 20, open_timeout=10)
        self._id = 0
        self._esperas: dict[int, tuple[threading.Event, list[Evento]]] = {}
        self._cerrojo = threading.Lock()
        self.manejadores: list[Callable[[Evento], None]] = []
        self.nombres: dict[str, str] = {}  # sesión CDP -> socio, para los registros
        self.vivo = True
        threading.Thread(target=self._leer, daemon=True).start()

    def _leer(self) -> None:
        try:
            for crudo in self._ws:
                try:
                    self._despachar(json.loads(crudo))
                except Exception as e:  # noqa: BLE001 — un mensaje raro o un manejador roto no deben matar el lector
                    self._log("lector CDP:", type(e).__name__)
        except ConnectionClosed:
            pass
        self.vivo = False
        for i in list(self._esperas):
            ev = self._esperas.pop(i, None)
            if ev:
                ev[1].append({"error": "Chromium ha terminado"})
                ev[0].set()

    def _despachar(self, m: Evento) -> None:
        if "id" in m:
            ev = self._esperas.pop(m["id"], None)
            if ev:
                ev[1].append(m)
                ev[0].set()
            return
        metodo = m.get("method")
        if metodo == "Page.javascriptDialogOpening":
            # Un diálogo nativo congela la página. Solo se acepta un alert: un confirm o un prompt pediría consentir algo.
            p = m["params"]
            self._log("diálogo", p.get("type"), "en", self.nombres.get(m.get("sessionId", ""), "?"))
            threading.Thread(
                target=self._cerrar_dialogo, args=(m.get("sessionId"), p.get("type") == "alert"), daemon=True
            ).start()
        elif metodo in ("Inspector.targetCrashed", "Inspector.detached"):
            self._log("página caída:", self.nombres.get(m.get("sessionId", ""), "?"), metodo)
        for h in list(self.manejadores):
            h(m)

    def _cerrar_dialogo(self, sesion: str | None, aceptar: bool) -> None:
        try:
            self.enviar("Page.handleJavaScriptDialog", {"accept": aceptar}, sesion=sesion, espera=10)
        except Exception as e:  # noqa: BLE001
            self._log("no se pudo cerrar el diálogo:", type(e).__name__)

    def enviar(self, metodo: str, params: dict[str, Any] | None = None, sesion: str | None = None, espera: float = 30) -> Any:
        with self._cerrojo:
            self._id += 1
            i = self._id
        ev: tuple[threading.Event, list[Evento]] = (threading.Event(), [])
        self._esperas[i] = ev
        if not self.vivo:
            self._esperas.pop(i, None)
            raise ChromiumNoDisponible("Chromium ha terminado")
        m: Evento = {"id": i, "method": metodo, "params": params or {}}
        if sesion:
            m["sessionId"] = sesion
        try:
            self._ws.send(json.dumps(m))
        except ConnectionClosed as e:
            self._esperas.pop(i, None)
            raise ChromiumNoDisponible("conexión CDP cerrada") from e
        if not ev[0].wait(espera):
            self._esperas.pop(i, None)
            raise TimeoutError(metodo)
        r = ev[1][0]
        if "error" in r:
            # El error de CDP puede repetir la URL (con la contraseña): solo el método llega al registro.
            raise RuntimeError(f"{metodo}: error de CDP")
        return r.get("result", {})

    def pagina(self, url: str, antes: tuple[str, ...] = (), nombre: str = "") -> tuple[str, str]:
        """(targetId, sessionId) de una página nueva que navega a `url` tras instalar los scripts `antes`."""
        t = self.enviar("Target.createTarget", {"url": "about:blank"})["targetId"]
        s = self.enviar("Target.attachToTarget", {"targetId": t, "flatten": True})["sessionId"]
        self.nombres[s] = nombre or t
        self.enviar("Page.enable", sesion=s)
        self.enviar("Inspector.enable", sesion=s)
        for js in antes:
            self.enviar("Page.addScriptToEvaluateOnNewDocument", {"source": js}, sesion=s)
        self.enviar("Page.navigate", {"url": url}, sesion=s)
        return t, s

    def evaluar(self, sesion: str, expr: str, espera: float = 30) -> Any:
        r = self.enviar(
            "Runtime.evaluate", {"expression": expr, "awaitPromise": True, "returnByValue": True}, sesion=sesion, espera=espera
        )
        return r.get("result", {}).get("value")

    def cerrar_pagina(self, target: str) -> None:
        try:
            self.enviar("Target.closeTarget", {"targetId": target}, espera=10)
        except Exception as e:  # noqa: BLE001
            self._log("no se pudo cerrar una página:", type(e).__name__)

    def cerrar(self) -> None:
        self._ws.close()
