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
    return {"ACTAS_DSN": "postgresql:///actas", "ACTAS_SOCIOS_FICHERO": str(f), "PGPASSWORD": "clave-secreta"}


def test_uvicorn_sin_registro_de_accesos_ni_server_ni_proxy(entorno):
    c = configuracion(object(), entorno)
    assert c.access_log is False
    assert c.server_header is False
    assert c.proxy_headers is False
    assert c.limit_concurrency == 4
    assert (c.host, c.port) == ("0.0.0.0", 8080)  # noqa: S104 — lo que se comprueba
    assert c.lifespan == "off"


def test_uvicorn_configurable(entorno):
    c = configuracion(object(), {**entorno, "ACTAS_PANEL_PUERTO": "9000", "ACTAS_PANEL_CONCURRENCIA": "2"})
    assert (c.port, c.limit_concurrency) == (9000, 2)


def test_preparar_lee_socios_textos_y_origen(entorno):
    app, registro = preparar(entorno)
    assert registro.secretos == ["clave-secreta"]
    assert callable(app)


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
    app = crear_app(_BaseRota(), {"pablo": "Pablo"}, {"v1": "x"}, "https://actas.cenitdigital.es", Registro())  # type: ignore[arg-type]
    with TestClient(app) as c:
        r = c.get("/buscar", params={"q": "marca-unica-de-la-busqueda"}, headers={"x-actas-usuario": "panel"})
    assert r.status_code == 500 and "marca" not in r.text
    assert r.headers["content-security-policy"].startswith("default-src 'none'")
    err = capsys.readouterr()
    assert "petición fallida: RuntimeError" in err.err
    assert "marca" not in err.err + err.out
