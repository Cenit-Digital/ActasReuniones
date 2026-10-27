"""V3 en la base (migración 0006, KubernetesInfrastructure#298, ADR 0023 decisiones 5 y 6): programar, modificar (@a49), cancelar
(@a50), la papelera y el borrado por `borrar_reunion` (@a51), la purga de 12 meses (@a52) y la serie (@a53, lado de la base).

El panel escribe solo por funciones SECURITY DEFINER (la puerta @a33 no le admite más UPDATE que el de la parada), y ningún rol
de aplicación tiene DELETE: borra solo `purgar_actas`, que ejecuta el supervisor."""

from datetime import UTC, datetime, timedelta

import psycopg
import pytest

from actas.base import PROGRAMADO
from actas.conformidad import Peticion
from actas.estados import Estado, TransicionNoValida
from actas.planificador import MADRID, Programacion

Denegado = (psycopg.errors.InsufficientPrivilege, psycopg.errors.RaiseException, psycopg.errors.CheckViolation)
USUARIO = "pablo"


def _sala(repo, nombre="socios"):
    return repo.crear_sala(nombre, f"room{nombre}", "abcd", b"\x00" * 40, USUARIO)


def _prog(sala, **cambios):
    datos = {
        "titulo": "Socios · seguimiento",
        "sala_id": sala,
        "para": datetime.now(UTC) + timedelta(days=2),
        "tope_min": 120,
        "repetir": "no",
        "espera_min": 15,
        "socios": ("pablo", "roberto"),
        "version": "v1",
    }
    datos.update(cambios)
    return Programacion(**datos)


def _transcrita(repo, sala=None):
    rid = repo.pedir(Peticion(("pablo",), "v1"), USUARIO, sala)
    repo.mover(rid, Estado.PEDIDA, Estado.GRABANDO, inicio=True)
    repo.mover(rid, Estado.GRABANDO, Estado.GRABADA, motivo="pedida", fin=True)
    repo.mover(rid, Estado.GRABADA, Estado.TRANSCRIBIENDO, trabajo_id="00000000-0000-4000-8000-00000000aaaa")
    repo.guardar_transcripcion(rid, [{"hablante": "pablo", "inicio_ms": 0, "fin_ms": 900, "texto": "presupuesto aprobado"}])
    return rid


def _cuenta(repo, tabla, rid):
    with repo.conexion() as c:
        columna = "id" if tabla == "reuniones" else "reunion_id"
        return c.execute(f"SELECT count(*) FROM {tabla} WHERE {columna} = %s", (rid,)).fetchone()[0]  # noqa: S608


# ── Programar ──────────────────────────────────────────────────────────────────────────────────────────────────────────


def test_programar_guarda_la_reunion_y_una_conformidad_por_socio(repo_panel, repo):
    sala = _sala(repo)
    p = _prog(sala, repetir="mensual")
    rid = repo_panel.programar(p, USUARIO)
    r = repo.reunion(rid)
    assert r["estado"] == "programada"
    assert (r["titulo"], r["sala_id"], r["tope_min"], r["repetir"], r["espera_min"]) == (
        "Socios · seguimiento",
        sala,
        120,
        "mensual",
        15,
    )
    assert r["programada_para"] == p.para
    assert r["repetir_dia"] == p.para.astimezone(MADRID).day
    assert r["repetir_hora"] == p.para.astimezone(MADRID).time().replace(tzinfo=None)
    assert (r["pedido_por"], r["inicio"], r["fin"]) == (USUARIO, None, None)
    assert repo.conformidades(rid) == [("pablo", "v1"), ("roberto", "v1")]


def test_programar_sin_repetir_no_guarda_dia(repo_panel, repo):
    rid = repo_panel.programar(_prog(_sala(repo)), USUARIO)
    assert (repo.reunion(rid)["repetir_dia"], repo.reunion(rid)["repetir_hora"]) == (None, None)


