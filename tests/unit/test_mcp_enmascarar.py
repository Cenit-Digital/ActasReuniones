from __future__ import annotations

import pytest

from actas.enmascarar import coincidencia_limpia, enmascarar


@pytest.mark.parametrize(
    "entrada",
    [
        "escribe a pablo.hurtado+cenit@gmail.com hoy",
        "PABLO@CENIT-DIGITAL.ES",
        "mi correo es juan arroba gmail punto com",
        "juan (at) gmail.com",
    ],
)
def test_el_correo_desaparece_entero(entrada: str) -> None:
    salida = enmascarar(entrada)
    assert "[correo]" in salida
    for resto in ("gmail", "cenit", "hurtado", "juan", "PABLO"):
        assert resto not in salida


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("llama al 612345678 ya", "llama al ···678 ya"),
        ("llama al 612 34 56 78 ya", "llama al ···678 ya"),
        ("llama al 612-345-678.", "llama al ···678."),
        ("llama al 612.345.678", "llama al ···678"),
        ("llama al +34 612 345 678", "llama al ···678"),
        ("llama al +34612345678", "llama al ···678"),
        ("llama al 0034 612345678", "llama al ···678"),
        ("llama al (91) 345 67 89", "llama al ···789"),
    ],
)
def test_telefono_solo_los_tres_ultimos_digitos(entrada: str, esperado: str) -> None:
    assert enmascarar(entrada) == esperado


@pytest.mark.parametrize(
    "entrada",
    [
        "en 2026 subimos un 35 por ciento",
        "el 25-11-2026 a las 10:30:15",
        "el 2026-11-25",
        "son 1500 euros y 12345678 puntos",
        "reunión a las 10:30 en la sala 4",
        "",
    ],
)
def test_lo_que_no_es_correo_ni_telefono_no_se_toca(entrada: str) -> None:
    assert enmascarar(entrada) == entrada


def test_los_nombres_de_los_socios_se_dejan() -> None:
    assert enmascarar("Andrés y Roberto aprueban") == "Andrés y Roberto aprueban"


def test_un_telefono_partido_por_la_marca_de_busqueda_tambien_se_enmascara() -> None:
    # ts_headline devuelve «<mark>612</mark> 345 678» y el texto va escapado en HTML.
    assert coincidencia_limpia("llama al <mark>612</mark> 345 678 &amp; vuelve") == "llama al ···678 & vuelve"


def test_coincidencia_sin_html_ni_correo() -> None:
    sucia = "&lt;b&gt;escribe&lt;/b&gt; a <mark>ana</mark>@mail.com"
    assert coincidencia_limpia(sucia) == "<b>escribe</b> a [correo]"


def test_texto_largo_se_trunca_con_marca() -> None:
    salida = enmascarar("a" * 50, maximo=10)
    assert salida == "a" * 10 + "…"


# ── Casos de la revisión de seguridad ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "entrada",
    [
        "juan @ gmail.com",
        "juan@ gmail.com",
        "juan＠gmail.com",
        "juan﹫gmail.com",
        "juan(at)gmail(dot)com",
        "juan@gmail. com",
        "juan@gmail",
        "juan%pepe@gmail.com",
        "o'brien@gmail.com",
        "escribe a juan arroba gmail",
    ],
)
def test_correos_con_formas_raras_salen_enteros(entrada: str) -> None:
    salida = enmascarar(entrada)
    assert "[correo]" in salida
    for resto in ("juan", "gmail", "pepe", "brien"):
        assert resto not in salida


@pytest.mark.parametrize(
    "entrada",
    [
        "tel612345678",
        "612345678h",
        "x_612345678",
        "612345678_",
        "612/345/678",
        "612 – 345 – 678",
        "612 - 345 - 678",
        "612 345 678",
        "612 345 678",
        "612\t345\t678",
        "6, 1, 2, 3, 4, 5, 6, 7, 8",
        "6 1 2 3 4 5 6 7 8",
    ],
)
def test_telefonos_con_formas_raras_solo_dejan_tres_digitos(entrada: str) -> None:
    salida = enmascarar(entrada)
    assert "···" in salida
    assert sum(c.isdigit() for c in salida) == 3


def test_una_lista_de_importes_con_comas_no_es_un_telefono() -> None:
    assert enmascarar("subió 1500, 2000, 3000 y 4000") == "subió 1500, 2000, 3000 y 4000"


@pytest.mark.parametrize("c", ["j", "6", "a.", "6 ", "@", "a@", "j@" + "b." * 40])
def test_el_enmascarado_es_lineal_con_textos_largos(c: str) -> None:
    import time

    inicio = time.perf_counter()
    enmascarar((c * 50_000)[:50_000])
    assert time.perf_counter() - inicio < 1.0


@pytest.mark.parametrize(
    ("fragmento", "esperado"),
    [
        ("345 678 <mark>presupuesto</mark>", "… presupuesto"),
        ("dijo <mark>presupuesto</mark> 612 345", "dijo presupuesto …"),
        ("su 2026 fue <mark>bueno</mark>", "su 2026 fue bueno"),
        ("llama al 612 345 678 <mark>hoy</mark>", "llama al ···678 hoy"),
    ],
)
def test_un_fragmento_cortado_no_deja_trozos_de_numero(fragmento: str, esperado: str) -> None:
    assert coincidencia_limpia(fragmento) == esperado


# ── Bordes que fijan los topes y las banderas ────────────────────────────────────────────────────────


def test_mayusculas_en_las_palabras_de_correo() -> None:
    assert enmascarar("Juan ARROBA Gmail PUNTO com") == "[correo]"
    assert enmascarar("Juan (AT) gmail (DOT) com") == "[correo]"


def test_el_tope_exacto_no_añade_puntos_suspensivos() -> None:
    assert enmascarar("a" * 10, maximo=10) == "a" * 10
    assert enmascarar("a" * 11, maximo=10) == "a" * 10 + "…"
    assert coincidencia_limpia("a" * 10, maximo=10) == "a" * 10
    assert coincidencia_limpia("a" * 11, maximo=10) == "a" * 10 + "…"


def test_sin_tope_no_recorta() -> None:
    assert enmascarar("a" * 5000) == "a" * 5000 and coincidencia_limpia("a" * 5000) == "a" * 5000


def test_el_fragmento_sin_cifras_en_los_bordes_queda_igual() -> None:
    assert coincidencia_limpia("hola <mark>mundo</mark>") == "hola mundo"


def test_por_debajo_del_tope_no_se_toca() -> None:
    assert enmascarar("a" * 5, maximo=10) == "a" * 5
    assert coincidencia_limpia("a" * 5, maximo=10) == "a" * 5


@pytest.mark.parametrize(
    "texto",
    ["Reunión del 2026-11-25 09:00", "el 25/11/2026 10 personas", "el 25-11-2026 9:30", "el 2026.11.25 10h"],
)
def test_una_fecha_con_hora_no_es_un_telefono(texto: str) -> None:
    assert enmascarar(texto) == texto


def test_un_telefono_pegado_a_una_fecha_sigue_enmascarado() -> None:
    salida = enmascarar("2026-11-25 612345678")  # se enmascara todo el tramo: la fecha se pierde, el teléfono no sale
    assert salida == "···678" and "612345" not in salida
