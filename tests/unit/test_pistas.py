"""@a8: de los ficheros que deja VDO.Ninja (`<id>_<ms>.webm`) a las pistas de la petición a la plataforma."""

import pytest

from actas.pistas import TOPE_PISTAS, Pista, PistasNoValidas, pistas_de


def test_una_pista_por_fichero_con_desfase_desde_la_primera():
    ficheros = ["sociob_1700000065700.webm", "socioa_1700000003000.webm"]
    assert pistas_de(ficheros, ["socioa", "sociob"]) == [
        Pista("socioa_1700000003000.webm", "socioa", 1700000003000, 0),
        Pista("sociob_1700000065700.webm", "sociob", 1700000065700, 62700),
    ]


def test_reconexion_varias_pistas_del_mismo_socio_ordenadas_por_marca():
    ficheros = ["socioa_2000.webm", "socioa_1000.webm", "sociob_1500.webm"]
    resultado = pistas_de(ficheros, ["socioa", "sociob"])
    assert [(p.socio, p.desfase_ms) for p in resultado] == [("socioa", 0), ("sociob", 500), ("socioa", 1000)]


def test_ignora_descargas_a_medias_y_otros_ficheros():
    ficheros = ["socioa_1000.webm", "socioa_2000.webm.crdownload", "inicio.json", ".com.google.Chrome.x"]
    assert [p.fichero for p in pistas_de(ficheros, ["socioa"])] == ["socioa_1000.webm"]


def test_sin_pistas_es_un_error():
    with pytest.raises(PistasNoValidas, match="ninguna pista"):
        pistas_de(["inicio.json"], ["socioa"])


def test_una_pista_de_un_socio_no_conforme_es_un_error_y_no_se_envia():
    with pytest.raises(PistasNoValidas, match="no conforme"):
        pistas_de(["socioa_1000.webm", "intruso_1200.webm"], ["socioa"])


def test_una_pista_partida_por_vdo_ninja_es_un_error():
    # VDO.Ninja añade «_<n>» detrás de la extensión cuando parte una grabación: su marca no es la del trozo.
    with pytest.raises(PistasNoValidas, match="partida"):
        pistas_de(["socioa_1000.webm", "socioa_1000.webm_1"], ["socioa"])


def test_como_mucho_el_tope_de_la_plataforma():
    assert TOPE_PISTAS == 16
    ficheros = [f"socioa_{1000 + n}.webm" for n in range(TOPE_PISTAS)]
    assert len(pistas_de(ficheros, ["socioa"])) == TOPE_PISTAS
    with pytest.raises(PistasNoValidas, match="17 pistas"):
        pistas_de([*ficheros, "socioa_9999.webm"], ["socioa"])


def test_marca_igual_para_dos_socios_desfase_cero_en_los_dos():
    resultado = pistas_de(["socioa_1000.webm", "sociob_1000.webm"], ["socioa", "sociob"])
    assert [p.desfase_ms for p in resultado] == [0, 0]
    assert [p.socio for p in resultado] == ["socioa", "sociob"]


@pytest.mark.parametrize("nombre", ["Socioa_1000.webm", "socio-a_1000.webm", "socioa_.webm", "socioa_1000.ogg", "_1000.webm"])
def test_nombres_que_no_son_pistas(nombre):
    with pytest.raises(PistasNoValidas):
        pistas_de([nombre], ["socioa"])
