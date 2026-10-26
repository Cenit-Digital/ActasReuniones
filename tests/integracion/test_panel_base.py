"""Migración 0002 contra PostgreSQL 18.6: quién pidió cada grabación (@a29) y el mínimo privilegio del rol del panel (@a33). El
panel escribe solo con Repositorio.pedir y Repositorio.pedir_parada, así que @a6 y el trigger diferido aplican igual que en
`actas.sh`."""

from datetime import timedelta

import psycopg
import pytest

from actas import base
from actas.busqueda import FIN, INICIO, LIMITE, OPCIONES
from actas.conformidad import Peticion
from actas.estados import Estado

Denegado = psycopg.errors.InsufficientPrivilege


def _transcrita(repo, socios, segmentos):
    rid = repo.pedir(Peticion(socios, "v1"))
    for d, h in [
        (Estado.PEDIDA, Estado.GRABANDO),
        (Estado.GRABANDO, Estado.GRABADA),
        (Estado.GRABADA, Estado.TRANSCRIBIENDO),
    ]:
        repo.mover(rid, d, h)
    repo.guardar_transcripcion(rid, segmentos)
    return rid


def test_pedir_guarda_quien_lo_pidio(repo):
    rid = repo.pedir(Peticion(("pablo",), "v1"), pedido_por="panel")
    assert repo.reunion(rid)["pedido_por"] == "panel"


def test_actas_sh_sigue_pidiendo_sin_usuario(repo):
    rid = repo.pedir(Peticion(("pablo",), "v1"))
    assert repo.reunion(rid)["pedido_por"] is None


@pytest.mark.parametrize("valor", ["", "pa blo", "x" * 65, "pablo\n", "<script>"])
def test_la_base_rechaza_un_usuario_mal_formado(repo, valor):
    with pytest.raises(psycopg.errors.CheckViolation):
        repo.pedir(Peticion(("pablo",), "v1"), pedido_por=valor)


def test_el_panel_pide_con_sus_conformidades(repo_panel, repo):
    rid = repo_panel.pedir(Peticion(("pablo", "roberto"), "v1"), pedido_por="panel")
    r = repo.reunion(rid)
    assert (r["estado"], r["socios"], r["pedido_por"]) == ("pedida", ["pablo", "roberto"], "panel")
    assert repo.conformidades(rid) == [("pablo", "v1"), ("roberto", "v1")]
    assert repo.siguiente(Estado.PEDIDA)["id"] == rid  # el supervisor la atiende como si viniera de actas.sh


def test_el_panel_tambien_pasa_por_el_trigger_de_conformidades(repo_panel):
    with pytest.raises(psycopg.errors.CheckViolation), repo_panel.conexion() as c:
        c.execute("INSERT INTO reuniones (socios, texto_version) VALUES ('{pablo}', 'v1')")


def test_el_panel_pide_la_parada_de_la_grabacion_activa(repo_panel, repo):
    assert repo_panel.pedir_parada() is None
    rid = repo.pedir(Peticion(("pablo",), "v1"))
    repo.mover(rid, Estado.PEDIDA, Estado.GRABANDO)
    assert repo_panel.pedir_parada() == rid
    assert repo.reunion(rid)["parar_pedido_en"] is not None


