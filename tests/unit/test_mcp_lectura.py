# ruff: noqa: E501 — fixtures compactos que imitan filas de PostgreSQL
import datetime as dt
import json
from typing import Any

import pytest

from actas import busqueda
from actas import lectura_mcp as lm

RID = "11111111-1111-1111-1111-111111111111"
AHORA = dt.datetime(2026, 11, 25, 9, 0, tzinfo=dt.UTC)
SOCIOS = [{"push": "pablo123", "nombre": "Pablo", "activo": True}, {"push": "roberto9", "nombre": "Roberto", "activo": True}]


def reunion(**extra: Any) -> dict[str, Any]:
    base = {
        "id": RID, "creado_en": AHORA, "inicio": AHORA, "fin": AHORA + dt.timedelta(minutes=30), "estado": "transcrita",
        "motivo": None, "socios": ["pablo123", "roberto9"], "pedido_por": "pablo", "titulo": "Socios: llama a 612345678",
        "programada_para": None, "tope_min": 120, "repetir": "no", "sala_id": "sala-secreta", "trabajo_id": "trabajo-9",
        "papelera_en": None,
    }  # fmt: skip
    return base | extra


def seg(n: int, texto: str, hablante: str = "pablo123") -> tuple[str, int, int, str]:
    return (hablante, n * 1000, n * 1000 + 900, texto)


class Repo:
    def __init__(self, segmentos: list[tuple[str, int, int, str]] | None = None, **r: Any) -> None:
        self.segmentos = segmentos if segmentos is not None else [seg(0, "hola")]
        self.r = reunion(**r)
        self.busquedas: list[tuple[Any, ...]] = []

    def socios(self) -> list[dict[str, Any]]:
        return SOCIOS

    def ultimas(self, limite: int) -> list[dict[str, Any]]:
        assert limite == 100
        return [self.r, reunion(id="22222222-2222-2222-2222-222222222222", estado="error", motivo="falló ana@mail.com")]

    def detalle(self, rid: str) -> Any:
        if rid != RID:
            raise KeyError(rid)
        return self.r, [("pablo123", "v1")], self.segmentos

    def buscar(self, q: str, limite: int, quitar: str, poner: str, opciones: str) -> list[dict[str, Any]]:
        self.busquedas.append((q, limite))
        frag = f"llama al {busqueda.INICIO}612{busqueda.FIN} 345 678 {busqueda.SUSTITUTOS['&']} escribe a ana@mail.com"
        return [{"reunion_id": RID, "creado_en": AHORA, "hablante": "pablo123", "inicio_ms": 61000, "fragmento": frag}]


def test_reunion_solo_lleva_la_lista_blanca_y_nunca_push_sala_ni_trabajo() -> None:
    r = lm.reunion_mcp(reunion(), {"pablo123": "Pablo", "roberto9": "Roberto"})
    assert set(r) == {"id", "titulo", "estado", "creada_en", "programada_para", "inicio", "fin", "duracion", "socios", "motivo"}
    assert r["socios"] == ["Pablo", "Roberto"] and r["titulo"] == "Socios: llama a ···678" and r["duracion"] == "00:30:00"
    texto = json.dumps(r)
    for prohibido in ("pablo123", "roberto9", "sala-secreta", "trabajo-9", "pedido_por"):
        assert prohibido not in texto


def test_un_socio_desconocido_no_enseña_su_push() -> None:
    r = lm.reunion_mcp(reunion(socios=["zzz999"]), {})
    assert r["socios"] == ["Socio"] and "zzz999" not in json.dumps(r)


def test_titulo_por_defecto_y_motivo_enmascarado() -> None:
    r = lm.reunion_mcp(reunion(titulo=None, motivo="falló ana@mail.com"), {})
    assert r["titulo"] == "Reunión del 2026-11-25 09:00" and r["motivo"] == "falló [correo]"


