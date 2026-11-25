"""El proceso real del panel con el MCP activado: los dos puertos y la parada con SIGTERM (ADR 0004)."""

import base64
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


def puerto_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def esperar(url: str, cabeceras: dict[str, str] | None = None, metodo: str = "GET") -> int:
    limite = time.monotonic() + 30
    while True:
        try:
            peticion = urllib.request.Request(url, headers=cabeceras or {}, method=metodo)  # noqa: S310 — http local
            with urllib.request.urlopen(peticion, timeout=2) as r:  # noqa: S310
                return int(r.status)
        except urllib.error.HTTPError as e:
            return e.code
        except OSError:
            assert time.monotonic() < limite, f"{url} no responde"
            time.sleep(0.3)


def test_dos_puertos_y_sigterm(tmp_path: Path) -> None:
    clave = tmp_path / "clave"
    clave.write_text(base64.b64encode(os.urandom(32)).decode(), encoding="utf-8")
    proxy = tmp_path / "proxy"
    proxy.write_text("secreto-del-proxy\n", encoding="utf-8")
    panel, mcp = puerto_libre(), puerto_libre()
    entorno = {
        **os.environ,
        "ACTAS_DSN": "postgresql:///nada",
        "ACTAS_SALAS_CLAVE_FICHERO": str(clave),
        "ACTAS_SECRETO_PROXY_FICHERO": str(proxy),
        "ACTAS_PANEL_PUERTO": str(panel),
        "ACTAS_MCP_PUERTO": str(mcp),
        "ACTAS_MCP_TOKEN_SHA256": "ab" * 32,
        "ACTAS_MCP_HOSTS": f"127.0.0.1:{mcp}",
        "PYTHONPATH": str(Path(__file__).resolve().parents[2] / "src"),
    }
    proceso = subprocess.Popen(
        [sys.executable, "-m", "actas.panel"], env=entorno, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
    )
    try:
        assert esperar(f"http://127.0.0.1:{panel}/salud") == 200
        assert esperar(f"http://127.0.0.1:{mcp}/mcp", metodo="GET") == 405  # el MCP, en su puerto
        assert esperar(f"http://127.0.0.1:{mcp}/salud") == 404  # y solo /mcp
        assert esperar(f"http://127.0.0.1:{panel}/mcp", {"Authorization": "Bearer x"}) == 401  # el panel no lo sirve: su guardia
        proceso.send_signal(signal.SIGTERM)
        assert proceso.wait(timeout=20) == 0
        salida = (proceso.stdout.read() if proceso.stdout else b"").decode()
        assert "secreto-del-proxy" not in salida
    finally:
        if proceso.poll() is None:
            proceso.kill()
            proceso.wait()
