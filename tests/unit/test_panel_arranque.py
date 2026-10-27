"""Arranque del panel (`python -m actas.panel`): uvicorn sin registro de accesos ni cabecera Server y con tope de concurrencia
(@a32), y errores sin rastro del texto de la petición ni de la base."""

import base64

import pytest
from starlette.testclient import TestClient

from actas.panel import cargar_textos, crear_app
from actas.panel.__main__ import configuracion, preparar
from actas.registro import Registro

MAESTRA = base64.b64encode(bytes(range(32))).decode()


@pytest.fixture
def entorno(tmp_path):
    f = tmp_path / "CLAVE"
    f.write_text(MAESTRA + "\n", encoding="utf-8")
    p = tmp_path / "proxy"
    p.write_text("secreto-del-proxy\n", encoding="utf-8")
    return {
        "ACTAS_DSN": "postgresql:///actas",
        "ACTAS_SALAS_CLAVE_FICHERO": str(f),
        "ACTAS_SECRETO_PROXY_FICHERO": str(p),
        "PGPASSWORD": "clave-secreta",
    }


def test_uvicorn_sin_registro_de_accesos_ni_server_ni_proxy(entorno):
    c = configuracion(object(), entorno)
    assert c.access_log is False
    assert c.server_header is False
    assert c.proxy_headers is False
    assert c.limit_concurrency is None  # el tope va en el panel y por peticiones: ver test_la_sonda_*
    assert (c.host, c.port) == ("0.0.0.0", 8080)  # noqa: S104 — lo que se comprueba
    assert c.lifespan == "off"


def test_uvicorn_configurable(entorno):
    c = configuracion(object(), {**entorno, "ACTAS_PANEL_PUERTO": "9000"})
    assert c.port == 9000


def test_el_tope_de_peticiones_se_configura_como_antes(entorno):
    app, _ = preparar(entorno)
    assert app.tope == 16  # type: ignore[attr-defined]
    app, _ = preparar({**entorno, "ACTAS_PANEL_CONCURRENCIA": "20"})
    assert app.tope == 20  # type: ignore[attr-defined]


def test_preparar_lee_la_clave_de_las_salas_textos_y_origen(entorno):
    app, registro = preparar(entorno)
    assert registro.secretos == ["clave-secreta", "secreto-del-proxy", MAESTRA]
    assert callable(app)


def test_preparar_con_una_version_que_no_existe_falla(entorno):
    from actas.formulario import TextoNoValido

    with pytest.raises(TextoNoValido):
        preparar({**entorno, "ACTAS_TEXTO_VERSION": "no-existe"})


def test_preparar_sin_secreto_del_proxy_falla(entorno, tmp_path):
    (tmp_path / "vacio").write_text("\n", encoding="utf-8")
    with pytest.raises(ValueError):
        preparar({**entorno, "ACTAS_SECRETO_PROXY_FICHERO": str(tmp_path / "vacio")})
    sin = dict(entorno)
    del sin["ACTAS_SECRETO_PROXY_FICHERO"]
    with pytest.raises(KeyError):
        preparar(sin)


def test_preparar_sin_la_clave_de_las_salas_falla(entorno, tmp_path):
    from actas.salas import ClaveNoValida

    with pytest.raises(FileNotFoundError):
        preparar({**entorno, "ACTAS_SALAS_CLAVE_FICHERO": str(tmp_path / "no")})
    (tmp_path / "corta").write_text(base64.b64encode(bytes(16)).decode(), encoding="utf-8")
    with pytest.raises(ClaveNoValida):
        preparar({**entorno, "ACTAS_SALAS_CLAVE_FICHERO": str(tmp_path / "corta")})


def test_preparar_ya_no_lee_el_fichero_de_socios(entorno, tmp_path):
    app, _ = preparar({**entorno, "ACTAS_SOCIOS_FICHERO": str(tmp_path / "no")})
    assert callable(app)


