"""«Salas y socios» del panel (V2 de KubernetesInfrastructure#298) con el TestClient de Starlette contra PostgreSQL 18.6 y el rol
actas_panel: crear sala (@a43), enlaces de los socios (@a44), mostrar y copiar la contraseña con auditoría (@a45), «Grabar» con
sala (@a46, lado del panel) y alta de socios (@a47)."""

import html
import re
import urllib.parse

import pytest
from starlette.testclient import TestClient

from actas import enlaces, salas
from actas.formulario import Socio
from actas.panel import crear_app
from actas.registro import Registro

ORIGEN = "https://actas.cenitdigital.es"
VERSION = "2026-10-26"
TEXTOS = {VERSION: "# Información\n\nTexto informativo."}
SECRETO = "secreto-del-proxy"
PROXY = {"x-actas-proxy": SECRETO}
USUARIO = {**PROXY, "x-actas-usuario": "pablo"}
MISMO_ORIGEN = {**USUARIO, "sec-fetch-site": "same-origin", "origin": ORIGEN}
MAESTRA = bytes(range(32))


@pytest.fixture
def cliente(repo_panel):
    repo_panel.alta_socio(Socio("pablo", "Pablo", None))
    repo_panel.alta_socio(Socio("andres", "Andrés", "andres@cenitdigital.es"))
    repo_panel.alta_socio(Socio("roberto", "Roberto", None))
    repo_panel.socio_activo("roberto", False)
    app = crear_app(repo_panel, MAESTRA, TEXTOS, VERSION, ORIGEN, SECRETO, Registro())
    with TestClient(app, base_url=ORIGEN, follow_redirects=False) as c:
        yield c


def _crear(cliente, nombre="Socios semanal"):
    r = cliente.post("/salas", data={"nombre": nombre}, headers=MISMO_ORIGEN)
    assert r.status_code == 303, r.text
    sid = r.headers["location"].rsplit("/", 1)[1]
    return sid


def _volcado(repo):
    with repo.conexion() as c:
        return c.execute(
            "SELECT coalesce(string_agg(x, ' '), '') FROM (SELECT s::text AS x FROM salas s "
            "UNION ALL SELECT e::text FROM salas_eventos e UNION ALL SELECT encode(cifrada, 'escape') FROM salas) t"
        ).fetchone()[0]


def _clave(repo, sid):
    room, cifrada = repo.cifrada_de_sala(sid)
    return room, salas.descifrar(MAESTRA, room, cifrada)


# ── @a43 crear sala ───────────────────────────────────────────────────────────────────────────────────────────────────


def test_crear_sala_pide_confirmacion(cliente, repo):
    r = cliente.get("/salas/nueva", headers=USUARIO)
    assert r.status_code == 200
    assert 'action="/salas"' in r.text and "Crear sala" in r.text
    assert repo.salas() == []


def test_crear_sala_con_room_y_contrasena_aleatorias_y_cifradas(cliente, repo):
    sid = _crear(cliente)
    s = repo.sala(sid)
    room, clave = _clave(repo, sid)
    assert (s["nombre"], s["creada_por"]) == ("Socios semanal", "pablo")
    assert salas.ROOM.fullmatch(room) and len(room) == salas.LARGO_ROOM
    assert len(clave) == salas.LARGO_CLAVE and set(clave) <= set(salas.ALFABETO_CLAVE)
    assert s["hash"] == enlaces.hash_sala(clave)
    assert clave not in _volcado(repo)
    with pytest.raises(salas.ClaveNoValida):
        salas.descifrar(bytes(range(1, 33)), room, repo.cifrada_de_sala(sid)[1])


def test_dos_salas_distintas(cliente, repo):
    a, b = _crear(cliente, "A"), _crear(cliente, "B")
    assert _clave(repo, a)[0] != _clave(repo, b)[0] and _clave(repo, a)[1] != _clave(repo, b)[1]


@pytest.mark.parametrize("nombre", ["", "   ", "x" * 65, "con\nsalto"])
def test_crear_sala_con_nombre_no_valido_400_y_ninguna_fila(cliente, repo, nombre):
    r = cliente.post("/salas", data={"nombre": nombre}, headers=MISMO_ORIGEN)
    assert r.status_code == 400
    assert repo.salas() == []


def test_crear_sala_con_nombre_repetido_400(cliente, repo):
    _crear(cliente, "Socios")
    r = cliente.post("/salas", data={"nombre": "Socios"}, headers=MISMO_ORIGEN)
    assert r.status_code == 400 and "Ya hay una sala con ese nombre" in r.text
    assert len(repo.salas()) == 1


def test_crear_sala_de_otro_origen_403_y_ninguna_fila(cliente, repo):
    r = cliente.post(
        "/salas", data={"nombre": "X"}, headers={**USUARIO, "sec-fetch-site": "cross-site", "origin": "https://otra.example"}
    )
    assert r.status_code == 403
    assert repo.salas() == []


