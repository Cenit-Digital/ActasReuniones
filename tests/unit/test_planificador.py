"""El planificador de V3 (KubernetesInfrastructure#298, ADR 0023 decisión 5): el formulario de programar, cuándo empieza una
reunión `programada` (@a48) y la fecha de la siguiente de una serie (@a53). Las horas, las de Madrid, con sus cambios de hora."""

from datetime import UTC, datetime, time, timedelta

import pytest

from actas.conformidad import ConformidadNoValida, Peticion
from actas.planificador import (
    ESPERAS_MIN,
    MADRID,
    REPETIR,
    TOPE_TITULO,
    TOPES_MIN,
    decidir,
    hora_local,
    siguiente,
    titulo,
    tope,
    validar_programacion,
)

AHORA = datetime(2026, 10, 27, 12, 0, tzinfo=UTC)
SALA = "00000000-0000-4000-8000-000000000001"
PETICION = Peticion(("pablo", "roberto"), "v1")


def _validar(**cambios):
    datos = {
        "titulo_": "Socios · seguimiento",
        "sala_id": SALA,
        "cuando": "2026-10-29T17:30",
        "tope_": "120",
        "repetir": "semanal",
        "espera": "15",
        "peticion": PETICION,
        "ahora": AHORA,
    }
    datos.update(cambios)
    return validar_programacion(
        datos["titulo_"],
        datos["sala_id"],
        datos["cuando"],
        datos["tope_"],
        datos["repetir"],
        datos["espera"],
        datos["peticion"],
        datos["ahora"],
    )


# ── Opciones del formulario ────────────────────────────────────────────────────────────────────────────────────────────


def test_opciones_del_diseno():
    assert TOPES_MIN == (60, 120, 180)  # 180: el tope de 3 h de F1 (@a7)
    assert ESPERAS_MIN == (15, 30, 60)
    assert REPETIR == ("no", "semanal", "mensual")
    assert TOPE_TITULO == 120
    assert MADRID.key == "Europe/Madrid"


# ── Título ─────────────────────────────────────────────────────────────────────────────────────────────────────────────


def test_titulo_sin_espacios_alrededor():
    assert titulo("  Socios · cierre  ") == "Socios · cierre"


def test_titulo_vacio_es_ninguno():
    assert titulo("   ") is None
    assert titulo("") is None


def test_titulo_en_el_tope_vale_y_uno_mas_no():
    assert titulo("x" * TOPE_TITULO) == "x" * TOPE_TITULO
    with pytest.raises(ConformidadNoValida):
        titulo("x" * (TOPE_TITULO + 1))


@pytest.mark.parametrize("malo", ["con\nsalto", "con\ttab", "con\x7fborrar", "con\x85nel"])
def test_titulo_sin_caracteres_de_control(malo):
    with pytest.raises(ConformidadNoValida):
        titulo(malo)


# ── Tope ───────────────────────────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("valor", ["60", "120", "180"])
def test_tope_de_las_opciones(valor):
    assert tope(valor) == int(valor)


@pytest.mark.parametrize("malo", ["", "0", "90", "181", "240", "-60", "2h", " 60"])
def test_tope_fuera_de_las_opciones(malo):
    with pytest.raises(ConformidadNoValida):
        tope(malo)


# ── Hora de Madrid ─────────────────────────────────────────────────────────────────────────────────────────────────────


def test_hora_local_en_horario_de_verano():
    # 2026-10-23: aún en CEST (UTC+2).
    assert hora_local("2026-10-23T17:30") == datetime(2026, 10, 23, 15, 30, tzinfo=UTC)


def test_hora_local_en_horario_de_invierno():
    # 2026-10-29: ya en CET (UTC+1); el cambio fue el domingo 25.
    assert hora_local("2026-10-29T17:30") == datetime(2026, 10, 29, 16, 30, tzinfo=UTC)


def test_hora_local_admite_segundos():
    assert hora_local("2026-10-29T17:30:15") == datetime(2026, 10, 29, 16, 30, 15, tzinfo=UTC)


def test_hora_local_devuelve_utc():
    assert hora_local("2026-10-29T17:30").tzinfo is UTC


def test_una_hora_que_no_existe_por_el_cambio_de_hora_se_rechaza():
    # 2027-03-28: de 02:00 se pasa a 03:00 en Madrid.
    with pytest.raises(ConformidadNoValida):
        hora_local("2027-03-28T02:30")


def test_la_hora_justo_despues_del_salto_existe():
    assert hora_local("2027-03-28T03:00") == datetime(2027, 3, 28, 1, 0, tzinfo=UTC)


