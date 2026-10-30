"""`/metricas` del supervisor (formato de texto de Prometheus), que vmsingle recoge en el puerto 9101. Solo números: ni
nombres, ni streamIDs, ni textos. vmalert las lleva a Telegram (aviso del grabador, errores y tope de 3 h)."""

import threading
import time
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from actas.estados import Estado


class Metricas:
    def __init__(self) -> None:
        self._cerrojo = threading.Lock()
        self.aviso_sin_coincidencia = 0
        self.grabando = 0
        self.socios_esperados = 0
        self.socios_vistos = 0
        self.socios_sin_grabar = 0
        self.errores_total = 0
        self.tope_total = 0
        self.transcritas_total = 0
        self.ultimo_paso_s = 0.0
        self.grabaciones_bytes = 0
        self.drenaje = 0  # 0: normal; 1: el pod se para y no empieza nada nuevo; 2: todo enviado, ya puede pararse
        self.por_estado: dict[str, int] = {}

    def sumar(self, nombre: str, n: int = 1) -> None:
        with self._cerrojo:
            setattr(self, nombre, getattr(self, nombre) + n)

    def texto(self) -> str:
        with self._cerrojo:
            lineas = [
                "# HELP actas_aviso_sin_coincidencia 1 si algún socio conforme no publica en la sala pasado 1 min.",
                "# TYPE actas_aviso_sin_coincidencia gauge",
                f"actas_aviso_sin_coincidencia {self.aviso_sin_coincidencia}",
                "# TYPE actas_grabando gauge",
                f"actas_grabando {self.grabando}",
                "# TYPE actas_socios_esperados gauge",
                f"actas_socios_esperados {self.socios_esperados}",
                "# TYPE actas_socios_vistos gauge",
                f"actas_socios_vistos {self.socios_vistos}",
                "# HELP actas_socios_sin_grabar Socios conformes que publican en la sala pero cuya página no graba.",
                "# TYPE actas_socios_sin_grabar gauge",
                f"actas_socios_sin_grabar {self.socios_sin_grabar}",
                "# TYPE actas_errores_total counter",
                f"actas_errores_total {self.errores_total}",
                "# TYPE actas_tope_total counter",
                f"actas_tope_total {self.tope_total}",
                "# TYPE actas_transcritas_total counter",
                f"actas_transcritas_total {self.transcritas_total}",
                "# HELP actas_ultimo_paso_segundos Momento (epoch) de la última vuelta completa del supervisor.",
                "# TYPE actas_ultimo_paso_segundos gauge",
                f"actas_ultimo_paso_segundos {self.ultimo_paso_s:.0f}",
                "# HELP actas_grabaciones_bytes Ocupación del tmpfs de las grabaciones (sizeLimit 768Mi: al llenarse, desalojo).",
                "# TYPE actas_grabaciones_bytes gauge",
                f"actas_grabaciones_bytes {self.grabaciones_bytes}",
                "# HELP actas_drenaje 0 normal; 1 el pod se para (no empieza grabaciones); 2 audio enviado, puede pararse.",
                "# TYPE actas_drenaje gauge",
                f"actas_drenaje {self.drenaje}",
                "# TYPE actas_reuniones gauge",
            ]
            lineas += [f'actas_reuniones{{estado="{e.value}"}} {self.por_estado.get(e.value, 0)}' for e in Estado]
        return "\n".join(lineas) + "\n"


# /salud (sondas del kubelet): 503 si el bucle del supervisor lleva más de 5 min sin dar una vuelta completa. La vuelta más
# larga prevista es la parada (45 s de descargas) más la subida de las pistas a la plataforma.
SALUD_MAX_S = 300


def servir(metricas: Metricas, puerto: int, reloj: Callable[[], float] = time.time) -> ThreadingHTTPServer:
    class Manejador(BaseHTTPRequestHandler):
        def log_message(self, *a: object) -> None:
            pass

        def do_GET(self) -> None:
            if self.path == "/salud":
                viva = reloj() - metricas.ultimo_paso_s < SALUD_MAX_S
                self.send_response(200 if viva else 503)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            if self.path != "/metricas":
                self.send_error(404)
                return
            datos = metricas.texto().encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4")
            self.send_header("Content-Length", str(len(datos)))
            self.end_headers()
            self.wfile.write(datos)

    srv = ThreadingHTTPServer(("0.0.0.0", puerto), Manejador)  # noqa: S104 (la NetworkPolicy solo deja entrar a vmsingle)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv
