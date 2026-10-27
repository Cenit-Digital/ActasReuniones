"""«Grabar» y «Parar» con un Chromium real (KubernetesInfrastructure#287, prueba real del 2026-10-26: 403 «Petición de otro
origen» porque `no-referrer` hacía que el navegador mandara `Origin: null`). El panel sirve en local con uvicorn y un repositorio
de mentira; Chromium recibe por CDP las dos cabeceras que pone Traefik, abre la página y envía el formulario. Las cabeceras de
la petición no se ponen a mano: son las del navegador. `ACTAS_CHROMIUM` = ruta del binario; sin ella, el test se salta."""

import json
import os
import socket
import threading
import time
from pathlib import Path

import pytest
import uvicorn
from panel_falso import MAESTRA, RID_PAPELERA, RID_PISTAS, RIDS, SALA, RepoFalso

from actas.cdp import Cdp
from actas.panel import crear_app
from actas.registro import Registro

SECRETO = "secreto-del-proxy"
RID = RIDS["grabando"]
COMPARTIR = f"/reuniones/{RIDS['transcrita']}/compartir"


@pytest.fixture
def panel():
    """(origen, repo, cabeceras de cada POST que llega al panel)."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        puerto = s.getsockname()[1]
    origen = f"http://127.0.0.1:{puerto}"
    repo = RepoFalso()
    textos = {"v1": "# Información\n\nTexto de prueba.\n\n## Qué se graba\n\n- Tu voz.\n- Tus palabras."}
    app = crear_app(repo, MAESTRA, textos, "v1", origen, SECRETO, Registro())
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


def test_reintentar_desde_el_navegador(chromium, panel):
    """@a57: «Reintentar» es un formulario POST del propio panel, sin JavaScript: lleva el Origin y pasa la guardia."""
    origen, repo, posts = panel
    cdp = Cdp(chromium, Registro())
    rid = RIDS["error"]
    try:
        t, s = _enviar_formulario(cdp, origen + f"/reuniones/{rid}", "true")
        assert _esperar(lambda: repo.reintentos), f"el panel rechazó el POST: Origin {[p.get('origin') for p in posts]}"
        assert posts[0]["origin"] == origen and repo.reintentos == [(rid, "panel")]
        assert _esperar(lambda: cdp.evaluar(s, "location.pathname + location.hash") == f"/reuniones/{rid}#diagnostico")
        cdp.cerrar_pagina(t)
    finally:
        cdp.cerrar()


# ── @a41: axe en 1280 y 390 px, en tema oscuro y claro ──────────────────────────────────────────────────────────────────

PANTALLAS = {
    "lista": "/",
    "reunion": f"/reuniones/{RIDS['transcrita']}",
    "reunion-error": f"/reuniones/{RIDS['error']}",
    "reunion-error-pistas": f"/reuniones/{RID_PISTAS}",
    "reunion-grabando": f"/reuniones/{RIDS['grabando']}",
    "buscar": "/buscar?q=presupuesto",
    "buscar-vacio": "/buscar",
    "grabar": "/grabar",
    "salas": "/salas",
    "sala-nueva": "/salas/nueva",
    "sala": f"/salas/{SALA}",
    "sala-confirmar-clave": f"/salas/{SALA}/clave",
    # V3: programación, modificar, cancelar, eliminar y papelera.
    "programacion": "/programacion",
    "reunion-programada": f"/reuniones/{RIDS['programada']}",
    "modificar": f"/reuniones/{RIDS['programada']}/modificar",
    "cancelar": f"/reuniones/{RIDS['programada']}/cancelar",
    "eliminar": f"/reuniones/{RIDS['transcrita']}/eliminar",
    "papelera": "/papelera",
    "reunion-en-papelera": f"/reuniones/{RID_PAPELERA}",
    "no-existe": "/no-existe",
    # V5 nivel 1 (@a58): el formulario, los mensajes preparados y el 400 de una petición que no se ofrece.
    "compartir": COMPARTIR,
    "compartir-mensajes": f"{COMPARTIR}?que=transcripcion&que=enlace_sala&socio=pablo&socio=roberto",
    "compartir-error": f"{COMPARTIR}?que=transcripcion",
}
WCAG_22_AA = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]
AUDITAR = (
    f"document.fonts.ready.then(() => axe.run(document, {{runOnly: {{type: 'tag', values: {json.dumps(WCAG_22_AA)}}}}}))"
    ".then(r => JSON.stringify(r.violations.map(v => ({id: v.id, nodos: v.nodes.map(n => n.target.join(' '))}))))"
)
SIN_SCROLL = "document.documentElement.scrollWidth <= document.documentElement.clientWidth"


@pytest.fixture
def axe():
    ruta = os.environ.get("ACTAS_AXE")
    if not ruta:
        pytest.skip("sin ACTAS_AXE")
    return Path(ruta).read_text(encoding="utf-8")


def _abrir(cdp, ancho, tema):
    t = cdp.enviar("Target.createTarget", {"url": "about:blank"})["targetId"]
    s = cdp.enviar("Target.attachToTarget", {"targetId": t, "flatten": True})["sessionId"]
    cdp.enviar("Network.enable", sesion=s)
    cdp.enviar("Network.setExtraHTTPHeaders", {"headers": {"X-Actas-Proxy": SECRETO, "X-Actas-Usuario": "panel"}}, sesion=s)
    metricas = {"width": ancho, "height": 900, "deviceScaleFactor": 1, "mobile": ancho < 500}
    cdp.enviar("Emulation.setDeviceMetricsOverride", metricas, sesion=s)
    cdp.enviar("Emulation.setEmulatedMedia", {"features": [{"name": "prefers-color-scheme", "value": tema}]}, sesion=s)
    return t, s


def _ir(cdp, s, origen, ruta):
    """Navega y espera, con plazo, a que la página cargada sea la de `ruta` (y no la anterior aún en pantalla)."""
    cdp.enviar("Page.navigate", {"url": origen + ruta}, sesion=s)
    cargada = f"location.pathname + location.search === {json.dumps(ruta)} && document.readyState === 'complete'"
    assert _esperar(lambda: cdp.evaluar(s, cargada)), f"{ruta} no terminó de cargar"


def _auditar(cdp, s, axe_js):
    assert _esperar(lambda: cdp.evaluar(s, "document.readyState === 'complete' && !!document.querySelector('main')"))
    cdp.evaluar(s, axe_js + "; true", espera=60)
    infracciones = json.loads(cdp.evaluar(s, AUDITAR, espera=60))
    return infracciones, cdp.evaluar(s, SIN_SCROLL)


@pytest.mark.parametrize("tema", ["dark", "light"])
@pytest.mark.parametrize("ancho", [1280, 390])
def test_axe_sin_infracciones_wcag22_aa_ni_scroll_horizontal(chromium, panel, axe, ancho, tema):
    origen, _repo, _posts = panel
    cdp = Cdp(chromium, Registro())
    try:
        t, s = _abrir(cdp, ancho, tema)
        assert cdp.evaluar(s, f"matchMedia('(prefers-color-scheme: {tema})').matches") is True
        for nombre, ruta in PANTALLAS.items():
            _ir(cdp, s, origen, ruta)
            infracciones, sin_scroll = _auditar(cdp, s, axe)
            assert infracciones == [], f"{nombre} ({ancho} px, {tema}): {infracciones}"
            assert sin_scroll, f"{nombre} ({ancho} px, {tema}): barra de desplazamiento horizontal"
        # «Grabar» sin marcar a nadie: el 400 con su aviso.
        _ir(cdp, s, origen, "/grabar")
        cdp.evaluar(s, "document.querySelector('form[method=post] button[type=submit]').click(); true")
        assert _esperar(lambda: cdp.evaluar(s, "!!document.querySelector('[role=alert]')"))
        infracciones, sin_scroll = _auditar(cdp, s, axe)
        assert infracciones == [] and sin_scroll, f"grabar con error ({ancho} px, {tema}): {infracciones}"
        # Los botones «Copiar» de «Compartir» (@a58) y de «Copiar diagnóstico para Claude» (@a60) aparecen con copiar.js.
        for ruta, boton in [(PANTALLAS["compartir-mensajes"], "mensaje-2"), (PANTALLAS["reunion-error"], "para-claude")]:
            _ir(cdp, s, origen, ruta)
            assert _esperar(lambda b=boton: cdp.evaluar(s, f"!document.querySelector('button[data-copiar={b}]').hidden"))
        # «Mostrar la contraseña» (V2): la sala con la contraseña visible y sus botones «Copiar».
        _ir(cdp, s, origen, f"/salas/{SALA}/clave")
        cdp.evaluar(s, "document.querySelector('form[method=post] button[type=submit]').click(); true")
        assert _esperar(lambda: cdp.evaluar(s, "!!document.querySelector('#clave')"))
        assert _esperar(lambda: cdp.evaluar(s, "!document.querySelector('button[data-copiar=clave]').hidden"))
        infracciones, sin_scroll = _auditar(cdp, s, axe)
        assert infracciones == [] and sin_scroll, f"sala con la contraseña ({ancho} px, {tema}): {infracciones}"
        cdp.cerrar_pagina(t)
    finally:
        cdp.cerrar()


def test_el_tema_elegido_se_recuerda_y_cambia_los_colores(chromium, panel):
    origen, _repo, _posts = panel
    cdp = Cdp(chromium, Registro())
    fondo = "getComputedStyle(document.body).backgroundColor"
    try:
        t, s = _abrir(cdp, 1280, "dark")
        _ir(cdp, s, origen, "/")
        assert _esperar(lambda: cdp.evaluar(s, "!!document.querySelector('#tema:not([hidden])')"))
        assert cdp.evaluar(s, fondo) == "rgb(26, 24, 32)"
        cdp.evaluar(s, "document.querySelector('#tema').click(); true")
        assert cdp.evaluar(s, fondo) == "rgb(251, 246, 241)"
        assert cdp.evaluar(s, "document.querySelector('#tema').getAttribute('aria-pressed')") == "true"
        _ir(cdp, s, origen, "/grabar")
        assert cdp.evaluar(s, fondo) == "rgb(251, 246, 241)"
        cdp.cerrar_pagina(t)
    finally:
        cdp.cerrar()
