"""@a58 «Copiar mensaje» y @a60 «Copiar diagnóstico para Claude» en el panel (V5 nivel 1 y V6 parte a de
KubernetesInfrastructure#298). Sin base: TestClient y `panel_falso.RepoFalso` (el navegador y axe, en test_panel_navegador.py).
Sin JavaScript todo se ve en un `<textarea readonly>`; `copiar.js` solo enseña el botón «Copiar»."""

import html
import re
import urllib.parse

import pytest
from panel_falso import MAESTRA, RID_PISTAS, RIDS, SALA, SOCIOS, RepoFalso
from starlette.testclient import TestClient

from actas.panel import crear_app
from actas.registro import Registro

ORIGEN = "https://actas.cenitdigital.es"
SECRETO = "secreto-del-proxy"
USUARIO = {"x-actas-proxy": SECRETO, "x-actas-usuario": "pablo"}
TRANSCRITA = f"/reuniones/{RIDS['transcrita']}"
ERROR = f"/reuniones/{RIDS['error']}"
COMPARTIR = f"{TRANSCRITA}/compartir"
# Lo que nunca puede salir: la contraseña de la sala de RepoFalso (ver_clave), su `room` y su `hash`, y el texto de un segmento.
CLAVE, ROOM, HASH = "k7m2p9qx4tz8wb3n", "k3v9q2m7x4t8w1za", "3931"
SEGMENTO = "Traigo las cifras de marketing"


@pytest.fixture
def repo():
    r = RepoFalso()
    socios = r.socios()
    r.socios = lambda: [{**s, "correo": "roberto@cenitdigital.es"} if s["push"] == "roberto" else s for s in socios]

    def nunca(*_: object) -> None:
        raise AssertionError("ni Compartir ni la ficha leen la contraseña de la sala")

    r.ver_clave = r.cifrada_de_sala = nunca  # @a58: la contraseña no se lee, así que no puede ir en ningún mensaje
    return r


@pytest.fixture
def cliente(repo):
    app = crear_app(repo, MAESTRA, {"v1": "# Información\n\nTexto."}, "v1", ORIGEN, SECRETO, Registro())
    with TestClient(app, base_url=ORIGEN, follow_redirects=False) as c:
        yield c


def _areas(pagina: str) -> dict[str, str]:
    """{id: texto} de cada `<textarea readonly>`, ya sin escapar (lo que se copia)."""
    return {
        m.group(1): html.unescape(m.group(2))
        for m in re.finditer(r'<textarea[^>]*\bid="([^"]+)"[^>]*\breadonly[^>]*>(.*?)</textarea>', pagina, re.S)
    }


def _mailtos(pagina: str) -> list[str]:
    return [html.unescape(m) for m in re.findall(r'href="(mailto:[^"]*)"', pagina)]


# ── @a58: Compartir ─────────────────────────────────────────────────────────────────────────────────────────────────────


def test_la_reunion_enlaza_compartir(cliente):
    assert f'href="{COMPARTIR}"' in cliente.get(TRANSCRITA, headers=USUARIO).text


def test_el_formulario_ofrece_transcripcion_enlace_y_los_socios_de_la_reunion_pero_no_la_contrasena(cliente):
    r = cliente.get(COMPARTIR, headers=USUARIO)
    assert r.status_code == 200
    assert 'method="get"' in r.text
    assert 'value="transcripcion"' in r.text and 'value="enlace_sala"' in r.text
    assert 'value="pablo"' in r.text and 'value="roberto"' in r.text and "antiguo" not in r.text
    assert 'value="clave"' not in r.text and CLAVE not in r.text
    assert f'href="/salas/{SALA}/clave"' in r.text  # la contraseña, por otro canal y con su rastro
    assert not _areas(r.text)


def test_copiar_mensaje_con_la_transcripcion(cliente):
    r = cliente.get(COMPARTIR, params={"que": "transcripcion", "socio": "roberto"}, headers=USUARIO)
    assert r.status_code == 200
    (texto,) = _areas(r.text).values()
    assert texto.startswith("Hola, Roberto:")
    assert f"[00:04:40] Roberto: De acuerdo. {SEGMENTO}" in texto
    assert ROOM not in texto
    (ident,) = _areas(r.text)
    assert f'data-copiar="{ident}"' in r.text
    (url,) = _mailtos(r.text)
    assert url.startswith("mailto:roberto@cenitdigital.es?")
    cuerpo = urllib.parse.unquote(url.split("body=")[1]).replace("\r\n", "\n")
    assert cuerpo == texto  # el mismo contenido
    assert f'href="{TRANSCRITA}/transcripcion.txt"' in r.text


