"""Panel v2 (V1 de KubernetesInfrastructure#298, ADR 0023): maquetación con los tokens de transcribir (@a40), estados con texto y
glifo (@a42), enlaces cruzados con transcribir (@a62, lado del panel) y páginas de mensaje. Sin base: TestClient y
`panel_falso.RepoFalso`. La auditoría con axe (@a41) va en test_panel_navegador.py, con un Chromium real."""

import re
from html.parser import HTMLParser

import pytest
from panel_falso import RIDS, SOCIOS, TRABAJO, RepoFalso
from starlette.testclient import TestClient

from actas.panel import crear_app
from actas.registro import Registro

ORIGEN = "https://actas.cenitdigital.es"
SECRETO = "secreto-del-proxy"
USUARIO = {"x-actas-proxy": SECRETO, "x-actas-usuario": "panel"}
PAGINAS = ["/", f"/reuniones/{RIDS['transcrita']}", "/buscar?q=presupuesto", "/grabar"]
CSP = (
    "default-src 'none'; script-src 'self'; style-src 'self'; font-src 'self'; img-src 'self'; connect-src 'self'; "
    "form-action 'self'; frame-ancestors 'none'; base-uri 'none'"
)


@pytest.fixture
def repo():
    return RepoFalso()


@pytest.fixture
def cliente(repo):
    app = crear_app(repo, SOCIOS, {"v1": "# Información\n\nTexto."}, "v1", ORIGEN, SECRETO, Registro())
    with TestClient(app, base_url=ORIGEN, follow_redirects=False) as c:
        yield c


class _Recursos(HTMLParser):
    """Lo que una página carga o ejecuta: URLs de link, script e img, y lo que la CSP bloquearía (estilos y scripts en línea)."""

    def __init__(self) -> None:
        super().__init__()
        self.urls: list[str] = []
        self.en_linea: list[str] = []
        self._script = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "style" or "style" in a or any(k.startswith("on") for k in a):
            self.en_linea.append(tag)
        if tag == "link" and a.get("rel") in ("stylesheet", "icon", "preload"):
            self.urls.append(a["href"])
        if tag in ("script", "img") or (tag == "link" and a.get("rel") == "preload"):
            if tag == "script" and not a.get("src"):
                self.en_linea.append("script")
            if a.get("src"):
                self.urls.append(a["src"])
        self._script = tag == "script"

    def handle_data(self, data):
        if self._script and data.strip():
            self.en_linea.append("script")

    def handle_endtag(self, tag):
        self._script = False


def _recursos(html: str) -> _Recursos:
    p = _Recursos()
    p.feed(html)
    return p


# ── @a40: tokens, solo recursos propios y CSP con script-src 'self' ─────────────────────────────────────────────────────


@pytest.mark.parametrize("ruta", [*PAGINAS, "/salud", "/estilo.css", "/no-existe"])
def test_csp_con_script_src_self_sin_unsafe_inline(cliente, ruta):
    csp = cliente.get(ruta, headers=USUARIO).headers["content-security-policy"]
    assert csp == CSP
    assert "unsafe" not in csp


@pytest.mark.parametrize("ruta", PAGINAS)
def test_cada_pagina_carga_solo_recursos_propios_y_nada_en_linea(cliente, ruta):
    r = cliente.get(ruta, headers=USUARIO)
    assert r.status_code == 200
    p = _recursos(r.text)
    assert p.en_linea == []
    assert {"/estilo.css", "/tema.js"} <= set(p.urls)
    for url in p.urls:
        assert url.startswith("/") and not url.startswith("//"), url
        assert cliente.get(url, headers=USUARIO).status_code == 200, url


def test_la_hoja_lleva_los_tokens_terracota_clasica_en_los_dos_temas(cliente):
    css = cliente.get("/estilo.css", headers=USUARIO).text
    oscuro = {"--bg": "#1a1820", "--surface": "#24212c", "--text": "#f4ece6", "--accent": "#c7663d", "--error": "#f08a8a"}
    claro = {"--bg": "#fbf6f1", "--surface": "#ffffff", "--text": "#3a2c2a", "--accent": "#c2683f", "--error": "#b3261e"}
    for nombre, valor in [*oscuro.items(), *claro.items()]:
        assert f"{nombre}: {valor};" in css, nombre
    assert "prefers-color-scheme: light" in css and ":root[data-tema='claro']" in css


