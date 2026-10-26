"""Arranque del panel (`python -m actas.panel`): uvicorn sin registro de accesos ni cabecera Server y con tope de concurrencia
(@a32), y errores sin rastro del texto de la petición ni de la base."""

import json

import pytest
from starlette.testclient import TestClient

from actas.panel import cargar_textos, crear_app
from actas.panel.__main__ import configuracion, preparar
from actas.registro import Registro

SOCIOS = json.dumps([{"id": "pablo", "nombre": "Pablo"}])


@pytest.fixture
def entorno(tmp_path):
    f = tmp_path / "socios.json"
    f.write_text(SOCIOS, encoding="utf-8")
    p = tmp_path / "proxy"
    p.write_text("secreto-del-proxy\n", encoding="utf-8")
    return {
        "ACTAS_DSN": "postgresql:///actas",
        "ACTAS_SOCIOS_FICHERO": str(f),
        "ACTAS_SECRETO_PROXY_FICHERO": str(p),
        "PGPASSWORD": "clave-secreta",
    }


def test_uvicorn_sin_registro_de_accesos_ni_server_ni_proxy(entorno):
    c = configuracion(object(), entorno)
    assert c.access_log is False
    assert c.server_header is False
    assert c.proxy_headers is False
    assert c.limit_concurrency == 16
    assert (c.host, c.port) == ("0.0.0.0", 8080)  # noqa: S104 — lo que se comprueba
    assert c.lifespan == "off"


def test_uvicorn_configurable(entorno):
    c = configuracion(object(), {**entorno, "ACTAS_PANEL_PUERTO": "9000", "ACTAS_PANEL_CONCURRENCIA": "20"})
    assert (c.port, c.limit_concurrency) == (9000, 20)


def test_preparar_lee_socios_textos_y_origen(entorno):
    app, registro = preparar(entorno)
    assert registro.secretos == ["clave-secreta", "secreto-del-proxy"]
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


def test_preparar_sin_fichero_de_socios_falla(entorno, tmp_path):
    with pytest.raises(FileNotFoundError):
        preparar({**entorno, "ACTAS_SOCIOS_FICHERO": str(tmp_path / "no")})


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
    app = crear_app(_BaseRota(), {"pablo": "Pablo"}, {"v1": "x"}, "v1", "https://actas.cenitdigital.es", "s", Registro())  # type: ignore[arg-type]
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

    app = crear_app(SinBase(), {"pablo": "Pablo"}, {"v1": "x"}, "v1", "https://actas.cenitdigital.es", "s", Registro())  # type: ignore[arg-type]
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

    app = crear_app(Lenta(), {"pablo": "Pablo"}, {"v1": "x"}, "v1", "https://a.example", "s", Registro(), conexiones=2)  # type: ignore[arg-type]

    async def todas():
        cabeceras = {"x-actas-usuario": "panel", "x-actas-proxy": "s"}
        transporte = httpx2.ASGITransport(app=app)
        async with httpx2.AsyncClient(transport=transporte, base_url="https://a.example", headers=cabeceras) as c:
            async with anyio.create_task_group() as tg:
                for _ in range(8):
                    tg.start_soon(c.get, "/buscar?q=hola")

    anyio.run(todas)
    assert vivas["maximo"] == 2
