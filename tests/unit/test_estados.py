"""@a7 y la máquina de estados de una reunión (ADR 0015, decisión 6)."""

import pytest

from actas.estados import TOPE_GRABACION_S, Estado, TransicionNoValida, motivo_parada, transicion


def test_tope_de_tres_horas():
    assert TOPE_GRABACION_S == 3 * 3600


def test_sin_peticion_y_antes_del_tope_sigue_grabando():
    assert motivo_parada(inicio_s=1000.0, ahora_s=1000.0 + TOPE_GRABACION_S - 1, parar_pedido=False) is None


def test_en_el_tope_para_con_motivo():
    assert motivo_parada(inicio_s=1000.0, ahora_s=1000.0 + TOPE_GRABACION_S, parar_pedido=False) == "tope_3h"


def test_la_peticion_de_parar_manda_aunque_sea_pronto():
    assert motivo_parada(inicio_s=1000.0, ahora_s=1001.0, parar_pedido=True) == "pedida"


def test_peticion_y_tope_a_la_vez_cuenta_como_pedida():
    assert motivo_parada(inicio_s=0.0, ahora_s=TOPE_GRABACION_S + 10.0, parar_pedido=True) == "pedida"


@pytest.mark.parametrize(
    ("desde", "hasta"),
    [
        (Estado.PEDIDA, Estado.GRABANDO),
        (Estado.PEDIDA, Estado.ERROR),
        (Estado.GRABANDO, Estado.GRABADA),
        (Estado.GRABANDO, Estado.ERROR),
        (Estado.GRABADA, Estado.TRANSCRIBIENDO),
        (Estado.GRABADA, Estado.ERROR),
        (Estado.TRANSCRIBIENDO, Estado.TRANSCRITA),
        (Estado.TRANSCRIBIENDO, Estado.ERROR),
        (Estado.ERROR, Estado.GRABADA),
    ],
)
def test_transiciones_validas(desde, hasta):
    assert transicion(desde, hasta) is hasta


@pytest.mark.parametrize(
    ("desde", "hasta"),
    [
        (Estado.PEDIDA, Estado.GRABADA),
        (Estado.GRABANDO, Estado.TRANSCRITA),
        (Estado.TRANSCRITA, Estado.GRABANDO),
        (Estado.TRANSCRITA, Estado.ERROR),
        (Estado.GRABADA, Estado.GRABANDO),
        (Estado.ERROR, Estado.TRANSCRITA),
        (Estado.TRANSCRIBIENDO, Estado.GRABADA),
    ],
)
def test_transiciones_no_validas(desde, hasta):
    with pytest.raises(TransicionNoValida):
        transicion(desde, hasta)


def test_valores_de_la_base():
    assert [e.value for e in Estado] == ["pedida", "grabando", "grabada", "transcribiendo", "transcrita", "error"]
