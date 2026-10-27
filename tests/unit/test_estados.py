"""@a7 y la máquina de estados de una reunión (ADR 0015, decisión 6), con las programadas y canceladas de V3
(KubernetesInfrastructure#298, ADR 0023 decisión 5): el tope de cada reunión y «si no entra nadie»."""

import pytest

from actas.estados import (
    ESTADOS_FINALES,
    TOPE_GRABACION_S,
    Estado,
    TransicionNoValida,
    motivo_parada,
    nadie_entro,
    transicion,
)


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
        (Estado.PROGRAMADA, Estado.GRABANDO),
        (Estado.PROGRAMADA, Estado.ERROR),
        (Estado.PROGRAMADA, Estado.CANCELADA),
        (Estado.GRABANDO, Estado.CANCELADA),
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
        (Estado.PROGRAMADA, Estado.GRABADA),
        (Estado.PROGRAMADA, Estado.PEDIDA),
        (Estado.PEDIDA, Estado.CANCELADA),
        (Estado.GRABADA, Estado.CANCELADA),
        (Estado.CANCELADA, Estado.PROGRAMADA),
        (Estado.CANCELADA, Estado.GRABANDO),
        (Estado.CANCELADA, Estado.ERROR),
        (Estado.ERROR, Estado.PROGRAMADA),
        (Estado.TRANSCRITA, Estado.CANCELADA),
    ],
)
def test_transiciones_no_validas(desde, hasta):
    with pytest.raises(TransicionNoValida):
        transicion(desde, hasta)


def test_valores_de_la_base():
    assert [e.value for e in Estado] == [
        "pedida",
        "grabando",
        "grabada",
        "transcribiendo",
        "transcrita",
        "error",
        "programada",
        "cancelada",
    ]


def test_estados_finales():
    """Los únicos que pueden ir a la papelera: nada en ellos sigue en marcha (el CHECK de la migración 0006)."""
    assert ESTADOS_FINALES == frozenset({Estado.TRANSCRITA, Estado.ERROR, Estado.CANCELADA})


# ── Tope de cada reunión (V3) ──────────────────────────────────────────────────────────────────────────────────────────


def test_un_tope_menor_para_antes_con_su_motivo():
    assert motivo_parada(inicio_s=0.0, ahora_s=3600.0, parar_pedido=False, tope_s=3600) == "tope"


def test_antes_de_un_tope_menor_sigue_grabando():
    assert motivo_parada(inicio_s=0.0, ahora_s=3599.0, parar_pedido=False, tope_s=3600) is None


def test_un_tope_mayor_que_tres_horas_se_queda_en_tres():
    assert motivo_parada(inicio_s=0.0, ahora_s=float(TOPE_GRABACION_S), parar_pedido=False, tope_s=5 * 3600) == "tope_3h"


def test_el_tope_de_tres_horas_explicito_es_el_de_f1():
    assert motivo_parada(inicio_s=0.0, ahora_s=float(TOPE_GRABACION_S), parar_pedido=False, tope_s=TOPE_GRABACION_S) == "tope_3h"


def test_la_peticion_manda_sobre_un_tope_menor():
    assert motivo_parada(inicio_s=0.0, ahora_s=7200.0, parar_pedido=True, tope_s=3600) == "pedida"


# ── Si no entra nadie (V3) ─────────────────────────────────────────────────────────────────────────────────────────────


def test_sin_espera_nunca_se_cancela():
    assert not nadie_entro(segundos=10 * 3600, espera_s=None, alguno_visto=False)


def test_antes_de_la_espera_no_se_cancela():
    assert not nadie_entro(segundos=899, espera_s=900, alguno_visto=False)


def test_en_la_espera_sin_nadie_se_cancela():
    assert nadie_entro(segundos=900, espera_s=900, alguno_visto=False)


def test_si_alguien_entro_no_se_cancela():
    assert not nadie_entro(segundos=3600, espera_s=900, alguno_visto=True)


def test_pasado_el_tope_tambien_para():
    """Una vuelta que llega tarde (la base caída, una parada lenta) no se salta el tope."""
    assert motivo_parada(inicio_s=0.0, ahora_s=3700.0, parar_pedido=False, tope_s=3600) == "tope"


def test_pasada_la_espera_sin_nadie_tambien_se_cancela():
    assert nadie_entro(segundos=960, espera_s=900, alguno_visto=False)
