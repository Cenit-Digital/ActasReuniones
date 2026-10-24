"""@a8: de la transcripción de la plataforma (contrato/openapi.yaml, `Transcripcion`) a los segmentos del archivo de actas."""

import pytest

from actas.transcripcion import TranscripcionNoValida, segmentos_de

HABLANTES = [{"id": "h1", "etiqueta": "socioa"}, {"id": "h2", "etiqueta": "sociob"}]


def test_hablante_por_etiqueta_y_orden_por_tiempo():
    t = {
        "hablantes": HABLANTES,
        "segmentos": [
            {"hablante_id": "h2", "inicio_ms": 62700, "fin_ms": 64000, "texto": " Hola. "},
            {"hablante_id": "h1", "inicio_ms": 1000, "fin_ms": 2500, "texto": "Doy mi conformidad"},
        ],
    }
    assert segmentos_de(t, ["socioa", "sociob"]) == [
        {"hablante": "socioa", "inicio_ms": 1000, "fin_ms": 2500, "texto": "Doy mi conformidad"},
        {"hablante": "sociob", "inicio_ms": 62700, "fin_ms": 64000, "texto": "Hola."},
    ]


def test_sin_segmentos_es_una_lista_vacia():
    assert segmentos_de({"hablantes": [], "segmentos": []}, ["socioa"]) == []


def test_segmentos_vacios_se_descartan():
    t = {"hablantes": HABLANTES, "segmentos": [{"hablante_id": "h1", "inicio_ms": 0, "fin_ms": 1, "texto": "  "}]}
    assert segmentos_de(t, ["socioa"]) == []


def test_hablante_que_no_es_un_socio_conforme_es_un_error():
    t = {
        "hablantes": [{"id": "h9", "etiqueta": "SPEAKER_00"}],
        "segmentos": [{"hablante_id": "h9", "inicio_ms": 0, "fin_ms": 1, "texto": "x"}],
    }
    with pytest.raises(TranscripcionNoValida, match="hablante"):
        segmentos_de(t, ["socioa"])


def test_segmento_sin_hablante_es_un_error():
    t = {"hablantes": HABLANTES, "segmentos": [{"hablante_id": None, "inicio_ms": 0, "fin_ms": 1, "texto": "x"}]}
    with pytest.raises(TranscripcionNoValida):
        segmentos_de(t, ["socioa"])


@pytest.mark.parametrize(
    "seg",
    [
        {"hablante_id": "h1", "inicio_ms": -1, "fin_ms": 1, "texto": "x"},
        {"hablante_id": "h1", "inicio_ms": 5, "fin_ms": 4, "texto": "x"},
        {"hablante_id": "h1", "inicio_ms": "0", "fin_ms": 1, "texto": "x"},
        {"hablante_id": "h1", "inicio_ms": 0, "fin_ms": 1, "texto": 3},
    ],
)
def test_tiempos_o_texto_no_validos(seg):
    with pytest.raises(TranscripcionNoValida):
        segmentos_de({"hablantes": HABLANTES, "segmentos": [seg]}, ["socioa"])


def test_forma_inesperada():
    with pytest.raises(TranscripcionNoValida):
        segmentos_de({"segmentos": "no"}, ["socioa"])


@pytest.mark.parametrize("seg", ["texto", None, 3])
def test_segmento_que_no_es_un_objeto(seg):
    with pytest.raises(TranscripcionNoValida):
        segmentos_de({"hablantes": HABLANTES, "segmentos": [seg]}, ["socioa"])


def test_tope_de_int4_incluido():
    t = {"hablantes": HABLANTES, "segmentos": [{"hablante_id": "h1", "inicio_ms": 0, "fin_ms": 2**31 - 1, "texto": "x"}]}
    assert segmentos_de(t, ["socioa"])[0]["fin_ms"] == 2**31 - 1
