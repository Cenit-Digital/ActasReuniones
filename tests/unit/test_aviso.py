"""@a25: el aviso del grabador cuando ningún stream de la sala casa con un socio conforme (lección de F0)."""

from actas.aviso import MARGEN_S, sin_coincidencia, streams_validos


def test_margen_de_un_minuto():
    assert MARGEN_S == 60


def test_antes_del_margen_no_avisa():
    assert sin_coincidencia({"sociopablo": []}, segundos=MARGEN_S - 1) == []


def test_avisa_de_los_socios_que_no_estan_pasado_el_margen():
    vistos = {"sociopablo": ["sociopablo", "x7kq2lm"], "socioroberto": ["sociopablo", "x7kq2lm"]}
    assert sin_coincidencia(vistos, segundos=MARGEN_S) == ["socioroberto"]


def test_si_todos_estan_no_avisa():
    assert sin_coincidencia({"sociopablo": ["sociopablo"]}, segundos=600) == []


def test_streams_validos_filtra_forma_y_tope():
    ids = ["b", "a", "a", 3, None, "con espacio", "x" * 65, *[f"s{n}" for n in range(60)]]
    resultado = streams_validos(ids)
    assert resultado[:2] == ["a", "b"]
    assert len(resultado) == 50
    assert "con espacio" not in resultado and "x" * 65 not in resultado
