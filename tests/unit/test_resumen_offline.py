"""F3: pruebas sin red ni contenido real; no acreditan anonimización del texto libre."""

import json

import pytest

from actas.resumen_offline import ErrorResumen, preparar, validar_respuesta


def test_peticion_usa_seudonimos_y_solo_campos_del_gateway():
    peticion, mapa = preparar([("a1", "Ana y Bruno hablaron con ANA."), ("b2", "Hola Ana")], {"a1": "Ana", "b2": "Bruno"})
    assert set(peticion) == {"model", "system", "messages", "max_tokens"}
    texto = json.dumps(peticion, ensure_ascii=False)
    assert "Ana" not in texto and "Bruno" not in texto and "a1" not in texto
    assert "S1" in texto and "S2" in texto
    assert mapa == {"S1": "Ana", "S2": "Bruno"}


@pytest.mark.parametrize(
    "segmentos,socios",
    [
        ([("x", "hola")], {"a": "Ana"}),
        ([("a", "S1 ya existía")], {"a": "Ana"}),
        ([("a", "hola")], {"a": "Ana", "b": "ANA"}),
    ],
)
def test_rechaza_hablante_desconocido_o_colisiones(segmentos, socios):
    with pytest.raises(ErrorResumen):
        preparar(segmentos, socios)


def test_validacion_y_restauracion_de_respuesta():
    acta = {
        "resumen": "S1 propuso",
        "temas": ["presupuesto"],
        "decisiones": [],
        "tareas": [{"que": "Revisar", "responsable": "S2", "fecha_limite": "2026-11-30"}],
        "pendientes": [],
    }
    respuesta = {"stop_reason": "end_turn", "content": [{"type": "text", "text": json.dumps(acta)}]}
    resultado = validar_respuesta(respuesta, {"S1": "Ana", "S2": "Bruno"})
    assert resultado["resumen"] == "Ana propuso"
    assert resultado["tareas"][0]["responsable"] == "Bruno"


def test_rechaza_refusal_json_ambiguo_y_seudonimos_desconocidos():
    with pytest.raises(ErrorResumen):
        validar_respuesta({"stop_reason": "refusal", "content": []}, {"S1": "Ana"})
    for texto in ('{"resumen":"a","resumen":"b"}', '{"resumen":"S2","temas":[],"decisiones":[],"tareas":[],"pendientes":[]}'):
        with pytest.raises(ErrorResumen):
            validar_respuesta({"stop_reason": "end_turn", "content": [{"type": "text", "text": texto}]}, {"S1": "Ana"})


def test_coincidencia_literal_no_afirma_ocultar_alias_o_referencias_indirectas():
    peticion, _ = preparar([("a", "Anita dijo que mañana llamaría la directora.")], {"a": "Ana"})
    texto = peticion["messages"][0]["content"]
    assert "Anita" in texto and "mañana" in texto and "directora" in texto


@pytest.mark.parametrize(
    "tarea",
    [
        {"que": "algo", "responsable": None, "fecha_limite": "2026-02-30"},
        {"que": "algo", "responsable": None, "fecha_limite": None, "extra": "dato"},
        {"que": "algo", "responsable": 42, "fecha_limite": None},
    ],
)
def test_rechaza_tareas_invalidas(tarea):
    texto = json.dumps({"resumen": "ok", "temas": [], "decisiones": [], "tareas": [tarea], "pendientes": []})
    with pytest.raises(ErrorResumen):
        validar_respuesta({"stop_reason": "end_turn", "content": [{"type": "text", "text": texto}]}, {"S1": "Ana"})


def test_casefold_unicode_expansiones_y_normalizacion():
    peticion, _ = preparar([("ida", "STRASSE y Straße vieron a Jose\u0301.")], {"ida": "Straße", "idb": "José"})
    texto = peticion["messages"][0]["content"]
    assert texto == "S1: S1 y S1 vieron a S2."


@pytest.mark.parametrize("responsable", ["Ana", "S1 y S2", "s1", "S3", "", "S1 "])
def test_rechaza_responsable_que_no_es_un_seudonimo_conocido_exacto(responsable):
    acta = {
        "resumen": "ok",
        "temas": [],
        "decisiones": [],
        "tareas": [{"que": "algo", "responsable": responsable, "fecha_limite": None}],
        "pendientes": [],
    }
    respuesta = {"stop_reason": "end_turn", "content": [{"type": "text", "text": json.dumps(acta)}]}
    with pytest.raises(ErrorResumen):
        validar_respuesta(respuesta, {"S1": "Ana", "S2": "Bruno"})