def test_el_texto_empaquetado_tiene_la_frase_de_conformidad():
    textos = cargar_textos()
    assert "2026-10-26" in textos
    assert "«Doy mi conformidad para grabar esta reunión»" in textos["2026-10-26"]


def test_cargar_textos_ignora_los_que_no_son_informativos(tmp_path):
    (tmp_path / "informativo-v1.md").write_text("uno", encoding="utf-8")
    (tmp_path / "informativo-v 2.md").write_text("dos", encoding="utf-8")
    (tmp_path / "otro.md").write_text("tres", encoding="utf-8")
    assert cargar_textos(tmp_path) == {"v1": "uno"}


def test_cargar_textos_sin_ninguno_falla(tmp_path):
    with pytest.raises(FileNotFoundError):
        cargar_textos(tmp_path)


class _BaseRota:
    def buscar(self, *_):
        raise RuntimeError("Failing row contains (marca-unica-del-segmento)")


def test_un_error_no_deja_rastro_de_la_peticion_ni_de_la_base(capsys):
    app = crear_app(_BaseRota(), bytes(32), {"v1": "x"}, "v1", "https://actas.cenitdigital.es", "s", Registro())  # type: ignore[arg-type]
    with TestClient(app) as c:
        cabeceras = {"x-actas-usuario": "panel", "x-actas-proxy": "s"}
        r = c.get("/buscar", params={"q": "marca-unica-de-la-busqueda"}, headers=cabeceras)
    assert r.status_code == 500 and "marca" not in r.text
    assert r.headers["content-security-policy"].startswith("default-src 'none'")
    err = capsys.readouterr()
    assert "petición fallida: RuntimeError" in err.err
    assert "marca" not in err.err + err.out


def test_salud_sin_usuario_ni_base():
    class SinBase:
        def __getattr__(self, _):
            raise AssertionError("la sonda no toca la base")

    app = crear_app(SinBase(), bytes(32), {"v1": "x"}, "v1", "https://actas.cenitdigital.es", "s", Registro())  # type: ignore[arg-type]
    with TestClient(app) as c:
        r = c.get("/salud")
    assert (r.status_code, r.text) == (200, "ok")


def test_el_panel_pide_las_fechas_en_hora_de_madrid(entorno, monkeypatch):
    import actas.panel.__main__ as m

    vistos = {}

    class Repo:
        def __init__(self, dsn, ajustes=None):
            vistos.update(dsn=dsn, ajustes=ajustes)

    monkeypatch.setattr(m, "Repositorio", Repo)
    preparar(entorno)
    assert vistos == {"dsn": "postgresql:///actas", "ajustes": {"TimeZone": "Europe/Madrid", "statement_timeout": "5s"}}


def test_como_mucho_n_consultas_a_la_vez():
    """B3: uvicorn cuenta conexiones (también las keep-alive ociosas de Traefik), así que el tope de la base va aparte."""
    import threading
    import time

    import anyio
    import httpx2

    vivas = {"ahora": 0, "maximo": 0}
    candado = threading.Lock()

    class Lenta:
        def buscar(self, *_):
            with candado:
                vivas["ahora"] += 1
                vivas["maximo"] = max(vivas["maximo"], vivas["ahora"])
            time.sleep(0.05)
            with candado:
                vivas["ahora"] -= 1
            return []

    app = crear_app(Lenta(), bytes(32), {"v1": "x"}, "v1", "https://a.example", "s", Registro(), conexiones=2)  # type: ignore[arg-type]

    async def todas():
        cabeceras = {"x-actas-usuario": "panel", "x-actas-proxy": "s"}
        transporte = httpx2.ASGITransport(app=app)
        async with httpx2.AsyncClient(transport=transporte, base_url="https://a.example", headers=cabeceras) as c:
            async with anyio.create_task_group() as tg:
                for _ in range(8):
                    tg.start_soon(c.get, "/buscar?q=hola")

    anyio.run(todas)
    assert vivas["maximo"] == 2