def test_una_transcripcion_larga_va_entera_al_copiar_y_adjunta_en_el_mailto(cliente, repo):
    detalle = repo.detalle
    largos = [("pablo", i * 1000, i * 1000 + 900, f"Frase número {i} de una reunión larga.") for i in range(200)]
    repo.detalle = lambda rid: (*detalle(rid)[:2], largos)
    r = cliente.get(COMPARTIR, params={"que": "transcripcion", "socio": "roberto"}, headers=USUARIO)
    (texto,) = _areas(r.text).values()
    assert "Frase número 199" in texto
    (url,) = _mailtos(r.text)
    assert "Frase número" not in urllib.parse.unquote(url) and "fichero adjunto" in urllib.parse.unquote(url)
    assert "adjuntar el .txt" in r.text and f'href="{TRANSCRITA}/transcripcion.txt"' in r.text


def test_copiar_mensaje_con_el_enlace_de_la_sala_nunca_lleva_la_contrasena(cliente):
    r = cliente.get(COMPARTIR, params={"que": "enlace_sala", "socio": ["pablo", "roberto"]}, headers=USUARIO)
    areas = _areas(r.text)
    assert len(areas) == 2
    pablo, roberto = areas.values()
    assert f"room={ROOM}&hash={HASH}&push=pablo&label=Pablo" in pablo and "push=roberto" not in pablo
    assert "push=roberto&label=Roberto" in roberto
    assert "otro canal" in roberto
    assert CLAVE not in r.text
    assert all(CLAVE not in urllib.parse.unquote(u) for u in _mailtos(r.text))
    assert _mailtos(r.text)[0].startswith("mailto:?subject=")  # Pablo no tiene correo


@pytest.mark.parametrize(
    "params",
    [
        {"que": "clave", "socio": "roberto"},
        {"que": ["enlace_sala", "clave"], "socio": "roberto"},
        {"que": "transcripcion", "socio": "antiguo"},
        {"que": "transcripcion"},
        {"socio": "roberto"},
    ],
)
def test_lo_que_no_se_ofrece_se_rechaza(cliente, params):
    r = cliente.get(COMPARTIR, params=params, headers=USUARIO)
    assert r.status_code == 400
    assert 'role="alert"' in r.text
    assert CLAVE not in r.text and not _areas(r.text)


def test_sin_sala_no_se_ofrece_el_enlace(cliente, repo):
    detalle = repo.detalle
    repo.detalle = lambda rid: ({**detalle(rid)[0], "sala_id": None}, *detalle(rid)[1:])
    r = cliente.get(COMPARTIR, headers=USUARIO)
    assert 'value="enlace_sala"' not in r.text
    assert cliente.get(COMPARTIR, params={"que": "enlace_sala", "socio": "roberto"}, headers=USUARIO).status_code == 400


def test_descargar_la_transcripcion_en_txt(cliente):
    r = cliente.get(f"{TRANSCRITA}/transcripcion.txt", headers=USUARIO)
    assert r.status_code == 200
    assert r.headers["content-type"] == "text/plain; charset=utf-8"
    assert r.headers["content-disposition"] == 'attachment; filename="transcripcion-2026-10-22-1800.txt"'
    assert "[00:03:12] Pablo: Empezamos por el presupuesto" in r.text
    assert r.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("ruta", ["/compartir", "/transcripcion.txt"])
def test_una_reunion_que_no_existe_da_404(cliente, ruta):
    assert cliente.get(f"/reuniones/no-es-un-uuid{ruta}", headers=USUARIO).status_code == 404
    assert cliente.get(f"/reuniones/99999999-0000-4000-8000-000000000000{ruta}", headers=USUARIO).status_code == 404


# ── @a60: Copiar diagnóstico para Claude ────────────────────────────────────────────────────────────────────────────────


def test_diagnostico_para_claude_en_una_reunion_en_error(cliente):
    pagina = cliente.get(ERROR, headers=USUARIO).text
    areas = _areas(pagina)
    assert "para-claude" in areas
    texto = areas["para-claude"]
    assert "plazo_envio" in texto and "Pasó a error (plazo_envio)" in texto and "HTTP 503" in texto
    assert "sha-0123456789abcdef0123456789abcdef01234567" in texto and "HeadlessChrome/141.0.7390.37" in texto
    assert "Socios: S1, S2" in texto and "Pedida por U1" in texto
    assert 'data-copiar="para-claude"' in pagina and "Copiar diagnóstico para Claude" in pagina


@pytest.mark.parametrize("rid", [RIDS["error"], RID_PISTAS])
def test_el_bloque_para_claude_no_lleva_nombres_secretos_enlaces_ni_texto(cliente, rid):
    texto = _areas(cliente.get(f"/reuniones/{rid}", headers=USUARIO).text)["para-claude"]
    for prohibido in [CLAVE, ROOM, f"hash={HASH}", SEGMENTO, "presupuesto", "Socios · semanal", "http", "cenitdigital", SALA]:
        assert prohibido not in texto, prohibido
    for push, nombre in {**SOCIOS, "andres": "andres"}.items():
        assert push not in texto.lower() and nombre.lower() not in texto.lower(), nombre


def test_sin_error_no_hay_bloque_para_claude(cliente):
    assert "para-claude" not in cliente.get(TRANSCRITA, headers=USUARIO).text
