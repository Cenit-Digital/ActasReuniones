"""Rutas del panel con el TestClient de Starlette contra PostgreSQL 18.6 migrado y el rol actas_panel: @a22, @a29, @a30, @a31 y la
cabecera de usuario de Traefik."""

import pytest
from starlette.testclient import TestClient

from actas.conformidad import Peticion
from actas.estados import Estado
from actas.panel import crear_app
from actas.registro import Registro

ORIGEN = "https://actas.cenitdigital.es"
SOCIOS = {"pablo": "Pablo", "roberto": "Roberto", "andres": "Andrés"}
VERSION = "2026-10-26"
TEXTOS = {VERSION: "# Información\n\nTexto <b>informativo</b> de prueba."}
SECRETO = "secreto-del-proxy"
PROXY = {"x-actas-proxy": SECRETO}
USUARIO = {**PROXY, "x-actas-usuario": "panel"}
MISMO_ORIGEN = {**USUARIO, "sec-fetch-site": "same-origin", "origin": ORIGEN}


@pytest.fixture
def cliente(repo_panel):
    app = crear_app(repo_panel, SOCIOS, TEXTOS, VERSION, ORIGEN, SECRETO, Registro())
    with TestClient(app, base_url=ORIGEN, follow_redirects=False) as c:
        yield c


def _cuenta(repo):
    with repo.conexion() as c:
        return c.execute("SELECT (SELECT count(*) FROM reuniones), (SELECT count(*) FROM conformidades)").fetchone()


def _grabando(repo):
    rid = repo.pedir(Peticion(("pablo",), "v1"))
    repo.mover(rid, Estado.PEDIDA, Estado.GRABANDO, inicio=True)
    return rid


def _transcrita(repo, segmentos, socios=("sociopruebaa",)):
    rid = repo.pedir(Peticion(socios, "v1"))
    for d, h in [(Estado.PEDIDA, Estado.GRABANDO), (Estado.GRABANDO, Estado.GRABADA), (Estado.GRABADA, Estado.TRANSCRIBIENDO)]:
        repo.mover(rid, d, h, inicio=d is Estado.PEDIDA, fin=d is Estado.GRABANDO)
    repo.guardar_transcripcion(rid, segmentos)
    return rid


# ── Cabecera de usuario (Traefik, headerField) ──────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("ruta", ["/", "/grabar", "/buscar?q=hola", "/estilo.css"])
def test_sin_usuario_401(cliente, ruta):
    assert cliente.get(ruta, headers=PROXY).status_code == 401


@pytest.mark.parametrize("valor", ["", "pa blo", "x" * 65])
def test_usuario_mal_formado_401(cliente, valor):
    assert cliente.get("/", headers={**PROXY, "x-actas-usuario": valor}).status_code == 401


@pytest.mark.parametrize("variante", ["x_actas_usuario", "X_Actas_Usuario", "x-actas_usuario"])
def test_solo_vale_la_cabecera_de_usuario_exacta(cliente, repo, variante):
    """Traefik solo sobrescribe X-Actas-Usuario exacta: una variante con guion bajo (estilo CGI) no cuenta como usuario."""
    assert cliente.get("/", headers={**PROXY, variante: "intruso"}).status_code == 401
    r = cliente.post(
        "/grabar", data={"socio": ["pablo"], "version": VERSION}, headers={**PROXY, variante: "intruso", "origin": ORIGEN}
    )
    assert r.status_code == 401
    assert _cuenta(repo) == (0, 0)


@pytest.mark.parametrize("proxy", [{}, {"x-actas-proxy": "otro"}, {"x-actas-proxy": ""}])
def test_sin_el_secreto_de_traefik_401_aunque_traiga_usuario(cliente, repo, proxy):
    """M1: un camino al pod que no sea la ruta de Traefik no puede hacerse pasar por un usuario."""
    assert cliente.get("/", headers={"x-actas-usuario": "panel", **proxy}).status_code == 401
    r = cliente.post(
        "/grabar",
        data={"socio": ["pablo"], "version": VERSION},
        headers={"x-actas-usuario": "panel", "sec-fetch-site": "same-origin", **proxy},
    )
    assert r.status_code == 401
    assert _cuenta(repo) == (0, 0)