def test_la_base_no_programa_en_el_pasado(repo_panel, repo):
    with pytest.raises(Denegado):
        repo_panel.programar(_prog(_sala(repo), para=datetime.now(UTC) - timedelta(minutes=1)), USUARIO)


def test_el_panel_no_inserta_el_estado_por_su_cuenta(repo_panel, repo):
    with pytest.raises(Denegado), repo_panel.conexion() as c:
        c.execute("INSERT INTO reuniones (estado, socios, texto_version) VALUES ('programada', '{pablo}', 'v1')")


@pytest.mark.parametrize("estado", ["grabando", "grabada", "transcribiendo", "transcrita", "error", "cancelada"])
def test_una_reunion_solo_nace_pedida_o_programada(repo_app, repo, estado):
    with pytest.raises(Denegado), repo_app.conexion() as c:
        c.execute(
            "INSERT INTO reuniones (estado, socios, texto_version, programada_para, espera_min) "
            "VALUES (%s, '{pablo}', 'v1', now() + interval '1 day', 15)",
            (estado,),
        )


def test_una_programada_necesita_su_hora_y_su_espera(repo):
    with pytest.raises(psycopg.errors.CheckViolation), repo.conexion() as c:
        c.execute("INSERT INTO reuniones (estado, socios, texto_version) VALUES ('programada', '{pablo}', 'v1')")


def test_grabar_ahora_con_titulo_y_tope(repo_panel, repo):
    rid = repo_panel.pedir(Peticion(("pablo",), "v1"), USUARIO, _sala(repo), titulo="Extraordinaria", tope_min=60)
    r = repo.reunion(rid)
    assert (r["estado"], r["titulo"], r["tope_min"], r["programada_para"]) == ("pedida", "Extraordinaria", 60, None)


def test_grabar_ahora_sin_tope_es_el_de_f1(repo):
    rid = repo.pedir(Peticion(("pablo",), "v1"))
    assert repo.reunion(rid)["tope_min"] == 180


# ── Conformidades (B1 de #287 y @a6, en programadas) ───────────────────────────────────────────────────────────────────


def test_el_panel_no_anade_conformidades_a_una_programada(repo_panel, repo):
    rid = repo_panel.programar(_prog(_sala(repo), socios=("pablo",)), USUARIO)
    with pytest.raises(Denegado), repo_panel.conexion() as c:
        c.execute("INSERT INTO conformidades (reunion_id, socio, texto_version) VALUES (%s, 'roberto', 'v1')", (rid,))


def test_el_supervisor_no_anade_conformidades_a_una_programada(repo_app, repo):
    rid = repo.programar(_prog(_sala(repo), socios=("pablo",)), USUARIO)
    with pytest.raises(Denegado), repo_app.conexion() as c:
        c.execute("INSERT INTO conformidades (reunion_id, socio, texto_version) VALUES (%s, 'roberto', 'v1')", (rid,))


def test_nadie_anade_conformidades_a_una_reunion_pasada(repo_app, repo):
    rid = _transcrita(repo)
    with pytest.raises(Denegado), repo_app.conexion() as c:
        c.execute("INSERT INTO conformidades (reunion_id, socio, texto_version) VALUES (%s, 'roberto', 'v1')", (rid,))


def test_una_programada_sin_todas_sus_conformidades_no_empieza(repo):
    """«Todos» (Pablo, 2026-10-27): si falta la conformidad de un socio, la base no la deja pasar a grabando."""
    rid = repo.programar(_prog(_sala(repo)), USUARIO)
    with repo.conexion() as c:
        c.execute("DELETE FROM conformidades WHERE reunion_id = %s AND socio = 'roberto'", (rid,))
    with pytest.raises(psycopg.errors.CheckViolation):
        repo.mover(rid, Estado.PROGRAMADA, Estado.GRABANDO, inicio=True)
    assert repo.reunion(rid)["estado"] == "programada"


