"""@a31: la defensa CSRF del panel (OWASP, «Fetch Metadata»: Sec-Fetch-Site primero y Origin de respaldo)."""

import pytest

from actas.origen import permitido

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
