"""@a56 y @a57 en el panel (V4 de KubernetesInfrastructure#298): el diagnóstico de una reunión en error en lenguaje claro, con
«qué hacer», el historial y las comprobaciones, y «Reintentar» solo donde tiene sentido. Sin base: TestClient y
`panel_falso.RepoFalso` (la base, en test_eventos_base.py; el navegador y axe, en test_panel_navegador.py)."""

import re

import pytest
from panel_falso import CHROMIUM, IMAGEN, MAESTRA, RID_PISTAS, RIDS, RepoFalso
from starlette.testclient import TestClient

from actas.panel import CONSOLA, crear_app
from actas.registro import Registro

ORIGEN = "https://actas.cenitdigital.es"
SECRETO = "secreto-del-proxy"
USUARIO = {"x-actas-proxy": SECRETO, "x-actas-usuario": "pablo"}
MISMO_ORIGEN = {**USUARIO, "sec-fetch-site": "same-origin", "origin": ORIGEN}
ERROR = f"/reuniones/{RIDS['error']}"
PISTAS = f"/reuniones/{RID_PISTAS}"


@pytest.fixture
def repo():
    return RepoFalso()


@pytest.fixture
def cliente(repo):
    app = crear_app(repo, MAESTRA, {"v1": "# Información\n\nTexto."}, "v1", ORIGEN, SECRETO, Registro())
    with TestClient(app, base_url=ORIGEN, follow_redirects=False) as c:
        yield c


