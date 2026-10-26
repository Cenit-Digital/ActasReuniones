"""Lo que el panel muestra de cada reunión: tiempos `hh:mm:ss`, duración y socios por su nombre (@a22)."""

from datetime import UTC, datetime, timedelta

import pytest

from actas.presentacion import duracion, hhmmss, nombres


@pytest.mark.parametrize(
    ("ms", "texto"),
    [
        (0, "00:00:00"),
        (999, "00:00:00"),
        (1000, "00:00:01"),
        (59_999, "00:00:59"),
        (60_000, "00:01:00"),
        (3_599_999, "00:59:59"),
        (3_600_000, "01:00:00"),
        (3 * 3_600_000 + 61_000, "03:01:01"),
        (100 * 3_600_000, "100:00:00"),
    ],
)
def test_hhmmss(ms, texto):
    assert hhmmss(ms) == texto


def test_hhmmss_negativo_no_es_un_tiempo():
    with pytest.raises(ValueError):
        hhmmss(-1)


T0 = datetime(2026, 10, 26, 10, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("inicio", "fin", "texto"),
    [
        (T0, T0, "00:00:00"),
        (T0, T0 + timedelta(seconds=59, milliseconds=999), "00:00:59"),
        (T0, T0 + timedelta(hours=1, minutes=2, seconds=3), "01:02:03"),
        (None, T0, "—"),
        (T0, None, "—"),
        (None, None, "—"),
        (T0, T0 - timedelta(seconds=1), "—"),
    ],
)
def test_duracion(inicio, fin, texto):
    assert duracion(inicio, fin) == texto


def test_nombres_de_los_socios_conocidos_y_streamid_de_los_demas():
    conocidos = {"pablo": "Pablo", "andres": "Andrés"}
    assert nombres(["pablo", "andres", "otro"], conocidos) == "Pablo, Andrés, otro"
    assert nombres([], conocidos) == ""


def test_bloques_del_texto_informativo():
    from actas.presentacion import bloques

    texto = "# Título\n\nUn párrafo\nen dos líneas.\n\n## Apartado\n\n- uno\n- dos\n\n\nFinal.\n"
    assert bloques(texto) == [
        ("h2", ["Título"]),
        ("p", ["Un párrafo en dos líneas."]),
        ("h3", ["Apartado"]),
        ("ul", ["uno", "dos"]),
        ("p", ["Final."]),
    ]


def test_bloques_con_lista_mezclada_es_parrafo_y_vacio_no_da_nada():
    from actas.presentacion import bloques

    assert bloques("- uno\nno es lista") == [("p", ["- uno no es lista"])]
    assert bloques(" \n\n") == []
    assert bloques("#sin espacio") == [("p", ["#sin espacio"])]
    assert bloques("  ## Con sangría  ") == [("h3", ["Con sangría"])]