def test_las_fuentes_son_propias_y_se_sirven_como_woff2(cliente):
    css = cliente.get("/estilo.css", headers=USUARIO).text
    urls = re.findall(r"url\('([^']+)'\)", css)
    familias = set(re.findall(r"font-family: '([^']+)';", css))
    assert familias == {"Manrope", "Gilda Display", "JetBrains Mono"}
    assert len(urls) == 6
    for url in urls:
        assert url.startswith("/fuentes/") and url.endswith(".woff2")
        r = cliente.get(url, headers=USUARIO)
        assert r.status_code == 200 and r.headers["content-type"] == "font/woff2"
        assert r.content[:4] == b"wOF2"


def test_las_licencias_de_las_fuentes_viajan_con_ellas(cliente):
    for nombre in ["OFL-manrope.txt", "OFL-gildadisplay.txt", "OFL-jetbrainsmono.txt"]:
        r = cliente.get(f"/fuentes/{nombre}", headers=USUARIO)
        assert r.status_code == 200 and "SIL OPEN FONT LICENSE Version 1.1" in r.text


@pytest.mark.parametrize("ruta", ["/fuentes/otra.woff2", "/fuentes/", "/fuentes/estilo.css"])
def test_solo_se_sirven_las_fuentes_conocidas(cliente, ruta):
    assert cliente.get(ruta, headers=USUARIO).status_code == 404


@pytest.mark.parametrize("ruta", ["/estilo.css", "/tema.js", "/fuentes/manrope-latin.woff2"])
def test_los_estaticos_se_guardan_en_la_cache_del_navegador_y_las_paginas_no(cliente, ruta):
    assert cliente.get(ruta, headers=USUARIO).headers["cache-control"] == "private, max-age=86400"
    assert cliente.get("/", headers=USUARIO).headers["cache-control"] == "no-store"


def test_los_estaticos_tambien_piden_el_proxy_y_el_usuario(cliente):
    assert cliente.get("/fuentes/manrope-latin.woff2").status_code == 401
    assert cliente.get("/tema.js").status_code == 401


def test_el_tema_se_elige_sin_javascript_en_linea(cliente):
    r = cliente.get("/tema.js", headers=USUARIO)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/javascript")
    html = cliente.get("/", headers=USUARIO).text
    boton = re.search(r"<button[^>]*id=\"tema\"[^>]*>", html)
    assert boton and 'type="button"' in boton[0] and "hidden" in boton[0]


def test_la_navegacion_solo_enlaza_pantallas_que_existen(cliente):
    html = cliente.get("/", headers=USUARIO).text
    cabecera = html[html.index("<header") : html.index("</header>")]
    internos = re.findall(r'href="(/[^"]*)"', cabecera)
    assert set(internos) == {"/", "/grabar"}
    assert 'href="https://transcribir.cenitdigital.es/#/actas"' in cabecera
    assert 'method="post"' not in cabecera
    for url in internos:
        assert cliente.get(url, headers=USUARIO).status_code == 200


@pytest.mark.parametrize(("ruta", "seccion"), [("/", "/"), ("/grabar", "/grabar")])
def test_la_seccion_actual_se_marca(cliente, ruta, seccion):
    html = cliente.get(ruta, headers=USUARIO).text
    assert re.search(rf'<a href="{seccion}"[^>]*aria-current="page"', html)


# ── @a42: estados con texto y glifo; una reunión en error, con aviso ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("estado", "texto", "glifo"),
    [
        ("grabando", "Grabando", "punto"),
        ("programada", "Programada", "reloj"),
        ("transcribiendo", "Transcribiendo", "medio"),
        ("transcrita", "Transcrita", "visto"),
        ("error", "Error", "cruz"),
        ("cancelada", "Cancelada", "prohibido"),
    ],
)
def test_cada_estado_de_la_lista_con_texto_y_glifo(cliente, estado, texto, glifo):
    html = cliente.get("/", headers=USUARIO).text
    svg = rf'<svg [^>]*data-glifo="{glifo}"[^>]*aria-hidden="true"[^>]*>.*?</svg>'
    patron = rf'<span class="estado estado-{estado}">{svg}{texto}</span>'
    assert re.search(patron, html, re.S), estado