def _texto(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def _seccion(html: str, ident: str) -> str:
    m = re.search(rf'<section[^>]*aria-labelledby="{ident}".*?</section>', html, re.S)
    assert m, ident
    return _texto(m.group(0))


# ── @a56: motivo, qué hacer, historial y comprobaciones ─────────────────────────────────────────────────────────────────


def test_diagnostico_en_lenguaje_claro_con_que_hacer(cliente):
    html = cliente.get(ERROR, headers=USUARIO).text
    diag = _seccion(html, "t-diagnostico")
    assert "no se pudo enviar a transcribir" in diag
    assert "Qué pasó" in diag and "12 h" in diag
    assert "Qué hacer" in diag and "Reintentar" in diag
    assert 'id="diagnostico"' in html  # el enlace «Ver qué pasó» de la lista


def test_historial_de_la_reunion(cliente):
    hist = _seccion(cliente.get(ERROR, headers=USUARIO).text, "t-historial")
    for frase in ["Pedida por pablo", "Empezó a grabar · 2 socios", "Grabación parada", "HTTP 503", "Pasó a error"]:
        assert frase in hist, frase
    assert hist.index("Pedida por") < hist.index("Empezó a grabar") < hist.index("HTTP 503") < hist.index("Pasó a error")


def test_comprobaciones_latido_chromium_transcribir_espacio_y_versiones(cliente):
    comp = _seccion(cliente.get(ERROR, headers=USUARIO).text, "t-comprobaciones")
    assert "Supervisor vivo · última vuelta hace 4 s" in comp
    assert f"Chromium responde · {CHROMIUM}" in comp
    assert "Transcribir · 2 fallos en la última hora" in comp and "HTTP 503" in comp
    assert "Espacio de grabación · 48 MiB de 768 MiB (6 %)" in comp
    assert f"Imagen {IMAGEN}" in comp


@pytest.mark.parametrize(("hace_s", "frase"), [(31.0, "Supervisor sin latido reciente · hace 31 s"), (None, "sin latido")])
def test_un_latido_viejo_o_ausente_se_marca_como_fallo(cliente, repo, hace_s, frase):
    if hace_s is None:
        repo.latido = None
    repo.latido_hace_s = hace_s
    html = cliente.get(ERROR, headers=USUARIO).text
    comp = _seccion(html, "t-comprobaciones")
    assert frase in comp
    assert "Reintentar" not in _seccion(html, "t-diagnostico").split("Qué hacer")[0]
    assert 'action="/reuniones/' not in html  # sin supervisor vivo, el botón no se ofrece


def test_chromium_que_no_responde(cliente, repo):
    repo.latido["chromium"] = None
    assert "Chromium no responde" in _seccion(cliente.get(ERROR, headers=USUARIO).text, "t-comprobaciones")


def test_enlace_a_los_registros_de_la_consola(cliente):
    html = cliente.get(ERROR, headers=USUARIO).text
    assert CONSOLA == "https://consola.cenitdigital.es/#/cargas/actas"
    assert f'href="{CONSOLA}"' in html


def test_el_historial_tambien_en_una_reunion_sin_error(cliente):
    html = cliente.get(f"/reuniones/{RIDS['transcrita']}", headers=USUARIO).text
    assert "Pedida por pablo" in _seccion(html, "t-historial")
    assert 'id="t-diagnostico"' not in html and 'id="t-comprobaciones"' not in html


# ── El caso real: 17d9d6ae, `error: pistas`, 6 s, sin historial ─────────────────────────────────────────────────────────


def test_el_caso_real_explica_que_paso_y_que_hacer_sin_reintentar(cliente):
    html = cliente.get(PISTAS, headers=USUARIO).text
    diag = _seccion(html, "t-diagnostico")
    assert "duró 5 s" in diag and "a los 3 s" in diag
    assert "00:00:05" in html  # la misma duración que la tarjeta «Datos»
    assert "anterior al historial" in diag
    assert "Reintentar no" in diag
    assert f'action="{PISTAS}/reintentar"' not in html
    hist = _seccion(html, "t-historial")
    assert "Pedida por pablo" in hist and "Empezó a grabar" in hist and "Parada pedida" in hist and "Terminó" in hist


# ── @a57: «Reintentar» ─────────────────────────────────────────────────────────────────────────────────────────────────


def test_reintentar_se_ofrece_con_el_audio_aun_disponible(cliente):
    html = cliente.get(ERROR, headers=USUARIO).text
    assert f'<form method="post" action="{ERROR}/reintentar"' in html


def test_reintentar_no_se_ofrece_sin_audio(cliente, repo):
    repo.latido["con_audio"] = []
    html = cliente.get(ERROR, headers=USUARIO).text
    assert f'action="{ERROR}/reintentar"' not in html
    assert "ya no está" in _seccion(html, "t-diagnostico")


def test_reintentar_pide_el_reenvio_con_el_usuario(cliente, repo):
    r = cliente.post(f"{ERROR}/reintentar", headers=MISMO_ORIGEN)
    assert (r.status_code, r.headers["location"]) == (303, f"{ERROR}#diagnostico")
    assert repo.reintentos == [(RIDS["error"], "pablo")]


def test_reintentar_una_reunion_que_no_esta_en_error_409(cliente, repo):
    r = cliente.post(f"/reuniones/{RIDS['transcrita']}/reintentar", headers=MISMO_ORIGEN)
    assert r.status_code == 409 and "no está en error" in r.text


def test_reintentar_una_reunion_que_no_existe_404(cliente, repo):
    assert cliente.post("/reuniones/00000000-0000-4000-8000-0000000000ff/reintentar", headers=MISMO_ORIGEN).status_code == 404


def test_reintentar_con_un_id_mal_formado_404_sin_consultar(cliente, repo):
    assert cliente.post("/reuniones/no-es-un-uuid/reintentar", headers=MISMO_ORIGEN).status_code == 404
    assert repo.reintentos == []


@pytest.mark.parametrize(
    "cabeceras", [{"sec-fetch-site": "cross-site"}, {"origin": "null"}, {"origin": "https://otro.example"}, {}]
)
def test_csrf_reintentar_403_y_nada_pedido(cliente, repo, cabeceras):
    assert cliente.post(f"{ERROR}/reintentar", headers={**USUARIO, **cabeceras}).status_code == 403
    assert repo.reintentos == []


def test_reintentar_solo_por_post(cliente):
    assert cliente.get(f"{ERROR}/reintentar", headers=USUARIO).status_code == 405
