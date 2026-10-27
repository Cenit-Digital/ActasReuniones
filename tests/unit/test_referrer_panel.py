"""El `Origin` que manda un navegador al enviar los formularios del panel (KubernetesInfrastructure#287, prueba real del
2026-10-26: «Grabar» desde Chrome daba 403 «Petición de otro origen»). Se calcula con las especificaciones a partir de lo que
sirve el panel de verdad (cabecera `Referrer-Policy` y `<meta name="referrer">`), con y sin la cabecera que añade Traefik
(KubernetesInfrastructure, kubernetes/ingress/config/middlewares.yaml), y tiene que pasar `origen.permitido` (@a31).

- Referrer Policy (W3C, §8.1 «Parse a referrer policy from a Referrer-Policy header»): «For each token in policy-tokens, if token
  is a referrer policy and token is not the empty string, then set policy to token»; §11.1: «when multiple sources specify a
  referrer policy, the value of the latest one will be used»; §3.7: el valor por defecto es «strict-origin-when-cross-origin».
- HTML, `<meta name="referrer">`: «If value is a referrer policy, then set element's node document's policy container's
  referrer policy to policy» (después de la cabecera: el `<meta>` manda) y «Only the most-recently-inserted or
  most-recently-modified meta element in this state has an effect».
- Fetch, «append a request `Origin` header»: si el método no es GET ni HEAD y el modo no es "cors" (un `<form method="post">`
  es "navigate"), «switch on request's referrer policy»: "no-referrer" → `null`; "no-referrer-when-downgrade",
  "strict-origin", "strict-origin-when-cross-origin" → `null` si el origen es https y la URL no; "same-origin" → `null` si el
  origen de la petición no es el mismo que el de la URL; los demás, nada.
"""

from datetime import datetime
from html.parser import HTMLParser
from urllib.parse import urlsplit

import pytest
from starlette.testclient import TestClient

from actas.origen import permitido
from actas.panel import crear_app
from actas.registro import Registro

ORIGEN = "https://actas.cenitdigital.es"
SECRETO = "secreto-del-proxy"
USUARIO = {"x-actas-proxy": SECRETO, "x-actas-usuario": "panel", "sec-fetch-site": "same-origin"}
TRAEFIK = "strict-origin-when-cross-origin"
RID = "00000000-0000-0000-0000-000000000001"
POLITICAS = {
    "no-referrer",
    "no-referrer-when-downgrade",
    "same-origin",
    "origin",
    "strict-origin",
    "origin-when-cross-origin",
    "strict-origin-when-cross-origin",
    "unsafe-url",
}
LEGADO = {"never": "no-referrer", "default": "strict-origin-when-cross-origin", "always": "unsafe-url"}
LEGADO["origin-when-crossorigin"] = "origin-when-cross-origin"


def politica_de_cabecera(valores: list[str]) -> str:
    politica = ""
    for token in (t.strip() for v in valores for t in v.split(",")):
        if token in POLITICAS:
            politica = token
    return politica


