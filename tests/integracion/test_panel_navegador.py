"""«Grabar» y «Parar» con un Chromium real (KubernetesInfrastructure#287, prueba real del 2026-10-26: 403 «Petición de otro
origen» porque `no-referrer` hacía que el navegador mandara `Origin: null`). El panel sirve en local con uvicorn y un repositorio
de mentira; Chromium recibe por CDP las dos cabeceras que pone Traefik, abre la página y envía el formulario. Las cabeceras de
la petición no se ponen a mano: son las del navegador. `ACTAS_CHROMIUM` = ruta del binario; sin ella, el test se salta."""

import socket
import threading
import time
from datetime import datetime

import pytest
import uvicorn

from actas.cdp import Cdp
from actas.panel import crear_app
from actas.registro import Registro

SECRETO = "secreto-del-proxy"
RID = "00000000-0000-0000-0000-000000000001"


class _Repo:
    """Lo justo para las tres páginas con formulario POST, y apunta lo que piden «Grabar» y «Parar»."""

    def __init__(self) -> None:
        self.pedidas: list[tuple[object, str]] = []
        self.paradas = 0

    def pedir(self, pedida, usuario):
        self.pedidas.append((pedida, usuario))
        return RID

    def pedir_parada(self):
        self.paradas += 1
        return RID

    def ultimas(self, _limite):
        return []

    def hay_grabacion(self):
        return True

    def detalle(self, _rid):
        r = {"creado_en": datetime(2026, 10, 26, 21, 30), "inicio": None, "fin": None, "estado": "grabando"}
        return {**r, "motivo": None, "socios": ["pablo"], "pedido_por": "panel"}, [], []


@pytest.fixture
def panel():
    """(origen, repo, cabeceras de cada POST que llega al panel)."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        puerto = s.getsockname()[1]
    origen = f"http://127.0.0.1:{puerto}"
    repo = _Repo()
    app = crear_app(repo, {"pablo": "Pablo"}, {"v1": "# Texto"}, "v1", origen, SECRETO, Registro())
    posts: list[dict[str, str]] = []

    async def espia(scope, receive, send):
        if scope["type"] == "http" and scope["method"] == "POST":
            posts.append({k.decode(): v.decode() for k, v in scope["headers"]})
        await app(scope, receive, send)

    config = uvicorn.Config(espia, host="127.0.0.1", port=puerto, access_log=False, lifespan="off", log_level="error")
    srv = uvicorn.Server(config)
    hilo = threading.Thread(target=srv.run, daemon=True)
    hilo.start()
    assert _esperar(lambda: srv.started), "uvicorn no arrancó"
    yield origen, repo, posts
    srv.should_exit = True
    hilo.join(10)


def _enviar_formulario(cdp, url, preparar_js):
    t = cdp.enviar("Target.createTarget", {"url": "about:blank"})["targetId"]
    s = cdp.enviar("Target.attachToTarget", {"targetId": t, "flatten": True})["sessionId"]
    cdp.enviar("Network.enable", sesion=s)
    cdp.enviar("Network.setExtraHTTPHeaders", {"headers": {"X-Actas-Proxy": SECRETO, "X-Actas-Usuario": "panel"}}, sesion=s)
    cdp.enviar("Page.navigate", {"url": url}, sesion=s)
    cargada = "document.readyState === 'complete' && !!document.querySelector('form[method=post]')"
    assert _esperar(lambda: cdp.evaluar(s, cargada)), f"{url} no muestra el formulario"
    cdp.evaluar(s, preparar_js + "; document.querySelector('form[method=post] button[type=submit]').click(); true")
    return t, s


def _esperar(condicion):
    for _ in range(100):
        if condicion():
            return True
        time.sleep(0.1)
    return False


def test_grabar_desde_el_navegador(chromium, panel):
    origen, repo, posts = panel
    cdp = Cdp(chromium, Registro())
    try:
        t, s = _enviar_formulario(cdp, origen + "/grabar", "document.querySelector('input[value=pablo]').checked = true")
        assert _esperar(lambda: repo.pedidas), f"el panel rechazó el POST: Origin {[p.get('origin') for p in posts]}"
        assert posts[0]["origin"] == origen and posts[0]["sec-fetch-site"] == "same-origin"
        assert repo.pedidas[0][1] == "panel"
        assert _esperar(lambda: cdp.evaluar(s, "location.pathname") == f"/reuniones/{RID}")
        cdp.cerrar_pagina(t)
    finally:
        cdp.cerrar()


@pytest.mark.parametrize("ruta", ["/", f"/reuniones/{RID}"])
def test_parar_desde_el_navegador(chromium, panel, ruta):
    origen, repo, posts = panel
    cdp = Cdp(chromium, Registro())
    try:
        t, _s = _enviar_formulario(cdp, origen + ruta, "true")
        assert _esperar(lambda: repo.paradas), f"el panel rechazó el POST: Origin {[p.get('origin') for p in posts]}"
        assert posts[0]["origin"] == origen
        cdp.cerrar_pagina(t)
    finally:
        cdp.cerrar()