def test_una_hora_doble_por_el_cambio_de_hora_es_la_primera():
    # 2026-10-25: de 03:00 se vuelve a 02:00; 02:30 pasa dos veces y vale la de verano (UTC+2).
    assert hora_local("2026-10-25T02:30") == datetime(2026, 10, 25, 0, 30, tzinfo=UTC)


@pytest.mark.parametrize("malo", ["", "mañana", "2026-10-29", "2026-10-29 17:30x", "2026-13-01T10:00", "2026-10-29T17:30+02:00"])
def test_hora_local_no_valida(malo):
    with pytest.raises(ConformidadNoValida):
        hora_local(malo)


# ── Programar ──────────────────────────────────────────────────────────────────────────────────────────────────────────


def test_programacion_valida():
    p = _validar()
    assert p.titulo == "Socios · seguimiento"
    assert p.sala_id == SALA
    assert p.para == datetime(2026, 10, 29, 16, 30, tzinfo=UTC)
    assert (p.tope_min, p.repetir, p.espera_min) == (120, "semanal", 15)
    assert (p.socios, p.version) == (("pablo", "roberto"), "v1")


def test_programar_sin_titulo():
    assert _validar(titulo_="").titulo is None


def test_programar_en_el_pasado_se_rechaza():
    with pytest.raises(ConformidadNoValida):
        _validar(cuando="2026-10-27T12:59", ahora=AHORA)  # 11:59 UTC


def test_programar_justo_ahora_se_rechaza():
    with pytest.raises(ConformidadNoValida):
        _validar(cuando="2026-10-27T13:00", ahora=AHORA)  # 12:00 UTC: es ahora, no el futuro


def test_programar_un_minuto_despues_vale():
    assert _validar(cuando="2026-10-27T13:01", ahora=AHORA).para == AHORA + timedelta(minutes=1)


def test_programar_a_un_ano_vale_y_mas_no():
    # AHORA + 366 días = 2027-10-28 12:00 UTC, las 14:00 en Madrid (aún en verano: el cambio de 2027 es el 31).
    assert _validar(cuando="2027-10-28T14:00", ahora=AHORA).para == datetime(2027, 10, 28, 12, 0, tzinfo=UTC)
    with pytest.raises(ConformidadNoValida):
        _validar(cuando="2027-10-28T14:01", ahora=AHORA)


@pytest.mark.parametrize("malo", ["", "diaria", "Semanal", "anual"])
def test_repetir_fuera_de_las_opciones(malo):
    with pytest.raises(ConformidadNoValida):
        _validar(repetir=malo)


@pytest.mark.parametrize("malo", ["", "0", "10", "45", "120"])
def test_espera_fuera_de_las_opciones(malo):
    with pytest.raises(ConformidadNoValida):
        _validar(espera=malo)


def test_espera_de_las_opciones():
    assert [_validar(espera=str(e)).espera_min for e in ESPERAS_MIN] == list(ESPERAS_MIN)


def test_sala_que_no_es_un_uuid_se_rechaza():
    with pytest.raises(ConformidadNoValida):
        _validar(sala_id="sala")


def test_tope_no_valido_al_programar():
    with pytest.raises(ConformidadNoValida):
        _validar(tope_="90")


# ── @a48: empezar a su hora ────────────────────────────────────────────────────────────────────────────────────────────


def test_antes_de_su_hora_espera():
    assert decidir(retraso_s=-1, espera_min=15) == "esperar"


def test_a_su_hora_empieza():
    assert decidir(retraso_s=0, espera_min=15) == "empezar"


def test_con_retraso_dentro_de_la_espera_empieza():
    assert decidir(retraso_s=15 * 60, espera_min=15) == "empezar"


def test_pasada_la_espera_llega_tarde():
    assert decidir(retraso_s=15 * 60 + 1, espera_min=15) == "tarde"


def test_la_espera_es_la_de_cada_reunion():
    assert decidir(retraso_s=20 * 60, espera_min=30) == "empezar"


# ── @a53: la siguiente de una serie ────────────────────────────────────────────────────────────────────────────────────


def _madrid(*a):
    return datetime(*a, tzinfo=MADRID).astimezone(UTC)


def test_sin_repetir_no_hay_siguiente():
    assert siguiente(_madrid(2026, 10, 29, 17, 30), "no", None, AHORA) is None


def test_semanal_a_la_misma_hora_de_madrid():
    assert siguiente(_madrid(2026, 10, 29, 17, 30), "semanal", None, AHORA) == _madrid(2026, 11, 5, 17, 30)


