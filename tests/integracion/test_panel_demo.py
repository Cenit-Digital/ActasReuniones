"""El panel de demostración de la puerta de diseño (`panel_demo.py`, docs/impeccable.md): sirve con 200 cada ruta de `ui.routes`
sin que la petición traiga las cabeceras de Traefik, y esas rutas son exactamente las de harness.config.json."""

import json
from pathlib import Path

import pytest
from panel_demo import RUTAS, crear_demo
from starlette.testclient import TestClient

CONFIG = Path(__file__).resolve().parents[2] / "harness.config.json"
ORIGEN = "http://127.0.0.1:4310"


def test_las_rutas_de_la_demo_son_las_de_ui_routes():
    assert json.loads(CONFIG.read_text(encoding="utf-8"))["ui"]["routes"] == RUTAS


@pytest.mark.parametrize("ruta", RUTAS)
def test_la_demo_sirve_cada_ruta_sin_redirigir(ruta):
    with TestClient(crear_demo(ORIGEN), base_url=ORIGEN) as cliente:
        r = cliente.get(ruta, follow_redirects=False)
    assert r.status_code == 200, ruta
    assert "/estilo.css" in r.text