@pytest.mark.parametrize(
    "orden",
    [
        "DELETE FROM reuniones",
        "DELETE FROM conformidades",
        "DELETE FROM segmentos",
        "UPDATE segmentos SET texto = 'otro'",
        "UPDATE segmentos SET hablante = 'otro'",
        "UPDATE reuniones SET estado = 'transcrita'",
        "UPDATE reuniones SET socios = '{pablo}'",
        "UPDATE reuniones SET pedido_por = 'otro'",
        "UPDATE conformidades SET texto_version = 'v2'",
        "INSERT INTO reuniones (socios, texto_version, estado) VALUES ('{pablo}', 'v1', 'transcrita')",
        "INSERT INTO reuniones (socios, texto_version, trabajo_id) VALUES ('{pablo}', 'v1', gen_random_uuid())",
        "INSERT INTO segmentos (reunion_id, hablante, inicio_ms, fin_ms, texto) VALUES (gen_random_uuid(), 'a', 0, 1, 'x')",
        "INSERT INTO purgas (motivo, ficheros, bytes) VALUES ('x', 0, 0)",
        "SELECT * FROM purgas",
        "SELECT * FROM esquema_migraciones",
        "TRUNCATE segmentos",
        "CREATE TABLE intrusa (x int)",
        "ALTER TABLE segmentos ADD COLUMN x int",
        "DROP TABLE segmentos",
        "CREATE INDEX intruso ON segmentos (hablante)",
    ],
)
def test_minimo_privilegio_del_panel(repo_panel, repo, orden):
    _transcrita(repo, ("pablo",), [{"hablante": "pablo", "inicio_ms": 0, "fin_ms": 1, "texto": "hola"}])
    with pytest.raises(Denegado), repo_panel.conexion() as c:
        c.execute(orden)


def test_sin_privilegios_de_tabla_que_anulen_los_de_columna(repo, dsn):
    # Doc de GRANT: un privilegio de tabla se suma al de columna; si lo hubiera, UPDATE (col) no restringiría nada.
    _, esquema = dsn
    with repo.conexion() as c:
        filas = c.execute(
            "SELECT t, p, has_table_privilege('actas_panel', %s || '.' || t, p) FROM unnest(%s::text[]) t, "
            "unnest('{INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER,MAINTAIN}'::text[]) p",
            (esquema, ["reuniones", "conformidades", "segmentos", "purgas", "esquema_migraciones"]),
        ).fetchall()
        assert [f for f in filas if f[2]] == []
        columnas = c.execute(
            "SELECT column_name FROM information_schema.column_privileges "
            "WHERE grantee = 'actas_panel' AND table_schema = %s AND table_name = 'reuniones' AND privilege_type = 'UPDATE' "
            "ORDER BY 1",
            (esquema,),
        ).fetchall()
    assert columnas == [("actualizado_en",), ("parar_pedido_en",)]


def test_el_panel_lee_reuniones_conformidades_y_segmentos(repo_panel, repo):
    rid = _transcrita(repo, ("pablo",), [{"hablante": "pablo", "inicio_ms": 61_000, "fin_ms": 62_000, "texto": "hola"}])
    assert repo_panel.reunion(rid)["estado"] == "transcrita"
    assert repo_panel.conformidades(rid) == [("pablo", "v1")]
    assert repo_panel.segmentos(rid) == [("pablo", 61_000, 62_000, "hola")]
    assert [r["id"] for r in repo_panel.ultimas(10)] == [rid]


def test_ultimas_de_la_mas_nueva_a_la_mas_vieja_con_tope(repo):
    ids = [repo.pedir(Peticion(("pablo",), "v1")) for _ in range(3)]
    assert [r["id"] for r in repo.ultimas(2)] == ids[::-1][:2]


def test_buscar_presupuesto_da_la_reunion_el_hablante_y_el_tiempo(repo_panel, repo):
    """@a22 con el esquema real migrado: el segmento de sociopruebaa que dice «presupuesto»."""
    rid = _transcrita(
        repo,
        ("sociopruebaa", "sociopruebab"),
        [
            {"hablante": "sociopruebaa", "inicio_ms": 75_000, "fin_ms": 80_000, "texto": "Revisamos el presupuesto de octubre"},
            {"hablante": "sociopruebab", "inicio_ms": 90_000, "fin_ms": 95_000, "texto": "De acuerdo con el viaje"},
        ],
    )
    hallados = repo_panel.buscar("presupuesto", LIMITE, INICIO + FIN, OPCIONES)
    assert [(h["reunion_id"], h["hablante"], h["inicio_ms"]) for h in hallados] == [(rid, "sociopruebaa", 75_000)]
    assert f"{INICIO}presupuesto{FIN}" in hallados[0]["fragmento"]