# ── @a44 enlaces ──────────────────────────────────────────────────────────────────────────────────────────────────────


def test_enlace_de_cada_socio_activo_sin_la_contrasena(cliente, repo):
    sid = _crear(cliente)
    room, clave = _clave(repo, sid)
    r = cliente.get(f"/salas/{sid}", headers=USUARIO)
    assert r.status_code == 200
    texto = html.unescape(r.text)
    assert clave not in texto and "password" not in texto
    urls = re.findall(r"https://reuniones\.cenitdigital\.es/\?[^\s<\"]+", texto)
    por_push = {urllib.parse.parse_qs(urllib.parse.urlsplit(u).query)["push"][0]: u for u in urls}
    assert set(por_push) == {"pablo", "andres"}  # roberto está de baja
    assert urllib.parse.parse_qs(urllib.parse.urlsplit(por_push["andres"]).query) == {
        "room": [room],
        "hash": [enlaces.hash_sala(clave)],
        "push": ["andres"],
        "label": ["Andrés"],
    }


def test_sala_que_no_existe_404(cliente):
    assert cliente.get("/salas/00000000-0000-4000-8000-000000000000", headers=USUARIO).status_code == 404
    assert cliente.get("/salas/no-es-uuid", headers=USUARIO).status_code == 404


# ── @a45 mostrar y copiar la contraseña ───────────────────────────────────────────────────────────────────────────────


def test_la_contrasena_no_se_ve_sin_pedirla(cliente, repo):
    sid = _crear(cliente)
    _, clave = _clave(repo, sid)
    assert clave not in cliente.get(f"/salas/{sid}", headers=USUARIO).text
    confirmar = cliente.get(f"/salas/{sid}/clave", headers=USUARIO)
    assert confirmar.status_code == 200 and clave not in confirmar.text
    assert f'action="/salas/{sid}/clave"' in confirmar.text
    assert [e["tipo"] for e in repo.eventos_de_sala(sid)] == ["sala_creada"]


def test_mostrar_la_contrasena_la_ensena_y_anota_clave_vista(cliente, repo):
    sid = _crear(cliente)
    _, clave = _clave(repo, sid)
    r = cliente.post(f"/salas/{sid}/clave", headers=MISMO_ORIGEN)
    assert r.status_code == 200
    assert clave in r.text
    assert r.headers["cache-control"] == "no-store"
    assert re.search(r'<button[^>]*data-copiar="clave"', r.text), "«Copiar» solo junto a la contraseña ya mostrada"
    eventos = repo.eventos_de_sala(sid)
    assert [(e["tipo"], e["usuario"]) for e in eventos] == [("sala_creada", "pablo"), ("clave_vista", "pablo")]
    assert clave not in _volcado(repo)


def test_mostrar_la_contrasena_de_otro_origen_403_sin_verla_ni_anotarla(cliente, repo):
    sid = _crear(cliente)
    _, clave = _clave(repo, sid)
    r = cliente.post(f"/salas/{sid}/clave", headers={**USUARIO, "sec-fetch-site": "cross-site", "origin": "https://otra.example"})
    assert r.status_code == 403 and clave not in r.text
    assert [e["tipo"] for e in repo.eventos_de_sala(sid)] == ["sala_creada"]


def test_mostrar_la_contrasena_de_una_sala_que_no_existe_404(cliente):
    assert cliente.post("/salas/00000000-0000-4000-8000-000000000000/clave", headers=MISMO_ORIGEN).status_code == 404


def test_con_otra_clave_del_panel_no_se_muestra_pero_queda_anotado(cliente, repo_panel):
    sid = _crear(cliente)
    otro = crear_app(repo_panel, bytes(range(1, 33)), TEXTOS, VERSION, ORIGEN, SECRETO, Registro())
    with TestClient(otro, base_url=ORIGEN, follow_redirects=False) as c:
        r = c.post(f"/salas/{sid}/clave", headers=MISMO_ORIGEN)
    assert r.status_code == 500 and "no se puede descifrar" in r.text
    assert [e["tipo"] for e in repo_panel.eventos_de_sala(sid)] == ["sala_creada", "clave_vista"]


def test_el_historial_de_la_sala_sin_la_contrasena(cliente, repo):
    sid = _crear(cliente)
    _, clave = _clave(repo, sid)
    cliente.post(f"/salas/{sid}/clave", headers=MISMO_ORIGEN)
    r = cliente.get(f"/salas/{sid}", headers=USUARIO)
    assert "Contraseña vista" in r.text and "Sala creada" in r.text and clave not in r.text


# ── @a47 socios ───────────────────────────────────────────────────────────────────────────────────────────────────────