def test_una_programada_sin_conformidades_puede_pasar_a_error(repo):
    rid = repo.programar(_prog(_sala(repo)), USUARIO)
    with repo.conexion() as c:
        c.execute("DELETE FROM conformidades WHERE reunion_id = %s", (rid,))
    repo.mover(rid, Estado.PROGRAMADA, Estado.ERROR, motivo="conformidad")
    assert repo.reunion(rid)["estado"] == "error"


def test_una_programada_con_sus_conformidades_empieza(repo):
    rid = repo.programar(_prog(_sala(repo)), USUARIO)
    repo.mover(rid, Estado.PROGRAMADA, Estado.GRABANDO, inicio=True)
    assert repo.reunion(rid)["estado"] == "grabando"


# ── @a49: modificar ────────────────────────────────────────────────────────────────────────────────────────────────────


def test_a49_modificar_una_programada(repo_panel, repo):
    sala, otra = _sala(repo), _sala(repo, "trimestral")
    rid = repo_panel.programar(_prog(sala), USUARIO)
    nueva = _prog(
        otra,
        titulo="Presupuesto",
        para=datetime.now(UTC) + timedelta(days=5),
        tope_min=60,
        repetir="semanal",
        espera_min=30,
        socios=("pablo",),
    )
    assert repo_panel.modificar_programada(rid, nueva, USUARIO) is True
    r = repo.reunion(rid)
    assert (r["titulo"], r["sala_id"], r["programada_para"], r["tope_min"], r["repetir"], r["espera_min"]) == (
        "Presupuesto",
        otra,
        nueva.para,
        60,
        "semanal",
        30,
    )
    assert list(r["socios"]) == ["pablo"]
    assert r["repetir_hora"] == nueva.para.astimezone(MADRID).time().replace(tzinfo=None)
    assert repo.conformidades(rid) == [("pablo", "v1")]
    assert [(e["tipo"], e["detalle"]) for e in repo.eventos(rid)] == [("modificada", {"usuario": USUARIO})]


def test_a49_modificar_anade_socios_con_su_conformidad(repo_panel, repo):
    rid = repo_panel.programar(_prog(_sala(repo), socios=("pablo",)), USUARIO)
    sala = repo.reunion(rid)["sala_id"]
    assert repo_panel.modificar_programada(rid, _prog(sala, socios=("pablo", "roberto")), USUARIO)
    assert repo.conformidades(rid) == [("pablo", "v1"), ("roberto", "v1")]


def test_a49_modificar_a_una_hora_pasada_se_rechaza(repo_panel, repo):
    sala = _sala(repo)
    rid = repo_panel.programar(_prog(sala), USUARIO)
    with pytest.raises(Denegado):
        repo_panel.modificar_programada(rid, _prog(sala, para=datetime.now(UTC) - timedelta(minutes=1)), USUARIO)


def test_a49_modificar_una_que_no_existe(repo_panel, repo):
    assert repo_panel.modificar_programada("00000000-0000-4000-8000-0000000000ff", _prog(_sala(repo)), USUARIO) is None


def test_a49_modificar_una_que_ya_graba_se_rechaza(repo_panel, repo):
    sala = _sala(repo)
    rid = repo_panel.programar(_prog(sala), USUARIO)
    repo.mover(rid, Estado.PROGRAMADA, Estado.GRABANDO, inicio=True)
    assert repo_panel.modificar_programada(rid, _prog(sala, tope_min=60), USUARIO) is False
    assert repo.reunion(rid)["tope_min"] == 120


@pytest.mark.parametrize(
    "cambio",
    [
        "programada_para = now() + interval '3 days'",
        "sala_id = NULL",
        "tope_min = 60",
        "socios = '{pablo}'",
        "titulo = 'otro'",
        "repetir = 'semanal'",
        "espera_min = 60",
        "repetir_hora = '09:00'",
        "texto_version = 'v2'",
    ],
)
def test_a49_la_base_rechaza_cambiar_una_que_ya_graba(repo_app, repo, cambio):
    """Ni el supervisor, que tiene UPDATE de tabla: lo impide un trigger."""
    rid = repo.programar(_prog(_sala(repo)), USUARIO)
    repo.mover(rid, Estado.PROGRAMADA, Estado.GRABANDO, inicio=True)
    with pytest.raises(Denegado), repo_app.conexion() as c:
        c.execute(f"UPDATE reuniones SET {cambio} WHERE id = %s", (rid,))  # noqa: S608