@pytest.mark.parametrize(
    ("cabeceras", "estado"),
    [
        ({"sec-fetch-site": "cross-site", "sec-fetch-mode": "no-cors", "sec-fetch-dest": "empty"}, 403),
        ({"sec-fetch-site": "same-site", "sec-fetch-mode": "cors", "sec-fetch-dest": "empty"}, 403),
        ({"sec-fetch-site": "cross-site", "sec-fetch-mode": "navigate", "sec-fetch-dest": "iframe"}, 403),
        ({"sec-fetch-site": "cross-site", "sec-fetch-mode": "navigate", "sec-fetch-dest": "document"}, 200),
        ({"sec-fetch-site": "none", "sec-fetch-mode": "navigate", "sec-fetch-dest": "document"}, 200),
    ],
)
def test_busqueda_aislada_de_otras_webs(cliente, cabeceras, estado):
    """M2: XS-Search. Una web ajena no puede pedir /buscar en segundo plano; un enlace sí abre la página."""
    assert cliente.get("/buscar", params={"q": "hola"}, headers={**USUARIO, **cabeceras}).status_code == estado


def test_grabar_sin_usuario_401_y_nada_escrito(cliente, repo):
    r = cliente.post("/grabar", data={"socio": ["pablo"], "version": VERSION}, headers={**PROXY, "sec-fetch-site": "same-origin"})
    assert r.status_code == 401
    assert _cuenta(repo) == (0, 0)


def test_parar_sin_usuario_401_y_nada_escrito(cliente, repo):
    rid = _grabando(repo)
    assert cliente.post("/parar", headers={**PROXY, "sec-fetch-site": "same-origin"}).status_code == 401
    assert repo.reunion(rid)["parar_pedido_en"] is None


# ── Cabeceras de seguridad ──────────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(("ruta", "cabeceras"), [("/", USUARIO), ("/no-existe", USUARIO), ("/", {}), ("/salud", {})])
def test_csp_estricta_en_todas_las_respuestas(cliente, ruta, cabeceras):
    r = cliente.get(ruta, headers=cabeceras)
    assert r.headers["content-security-policy"] == (
        "default-src 'none'; style-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'"
    )
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["referrer-policy"] == "same-origin"
    assert r.headers["cache-control"] == "no-store"
    assert r.headers["cross-origin-resource-policy"] == "same-origin"
    assert r.headers["cross-origin-opener-policy"] == "same-origin"
    assert "server" not in r.headers


def test_hoja_de_estilo_propia(cliente):
    r = cliente.get("/estilo.css", headers=USUARIO)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/css")


def test_sin_javascript(cliente, repo):
    _transcrita(repo, [{"hablante": "sociopruebaa", "inicio_ms": 0, "fin_ms": 1, "texto": "hola"}])
    for ruta in ["/", "/grabar", "/buscar?q=hola"]:
        assert "<script" not in cliente.get(ruta, headers=USUARIO).text


# ── Lista y reunión ─────────────────────────────────────────────────────────────────────────────────────────────────────


def test_lista_con_fecha_duracion_estado_motivo_y_socios(cliente, repo):
    rid = _transcrita(repo, [{"hablante": "pablo", "inicio_ms": 0, "fin_ms": 1, "texto": "hola"}], socios=("pablo", "andres"))
    r = cliente.get("/", headers=USUARIO)
    assert r.status_code == 200
    assert f'href="/reuniones/{rid}"' in r.text
    assert "transcrita" in r.text and "Pablo, Andrés" in r.text
    assert "00:00:00" in r.text  # duración: inicio y fin en la misma transacción de prueba


def test_reunion_con_transcripcion_hablante_y_tiempo(cliente, repo):
    rid = _transcrita(
        repo,
        [
            {"hablante": "pablo", "inicio_ms": 3_725_000, "fin_ms": 3_726_000, "texto": "Doy mi conformidad <script>x</script>"},
        ],
        socios=("pablo",),
    )
    r = cliente.get(f"/reuniones/{rid}", headers=USUARIO)
    assert r.status_code == 200
    assert "01:02:05" in r.text and "Pablo" in r.text
    assert "&lt;script&gt;x&lt;/script&gt;" in r.text and "<script>" not in r.text


@pytest.mark.parametrize("rid", ["no-es-uuid", "00000000-0000-0000-0000-000000000000"])
def test_reunion_que_no_existe_404(cliente, rid):
    assert cliente.get(f"/reuniones/{rid}", headers=USUARIO).status_code == 404


# ── @a22 búsqueda ───────────────────────────────────────────────────────────────────────────────────────────────────────