def test_buscar_devuelve_el_fragmento_sin_escapar_para_escaparlo_despues(repo_panel, repo):
    # ts_headline quita lo que su analizador toma por etiquetas (`<script>`), pero no escapa el resto: `<` y `&` llegan crudos.
    _transcrita(repo, ("pablo",), [{"hablante": "pablo", "inicio_ms": 0, "fin_ms": 1, "texto": "presupuesto 1 < 2 & 3 <script"}])
    (h,) = repo_panel.buscar("presupuesto", LIMITE, INICIO + FIN, OPCIONES)
    assert "<" in h["fragmento"] and "&" in h["fragmento"]


def test_buscar_quita_los_centinelas_del_texto_original(repo_panel, repo):
    _transcrita(repo, ("pablo",), [{"hablante": "pablo", "inicio_ms": 0, "fin_ms": 1, "texto": f"{FIN}presupuesto{INICIO} x"}])
    (h,) = repo_panel.buscar("presupuesto", LIMITE, INICIO + FIN, OPCIONES)
    assert h["fragmento"].count(INICIO) == h["fragmento"].count(FIN) == 1
    assert h["fragmento"].index(INICIO) < h["fragmento"].index(FIN)


def test_buscar_con_tope(repo_panel, repo):
    _transcrita(
        repo,
        ("pablo",),
        [{"hablante": "pablo", "inicio_ms": i * 1000, "fin_ms": i * 1000 + 1, "texto": "presupuesto"} for i in range(5)],
    )
    assert [h["inicio_ms"] for h in repo_panel.buscar("presupuesto", 3, INICIO + FIN, OPCIONES)] == [0, 1000, 2000]


@pytest.mark.parametrize("q", ['"plan de" or -', "((( )))", "de la el", "&|!:*"])
def test_buscar_nunca_falla_por_la_sintaxis(repo_panel, repo, q):
    _transcrita(repo, ("pablo",), [{"hablante": "pablo", "inicio_ms": 0, "fin_ms": 1, "texto": "presupuesto"}])
    assert repo_panel.buscar(q, LIMITE, INICIO + FIN, OPCIONES) == []


def test_detalle_en_una_sola_consulta_de_conexion(repo_panel, repo):
    rid = _transcrita(repo, ("pablo",), [{"hablante": "pablo", "inicio_ms": 0, "fin_ms": 1, "texto": "hola"}])
    r, conformidades, segmentos = repo_panel.detalle(rid)
    assert (r["id"], r["estado"]) == (rid, "transcrita")
    assert conformidades == [("pablo", "v1")]
    assert segmentos == [("pablo", 0, 1, "hola")]


def test_detalle_de_una_reunion_que_no_existe(repo_panel):
    with pytest.raises(KeyError):
        repo_panel.detalle("00000000-0000-0000-0000-000000000000")


def test_hay_grabacion_activa_aunque_no_este_entre_las_ultimas(repo):
    assert repo.hay_grabacion() is False
    rid = repo.pedir(Peticion(("pablo",), "v1"))
    repo.mover(rid, Estado.PEDIDA, Estado.GRABANDO)
    for _ in range(3):
        repo.pedir(Peticion(("pablo",), "v1"))
    assert rid not in [r["id"] for r in repo.ultimas(2)]
    assert repo.hay_grabacion() is True


def test_fechas_en_la_zona_del_panel(dsn, repo):
    url, esquema = dsn
    repo.pedir(Peticion(("pablo",), "v1"))
    madrid = base.Repositorio(url, esquema, zona="Europe/Madrid").ultimas(1)[0]["creado_en"]
    utc = base.Repositorio(url, esquema, zona="UTC").ultimas(1)[0]["creado_en"]
    assert madrid == utc
    assert madrid.utcoffset() in {timedelta(hours=1), timedelta(hours=2)}
    assert utc.utcoffset() == timedelta(0)