def test_a49_el_panel_no_modifica_con_update(repo_panel, repo):
    rid = repo_panel.programar(_prog(_sala(repo)), USUARIO)
    with pytest.raises(Denegado), repo_panel.conexion() as c:
        c.execute("UPDATE reuniones SET tope_min = 60 WHERE id = %s", (rid,))


def test_la_vida_de_una_reunion_sigue_pudiendo_actualizarse(repo_app, repo):
    """El trigger solo congela lo programado: el supervisor sigue moviendo el estado, el motivo, el inicio y el fin."""
    rid = repo.programar(_prog(_sala(repo)), USUARIO)
    repo_app.mover(rid, Estado.PROGRAMADA, Estado.GRABANDO, inicio=True)
    repo_app.mover(rid, Estado.GRABANDO, Estado.GRABADA, motivo="pedida", fin=True)
    assert repo.reunion(rid)["estado"] == "grabada"


# ── @a50: cancelar ─────────────────────────────────────────────────────────────────────────────────────────────────────


def test_a50_cancelar_no_borra_filas(repo_panel, repo):
    rid = repo_panel.programar(_prog(_sala(repo), repetir="semanal"), USUARIO)
    assert repo_panel.cancelar(rid, USUARIO) is True
    r = repo.reunion(rid)
    assert (r["estado"], r["repetir"], r["motivo"]) == ("cancelada", "semanal", None)  # quién, en el historial
    assert (_cuenta(repo, "reuniones", rid), _cuenta(repo, "conformidades", rid)) == (1, 2)
    assert [(e["tipo"], e["detalle"]) for e in repo.eventos(rid)] == [
        ("estado", {"desde": "programada", "hasta": "cancelada", "usuario": USUARIO})
    ]


def test_a50_cancelar_la_serie_deja_de_repetir(repo_panel, repo):
    rid = repo_panel.programar(_prog(_sala(repo), repetir="semanal"), USUARIO)
    assert repo_panel.cancelar(rid, USUARIO, serie=True) is True
    r = repo.reunion(rid)
    assert (r["estado"], r["repetir"]) == ("cancelada", "no")
    assert repo.eventos(rid)[-1]["detalle"] == {
        "desde": "programada",
        "hasta": "cancelada",
        "usuario": USUARIO,
        "accion": "serie",
    }


def test_a50_solo_se_cancela_una_programada(repo_panel, repo):
    rid = _transcrita(repo)
    assert repo_panel.cancelar(rid, USUARIO) is False
    assert repo.reunion(rid)["estado"] == "transcrita"


def test_a50_cancelar_una_que_no_existe(repo_panel, repo):
    assert repo_panel.cancelar("00000000-0000-4000-8000-0000000000ff", USUARIO) is None


# ── @a51: papelera y borrado ───────────────────────────────────────────────────────────────────────────────────────────


def test_a51_eliminar_la_manda_a_la_papelera_y_se_recupera(repo_panel, repo):
    rid = _transcrita(repo)
    assert repo_panel.a_papelera(rid, USUARIO) is True
    r = repo.reunion(rid)
    assert r["papelera_en"] is not None and r["papelera_por"] == USUARIO
    assert repo_panel.a_papelera(rid, USUARIO) is False  # ya está
    assert [e["id"] for e in repo_panel.papelera()] == [rid]
    assert repo_panel.recuperar(rid, USUARIO) is True
    assert repo.reunion(rid)["papelera_en"] is None and repo_panel.papelera() == []
    assert repo_panel.recuperar(rid, USUARIO) is False
    assert [(e["tipo"], e["detalle"]) for e in repo.eventos(rid) if e["tipo"] == "papelera"] == [
        ("papelera", {"accion": "eliminada", "usuario": USUARIO}),
        ("papelera", {"accion": "recuperada", "usuario": USUARIO}),
    ]