# ── Sonda de vida (reinicio del panel a las 22:10 UTC del 2026-10-26, KubernetesInfrastructure#287) ──────────────────────
# uvicorn 0.4x, protocols/http/h11_impl.py: con `limit_concurrency`, «len(self.connections) >= self.limit_concurrency» da 503
# a cualquier petición, y una conexión keep-alive ociosa (Traefik las guarda; uvicorn las cierra a los 5 s) cuenta. Con 16
# ocupadas, la sonda de vida de /salud recibía 503 y, a la tercera, el kubelet paraba el contenedor de forma ordenada.


def _servidor(app, entorno):
    import socket
    import threading
    import time

    import uvicorn

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        puerto = s.getsockname()[1]
    cfg = configuracion(app, {**entorno, "ACTAS_PANEL_PUERTO": str(puerto)})
    cfg.host = "127.0.0.1"
    srv = uvicorn.Server(cfg)
    threading.Thread(target=srv.run, daemon=True).start()
    for _ in range(100):
        if srv.started:
            break
        time.sleep(0.05)
    return srv, puerto


def _ociosa(puerto):
    import socket

    s = socket.create_connection(("127.0.0.1", puerto))
    s.sendall(b"GET /salud HTTP/1.1\r\nHost: panel\r\n\r\n")
    s.recv(1000)
    return s


def test_la_sonda_responde_aunque_haya_conexiones_ociosas(entorno):
    import urllib.request

    app = crear_app(object(), bytes(32), {"v1": "x"}, "v1", "https://a.example", "s", Registro(), concurrencia=4)  # type: ignore[arg-type]
    srv, puerto = _servidor(app, entorno)
    ociosas = [_ociosa(puerto) for _ in range(8)]
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{puerto}/salud", timeout=5) as r:  # noqa: S310 — local
            assert (r.status, r.read()) == (200, b"ok")
    finally:
        for s in ociosas:
            s.close()
        srv.should_exit = True


def test_tope_de_peticiones_en_curso_salvo_la_sonda_y_los_estaticos():
    import threading

    import anyio
    import httpx2

    soltar = threading.Event()
    dentro = threading.Semaphore(0)

    class Lenta:
        def buscar(self, *_):
            dentro.release()
            soltar.wait(5)
            return []

    app = crear_app(Lenta(), bytes(32), {"v1": "x"}, "v1", "https://a.example", "s", Registro(), concurrencia=2)  # type: ignore[arg-type]
    estados: dict[str, int] = {}

    async def todas():
        cabeceras = {"x-actas-usuario": "panel", "x-actas-proxy": "s"}
        transporte = httpx2.ASGITransport(app=app)
        async with httpx2.AsyncClient(transport=transporte, base_url="https://a.example", headers=cabeceras) as c:

            async def lenta(n):
                estados[f"lenta{n}"] = (await c.get("/buscar", params={"q": "hola"})).status_code

            async with anyio.create_task_group() as tg:
                tg.start_soon(lenta, 1)
                tg.start_soon(lenta, 2)
                for _ in range(2):
                    await anyio.to_thread.run_sync(dentro.acquire)
                tercera = await c.get("/buscar", params={"q": "hola"})
                estados["tercera"] = tercera.status_code
                estados["reintentar"] = int(tercera.headers["retry-after"])
                estados["salud"] = (await c.get("/salud")).status_code
                estados["fuente"] = (await c.get("/fuentes/manrope-latin.woff2")).status_code
                # Sin el secreto de Traefik, 401 aunque el tope esté lleno: la autenticación va antes que el 503.
                estados["sin_credenciales"] = (await c.get("/buscar", headers={"x-actas-proxy": "otro"})).status_code
                soltar.set()
            estados["despues"] = (await c.get("/buscar", params={"q": "hola"})).status_code

    anyio.run(todas)
    esperados = {"tercera": 503, "reintentar": 1, "salud": 200, "fuente": 200, "sin_credenciales": 401}
    assert estados == {**esperados, "lenta1": 200, "lenta2": 200, "despues": 200}
