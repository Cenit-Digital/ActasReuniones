"""@a55 (lado del supervisor): un evento solo lleva tipos y claves de la lista blanca, valores escalares cortos y ningún secreto.
La base lo impone otra vez con un CHECK (tests/integracion/test_eventos_base.py), pero la contraseña de la sala solo la conoce el
proceso: esa mitad es de aquí."""

import pytest

from actas.eventos import CLAVES, TIPOS, EventoNoValido, validar


def test_un_evento_de_la_lista_blanca_pasa_tal_cual():
    detalle = {"desde": "grabada", "hasta": "error", "motivo": "pistas", "causa": "ninguna_pista", "ficheros": 0}
    assert validar("estado", detalle, ["clave-de-la-sala"]) == detalle


def test_un_tipo_fuera_de_la_lista_blanca_se_rechaza():
    with pytest.raises(EventoNoValido):
        validar("depuracion", {}, [])


def test_una_clave_fuera_de_la_lista_blanca_se_rechaza():
    with pytest.raises(EventoNoValido):
        validar("estado", {"desde": "grabada", "texto": "hola"}, [])


@pytest.mark.parametrize("secreto", ["Cl4ve-Sala", "tok3n-de-servicio"])
def test_una_cadena_igual_a_un_secreto_se_rechaza(secreto):
    with pytest.raises(EventoNoValido):
        validar("estado", {"motivo": secreto}, ["Cl4ve-Sala", "tok3n-de-servicio"])


def test_una_cadena_que_contiene_un_secreto_se_rechaza():
    with pytest.raises(EventoNoValido):
        validar("estado", {"motivo": "x_Cl4ve-Sala_y"}, ["Cl4ve-Sala"])


def test_un_secreto_corto_solo_se_rechaza_si_es_el_valor_entero():
    """Una contraseña corta podría aparecer por azar dentro de un código y bloquear un cambio de estado."""
    assert validar("estado", {"motivo": "pistas"}, ["pis"]) == {"motivo": "pistas"}
    with pytest.raises(EventoNoValido):
        validar("estado", {"motivo": "pis"}, ["pis"])


def test_un_secreto_vacio_no_rechaza_todo():
    assert validar("estado", {"motivo": "pistas"}, ["", "  "]) == {"motivo": "pistas"}


@pytest.mark.parametrize(
    "valor",
    [
        ["lista"],
        {"anidado": 1},
        "con espacios",
        "salto\nde línea",
        "x" * 65,
        "ñandú",
        1.5,
    ],
)
def test_solo_valores_escalares_y_cadenas_cortas_y_seguras(valor):
    with pytest.raises(EventoNoValido):
        validar("estado", {"motivo": valor}, [])


@pytest.mark.parametrize("valor", [0, 503, True, False, None, "http_503", "pablo@cenit.es", "a" * 64])
def test_enteros_booleanos_nulo_y_codigos(valor):
    assert validar("estado", {"motivo": valor}, []) == {"motivo": valor}


def test_la_lista_blanca_es_la_de_la_migracion():
    """La misma lista que impone el CHECK de 0005_eventos.sql: si una cambia, este test obliga a cambiar la otra."""
    from pathlib import Path

    sql = (Path(__file__).resolve().parents[2] / "migraciones" / "0005_eventos.sql").read_text(encoding="utf-8")
    for nombre in sorted(TIPOS | CLAVES):
        assert f"'{nombre}'" in sql, nombre