@pytest.mark.parametrize("estado", ["pedida", "programada"])
def test_a51_solo_va_a_la_papelera_una_reunion_terminada(repo_panel, repo, estado):
    sala = _sala(repo)
    if estado == "pedida":
        rid = repo.pedir(Peticion(("pablo",), "v1"), USUARIO, sala)
    else:
        rid = repo.programar(_prog(sala), USUARIO)
    assert repo_panel.a_papelera(rid, USUARIO) is False
    assert repo.reunion(rid)["papelera_en"] is None


def test_a51_la_base_no_admite_en_la_papelera_una_reunion_en_marcha(repo):
    rid = repo.pedir(Peticion(("pablo",), "v1"))
    with pytest.raises(psycopg.errors.CheckViolation), repo.conexion() as c:
        c.execute("UPDATE reuniones SET papelera_en = now(), papelera_por = 'pablo' WHERE id = %s", (rid,))


def test_a51_eliminar_una_que_no_existe(repo_panel, repo):
    assert repo_panel.a_papelera("00000000-0000-4000-8000-0000000000ff", USUARIO) is None
    assert repo_panel.recuperar("00000000-0000-4000-8000-0000000000ff", USUARIO) is None


def _a_mano(repo, orden, params):
    """Una fecha de hace tiempo, escrita sin los triggers (la base no deja cambiar `creado_en` ni lo programado de una
    reunión que ya no está programada)."""
    with repo.conexion() as c:
        c.execute("ALTER TABLE reuniones DISABLE TRIGGER USER")
        c.execute(orden, params)
        c.execute("ALTER TABLE reuniones ENABLE TRIGGER USER")


def _hace(repo, rid, columna, intervalo):
    with repo.conexion() as c:
        c.execute(f"UPDATE reuniones SET {columna} = now() - %s::interval WHERE id = %s", (intervalo, rid))  # noqa: S608


def test_a51_a_los_7_dias_se_borra_con_sus_dependientes_y_queda_en_purgas(repo_panel, repo_app, repo):
    rid = _transcrita(repo)
    repo_panel.a_papelera(rid, USUARIO)
    _hace(repo, rid, "papelera_en", "6 days 23 hours")
    assert repo_app.purgar_actas() == 0
    assert _cuenta(repo, "reuniones", rid) == 1
    _hace(repo, rid, "papelera_en", "7 days 1 minute")
    assert repo_app.purgar_actas() == 1
    assert [_cuenta(repo, t, rid) for t in ("reuniones", "conformidades", "segmentos", "eventos")] == [0, 0, 0, 0]
    with repo.conexion() as c:
        filas = c.execute(
            "SELECT reunion_id::text, motivo, ficheros, bytes, usuario FROM purgas WHERE reunion_id = %s", (rid,)
        ).fetchall()
    assert filas == [(rid, "papelera_7d", 0, 0, USUARIO)]


def test_a51_purgas_no_guarda_contenido(repo):
    with repo.conexion() as c:
        columnas = [
            f[0]
            for f in c.execute(
                "SELECT attname FROM pg_attribute WHERE attrelid = 'purgas'::regclass AND attnum > 0 AND NOT attisdropped "
                "ORDER BY attnum"
            ).fetchall()
        ]
    assert columnas == ["id", "reunion_id", "motivo", "ficheros", "bytes", "creado_en", "usuario"]


def test_a51_ningun_rol_de_aplicacion_tiene_delete_directo(repo):
    with repo.conexion() as c:
        con_borrado = c.execute(
            """SELECT r.rolname, c.relname FROM pg_class c, (VALUES ('actas_panel'), ('actas_app')) AS r(rolname)
               WHERE c.relnamespace = current_schema()::regnamespace AND c.relkind IN ('r', 'p')
                 AND has_table_privilege(r.rolname, c.oid, 'DELETE,TRUNCATE')"""
        ).fetchall()
    assert con_borrado == []


