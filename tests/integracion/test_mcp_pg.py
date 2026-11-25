"""MCP de solo lectura contra PostgreSQL con el rol del panel (migración 0010, ADR 0004): las consultas de siempre, sin push ni
correo, el enmascarado sobre filas reales, la papelera y la auditoría (con el mínimo privilegio)."""

import psycopg
import pytest

from actas import lectura_mcp as lm
from actas.conformidad import Peticion
from actas.estados import Estado
from actas.formulario import Socio

Denegado = psycopg.errors.InsufficientPrivilege
SEGMENTOS = [
    {
        "hablante": "pablo123", "inicio_ms": 0, "fin_ms": 3000,
        "texto": "El presupuesto sale mañana; escribe a ana@mail.com o llama al 612 345 678.",
    },
    {"hablante": "roberto9", "inicio_ms": 3500, "fin_ms": 5000, "texto": "De acuerdo con el presupuesto."},
]  # fmt: skip


@pytest.fixture
def rid(repo):
    repo.alta_socio(Socio("pablo123", "Pablo", "pablo@correo-privado.es"))
    repo.alta_socio(Socio("roberto9", "Roberto", None))
    rid = repo.pedir(Peticion(("pablo123", "roberto9"), "v1"), titulo="Socios 612345678")
    for d, h in [(Estado.PEDIDA, Estado.GRABANDO), (Estado.GRABANDO, Estado.GRABADA), (Estado.GRABADA, Estado.TRANSCRIBIENDO)]:
        repo.mover(rid, d, h)
    repo.guardar_transcripcion(rid, SEGMENTOS)
    return rid


def test_listar_y_leer_con_el_rol_del_panel(repo_panel, rid):
    lista = lm.listar_reuniones(repo_panel, None, 1)
    assert lista["total"] == 1 and lista["reuniones"][0]["titulo"] == "Socios ···678"
    assert lista["reuniones"][0]["socios"] == ["Pablo", "Roberto"]
    acta = lm.leer_acta(repo_panel, rid, 0)
    assert acta["segmentos"][0]["texto"] == "El presupuesto sale mañana; escribe a [correo] o llama al ···678."
    assert [s["hablante"] for s in acta["segmentos"]] == ["Pablo", "Roberto"]
    volcado = str(acta) + str(lista)
    for prohibido in ("pablo123", "roberto9", "correo-privado", "612"):
        assert prohibido not in volcado


def test_buscar_con_la_base_real(repo_panel, rid):
    r = lm.buscar_en_actas(repo_panel, "presupuesto")
    assert r["total"] == 2 and r["resultados"][0]["hablante"] in {"Pablo", "Roberto"}
    texto = str(r)
    assert "ana@mail.com" not in texto and "" not in texto and "<mark>" not in texto
    assert lm.buscar_en_actas(repo_panel, "inexistentezzz")["total"] == 0


def test_una_reunion_en_la_papelera_no_se_lee(repo_panel, repo, rid):
    repo_panel.a_papelera(rid, "pablo")
    with pytest.raises(lm.NoEncontrada):
        lm.leer_acta(repo_panel, rid, 0)
    assert lm.buscar_en_actas(repo_panel, "presupuesto")["total"] == 0


def test_la_auditoria_solo_se_inserta(repo_panel, repo):
    repo_panel.auditar_mcp("buscar_en_actas", "ok", 12)
    with repo.conexion() as c:
        assert c.execute("SELECT origen, herramienta, resultado, duracion_ms FROM auditoria_mcp").fetchall() == [
            ("mcp", "buscar_en_actas", "ok", 12)
        ]
    with repo_panel.conexion() as c, pytest.raises(Denegado):
        c.execute("SELECT * FROM auditoria_mcp")
    with repo_panel.conexion() as c, pytest.raises(Denegado):
        c.execute("UPDATE auditoria_mcp SET resultado = 'error'")
    with repo_panel.conexion() as c, pytest.raises(Denegado):
        c.execute("DELETE FROM auditoria_mcp")


@pytest.mark.parametrize(
    ("herramienta", "resultado", "ms"),
    [("Buscar con espacios", "ok", 1), ("buscar", "quizá", 1), ("buscar", "ok", -1), ("", "ok", 1)],
)
def test_la_base_rechaza_filas_mal_formadas(repo_panel, herramienta, resultado, ms):
    with pytest.raises(psycopg.errors.CheckViolation):
        repo_panel.auditar_mcp(herramienta, resultado, ms)