def test_listar_filtra_por_estado_y_pagina() -> None:
    r = lm.listar_reuniones(Repo(), "error", 1)
    assert r["total"] == 1 and r["reuniones"][0]["estado"] == "error" and r["pagina"] == 1
    assert lm.listar_reuniones(Repo(), None, 1)["total"] == 2
    assert lm.listar_reuniones(Repo(), None, 10**40)["pagina"] == lm.MAX_PAGINA
    assert lm.listar_reuniones(Repo(), None, 2)["reuniones"] == []


def test_listar_rechaza_un_estado_inventado() -> None:
    with pytest.raises(lm.ConsultaNoValida):
        lm.listar_reuniones(Repo(), "'; drop", 1)


def test_leer_acta_enmascara_y_pone_nombres_de_socios() -> None:
    repo = Repo([seg(0, "mi móvil es 612 345 678 y ana@mail.com"), seg(1, "ok", "roberto9"), seg(2, "x", "otro")])
    r = lm.leer_acta(repo, RID, 0)
    assert [s["hablante"] for s in r["segmentos"]] == ["Pablo", "Roberto", "Socio"]
    assert r["segmentos"][0]["texto"] == "mi móvil es ···678 y [correo]" and r["segmentos"][0]["tiempo"] == "00:00:00"
    assert r["siguiente"] is None and r["total_segmentos"] == 3
    assert "pablo123" not in json.dumps(r) and "sala-secreta" not in json.dumps(r)


@pytest.mark.parametrize("rid", ["", "no-es-uuid", "../x"])
def test_leer_acta_valida_el_identificador(rid: str) -> None:
    with pytest.raises(lm.ConsultaNoValida):
        lm.leer_acta(Repo(), rid, 0)


def test_leer_acta_inexistente_o_en_papelera_no_se_lee() -> None:
    with pytest.raises(lm.NoEncontrada):
        lm.leer_acta(Repo(), "22222222-2222-2222-2222-222222222222", 0)
    with pytest.raises(lm.NoEncontrada):
        lm.leer_acta(Repo(papelera_en=AHORA), RID, 0)


def test_leer_acta_pagina_por_segmentos() -> None:
    repo = Repo([seg(n, "x") for n in range(lm.MAX_SEGMENTOS + 5)])
    p1 = lm.leer_acta(repo, RID, 0)
    assert len(p1["segmentos"]) == lm.MAX_SEGMENTOS and p1["siguiente"] == lm.MAX_SEGMENTOS
    p2 = lm.leer_acta(repo, RID, p1["siguiente"])
    assert len(p2["segmentos"]) == 5 and p2["siguiente"] is None
    assert lm.leer_acta(repo, RID, -3)["desde"] == 0
    assert lm.leer_acta(Repo([seg(n, "x") for n in range(500)]), RID, 8)["siguiente"] == 208