def test_buscar_presupuesto(cliente, repo):
    rid = _transcrita(repo, [{"hablante": "sociopruebaa", "inicio_ms": 75_000, "fin_ms": 80_000, "texto": "el presupuesto"}])
    r = cliente.get("/buscar", params={"q": "presupuesto"}, headers=USUARIO)
    assert r.status_code == 200
    assert f'href="/reuniones/{rid}"' in r.text
    assert "sociopruebaa" in r.text and "00:01:15" in r.text
    assert "<mark>presupuesto</mark>" in r.text


def test_buscar_escapa_el_fragmento(cliente, repo):
    _transcrita(repo, [{"hablante": "sociopruebaa", "inicio_ms": 0, "fin_ms": 1, "texto": "presupuesto 1 < 2 & <img"}])
    r = cliente.get("/buscar", params={"q": "presupuesto"}, headers=USUARIO)
    assert "1 &lt; 2 &amp;" in r.text and "<img" not in r.text


def test_buscar_un_segmento_con_script_lo_muestra_como_texto(cliente, repo):
    """@a22 tal cual: ts_headline borra lo que toma por etiquetas; el panel se las oculta y las devuelve escapadas."""
    _transcrita(
        repo, [{"hablante": "sociopruebaa", "inicio_ms": 0, "fin_ms": 1, "texto": "presupuesto <script>x</script> & fin"}]
    )
    r = cliente.get("/buscar", params={"q": "presupuesto"}, headers=USUARIO)
    assert "<mark>presupuesto</mark> &lt;script&gt;x&lt;/script&gt; &amp; fin" in r.text
    assert "<script>" not in r.text


def test_buscar_vacio_no_consulta(cliente):
    r = cliente.get("/buscar", params={"q": "   "}, headers=USUARIO)
    assert r.status_code == 200 and "<mark>" not in r.text


def test_buscar_escapa_la_consulta_en_el_formulario(cliente):
    r = cliente.get("/buscar", params={"q": '"><b>x'}, headers=USUARIO)
    assert "&#34;&gt;&lt;b&gt;x" in r.text and "<b>x" not in r.text


# ── @a29 grabar ─────────────────────────────────────────────────────────────────────────────────────────────────────────


def test_formulario_grabar_con_socios_version_y_texto(cliente):
    r = cliente.get("/grabar", headers=USUARIO)
    assert r.status_code == 200
    for sid, nombre in SOCIOS.items():
        assert f'value="{sid}"' in r.text and nombre in r.text
    assert f'name="version" value="{VERSION}"' in r.text
    assert "Texto &lt;b&gt;informativo&lt;/b&gt; de prueba." in r.text


def test_grabar_con_socios_validos(cliente, repo):
    r = cliente.post("/grabar", data={"socio": ["roberto", "pablo"], "version": VERSION}, headers=MISMO_ORIGEN)
    assert r.status_code == 303
    (fila,) = repo.ultimas(10)
    assert r.headers["location"] == f"/reuniones/{fila['id']}"
    assert (fila["estado"], fila["socios"], fila["pedido_por"]) == ("pedida", ["pablo", "roberto"], "panel")
    assert repo.conformidades(fila["id"]) == [("pablo", VERSION), ("roberto", VERSION)]


@pytest.mark.parametrize(
    "datos",
    [
        {"version": VERSION},
        {"socio": ["pablo", "intruso"], "version": VERSION},
        {"socio": ["pablo"], "version": "v 1"},
        {"socio": ["pablo"], "version": "otra"},
        {"socio": ["pablo"]},
        {"socio": ["Pablo"], "version": VERSION},
    ],
)
def test_grabar_no_valido_400_y_ninguna_fila(cliente, repo, datos):
    assert cliente.post("/grabar", data=datos, headers=MISMO_ORIGEN).status_code == 400
    assert _cuenta(repo) == (0, 0)


def test_grabar_con_demasiados_campos_400(cliente, repo):
    datos = {"socio": ["pablo"] * 100, "version": VERSION}
    assert cliente.post("/grabar", data=datos, headers=MISMO_ORIGEN).status_code == 400
    assert _cuenta(repo) == (0, 0)


def test_grabar_con_cuerpo_demasiado_grande_413(cliente, repo):
    datos = {"socio": ["pablo"], "version": VERSION, "relleno": "x" * 20_000}
    assert cliente.post("/grabar", data=datos, headers=MISMO_ORIGEN).status_code == 413
    assert _cuenta(repo) == (0, 0)


