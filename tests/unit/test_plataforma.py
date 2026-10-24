"""@a8 y @a24: el cliente de la API interna de la plataforma (ADR 0017, D8), contra un servidor falso en el propio proceso.
La subida va en flujo: el cuerpo multipart no se arma en memoria (una pista de 3 h pesa ~110 MB)."""

import json
import os
import threading
from email.parser import BytesParser
from email.policy import HTTP
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from actas.pistas import Pista, PistasNoValidas
from actas.plataforma import Plataforma


class Falso(BaseHTTPRequestHandler):
    recibido: dict = {}
    respuesta = (201, {"id": "1b4e28ba-2fa1-11d2-883f-0016d3cca427"})

    def log_message(self, *a):  # sin ruido en la salida de pytest
        pass

    def _responder(self):
        codigo, cuerpo = type(self).respuesta
        datos = json.dumps(cuerpo).encode()
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(datos)))
        self.end_headers()
        self.wfile.write(datos)

    def do_POST(self):
        n = int(self.headers["Content-Length"])
        cuerpo = self.rfile.read(n)
        msg = BytesParser(policy=HTTP).parsebytes(
            b"Content-Type: " + self.headers["Content-Type"].encode() + b"\r\n\r\n" + cuerpo
        )
        partes = [
            (
                p.get_param("name", header="content-disposition"),
                p.get_filename(),
                p.get_content_type(),
                p.get_payload(decode=True),
            )
            for p in msg.iter_parts()
        ]
        type(self).recibido = {
            "ruta": self.path,
            "auth": self.headers["Authorization"],
            "partes": partes,
            "chunked": self.headers.get("Transfer-Encoding"),
        }
        self._responder()

    def do_GET(self):
        type(self).recibido = {"ruta": self.path, "auth": self.headers["Authorization"]}
        self._responder()


@pytest.fixture
def servidor():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Falso)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def test_crear_trabajo_multipart_con_una_pista_por_fichero(servidor, tmp_path):
    (tmp_path / "socioa_1000.webm").write_bytes(b"A" * 70000)
    (tmp_path / "sociob_1500.webm").write_bytes(b"B" * 10)
    pistas = [Pista("socioa_1000.webm", "socioa", 1000, 0), Pista("sociob_1500.webm", "sociob", 1500, 500)]
    Falso.respuesta = (201, {"id": "1b4e28ba-2fa1-11d2-883f-0016d3cca427"})
    codigo, cuerpo = Plataforma(servidor, "tok3n").crear(tmp_path, pistas, "r-uuid")
    assert (codigo, cuerpo["id"]) == (201, "1b4e28ba-2fa1-11d2-883f-0016d3cca427")
    r = Falso.recibido
    assert r["ruta"] == "/api/interno/actas/trabajos" and r["auth"] == "Bearer tok3n" and r["chunked"] is None
    assert r["partes"] == [
        ("referencia", None, "text/plain", b"r-uuid"),
        ("idioma", None, "text/plain", b"es"),
        ("pistas", "socioa_1000.webm", "audio/webm", b"A" * 70000),
        ("interlocutores", None, "text/plain", b"socioa"),
        ("desfases_ms", None, "text/plain", b"0"),
        ("pistas", "sociob_1500.webm", "audio/webm", b"B" * 10),
        ("interlocutores", None, "text/plain", b"sociob"),
        ("desfases_ms", None, "text/plain", b"500"),
    ]


def test_estado_con_token(servidor):
    Falso.respuesta = (200, {"trabajo": {"estado": "en_cola"}})
    assert Plataforma(servidor, "tok3n").estado("1b4e28ba-2fa1-11d2-883f-0016d3cca427") == (
        200,
        {"trabajo": {"estado": "en_cola"}},
    )
    assert Falso.recibido == {"ruta": "/api/interno/actas/trabajos/1b4e28ba-2fa1-11d2-883f-0016d3cca427", "auth": "Bearer tok3n"}


def test_estado_con_id_que_no_es_uuid_no_llama(servidor):
    with pytest.raises(ValueError):
        Plataforma(servidor, "t").estado("../salud")


def test_401_se_devuelve_tal_cual(servidor):
    Falso.respuesta = (401, {"detail": "Token de servicio no válido"})
    assert Plataforma(servidor, "malo").estado("1b4e28ba-2fa1-11d2-883f-0016d3cca427")[0] == 401


def test_sin_servidor_codigo_cero():
    assert Plataforma("http://127.0.0.1:9", "t", tiempo_s=2).estado("1b4e28ba-2fa1-11d2-883f-0016d3cca427") == (0, None)


def _una(tmp_path):
    return [Pista("socioa_1000.webm", "socioa", 1000, 0)]


def test_un_enlace_simbolico_no_se_sigue(servidor, tmp_path):
    # Un Chromium comprometido escribe en el tmpfs un enlace con nombre de pista hacia un secreto del supervisor.
    secreto = tmp_path / "token"
    secreto.write_text("tok3n-secreto")
    (tmp_path / "r").mkdir()
    (tmp_path / "r" / "socioa_1000.webm").symlink_to(secreto)
    Falso.recibido = {}
    with pytest.raises(PistasNoValidas):
        Plataforma(servidor, "t").crear(tmp_path / "r", _una(tmp_path), "r")
    assert Falso.recibido == {}


def test_un_fifo_no_bloquea(servidor, tmp_path):
    os.mkfifo(tmp_path / "socioa_1000.webm")
    with pytest.raises(PistasNoValidas):
        Plataforma(servidor, "t").crear(tmp_path, _una(tmp_path), "r")


def test_una_pista_vacia_no_se_envia(servidor, tmp_path):
    (tmp_path / "socioa_1000.webm").write_bytes(b"")
    with pytest.raises(PistasNoValidas):
        Plataforma(servidor, "t").crear(tmp_path, _una(tmp_path), "r")


def test_el_directorio_no_puede_ser_un_enlace(servidor, tmp_path):
    (tmp_path / "real").mkdir()
    (tmp_path / "real" / "socioa_1000.webm").write_bytes(b"opus")
    (tmp_path / "r").symlink_to(tmp_path / "real")
    with pytest.raises(PistasNoValidas):
        Plataforma(servidor, "t").crear(tmp_path / "r", _una(tmp_path), "r")