class _Metas(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.valores: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        if tag == "meta" and (a.get("name") or "").lower() == "referrer" and a.get("content"):
            self.valores.append(a["content"].lower())


def politica_del_documento(cabeceras: list[str], html: str) -> str:
    politica = politica_de_cabecera(cabeceras)
    metas = _Metas()
    metas.feed(html)
    for valor in metas.valores:
        valor = LEGADO.get(valor, valor)
        if valor in POLITICAS:
            politica = valor
    return politica or "strict-origin-when-cross-origin"


def _origen(url: str) -> tuple[str, str | None, int | None]:
    p = urlsplit(url)
    return p.scheme, p.hostname, p.port


def origin_de_un_post(politica: str, origen: str, url: str) -> str:
    """Fetch, «append a request `Origin` header», para un POST de formulario (modo "navigate")."""
    if politica == "no-referrer":
        return "null"
    if politica in ("no-referrer-when-downgrade", "strict-origin", "strict-origin-when-cross-origin"):
        return "null" if urlsplit(origen).scheme == "https" and urlsplit(url).scheme != "https" else origen
    if politica == "same-origin":
        return origen if _origen(origen) == _origen(url) else "null"
    return origen


class _Repo:
    """Lo justo para pintar las tres páginas con un formulario POST: «Grabar», la lista y una reunión que se está grabando."""

    def ultimas(self, _limite):
        return []

    def hay_grabacion(self):
        return True

    def detalle(self, _rid):
        r = {"creado_en": datetime(2026, 10, 26, 21, 30), "inicio": None, "fin": None, "estado": "grabando"}
        return {**r, "motivo": None, "socios": ["pablo"], "pedido_por": "panel"}, [], []

    def socios(self):
        return [{"push": "pablo", "nombre": "Pablo", "correo": None, "activo": True}]

    def salas(self):
        return []

    def diagnostico(self, _rid):
        return {"eventos": [], "latido": None, "latido_hace_s": None, "fallos_transcribir_1h": 0}


@pytest.fixture
def cliente():
    app = crear_app(_Repo(), bytes(32), {"v1": "# Texto"}, "v1", ORIGEN, SECRETO, Registro())
    with TestClient(app, base_url=ORIGEN) as c:
        yield c


@pytest.mark.parametrize(
    ("ruta", "accion"),
    [
        ("/grabar", "/grabar"),
        ("/", "/parar"),
        (f"/reuniones/{RID}", "/parar"),
        ("/salas", "/socios"),
        ("/salas", "/socios/pablo/activo"),
        ("/salas/nueva", "/salas"),
    ],
)
@pytest.mark.parametrize(
    "traefik",
    [
        lambda panel: panel,
        lambda panel: [*panel, TRAEFIK],
        lambda panel: [TRAEFIK, *panel],
        lambda _panel: [TRAEFIK],
    ],
    ids=["solo-panel", "traefik-despues", "traefik-antes", "traefik-sustituye"],
)
def test_el_post_de_un_formulario_del_panel_lleva_su_origen(cliente, ruta, accion, traefik):
    r = cliente.get(ruta, headers=USUARIO)
    assert r.status_code == 200
    assert f'<form method="post" action="{accion}"' in r.text
    politica = politica_del_documento(traefik(r.headers.get_list("referrer-policy")), r.text)
    origin = origin_de_un_post(politica, ORIGEN, ORIGEN + accion)
    assert origin == ORIGEN
    assert permitido({"origin": origin, "sec-fetch-site": "same-origin"}, ORIGEN)


def test_a_otro_origen_no_se_manda_el_referer():
    """same-origin: «Cross-origin-referrer requests, on the other hand, will contain no referrer information»."""
    assert origin_de_un_post("same-origin", ORIGEN, "https://otro.example/x") == "null"


@pytest.mark.parametrize(
    ("cabeceras", "html", "esperada"),
    [
        (["same-origin"], '<meta name="referrer" content="no-referrer">', "no-referrer"),
        (["no-referrer"], '<meta name="referrer" content="same-origin">', "same-origin"),
        (["same-origin, no-referrer"], "", "no-referrer"),
        (["no-referrer", "desconocida"], "", "no-referrer"),
        ([], '<meta name="referrer" content="never">', "no-referrer"),
        ([], "", "strict-origin-when-cross-origin"),
    ],
)
def test_la_precedencia_del_ayudante(cabeceras, html, esperada):
    """El `<meta>` manda sobre la cabecera y, en cada una, la última política válida: si el panel corrigiera solo la cabecera,
    el `<meta name="referrer" content="no-referrer">` seguiría dando `Origin: null`."""
    assert politica_del_documento(cabeceras, html) == esperada


@pytest.mark.parametrize(
    ("politica", "origin"),
    [("no-referrer", "null"), ("strict-origin-when-cross-origin", ORIGEN), ("same-origin", ORIGEN), ("unsafe-url", ORIGEN)],
)
def test_el_switch_de_fetch_en_el_mismo_origen(politica, origin):
    assert origin_de_un_post(politica, ORIGEN, ORIGEN + "/grabar") == origin


def test_https_a_http_con_strict_origin_es_null():
    assert origin_de_un_post("strict-origin-when-cross-origin", ORIGEN, "http://actas.cenitdigital.es/grabar") == "null"
