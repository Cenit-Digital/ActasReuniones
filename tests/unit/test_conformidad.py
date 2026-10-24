"""@a6: sin socios conformes no se graba; con la lista, una conformidad por socio con la versión del texto."""

import pytest

from actas.conformidad import ConformidadNoValida, Peticion, validar


def test_sin_socios_se_rechaza():
    with pytest.raises(ConformidadNoValida, match="ningún socio"):
        validar([], "v1")


def test_lista_valida_normalizada_sin_repetidos_y_ordenada():
    assert validar(["socioroberto", "sociopablo", "sociopablo"], "v1") == Peticion(("sociopablo", "socioroberto"), "v1")


@pytest.mark.parametrize("socio", ["socio-pablo", "SocioPablo", "socio pablo", "", "a" * 33, "sociopablo&push=x"])
def test_streamid_no_alfanumerico_se_rechaza(socio):
    with pytest.raises(ConformidadNoValida, match="streamID"):
        validar([socio], "v1")


def test_streamid_de_32_caracteres_vale():
    assert validar(["a" * 32], "v1").socios == ("a" * 32,)


@pytest.mark.parametrize("version", ["", "  ", "v1 con espacios", "x" * 41])
def test_version_del_texto_informativo_obligatoria(version):
    with pytest.raises(ConformidadNoValida, match="versión"):
        validar(["sociopablo"], version)


def test_version_con_puntos_y_guiones_vale():
    assert validar(["sociopablo"], "2026-10-24.v1").version == "2026-10-24.v1"


def test_como_mucho_16_socios():
    with pytest.raises(ConformidadNoValida, match="16"):
        validar([f"socio{n}" for n in range(17)], "v1")
    assert len(validar([f"socio{n}" for n in range(16)], "v1").socios) == 16
