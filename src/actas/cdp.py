"""Cliente CDP por WebSocket del Chromium del contenedor `chromium` del mismo pod (127.0.0.1:9222).

Chromium va en su propio contenedor, sin ningún Secret: el token de la plataforma y las credenciales de la base viven solo en
el contenedor del supervisor (plan de F1, KubernetesInfrastructure#223). La contraseña de la sala sí llega a Chromium, dentro
de la URL de cada página (Page.navigate): es la única forma de entrar en la sala, y nunca se registra.
"""

import json
import threading
import time
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any

from websockets.exceptions import ConnectionClosed
from websockets.sync.client import ClientConnection, connect

from actas.registro import Registro

Evento = dict[str, Any]


class ChromiumNoDisponible(RuntimeError):
    pass


MAX_MENSAJE = 8 << 20  # las respuestas de CDP que se usan son pequeñas; el contenedor tiene 256Mi


def _version(base: str) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(f"{base}/json/version", timeout=5) as r:  # noqa: S310 (solo http://127.0.0.1)
            datos = json.loads(r.read(MAX_MENSAJE))
    except (OSError, ValueError) as e:
        raise ChromiumNoDisponible(type(e).__name__) from e
    if not isinstance(datos, dict):
        raise ChromiumNoDisponible("respuesta de /json/version no válida")
    return datos


def version_chromium(base: str) -> str:
    """El campo `Browser` de /json/version (p. ej., `HeadlessChrome/141.0.7390.37`) para el latido. Lanza si no responde."""
    return str(_version(base).get("Browser", ""))


def esperar_chromium(base: str, plazo_s: float = 300, intervalo_s: float = 5) -> None:
    """Al arrancar el pod, Chromium puede tardar: hasta que responde no se puede rescatar ni cerrar ninguna página."""
    limite = time.monotonic() + plazo_s
    while True:
        try:
            _version(base)
            return
        except ChromiumNoDisponible:
            if time.monotonic() >= limite:
                raise
            time.sleep(intervalo_s)


class Cdp:
    def __init__(self, base: str, registro: Registro) -> None:
        ws = _version(base).get("webSocketDebuggerUrl")
        # Solo el WebSocket del mismo Chromium (mismo host y puerto que `base`, ruta del navegador): nunca otro destino.
        esperado = urllib.parse.urlsplit(base)
        if not isinstance(ws, str):
            raise ChromiumNoDisponible("WebSocket de CDP inesperado")
        partes = urllib.parse.urlsplit(ws)
        if (
            partes.scheme != "ws"
            or (partes.hostname, partes.port) != (esperado.hostname, esperado.port)
            or not partes.path.startswith("/devtools/browser/")
        ):
            raise ChromiumNoDisponible("WebSocket de CDP inesperado")
        self._log = registro
        # Se entra en el gestor de contexto a mano: la conexión vive lo que dura la grabación y se cierra en cerrar().
        self._conexion = connect(ws, max_size=MAX_MENSAJE, open_timeout=10)
        self._ws: ClientConnection = self._conexion.__enter__()
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
        self._conexion.__exit__(None, None, None)
