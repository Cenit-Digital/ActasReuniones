"""V3 en el panel (KubernetesInfrastructure#298, ADR 0023 decisiones 5 y 6): «Grabar» con título, tope y «Programar», la página
«Programación», Modificar (@a49), Cancelar (@a50) y Eliminar a la papelera escribiendo el título, y Recuperar (@a51). Sin base:
TestClient y `panel_falso.RepoFalso` (la base, en test_programar_base.py; axe, en test_panel_navegador.py)."""

import re
from datetime import datetime, timedelta

import pytest
from panel_falso import MAESTRA, PARA, RID_PAPELERA, RIDS, SALA, TITULO, RepoFalso
from starlette.testclient import TestClient

from actas.panel import crear_app
from actas.planificador import MADRID, Programacion
from actas.registro import Registro

ORIGEN = "https://actas.cenitdigital.es"
SECRETO = "secreto-del-proxy"
USUARIO = {"x-actas-proxy": SECRETO, "x-actas-usuario": "pablo"}
MISMO_ORIGEN = {**USUARIO, "sec-fetch-site": "same-origin", "origin": ORIGEN}
PROG = RIDS["programada"]


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


def _dentro_de(dias: float) -> str:
    """Una hora de Madrid en el futuro, como la envía un <input type="datetime-local">."""
    return (datetime.now(MADRID) + timedelta(days=dias)).strftime("%Y-%m-%dT%H:%M")


def _programar(**cambios):
    datos = {
        "sala": SALA,
        "socio": ["pablo", "roberto"],
        "version": "v1",
        "titulo": "Presupuesto",
        "cuando": "programar",
        "fecha": _dentro_de(2),
        "tope": "120",
        "repetir": "semanal",
        "espera": "30",
    }
    datos.update(cambios)
    return datos


# ── «Grabar»: ahora o programada ──────────────────────────────────────────────────────────────────────────────────────


def test_grabar_tiene_titulo_cuando_fecha_tope_repetir_y_espera(cliente):
    html = cliente.get("/grabar", headers=USUARIO).text
    for campo in ['name="titulo"', 'name="cuando" value="ahora"', 'name="cuando" value="programar"', 'type="datetime-local"']:
        assert campo in html, campo
    for valor in ['value="60"', 'value="120"', 'value="180"', 'value="semanal"', 'value="mensual"', 'value="15"']:
        assert valor in html, valor
    assert "Fecha y hora (Madrid)" in _texto(html)


def test_programar_desde_grabar(cliente, repo):
    datos = _programar()
    r = cliente.post("/grabar", data=datos, headers=MISMO_ORIGEN)
    assert r.status_code == 303 and r.headers["location"] == f"/reuniones/{PROG}"
    ((p, usuario),) = repo.programaciones
    assert usuario == "pablo" and repo.pedidas == []
    assert isinstance(p, Programacion)
    assert (p.titulo, p.sala_id, p.tope_min, p.repetir, p.espera_min, p.socios, p.version) == (
        "Presupuesto",
        SALA,
        120,
        "semanal",
        30,
        ("pablo", "roberto"),
        "v1",
    )
    assert p.para.astimezone(MADRID).strftime("%Y-%m-%dT%H:%M") == datos["fecha"]


@pytest.mark.parametrize(
    ("cambio", "frase"),
    [
        ({"fecha": "2020-01-01T10:00"}, "ya ha pasado"),
        ({"fecha": ""}, "AAAA-MM-DD"),
        ({"tope": "240"}, "1, 2 o 3 horas"),
        ({"repetir": "diaria"}, "repetir"),
        ({"espera": "5"}, "15, 30 o 60"),
        ({"socio": []}, "ningún socio"),
        ({"titulo": "con\nsalto"}, "título"),
    ],
)
def test_programar_no_valido_no_programa_nada(cliente, repo, cambio, frase):
    r = cliente.post("/grabar", data=_programar(**cambio), headers=MISMO_ORIGEN)
    assert r.status_code == 400 and frase in r.text
    assert repo.programaciones == [] and repo.pedidas == []


