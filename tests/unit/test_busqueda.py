"""@a22: la búsqueda del panel. La consulta se normaliza antes de llegar a `websearch_to_tsquery` y el resaltado de
`ts_headline` se escapa antes de marcar (su salida «is not guaranteed to be safe for direct inclusion in web pages»)."""

import pytest
from markupsafe import Markup

from actas.busqueda import (
    FIN,
    INICIO,
    LIMITE,
    OPCIONES,
    PONER,
    QUITAR,
    SUSTITUTOS,
    TOPE_CONSULTA,
    normalizar,
    resaltar,
    sin_centinelas,
)


@pytest.mark.parametrize(
    ("q", "esperado"),
    [
        (None, None),
        ("", None),
        ("   \t\n ", None),
        ("presupuesto", "presupuesto"),
        ("  presupuesto   anual ", "presupuesto anual"),
        ('"plan de empresa" -viaje or gasto', '"plan de empresa" -viaje or gasto'),
        ("pre\x00su\x1fpuesto\x7f", "pre su puesto"),
        ("\x00\x01", None),
        ("a" * (TOPE_CONSULTA + 10), "a" * TOPE_CONSULTA),
        ("a" * (TOPE_CONSULTA - 1) + " b", "a" * (TOPE_CONSULTA - 1)),
        (INICIO + "x" + FIN, "x"),
    ],
)
def test_normalizar(q, esperado):
    assert normalizar(q) == esperado


def test_limite_de_resultados():
    assert LIMITE == 50
    assert TOPE_CONSULTA == 200


def test_resaltar_escapa_y_despues_marca():
    r = resaltar(f"el {INICIO}presupuesto{FIN} <script>alert(1)</script> & más")
    assert isinstance(r, Markup)
    assert str(r) == "el <mark>presupuesto</mark> &lt;script&gt;alert(1)&lt;/script&gt; &amp; más"


def test_resaltar_sin_marcas():
    assert str(resaltar("<b>hola</b>")) == "&lt;b&gt;hola&lt;/b&gt;"


def test_resaltar_varias_marcas():
    assert str(resaltar(f"{INICIO}a{FIN} y {INICIO}b{FIN}")) == "<mark>a</mark> y <mark>b</mark>"


@pytest.mark.parametrize(
    "texto",
    [
        f"{INICIO}a",
        f"a{FIN}",
        f"{FIN}a{INICIO}",
        f"{INICIO}{INICIO}a{FIN}{FIN}",
        f"{INICIO}a{FIN}{FIN}",
        f"{INICIO}a{FIN}{INICIO}",
    ],
)
def test_resaltar_con_centinelas_descompensados_no_marca_nada(texto):
    assert str(resaltar(texto)) == "a"


def test_sin_centinelas_quita_los_que_traiga_el_texto():
    assert sin_centinelas(f"a{INICIO}b{FIN}c") == "abc"


def test_los_centinelas_no_los_toca_el_escape_html():
    from html import escape

    assert escape(INICIO + FIN) == INICIO + FIN
    assert INICIO != FIN


def test_opciones_de_ts_headline_con_los_centinelas():
    assert f"StartSel={INICIO}" in OPCIONES and f"StopSel={FIN}" in OPCIONES


def test_resaltar_devuelve_escapados_los_sustitutos_de_las_etiquetas():
    lt, gt, amp = SUSTITUTOS["<"], SUSTITUTOS[">"], SUSTITUTOS["&"]
    r = resaltar(f"{INICIO}a{FIN} {lt}script{gt} {amp} <b>")
    assert str(r) == "<mark>a</mark> &lt;script&gt; &amp; &lt;b&gt;"


def test_translate_de_postgresql():
    """translate(texto, QUITAR, PONER): cada carácter de QUITAR pasa al de su posición en PONER, y los que sobran se borran."""
    assert QUITAR[: len(PONER)] == "<>&"
    assert PONER == SUSTITUTOS["<"] + SUSTITUTOS[">"] + SUSTITUTOS["&"]
    assert set(QUITAR[len(PONER) :]) == {INICIO, FIN, *SUSTITUTOS.values()}
    assert len(set(QUITAR)) == len(QUITAR)


def test_los_sustitutos_no_son_centinelas_ni_los_toca_el_escape():
    from html import escape

    todos = "".join(SUSTITUTOS.values())
    assert escape(todos) == todos
    assert INICIO not in todos and FIN not in todos
    assert len(set(todos)) == 3


def test_sin_centinelas_quita_tambien_los_sustitutos():
    assert sin_centinelas("a" + "".join(SUSTITUTOS.values()) + "b") == "ab"