def test_una_reunion_en_error_saca_un_aviso_con_enlace_a_su_diagnostico(cliente):
    html = cliente.get("/", headers=USUARIO).text
    aviso = re.search(r'<section class="aviso aviso-error".*?</section>', html, re.S)
    assert aviso and "1 reunión en error" in aviso[0] and "plazo_envio" in aviso[0]
    assert f'href="/reuniones/{RIDS["error"]}#diagnostico"' in aviso[0]
    ficha = cliente.get(f"/reuniones/{RIDS['error']}", headers=USUARIO).text
    assert re.search(r'id="diagnostico"[^>]*>.*?plazo_envio', ficha, re.S)


def test_sin_reuniones_en_error_no_hay_aviso(repo, cliente, monkeypatch):
    ultimas = repo.ultimas
    monkeypatch.setattr(repo, "ultimas", lambda n: [r for r in ultimas(n) if r["estado"] != "error"])
    assert "aviso-error" not in cliente.get("/", headers=USUARIO).text


# ── @a62: enlaces cruzados con transcribir ──────────────────────────────────────────────────────────────────────────────


def test_la_ficha_enlaza_a_su_trabajo_en_transcribir(cliente):
    html = cliente.get(f"/reuniones/{RIDS['transcrita']}", headers=USUARIO).text
    enlace = re.search(rf'<a [^>]*href="https://transcribir.cenitdigital.es/#/trabajos/{TRABAJO}"[^>]*>', html)
    assert enlace and 'rel="noopener noreferrer"' in enlace[0]


def test_sin_trabajo_no_hay_enlace_a_transcribir_en_la_ficha(cliente):
    html = cliente.get(f"/reuniones/{RIDS['grabando']}", headers=USUARIO).text
    assert "/#/trabajos/" not in html


# Lo que manda el navegador al seguir el enlace de transcribir.cenitdigital.es (otro origen del mismo sitio, sin Referer).
DESDE_TRANSCRIBIR = {**USUARIO, "sec-fetch-site": "same-site", "sec-fetch-mode": "navigate", "sec-fetch-dest": "document"}


@pytest.mark.parametrize("sitio", ["same-site", "cross-site", "none"])
def test_el_trabajo_de_transcribir_lleva_a_su_reunion(cliente, repo, sitio):
    r = cliente.get("/reuniones", params={"trabajo": TRABAJO}, headers={**DESDE_TRANSCRIBIR, "sec-fetch-site": sitio})
    assert r.status_code == 303 and r.headers["location"] == f"/reuniones/{RIDS['transcrita']}"
    assert repo.trabajos == [TRABAJO]


def test_un_trabajo_sin_reunion_da_un_404_claro(cliente):
    r = cliente.get("/reuniones", params={"trabajo": "99999999-2222-4333-8444-555555555555"}, headers=DESDE_TRANSCRIBIR)
    assert r.status_code == 404 and "Ninguna reunión tiene ese trabajo de transcribir" in r.text


@pytest.mark.parametrize("params", [{"trabajo": "no-es-uuid"}, {"trabajo": ""}, {}])
def test_un_trabajo_mal_formado_da_404_sin_consultar(cliente, repo, params):
    assert cliente.get("/reuniones", params=params, headers=DESDE_TRANSCRIBIR).status_code == 404
    assert repo.trabajos == []


def test_el_trabajo_pedido_en_segundo_plano_desde_otra_web_403(cliente, repo):
    cabeceras = {**DESDE_TRANSCRIBIR, "sec-fetch-mode": "cors", "sec-fetch-dest": "empty"}
    assert cliente.get("/reuniones", params={"trabajo": TRABAJO}, headers=cabeceras).status_code == 403
    assert repo.trabajos == []


# ── Mensajes ────────────────────────────────────────────────────────────────────────────────────────────────────────────


def test_una_pagina_que_no_existe_da_un_404_con_la_maquetacion(cliente):
    r = cliente.get("/no-existe", headers=USUARIO)
    assert r.status_code == 404 and "/estilo.css" in r.text and "Esa página no existe" in r.text


def test_parar_sin_grabacion_con_la_maquetacion(cliente, repo):
    repo.activa = False
    cabeceras = {**USUARIO, "sec-fetch-site": "same-origin", "origin": ORIGEN}
    r = cliente.post("/parar", headers=cabeceras)
    assert r.status_code == 409 and "No hay ninguna grabación activa." in r.text and "/estilo.css" in r.text


def test_el_hablante_desconocido_se_muestra_por_su_identificador(cliente):
    html = cliente.get(f"/reuniones/{RIDS['transcrita']}", headers=USUARIO).text
    assert re.search(r'class="hablante h\d"[^>]*>invitado<', html)
