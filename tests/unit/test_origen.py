"""@a31: la defensa CSRF del panel (OWASP, «Fetch Metadata»: Sec-Fetch-Site primero y Origin de respaldo)."""

import pytest

from actas.origen import del_proxy, lectura_permitida, permitido

PANEL = "https://actas.cenitdigital.es"


@pytest.mark.parametrize(
    ("cabeceras", "esperado"),
    [
        ({"sec-fetch-site": "same-origin"}, True),
        ({"sec-fetch-site": "same-origin", "origin": PANEL}, True),
        ({"origin": PANEL}, True),
        ({"sec-fetch-site": "cross-site"}, False),
        ({"sec-fetch-site": "same-site"}, False),
        ({"sec-fetch-site": "none"}, False),
        ({"sec-fetch-site": "cross-site", "origin": PANEL}, False),
        ({"sec-fetch-site": "same-origin", "origin": "https://otro.example"}, False),
        ({"sec-fetch-site": "same-origin", "origin": "null"}, False),
        ({"origin": "null"}, False),
        ({"origin": "https://otro.example"}, False),
        ({"origin": PANEL + "/"}, False),
        ({"origin": "http://actas.cenitdigital.es"}, False),
        ({"origin": "https://actas.cenitdigital.es.otro.example"}, False),
        ({"sec-fetch-site": "SAME-ORIGIN"}, False),
        ({"sec-fetch-site": ""}, False),
        ({"origin": ""}, False),
        ({}, False),
    ],
)
def test_solo_el_mismo_origen(cabeceras, esperado):
    assert permitido(cabeceras, PANEL) is esperado


def test_el_origen_es_configurable():
    assert permitido({"origin": "http://127.0.0.1:8080"}, "http://127.0.0.1:8080") is True
    assert permitido({"origin": PANEL}, "http://127.0.0.1:8080") is False


@pytest.mark.parametrize(
    ("cabeceras", "esperado"),
    [
        ({}, True),
        ({"sec-fetch-site": "same-origin"}, True),
        ({"sec-fetch-site": "none"}, True),
        ({"sec-fetch-site": "cross-site", "sec-fetch-mode": "navigate", "sec-fetch-dest": "document"}, True),
        ({"sec-fetch-site": "same-site", "sec-fetch-mode": "navigate", "sec-fetch-dest": "document"}, True),
        ({"sec-fetch-site": "cross-site"}, False),
        ({"sec-fetch-site": "cross-site", "sec-fetch-mode": "no-cors", "sec-fetch-dest": "empty"}, False),
        ({"sec-fetch-site": "cross-site", "sec-fetch-mode": "navigate", "sec-fetch-dest": "iframe"}, False),
        ({"sec-fetch-site": "cross-site", "sec-fetch-mode": "cors", "sec-fetch-dest": "document"}, False),
        ({"sec-fetch-site": "same-site", "sec-fetch-mode": "no-cors", "sec-fetch-dest": "image"}, False),
        ({"sec-fetch-site": ""}, False),
        ({"sec-fetch-site": "", "sec-fetch-mode": "navigate", "sec-fetch-dest": "document"}, False),
    ],
)
def test_lectura_aislada_con_fetch_metadata(cabeceras, esperado):
    """M2 de la revisión de seguridad: una web ajena no puede pedir /buscar en segundo plano (XS-Search); sí enlazarlo."""
    assert lectura_permitida(cabeceras) is esperado


@pytest.mark.parametrize(
    ("recibido", "esperado"),
    [("s3creto", True), ("otro", False), ("", False), (None, False), ("s3creto ", False)],
)
def test_secreto_del_proxy(recibido, esperado):
    assert del_proxy(recibido, "s3creto") is esperado


def test_secreto_del_proxy_vacio_nunca_vale():
    assert del_proxy("", "") is False
