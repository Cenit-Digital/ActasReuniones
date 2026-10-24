"""@a10: qué audio se borra del tmpfs."""

from actas.purga import PLAZO_AUDIO_S, Audio, a_borrar

AHORA = 10_000_000.0


def test_plazo_de_siete_dias():
    assert PLAZO_AUDIO_S == 7 * 24 * 3600


def test_se_borra_el_audio_de_una_reunion_transcrita():
    assert a_borrar([Audio("r1", "transcrita", AHORA - 60)], AHORA) == [("r1", "transcrita")]


def test_se_conserva_el_de_una_reunion_en_curso_o_en_error_dentro_del_plazo():
    audios = [
        Audio(r, e, AHORA - PLAZO_AUDIO_S + 1)
        for r, e in [("a", "grabando"), ("b", "grabada"), ("c", "transcribiendo"), ("d", "error")]
    ]
    assert a_borrar(audios, AHORA) == []


def test_cualquier_audio_de_mas_de_siete_dias_se_borra():
    audios = [Audio("viejo", "error", AHORA - PLAZO_AUDIO_S), Audio("nuevo", "error", AHORA - 10)]
    assert a_borrar(audios, AHORA) == [("viejo", "plazo_7d")]


def test_audio_sin_reunion_conocida_es_huerfano():
    assert a_borrar([Audio("x", None, AHORA)], AHORA) == [("x", "huerfano")]


def test_transcrita_y_vieja_cuenta_como_transcrita():
    assert a_borrar([Audio("r", "transcrita", AHORA - PLAZO_AUDIO_S - 5)], AHORA) == [("r", "transcrita")]
