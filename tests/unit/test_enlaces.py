"""Enlaces de los socios (@a44): `room`, `hash`, `push` y `label`, y nunca la contraseña.

Los valores de `hash` se calcularon con `hash_sala` de `scripts/actas_f0/analisis.py` de KubernetesInfrastructure (commit
c1b228c6397f0843ecfa3a4a77a3bd18a045dbd6, el último que tocó el fichero en origin/main el 2026-10-27): ese repo no se puede
importar en la CI de este."""

import urllib.parse

import pytest

from actas import enlaces


@pytest.mark.parametrize(
    ("clave", "salt", "esperado"),
    [
        ("k7m2p9qx4tz8wb3n", "reuniones.cenitdigital.es", "3931"),
        ("  k7m2p9qx4tz8wb3n ", "reuniones.cenitdigital.es", "3931"),  # sanitizePassword hace trim
        ("a b/c?d&é", "reuniones.cenitdigital.es", "0496"),  # lo que escapa encodeURIComponent
        ("Clave-Con_Mayús!~", "reuniones.cenitdigital.es", "a4fe"),  # y lo que no escapa
        ("abc", "otra.sal", "8d3a"),
    ],
)
def test_hash_igual_que_analisis_hash_sala(clave, salt, esperado):
    assert enlaces.hash_sala(clave, salt) == esperado


def test_hash_con_la_sal_del_sitio_por_defecto():
    assert enlaces.SAL_SITIO == "reuniones.cenitdigital.es"
    assert enlaces.hash_sala("k7m2p9qx4tz8wb3n") == "3931"


def test_hash_de_n_caracteres():
    assert enlaces.hash_sala("abc", "otra.sal", 8) == "8d3a" + enlaces.hash_sala("abc", "otra.sal", 8)[4:]
    assert len(enlaces.hash_sala("abc", "otra.sal", 8)) == 8


def _query(url: str) -> dict[str, list[str]]:
    partes = urllib.parse.urlsplit(url)
    assert f"{partes.scheme}://{partes.netloc}{partes.path}" == enlaces.BASE
    return urllib.parse.parse_qs(partes.query, keep_blank_values=True)


def test_enlace_del_socio():
    url = enlaces.enlace_socio("sala1abc", "k7m2p9qx4tz8wb3n", "pablo", "Pablo")
    assert _query(url) == {"room": ["sala1abc"], "hash": ["3931"], "push": ["pablo"], "label": ["Pablo"]}
    assert url == "https://reuniones.cenitdigital.es/?room=sala1abc&hash=3931&push=pablo&label=Pablo"


def test_enlace_sin_la_contrasena():
    clave = "k7m2p9qx4tz8wb3n"
    url = enlaces.enlace_socio("sala1abc", clave, "pablo", "Pablo")
    assert clave not in url
    assert "password" not in url
    assert "salt" not in url
    assert "pw=" not in url


def test_enlace_con_nombre_con_tilde_y_espacio():
    url = enlaces.enlace_socio("sala1abc", "k7m2p9qx4tz8wb3n", "andres", "Andrés M")
    assert _query(url)["label"] == ["Andrés M"]
    assert "Andr%C3%A9s" in url


def test_enlace_con_el_hash_ya_calculado_es_el_mismo():
    assert enlaces.enlace("sala1abc", "3931", "pablo", "Pablo") == enlaces.enlace_socio(
        "sala1abc", "k7m2p9qx4tz8wb3n", "pablo", "Pablo"
    )