def _trozos(datos: bytes):
    yield datos[:10]
    yield datos[10:]


def test_grabar_con_cuerpo_por_trozos_sin_content_length(cliente, repo):
    # Traefik reenvía por trozos (Transfer-Encoding: chunked) si no conoce la longitud: el tope se cuenta, sin exigir la cabecera.
    cuerpo = f"socio=pablo&version={VERSION}".encode()
    r = cliente.post(
        "/grabar",
        content=_trozos(cuerpo),
        headers={**MISMO_ORIGEN, "content-type": "application/x-www-form-urlencoded"},
    )
    assert r.status_code == 303
    assert _cuenta(repo) == (1, 1)


def test_grabar_por_trozos_demasiado_grande_413(cliente, repo):
    cuerpo = f"socio=pablo&version={VERSION}&relleno={'x' * 20_000}".encode()
    r = cliente.post(
        "/grabar",
        content=_trozos(cuerpo),
        headers={**MISMO_ORIGEN, "content-type": "application/x-www-form-urlencoded"},
    )
    assert r.status_code == 413
    assert _cuenta(repo) == (0, 0)


def test_grabar_con_ficheros_400(cliente, repo):
    r = cliente.post("/grabar", data={"version": VERSION}, files={"socio": ("a.txt", b"pablo")}, headers=MISMO_ORIGEN)
    assert r.status_code == 400
    assert _cuenta(repo) == (0, 0)


# ── @a30 parar ──────────────────────────────────────────────────────────────────────────────────────────────────────────


def test_parar_la_grabacion_activa(cliente, repo):
    rid = _grabando(repo)
    r = cliente.post("/parar", headers=MISMO_ORIGEN)
    assert (r.status_code, r.headers["location"]) == (303, f"/reuniones/{rid}")
    assert repo.reunion(rid)["parar_pedido_en"] is not None


def test_parar_sin_grabacion_activa_lo_dice_y_no_escribe(cliente, repo):
    rid = repo.pedir(Peticion(("pablo",), "v1"))
    antes = repo.reunion(rid)
    r = cliente.post("/parar", headers=MISMO_ORIGEN)
    assert r.status_code == 409 and "No hay ninguna grabación activa" in r.text
    assert repo.reunion(rid) == antes


def test_la_lista_ofrece_parar_solo_con_una_grabacion_activa(cliente, repo):
    assert 'action="/parar"' not in cliente.get("/", headers=USUARIO).text
    _grabando(repo)
    assert 'action="/parar"' in cliente.get("/", headers=USUARIO).text


def test_la_lista_ofrece_parar_aunque_la_activa_no_este_entre_las_ultimas(cliente, repo, monkeypatch):
    import actas.panel

    monkeypatch.setattr(actas.panel, "TOPE_LISTA", 1)
    _grabando(repo)
    repo.pedir(Peticion(("pablo",), "v1"))
    assert 'action="/parar"' in cliente.get("/", headers=USUARIO).text


# ── @a31 CSRF ───────────────────────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "cabeceras",
    [
        {"sec-fetch-site": "cross-site"},
        {"sec-fetch-site": "same-site"},
        {"origin": "https://otro.example"},
        {"origin": "null"},
        {"sec-fetch-site": "same-origin", "origin": "null"},
        {},
    ],
)
def test_csrf_grabar_403_y_ninguna_fila(cliente, repo, cabeceras):
    r = cliente.post("/grabar", data={"socio": ["pablo"], "version": VERSION}, headers={**USUARIO, **cabeceras})
    assert r.status_code == 403
    assert _cuenta(repo) == (0, 0)


@pytest.mark.parametrize(
    "cabeceras", [{"sec-fetch-site": "cross-site"}, {"origin": "null"}, {"origin": "https://otro.example"}, {}]
)
def test_csrf_parar_403_y_nada_escrito(cliente, repo, cabeceras):
    rid = _grabando(repo)
    assert cliente.post("/parar", headers={**USUARIO, **cabeceras}).status_code == 403
    assert repo.reunion(rid)["parar_pedido_en"] is None


def test_grabar_solo_con_origin_del_panel(cliente, repo):
    r = cliente.post("/grabar", data={"socio": ["pablo"], "version": VERSION}, headers={**USUARIO, "origin": ORIGEN})
    assert r.status_code == 303
    assert _cuenta(repo) == (1, 1)
