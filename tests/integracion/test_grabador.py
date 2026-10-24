"""El grabador con un Chromium real (la misma imagen que en el clúster, en la CI) y una sala falsa servida en local: abre
una página por socio con la URL de VDO.Ninja, lee los streams de la sala y, al parar, cada página descarga su
`<id>_<ms>.webm` en el directorio de la reunión. `ACTAS_CHROMIUM` = ruta del binario; sin ella, el test se salta."""

import functools
import os
import subprocess
import tempfile
import threading
import time
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from actas.cdp import Cdp
from actas.grabador import Grabacion, Sala
from actas.pistas import pistas_de
from actas.registro import Registro

SALA_FALSA = Path(__file__).parent / "sala_falsa"


@pytest.fixture
def chromium():
    binario = os.environ.get("ACTAS_CHROMIUM")
    if not binario:
        pytest.skip("sin ACTAS_CHROMIUM")
    perfil = tempfile.mkdtemp()
    proc = subprocess.Popen(  # noqa: S603
        [
            binario,
            "--headless=new",
            "--no-sandbox",
            "--disable-gpu",
            "--remote-debugging-port=9333",
            f"--user-data-dir={perfil}",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(100):
        try:
            urllib.request.urlopen("http://127.0.0.1:9333/json/version", timeout=1)  # noqa: S310
            break
        except OSError:
            time.sleep(0.1)
    yield "http://127.0.0.1:9333"
    proc.terminate()
    proc.wait(10)


@pytest.fixture
def sala_falsa():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(SimpleHTTPRequestHandler, directory=str(SALA_FALSA)))
    srv.RequestHandlerClass.log_message = lambda *a: None
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}/"
    srv.shutdown()


def test_grabar_vistos_y_parada_ordenada(chromium, sala_falsa, tmp_path):
    sala = Sala("salaprueba", "clave secreta", base=sala_falsa + "?publican=socioa,x7kq2lm&")
    lineas: list[str] = []
    cdp = Cdp(chromium, Registro([sala.clave]))
    g = Grabacion(cdp, sala, ("socioa", "sociob"), tmp_path / "reunion", lambda *p: lineas.append(" ".join(map(str, p))))
    g.empezar()
    time.sleep(2)
    assert g.vistos() == {"socioa": ["socioa", "x7kq2lm"], "sociob": ["socioa", "x7kq2lm"]}
    assert g.parar() is True
    ficheros = sorted(p.name for p in (tmp_path / "reunion").iterdir())
    assert [p.socio for p in pistas_de(ficheros, ["socioa", "sociob"])] == sorted(["socioa", "sociob"])
    assert (tmp_path / "reunion" / ficheros[0]).read_bytes().startswith(b"opus de ")
    assert not any("clave" in linea for linea in lineas)
    targets = cdp.enviar("Target.getTargets")["targetInfos"]
    assert not [t for t in targets if t["url"].startswith(sala_falsa)]  # las páginas de la sala se cerraron
    cdp.cerrar()


def test_url_de_la_pagina_espectadora():
    url = Sala("sala", "clave é&x", salt="reuniones.cenitdigital.es").url("sociopablo")
    assert url.startswith(
        "https://reuniones.cenitdigital.es/?room=sala&password=clave%20%C3%A9%26x&salt=reuniones.cenitdigital.es"
    )
    assert url.endswith("&relay&tcp&cleanoutput&scene&view=sociopablo&label=sociopablo&autorecordremote=-64&novideo")