@pytest.mark.parametrize("tabla", ["reuniones", "conformidades", "segmentos", "eventos", "purgas"])
def test_a51_el_panel_no_borra_con_delete(repo_panel, repo, tabla):
    _transcrita(repo)
    with pytest.raises(Denegado), repo_panel.conexion() as c:
        c.execute(f"DELETE FROM {tabla}")  # noqa: S608


def test_a51_el_supervisor_no_borra_con_delete(repo_app, repo):
    _transcrita(repo)
    with pytest.raises(Denegado), repo_app.conexion() as c:
        c.execute("DELETE FROM reuniones")


FUNCIONES = {
    "programar(text, uuid, timestamp with time zone, integer, text, integer, text[], text, text)": "actas_panel",
    "modificar_programada(uuid, text, uuid, timestamp with time zone, integer, text, integer, text[], text, text)": (
        "actas_panel"
    ),
    "cancelar_reunion(uuid, text, boolean)": "actas_panel",
    "a_papelera(uuid, text)": "actas_panel",
    "recuperar(uuid, text)": "actas_panel",
    "purgar_actas()": "actas_app",
    "borrar_reunion(uuid, text, text)": None,
}


@pytest.mark.parametrize(("firma", "rol"), FUNCIONES.items())
def test_a51_cada_funcion_la_ejecuta_solo_su_rol_con_search_path_fijo(repo, dsn, firma, rol):
    _, esquema = dsn
    with repo.conexion() as c:
        fila = c.execute(
            """SELECT has_function_privilege('actas_panel', p.oid, 'EXECUTE'),
                      has_function_privilege('actas_app', p.oid, 'EXECUTE'),
                      p.prosecdef, p.proconfig,
                      EXISTS (SELECT FROM aclexplode(p.proacl) a WHERE a.grantee = 0)
               FROM pg_proc p WHERE p.oid = %s::regprocedure""",
            (f"{esquema}.{firma}",),
        ).fetchone()
    assert fila[:2] == (rol == "actas_panel", rol == "actas_app")
    assert fila[2] is True
    assert fila[3] == [f"search_path={esquema}, pg_temp"]
    assert fila[4] is False  # sin EXECUTE para PUBLIC


# ── @a52: purga de 12 meses ────────────────────────────────────────────────────────────────────────────────────────────


def test_a52_una_transcripcion_de_mas_de_12_meses_se_borra(repo_app, repo):
    vieja, reciente = _transcrita(repo), _transcrita(repo)
    _hace(repo, vieja, "fin", "12 months 1 day")
    _hace(repo, reciente, "fin", "11 months 27 days")
    assert repo_app.purgar_actas() == 1
    assert (_cuenta(repo, "reuniones", vieja), _cuenta(repo, "reuniones", reciente)) == (0, 1)
    with repo.conexion() as c:
        assert c.execute("SELECT motivo, usuario FROM purgas WHERE reunion_id = %s", (vieja,)).fetchall() == [("plazo_12m", None)]


def test_a52_la_purga_no_toca_lo_que_esta_en_marcha(repo_app, repo):
    rid = repo.pedir(Peticion(("pablo",), "v1"))
    _a_mano(repo, "UPDATE reuniones SET creado_en = now() - interval '2 years' WHERE id = %s", (rid,))
    assert repo_app.purgar_actas() == 0 and _cuenta(repo, "reuniones", rid) == 1


def test_a52_una_cancelada_de_hace_mas_de_12_meses_tambien_se_borra(repo_panel, repo_app, repo):
    rid = repo_panel.programar(_prog(_sala(repo)), USUARIO)
    repo_panel.cancelar(rid, USUARIO)
    _a_mano(repo, "UPDATE reuniones SET creado_en = now() - interval '13 months' WHERE id = %s", (rid,))
    assert repo_app.purgar_actas() == 0  # su fecha es la de programada_para, que es futura
    _a_mano(repo, "UPDATE reuniones SET programada_para = now() - interval '13 months' WHERE id = %s", (rid,))
    assert repo_app.purgar_actas() == 1