def test_semanal_cruza_el_cambio_de_hora_sin_moverse_en_madrid():
    # 2026-10-23 17:30 CEST (15:30 UTC) → 2026-10-30 17:30 CET (16:30 UTC).
    para = _madrid(2026, 10, 23, 17, 30)
    sig = siguiente(para, "semanal", None, datetime(2026, 10, 23, 16, 0, tzinfo=UTC))
    assert sig == datetime(2026, 10, 30, 16, 30, tzinfo=UTC)
    assert sig.astimezone(MADRID).hour == 17


def test_siguiente_devuelve_utc():
    assert siguiente(_madrid(2026, 10, 29, 17, 30), "semanal", None, AHORA).tzinfo is UTC


def test_mensual_el_mismo_dia():
    assert siguiente(_madrid(2026, 10, 15, 10, 0), "mensual", 15, AHORA) == _madrid(2026, 11, 15, 10, 0)


def test_mensual_el_ultimo_dia_si_el_mes_no_lo_tiene():
    assert siguiente(_madrid(2027, 1, 31, 10, 0), "mensual", 31, AHORA) == _madrid(2027, 2, 28, 10, 0)


def test_mensual_en_bisiesto():
    assert siguiente(_madrid(2028, 1, 31, 10, 0), "mensual", 31, AHORA) == _madrid(2028, 2, 29, 10, 0)


def test_mensual_vuelve_al_dia_original_sin_correrse():
    # 31 → 28 de febrero → 31 de marzo, no 28 de marzo.
    assert siguiente(_madrid(2027, 2, 28, 10, 0), "mensual", 31, AHORA) == _madrid(2027, 3, 31, 10, 0)


def test_mensual_de_diciembre_a_enero():
    assert siguiente(_madrid(2026, 12, 10, 10, 0), "mensual", 10, AHORA) == _madrid(2027, 1, 10, 10, 0)


def test_mensual_sin_dia_usa_el_de_la_reunion():
    assert siguiente(_madrid(2026, 11, 30, 10, 0), "mensual", None, AHORA) == _madrid(2026, 12, 30, 10, 0)


def test_salta_las_que_ya_pasaron():
    """El supervisor estuvo parado: la siguiente es la primera que aún no ha pasado, no una en el pasado."""
    para = _madrid(2026, 10, 1, 10, 0)
    assert siguiente(para, "semanal", None, AHORA) == _madrid(2026, 10, 29, 10, 0)


def test_la_que_coincide_con_ahora_tambien_se_salta():
    para = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)  # sin cambio de hora en medio
    assert siguiente(para, "semanal", None, para + timedelta(days=7)) == para + timedelta(days=14)


def test_salta_meses_ya_pasados():
    assert siguiente(_madrid(2026, 7, 31, 10, 0), "mensual", 31, AHORA) == _madrid(2026, 10, 31, 10, 0)


def test_repetir_desconocido_se_rechaza():
    with pytest.raises(ValueError):
        siguiente(_madrid(2026, 10, 29, 17, 30), "diaria", None, AHORA)


def test_una_de_la_serie_en_el_salto_de_marzo_pasa_a_la_hora_siguiente():
    # 2027-03-28: las 02:30 no existen en Madrid; ese día va a las 03:30 (PEP 495, fold=0).
    para = _madrid(2027, 3, 21, 2, 30)
    sig = siguiente(para, "semanal", None, datetime(2027, 3, 21, 2, 0, tzinfo=UTC), hora=time(2, 30))
    assert sig == datetime(2027, 3, 28, 1, 30, tzinfo=UTC)
    assert sig.astimezone(MADRID).strftime("%H:%M") == "03:30"


def test_tras_el_salto_de_marzo_la_serie_vuelve_a_su_hora():
    """Revisión de V3: sin la hora original, la serie se quedaba a las 03:30 para siempre."""
    para = datetime(2027, 3, 28, 1, 30, tzinfo=UTC)  # la del salto, a las 03:30
    sig = siguiente(para, "semanal", None, para, hora=time(2, 30))
    assert sig == _madrid(2027, 4, 4, 2, 30)


def test_sin_hora_original_usa_la_de_la_reunion():
    assert siguiente(_madrid(2026, 11, 5, 17, 30), "semanal", None, AHORA, hora=None) == _madrid(2026, 11, 12, 17, 30)


def test_la_hora_original_manda_sobre_la_de_la_reunion():
    assert siguiente(_madrid(2026, 11, 5, 18, 0), "semanal", None, AHORA, hora=time(17, 30)) == _madrid(2026, 11, 12, 17, 30)