def test_grabar_ahora_con_titulo_y_tope(cliente, repo):
    r = cliente.post("/grabar", data=_programar(cuando="ahora", fecha=""), headers=MISMO_ORIGEN)
    assert r.status_code == 303
    assert repo.titulos_pedidos == [("Presupuesto", 120)] and repo.programaciones == []


def test_grabar_ahora_sin_titulo_ni_tope_es_el_de_f1(cliente, repo):
    datos = {"sala": SALA, "socio": ["pablo"], "version": "v1"}
    assert cliente.post("/grabar", data=datos, headers=MISMO_ORIGEN).status_code == 303
    assert repo.titulos_pedidos == [(None, 180)]


def test_cuando_desconocido_se_rechaza(cliente, repo):
    r = cliente.post("/grabar", data=_programar(cuando="ayer"), headers=MISMO_ORIGEN)
    assert r.status_code == 400 and repo.programaciones == [] and repo.pedidas == []


# ── «Programación» ────────────────────────────────────────────────────────────────────────────────────────────────────


def test_programacion_lista_las_programadas(cliente):
    html = cliente.get("/programacion", headers=USUARIO).text
    texto = _texto(html)
    assert TITULO in texto and "Socios · semanal" in texto  # la sala
    assert PARA.strftime("%Y-%m-%d %H:%M") in texto
    assert "1 de 2 conformes" in texto and "cada semana" in texto
    assert f'href="/reuniones/{PROG}/modificar"' in html and f'href="/reuniones/{PROG}/cancelar"' in html


def test_la_navegacion_lleva_a_programacion(cliente):
    assert 'href="/programacion"' in cliente.get("/", headers=USUARIO).text


# ── @a49: modificar ───────────────────────────────────────────────────────────────────────────────────────────────────


def test_a49_modificar_muestra_lo_programado(cliente):
    html = cliente.get(f"/reuniones/{PROG}/modificar", headers=USUARIO).text
    assert f'value="{TITULO}"' in html
    assert f'value="{PARA.strftime("%Y-%m-%dT%H:%M")}"' in html
    assert re.search(r'value="120"\s+selected', html) and re.search(r'value="semanal"\s+selected', html)
    assert re.search(r'value="pablo"\s+checked', html)  # tiene su conformidad
    assert not re.search(r'value="roberto"\s+checked', html)  # no: se pide de nuevo


def test_a49_modificar_guarda(cliente, repo):
    datos = _programar(titulo="Cambiada", tope="60", socio=["pablo"])
    r = cliente.post(f"/reuniones/{PROG}/modificar", data=datos, headers=MISMO_ORIGEN)
    assert r.status_code == 303 and r.headers["location"] == f"/reuniones/{PROG}"
    ((rid, p, usuario),) = repo.modificaciones
    assert (rid, usuario, p.titulo, p.tope_min, p.socios) == (PROG, "pablo", "Cambiada", 60, ("pablo",))


def test_a49_modificar_una_que_ya_no_esta_programada(cliente, repo):
    rid = RIDS["grabando"]
    assert cliente.get(f"/reuniones/{rid}/modificar", headers=USUARIO).status_code == 409
    r = cliente.post(f"/reuniones/{rid}/modificar", data=_programar(), headers=MISMO_ORIGEN)
    assert r.status_code == 409 and "ya no está programada" in r.text


def test_a49_modificar_no_valido(cliente, repo):
    r = cliente.post(f"/reuniones/{PROG}/modificar", data=_programar(fecha="2020-01-01T10:00"), headers=MISMO_ORIGEN)
    assert r.status_code == 400 and "ya ha pasado" in r.text and repo.modificaciones == []


def test_a49_modificar_una_que_no_existe(cliente):
    rid = "00000000-0000-4000-8000-0000000000ff"
    assert cliente.get(f"/reuniones/{rid}/modificar", headers=USUARIO).status_code == 404
    assert cliente.post(f"/reuniones/{rid}/modificar", data=_programar(), headers=MISMO_ORIGEN).status_code == 404


