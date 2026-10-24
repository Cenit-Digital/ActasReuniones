"""@a8 y @a24: cómo se interpretan las respuestas de la plataforma de transcripción."""

import pytest

from actas.sondeo import ESPERA_MAX_S, PLAZO_S, Decision, espera, interpretar_creacion, interpretar_estado


def test_creacion_201_devuelve_el_id():
    assert interpretar_creacion(201, {"id": "1b4e28ba-2fa1-11d2-883f-0016d3cca427"}) == Decision(
        "seguir", trabajo_id="1b4e28ba-2fa1-11d2-883f-0016d3cca427"
    )


def test_creacion_201_sin_id_valido_es_error():
    assert interpretar_creacion(201, {"id": "../x"}) == Decision("error", motivo="respuesta_sin_id")


@pytest.mark.parametrize(("codigo", "motivo"), [(401, "token"), (413, "rechazada_413"), (422, "rechazada_422")])
def test_creacion_rechazada(codigo, motivo):
    assert interpretar_creacion(codigo, {}) == Decision("error", motivo=motivo)


@pytest.mark.parametrize("codigo", [500, 502, 503, 0])
def test_creacion_con_fallo_transitorio_se_reintenta(codigo):
    assert interpretar_creacion(codigo, None) == Decision("reintentar", motivo=f"http_{codigo}")


def test_estado_listo_trae_la_transcripcion():
    cuerpo = {"trabajo": {"estado": "listo"}, "transcripcion": {"segmentos": []}}
    assert interpretar_estado(200, cuerpo) == Decision("listo")


@pytest.mark.parametrize("estado", ["recibido", "ingestando", "preparado", "en_cola", "transcribiendo", "alineando"])
def test_estado_en_curso_sigue(estado):
    assert interpretar_estado(200, {"trabajo": {"estado": estado}}) == Decision("seguir")


@pytest.mark.parametrize("estado", ["error", "cancelado"])
def test_estado_final_sin_texto_es_error(estado):
    assert interpretar_estado(200, {"trabajo": {"estado": estado}}) == Decision("error", motivo=f"plataforma_{estado}")


def test_listo_sin_transcripcion_es_error():
    assert interpretar_estado(200, {"trabajo": {"estado": "listo"}}) == Decision("error", motivo="listo_sin_texto")


def test_estado_desconocido_es_error():
    assert interpretar_estado(200, {"trabajo": {"estado": "raro"}}) == Decision("error", motivo="estado_desconocido")


@pytest.mark.parametrize(
    ("codigo", "motivo"), [(401, "token"), (404, "trabajo_no_encontrado"), (403, "rechazada_403"), (422, "rechazada_422")]
)
def test_estado_rechazado(codigo, motivo):
    assert interpretar_estado(codigo, None) == Decision("error", motivo=motivo)


@pytest.mark.parametrize("codigo", [500, 503, 0])
def test_estado_con_fallo_transitorio_sigue(codigo):
    assert interpretar_estado(codigo, None) == Decision("seguir", motivo=f"http_{codigo}")


def test_espera_creciente_con_tope():
    assert [espera(n) for n in range(6)] == [5, 10, 20, 40, 60, 60]
    assert ESPERA_MAX_S == 60


def test_plazo_total_de_doce_horas():
    # Una reunión de 3 h con el nodo cargado: 3 pistas a ~1,5 s por segundo de voz, más la cola de la plataforma.
    assert PLAZO_S == 12 * 3600


@pytest.mark.parametrize("cuerpo", [None, "texto", [], {"trabajo": "x"}, {"trabajo": None}])
def test_estado_200_con_cuerpo_no_valido_es_error(cuerpo):
    assert interpretar_estado(200, cuerpo) == Decision("error", motivo="respuesta_no_valida")


def test_creacion_201_con_cuerpo_que_no_es_un_objeto():
    assert interpretar_creacion(201, ["x"]) == Decision("error", motivo="respuesta_sin_id")
