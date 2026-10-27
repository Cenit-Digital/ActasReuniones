"""El supervisor solo habla con el CDP del Chromium de su pod: 127.0.0.1 y el puerto configurado."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from actas.cdp import Cdp, ChromiumNoDisponible, esperar_chromium, version_chromium
from actas.registro import Registro


def servidor_version(ws, navegador=None):
    class M(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            version = {"webSocketDebuggerUrl": ws.format(puerto=self.server.server_address[1])}
            if navegador:
                version["Browser"] = navegador
            datos = json.dumps(version).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(datos)))
            self.end_headers()
            self.wfile.write(datos)

    srv = ThreadingHTTPServer(("127.0.0.1", 0), M)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


@pytest.mark.parametrize(
    "ws",
    [
        "ws://evil.example:{puerto}/devtools/browser/x",
        "ws://127.0.0.1:1/devtools/browser/x",
        "wss://127.0.0.1:{puerto}/devtools/browser/x",
        "ws://127.0.0.1:{puerto}/otra/cosa",
    ],
)
def test_rechaza_un_websocket_que_no_es_el_del_mismo_chromium(ws):
    srv = servidor_version(ws)
    try:
        with pytest.raises(ChromiumNoDisponible, match="WebSocket"):
            Cdp(f"http://127.0.0.1:{srv.server_address[1]}", Registro())
    finally:
        srv.shutdown()


def test_esperar_chromium_se_rinde_al_plazo():
    with pytest.raises(ChromiumNoDisponible):
        esperar_chromium("http://127.0.0.1:9", plazo_s=1.5, intervalo_s=0.2)


def test_esperar_chromium_vuelve_en_cuanto_responde():
    srv = servidor_version("ws://127.0.0.1:{puerto}/devtools/browser/x")
    try:
        esperar_chromium(f"http://127.0.0.1:{srv.server_address[1]}", plazo_s=5, intervalo_s=0.1)
    finally:
        srv.shutdown()


def test_version_de_chromium_para_el_latido():
    srv = servidor_version("ws://127.0.0.1:{puerto}/devtools/browser/x", "HeadlessChrome/141.0.7390.37")
    try:
        assert version_chromium(f"http://127.0.0.1:{srv.server_address[1]}") == "HeadlessChrome/141.0.7390.37"
    finally:
        srv.shutdown()


def test_version_de_chromium_sin_chromium_lanza():
    with pytest.raises(ChromiumNoDisponible):
        version_chromium("http://127.0.0.1:9")