# ── @a50: cancelar ────────────────────────────────────────────────────────────────────────────────────────────────────


def test_a50_cancelar_pide_confirmacion_y_ofrece_la_serie(cliente):
    html = cliente.get(f"/reuniones/{PROG}/cancelar", headers=USUARIO).text
    assert f'action="/reuniones/{PROG}/cancelar"' in html
    assert 'name="serie" value="0"' in html and 'name="serie" value="1"' in html
    assert "no se borra" in _texto(html)


@pytest.mark.parametrize(("serie", "esperado"), [("0", False), ("1", True)])
def test_a50_cancelar(cliente, repo, serie, esperado):
    r = cliente.post(f"/reuniones/{PROG}/cancelar", data={"serie": serie}, headers=MISMO_ORIGEN)
    assert r.status_code == 303 and r.headers["location"] == f"/reuniones/{PROG}"
    assert repo.cancelaciones == [(PROG, "pablo", esperado)]


def test_a50_cancelar_una_que_no_esta_programada(cliente, repo):
    r = cliente.post(f"/reuniones/{RIDS['transcrita']}/cancelar", data={"serie": "0"}, headers=MISMO_ORIGEN)
    assert r.status_code == 409


def test_a50_cancelar_sin_decir_si_la_serie(cliente, repo):
    r = cliente.post(f"/reuniones/{PROG}/cancelar", data={}, headers=MISMO_ORIGEN)
    assert r.status_code == 400 and repo.cancelaciones == []


# ── @a51: eliminar (a la papelera) y recuperar ───────────────────────────────────────────────────────────────────────


def test_a51_eliminar_pide_escribir_el_titulo_y_avisa_de_los_backups(cliente):
    html = cliente.get(f"/reuniones/{RIDS['transcrita']}/eliminar", headers=USUARIO).text
    texto = _texto(html)
    assert f"«{TITULO}»" in texto
    assert "7 días" in texto and "copias de seguridad" in texto and "6 meses" in texto
    assert 'name="confirmacion"' in html


def test_a51_eliminar_sin_titulo_pide_la_fecha(cliente):
    texto = _texto(cliente.get(f"/reuniones/{RIDS['error']}/eliminar", headers=USUARIO).text)
    assert "«2026-10-23 18:00»" in texto


def test_a51_eliminar_con_el_titulo_mal_escrito_no_hace_nada(cliente, repo):
    r = cliente.post(f"/reuniones/{RIDS['transcrita']}/eliminar", data={"confirmacion": "Socios"}, headers=MISMO_ORIGEN)
    assert r.status_code == 400 and repo.papeleras == []


def test_a51_eliminar_con_el_titulo_bien_escrito_la_manda_a_la_papelera(cliente, repo):
    r = cliente.post(f"/reuniones/{RIDS['transcrita']}/eliminar", data={"confirmacion": f"  {TITULO} "}, headers=MISMO_ORIGEN)
    assert r.status_code == 303 and r.headers["location"] == "/papelera"
    assert repo.papeleras == [(RIDS["transcrita"], "pablo")]


@pytest.mark.parametrize("estado", ["grabando", "programada", "pedida", "grabada", "transcribiendo"])
def test_a51_no_se_elimina_lo_que_esta_en_marcha(cliente, repo, estado):
    rid = RIDS[estado]
    assert cliente.get(f"/reuniones/{rid}/eliminar", headers=USUARIO).status_code == 409
    assert cliente.post(f"/reuniones/{rid}/eliminar", data={"confirmacion": "x"}, headers=MISMO_ORIGEN).status_code == 409
    assert repo.papeleras == []


def test_a51_la_papelera_dice_cuando_se_borra_y_ofrece_recuperar(cliente):
    html = cliente.get("/papelera", headers=USUARIO).text
    texto = _texto(html)
    assert "Prueba de V3" in texto and "pablo" in texto
    assert "se borra el 2026-11-03" in texto  # 7 días después, en la hora de la base
    assert f'action="/reuniones/{RID_PAPELERA}/recuperar"' in html


def test_a51_recuperar(cliente, repo):
    r = cliente.post(f"/reuniones/{RID_PAPELERA}/recuperar", headers=MISMO_ORIGEN)
    assert r.status_code == 303 and r.headers["location"] == f"/reuniones/{RID_PAPELERA}"
    assert repo.recuperaciones == [(RID_PAPELERA, "pablo")]


def test_a51_recuperar_una_que_no_esta_en_la_papelera(cliente):
    assert cliente.post(f"/reuniones/{RIDS['transcrita']}/recuperar", headers=MISMO_ORIGEN).status_code == 409


def test_una_reunion_en_la_papelera_no_ensena_su_transcripcion(cliente):
    html = cliente.get(f"/reuniones/{RID_PAPELERA}", headers=USUARIO).text
    texto = _texto(html)
    assert "En la papelera" in texto and "presupuesto del trimestre" not in texto
    assert f'action="/reuniones/{RID_PAPELERA}/recuperar"' in html


# ── Acciones en la ficha y la lista ───────────────────────────────────────────────────────────────────────────────────


def test_la_ficha_de_una_programada_ofrece_modificar_y_cancelar(cliente):
    html = cliente.get(f"/reuniones/{PROG}", headers=USUARIO).text
    assert f'href="/reuniones/{PROG}/modificar"' in html and f'href="/reuniones/{PROG}/cancelar"' in html
    assert f'href="/reuniones/{PROG}/eliminar"' not in html
    assert TITULO in _texto(html) and PARA.strftime("%Y-%m-%d %H:%M") in _texto(html)


@pytest.mark.parametrize("estado", ["transcrita", "error", "cancelada"])
def test_la_ficha_de_una_terminada_ofrece_eliminar(cliente, estado):
    rid = RIDS[estado]
    html = cliente.get(f"/reuniones/{rid}", headers=USUARIO).text
    assert f'href="/reuniones/{rid}/eliminar"' in html and f'href="/reuniones/{rid}/modificar"' not in html


def test_la_lista_ensena_el_titulo_y_la_hora_programada(cliente):
    texto = _texto(cliente.get("/", headers=USUARIO).text)
    assert TITULO in texto and PARA.strftime("%Y-%m-%d %H:%M") in texto


# ── La guardia de siempre ─────────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "ruta",
    [
        f"/reuniones/{PROG}/modificar",
        f"/reuniones/{PROG}/cancelar",
        f"/reuniones/{RIDS['transcrita']}/eliminar",
        f"/reuniones/{RID_PAPELERA}/recuperar",
    ],
)
def test_sin_origen_no_se_cambia_nada(cliente, repo, ruta):
    assert cliente.post(ruta, data={"serie": "0", "confirmacion": TITULO}, headers=USUARIO).status_code == 403
    assert repo.modificaciones == repo.cancelaciones == repo.papeleras == repo.recuperaciones == []


@pytest.mark.parametrize("accion", ["modificar", "cancelar", "eliminar", "recuperar"])
def test_un_id_que_no_es_un_uuid_da_404(cliente, accion):
    assert cliente.post(f"/reuniones/x/{accion}", data={}, headers=MISMO_ORIGEN).status_code == 404


# ── Con V5: lo de la papelera tampoco se comparte ────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("ruta", ["compartir", "compartir?que=transcripcion&socio=pablo", "transcripcion.txt"])
def test_una_reunion_en_la_papelera_no_se_comparte(cliente, ruta):
    r = cliente.get(f"/reuniones/{RID_PAPELERA}/{ruta}", headers=USUARIO)
    assert r.status_code == 404 and "presupuesto del trimestre" not in r.text


def test_la_ficha_de_una_reunion_en_la_papelera_no_ofrece_compartir(cliente):
    assert f'href="/reuniones/{RID_PAPELERA}/compartir"' not in cliente.get(f"/reuniones/{RID_PAPELERA}", headers=USUARIO).text