# ── La papelera no aparece en la lista, la búsqueda ni el enlace de transcribir ────────────────────────────────────────


def test_lo_de_la_papelera_no_sale_en_el_panel(repo_panel, repo):
    rid = _transcrita(repo)
    otra = _transcrita(repo)
    repo_panel.a_papelera(rid, USUARIO)
    assert [r["id"] for r in repo_panel.ultimas(10)] == [otra]
    assert {h["reunion_id"] for h in repo_panel.buscar("presupuesto", 10, "", "", "")} == {otra}
    assert repo_panel.reunion_de_trabajo("00000000-0000-4000-8000-00000000aaaa") == otra


# ── Programadas y serie (lado de la base de @a48 y @a53) ──────────────────────────────────────────────────────────────


def test_programadas_en_orden_de_hora(repo_panel, repo):
    sala = _sala(repo)
    tarde = repo_panel.programar(_prog(sala, para=datetime.now(UTC) + timedelta(days=3)), USUARIO)
    pronto = repo_panel.programar(_prog(sala, para=datetime.now(UTC) + timedelta(days=1)), USUARIO)
    assert [(r["id"], r["conformes"]) for r in repo_panel.programadas()] == [(pronto, 2), (tarde, 2)]


def test_vencidas_con_su_retraso_segun_la_base(repo_panel, repo):
    sala = _sala(repo)
    futura = repo_panel.programar(_prog(sala), USUARIO)
    vencida = repo_panel.programar(_prog(sala, para=datetime.now(UTC) + timedelta(minutes=1)), USUARIO)
    with repo.conexion() as c:
        c.execute("UPDATE reuniones SET programada_para = now() - interval '90 seconds' WHERE id = %s", (vencida,))
    filas = repo.vencidas()
    assert [r["id"] for r in filas] == [vencida] and futura not in [r["id"] for r in filas]
    assert 89 <= filas[0]["retraso_s"] < 100


def test_la_siguiente_de_una_serie_nace_sin_conformidades_y_una_sola_vez(repo_app, repo):
    sala = _sala(repo)
    rid = repo.programar(_prog(sala, repetir="semanal", tope_min=60), USUARIO)
    assert repo.series_pendientes() == []  # mientras está programada no hace falta la siguiente
    repo.mover(rid, Estado.PROGRAMADA, Estado.GRABANDO, inicio=True)
    pendientes = repo_app.series_pendientes()
    assert [r["id"] for r in pendientes] == [rid]
    para = datetime.now(UTC) + timedelta(days=7)
    sig = repo_app.crear_siguiente(pendientes[0], para)
    assert repo_app.crear_siguiente(pendientes[0], para) is None  # dos veces: una sola
    s = repo.reunion(sig)
    assert (s["estado"], s["sala_id"], s["tope_min"], list(s["socios"]), s["repetir"]) == (
        "programada",
        sala,
        60,
        ["pablo", "roberto"],
        "semanal",
    )
    assert (s["programada_para"], s["anterior_id"], s["pedido_por"], s["titulo"]) == (
        para,
        rid,
        USUARIO,
        "Socios · seguimiento",
    )
    assert repo.conformidades(sig) == []
    assert s["repetir_hora"] == repo.reunion(rid)["repetir_hora"] is not None
    assert repo_app.series_pendientes() == []


def test_si_se_borra_la_siguiente_no_se_vuelve_a_crear(repo_app, repo):
    rid = repo.programar(_prog(_sala(repo), repetir="semanal"), USUARIO)
    repo.mover(rid, Estado.PROGRAMADA, Estado.ERROR, motivo="conformidad")
    sig = repo_app.crear_siguiente(repo_app.series_pendientes()[0], datetime.now(UTC) + timedelta(days=7))
    with repo.conexion() as c:
        c.execute("DELETE FROM reuniones WHERE id = %s", (sig,))
    assert repo_app.series_pendientes() == []


def test_una_serie_cancelada_no_tiene_siguiente(repo_panel, repo):
    rid = repo_panel.programar(_prog(_sala(repo), repetir="mensual"), USUARIO)
    repo_panel.cancelar(rid, USUARIO, serie=True)
    assert repo.series_pendientes() == []


# ── Revisión de seguridad de V3 ────────────────────────────────────────────────────────────────────────────────────────


def test_el_supervisor_no_traslada_conformidades_con_update(repo_app, repo):
    """Ni a la siguiente de una serie, que nace sin ellas: B1 también por UPDATE."""
    vieja = _transcrita(repo)
    nueva = repo.programar(_prog(_sala(repo), socios=("pablo",)), USUARIO)
    with repo.conexion() as c:
        c.execute("DELETE FROM conformidades WHERE reunion_id = %s", (nueva,))
    with pytest.raises(Denegado), repo_app.conexion() as c:
        c.execute("UPDATE conformidades SET reunion_id = %s WHERE reunion_id = %s", (nueva, vieja))


def test_nadie_cambia_una_conformidad_ni_siendo_el_dueno(repo):
    rid = _transcrita(repo)
    with pytest.raises(psycopg.errors.CheckViolation), repo.conexion() as c:
        c.execute("UPDATE conformidades SET texto_version = 'v2' WHERE reunion_id = %s", (rid,))


@pytest.mark.parametrize("estado", ["programada", "pedida"])
def test_una_reunion_no_vuelve_a_pedida_ni_a_programada(repo_app, repo, estado):
    rid = repo.programar(_prog(_sala(repo)), USUARIO)
    repo.mover(rid, Estado.PROGRAMADA, Estado.GRABANDO, inicio=True)
    repo.mover(rid, Estado.GRABANDO, Estado.GRABADA, motivo="pedida", fin=True)
    with pytest.raises(Denegado), repo_app.conexion() as c:
        c.execute("UPDATE reuniones SET estado = %s WHERE id = %s", (estado, rid))


def test_nadie_cambia_cuando_se_creo_una_reunion(repo_app, repo):
    rid = repo.pedir(Peticion(("pablo",), "v1"))
    with pytest.raises(Denegado), repo_app.conexion() as c:
        c.execute("UPDATE reuniones SET creado_en = now() - interval '1 day' WHERE id = %s", (rid,))


def test_no_se_pide_reintento_de_una_reunion_en_la_papelera(repo_panel, repo):
    rid = repo.pedir(Peticion(("pablo",), "v1"))
    repo.mover(rid, Estado.PEDIDA, Estado.ERROR, motivo="conformidad")
    repo_panel.a_papelera(rid, USUARIO)
    assert repo_panel.pedir_reintento(rid, USUARIO) is False


def test_mover_no_toca_una_programada_que_cambio_desde_que_se_leyo(repo):
    sala, otra = _sala(repo), _sala(repo, "otra")
    rid = repo.programar(_prog(sala), USUARIO)
    leida = repo.reunion(rid)
    repo.modificar_programada(rid, _prog(otra), USUARIO)
    with pytest.raises(TransicionNoValida):
        repo.mover(rid, Estado.PROGRAMADA, Estado.GRABANDO, inicio=True, igual={k: leida[k] for k in PROGRAMADO})
    assert repo.reunion(rid)["estado"] == "programada"
    actual = repo.reunion(rid)
    repo.mover(rid, Estado.PROGRAMADA, Estado.GRABANDO, inicio=True, igual={k: actual[k] for k in PROGRAMADO})
    assert repo.reunion(rid)["estado"] == "grabando"


def test_mover_solo_compara_lo_programado(repo):
    rid = repo.pedir(Peticion(("pablo",), "v1"))
    with pytest.raises(ValueError):
        repo.mover(rid, Estado.PEDIDA, Estado.GRABANDO, igual={"estado": "pedida"})