def test_alta_de_un_socio(cliente, repo):
    r = cliente.post("/socios", data={"push": "pruebav2", "nombre": "Prueba V2", "correo": ""}, headers=MISMO_ORIGEN)
    assert r.status_code == 303 and r.headers["location"] == "/salas#socios"
    assert ("pruebav2", "Prueba V2", None, True) in [(s["push"], s["nombre"], s["correo"], s["activo"]) for s in repo.socios()]


def test_alta_de_un_socio_con_guiones_se_rechaza(cliente, repo):
    antes = repo.socios()
    r = cliente.post("/socios", data={"push": "socio-prueba", "nombre": "Prueba", "correo": ""}, headers=MISMO_ORIGEN)
    assert r.status_code == 400
    assert "sin guiones" in r.text
    assert repo.socios() == antes


def test_alta_de_un_socio_repetido_400(cliente, repo):
    r = cliente.post("/socios", data={"push": "pablo", "nombre": "Otro", "correo": ""}, headers=MISMO_ORIGEN)
    assert r.status_code == 400 and "Ya hay un socio con ese identificador" in r.text


def test_dar_de_baja_y_de_alta_un_socio(cliente, repo):
    r = cliente.post("/socios/pablo/activo", data={"activo": "0"}, headers=MISMO_ORIGEN)
    assert r.status_code == 303
    assert {s["push"]: s["activo"] for s in repo.socios()}["pablo"] is False
    cliente.post("/socios/pablo/activo", data={"activo": "1"}, headers=MISMO_ORIGEN)
    assert {s["push"]: s["activo"] for s in repo.socios()}["pablo"] is True


def test_dar_de_baja_un_socio_que_no_existe_404(cliente):
    assert cliente.post("/socios/nadie/activo", data={"activo": "0"}, headers=MISMO_ORIGEN).status_code == 404


def test_salas_y_socios_en_una_pantalla(cliente):
    _crear(cliente, "Socios semanal")
    r = cliente.get("/salas", headers=USUARIO)
    assert r.status_code == 200
    for texto in ["Socios semanal", "Crear sala nueva", "Pablo", "Andrés", "andres@cenitdigital.es", "Roberto", "de baja"]:
        assert texto in r.text


# ── «Grabar» con sala (@a46, lado del panel) ─────────────────────────────────────────────────────────────────────────


def test_grabar_ofrece_las_salas_y_solo_los_socios_activos(cliente):
    sid = _crear(cliente)
    r = cliente.get("/grabar", headers=USUARIO)
    assert f'value="{sid}"' in r.text
    assert 'value="pablo"' in r.text and 'value="andres"' in r.text and 'value="roberto"' not in r.text


def test_grabar_sin_salas_lleva_a_crear_una(cliente):
    r = cliente.get("/grabar", headers=USUARIO)
    assert 'href="/salas/nueva"' in r.text


def test_grabar_guarda_la_sala_de_la_reunion(cliente, repo):
    sid = _crear(cliente)
    r = cliente.post("/grabar", data={"sala": sid, "socio": ["pablo"], "version": VERSION}, headers=MISMO_ORIGEN)
    assert r.status_code == 303
    rid = r.headers["location"].rsplit("/", 1)[1]
    assert repo.reunion(rid)["sala_id"] == sid


@pytest.mark.parametrize("sala", [None, "", "no-es-uuid", "00000000-0000-4000-8000-000000000000"])
def test_grabar_sin_una_sala_valida_400_y_ninguna_fila(cliente, repo, sala):
    _crear(cliente)
    datos = {"socio": ["pablo"], "version": VERSION} | ({"sala": sala} if sala is not None else {})
    r = cliente.post("/grabar", data=datos, headers=MISMO_ORIGEN)
    assert r.status_code == 400
    assert repo.ultimas(10) == []


def test_grabar_a_un_socio_de_baja_400(cliente, repo):
    sid = _crear(cliente)
    r = cliente.post("/grabar", data={"sala": sid, "socio": ["roberto"], "version": VERSION}, headers=MISMO_ORIGEN)
    assert r.status_code == 400
    assert repo.ultimas(10) == []


def test_la_reunion_ensena_su_sala(cliente, repo):
    sid = _crear(cliente, "Socios semanal")
    r = cliente.post("/grabar", data={"sala": sid, "socio": ["pablo"], "version": VERSION}, headers=MISMO_ORIGEN)
    pagina = cliente.get(r.headers["location"], headers=USUARIO)
    assert f'href="/salas/{sid}"' in pagina.text and "Socios semanal" in pagina.text


def test_los_nombres_de_los_socios_de_baja_siguen_en_sus_reuniones(cliente, repo):
    sid = _crear(cliente)
    r = cliente.post("/grabar", data={"sala": sid, "socio": ["andres"], "version": VERSION}, headers=MISMO_ORIGEN)
    cliente.post("/socios/andres/activo", data={"activo": "0"}, headers=MISMO_ORIGEN)
    assert "Andrés" in cliente.get(r.headers["location"], headers=USUARIO).text
    assert "Andrés" in cliente.get("/", headers=USUARIO).text