def test_leer_acta_pagina_por_tamano_y_el_tope_es_exacto() -> None:
    repo = Repo([seg(n, "t" * 1000) for n in range(30)])
    p = lm.leer_acta(repo, RID, 0)
    assert len(p["segmentos"]) == 20 and p["siguiente"] == 20  # 20 × 1 000 = 20 000: cabe justo
    grandes = Repo([seg(n, "g" * 1900) for n in range(11)] + [seg(11, "pequeño")])
    assert [s["inicio_ms"] // 1000 for s in lm.leer_acta(grandes, RID, 0)["segmentos"]] == list(range(10))


def test_un_segmento_gigante_se_recorta() -> None:
    p = lm.leer_acta(Repo([seg(0, "a" * 50_000)]), RID, 0)
    assert len(p["segmentos"][0]["texto"]) == lm.MAX_TEXTO + 1


def test_buscar_limpia_centinelas_y_enmascara() -> None:
    repo = Repo()
    r = lm.buscar_en_actas(repo, "  presupuesto  ")
    assert repo.busquedas == [("presupuesto", lm.MAX_BUSQUEDA)]
    h = r["resultados"][0]
    assert h["fragmento"] == "llama al ···678 & escribe a [correo]" and h["hablante"] == "Pablo" and h["tiempo"] == "00:01:01"
    assert busqueda.INICIO not in json.dumps(h, ensure_ascii=False)


@pytest.mark.parametrize(
    "consulta",
    [
        "612",
        "ana@mail.com",
        "ana arroba mail",
        "6 1 2",
        "61234",
        "tel 612345678",
        "ARROBA",
        "",
        "   ",
        '"6, 1, 2"',
        "6,1,2",
        "6;1;2",
        "6_1_2",
        "6 1 2 3",
    ],
)
def test_buscar_rechaza_vacias_y_oraculos(consulta: str) -> None:
    with pytest.raises(lm.ConsultaNoValida):
        lm.buscar_en_actas(Repo(), consulta)


@pytest.mark.parametrize("consulta", ["presupuesto", "acta 2026", "sala 4", "1999 balance"])
def test_buscar_admite_palabras_anos_y_numeros_cortos(consulta: str) -> None:
    assert lm.buscar_en_actas(Repo(), consulta)["total"] == 1


def test_los_topes_son_los_documentados() -> None:
    assert (lm.MAX_REUNIONES, lm.MAX_BUSQUEDA, lm.MAX_SEGMENTOS, lm.MAX_CARACTERES) == (25, 20, 200, 20_000)
    assert (lm.MAX_TEXTO, lm.MAX_TITULO, lm.MAX_MOTIVO, lm.MAX_PAGINA) == (2_000, 200, 200, 10_000)


def test_dos_cifras_si_y_tres_no_y_los_anos_no_cuentan() -> None:
    assert lm.buscar_en_actas(Repo(), "sala 12")["total"] == 1
    assert lm.buscar_en_actas(Repo(), "acta 2026 sala 12")["total"] == 1
    with pytest.raises(lm.ConsultaNoValida):
        lm.buscar_en_actas(Repo(), "sala 123")


# ── Bordes que fijan topes y paginación ──────────────────────────────────────────────────────────────


class RepoMuchas(Repo):
    def ultimas(self, limite: int) -> list[dict[str, Any]]:
        return [reunion(id=f"{n:08d}-0000-0000-0000-000000000000", estado="transcrita") for n in range(60)]


def test_listar_pagina_de_25_en_25() -> None:
    p1, p2, p3 = (lm.listar_reuniones(RepoMuchas(), None, n) for n in (1, 2, 3))
    assert [len(p["reuniones"]) for p in (p1, p2, p3)] == [25, 25, 10] and p1["total"] == 60
    assert p2["reuniones"][0]["id"].startswith("00000025") and p3["reuniones"][0]["id"].startswith("00000050")


def test_la_pagina_cero_o_negativa_es_la_primera() -> None:
    assert lm.listar_reuniones(Repo(), None, 0)["pagina"] == 1
    assert lm.listar_reuniones(Repo(), None, -5)["pagina"] == 1


def test_el_filtro_por_estado_deja_solo_ese_estado() -> None:
    r = lm.listar_reuniones(Repo(), "transcrita", 1)
    assert r["total"] == 1 and r["reuniones"][0]["estado"] == "transcrita"


def test_los_nombres_de_socio_se_recortan_a_64() -> None:
    larga = "n" * 100
    repo = Repo([seg(0, "x")])
    repo.socios = lambda: [{"push": "pablo123", "nombre": larga, "activo": True}]  # type: ignore[method-assign]
    assert len(lm.leer_acta(repo, RID, 0)["segmentos"][0]["hablante"]) == 65
    assert len(lm.reunion_mcp(reunion(), {"pablo123": larga})["socios"][0]) == 65
    assert len(lm.buscar_en_actas(repo, "presupuesto")["resultados"][0]["hablante"]) == 65


def test_el_tope_se_suma_y_no_se_combina_con_un_o() -> None:
    p = lm.leer_acta(Repo([seg(n, "t" * 1023) for n in range(30)]), RID, 0)
    assert len(p["segmentos"]) == 19 and p["siguiente"] == 19  # 19 × 1 023 = 19 437; el 20.º llegaría a 20 460


def test_el_tope_exacto_no_deja_pasar_un_caracter_mas() -> None:
    p = lm.leer_acta(Repo([*[seg(n, "t" * 1000) for n in range(20)], seg(20, "x")]), RID, 0)
    assert len(p["segmentos"]) == 20 and p["siguiente"] == 20
