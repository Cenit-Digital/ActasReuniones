"""Persistencia desconectada de F3: no hace llamadas a la API."""

import json
import time
from concurrent.futures import ThreadPoolExecutor

import psycopg
import pytest

from actas.base import Repositorio
from actas.conformidad import Peticion
from actas.estados import Estado
from actas.resumen_offline import ErrorResumen


def respuesta(resumen="Acuerdo S1"):
    acta = {"resumen": resumen, "temas": [], "decisiones": [], "tareas": [], "pendientes": []}
    return {"stop_reason": "end_turn", "content": [{"type": "text", "text": json.dumps(acta)}]}


def transcrita(repo):
    rid = repo.pedir(Peticion(("pablo",), "v1"), "pablo")
    repo.mover(rid, Estado.PEDIDA, Estado.GRABANDO, inicio=True)
    repo.mover(rid, Estado.GRABANDO, Estado.GRABADA, motivo="pedida", fin=True)
    repo.mover(rid, Estado.GRABADA, Estado.TRANSCRIBIENDO, trabajo_id="00000000-0000-4000-8000-00000000aaaa")
    repo.guardar_transcripcion(rid, [{"hablante": "pablo", "inicio_ms": 0, "fin_ms": 1, "texto": "t"}])
    return rid


def test_insercion_idempotente_y_conflicto(repo, repo_app):
    rid = transcrita(repo)
    with ThreadPoolExecutor(max_workers=2) as pool:
        resultados = list(pool.map(lambda _: repo_app.guardar_acta_offline(rid, respuesta(), {"S1": "Pablo"}), range(2)))
    assert resultados == [True, True]
    with repo.conexion() as c:
        fila = c.execute("SELECT contenido FROM actas_resumen WHERE reunion_id = %s", (rid,)).fetchone()
    assert fila[0]["resumen"] == "Acuerdo Pablo"
    with pytest.raises(ValueError, match="acta ya existente"):
        repo_app.guardar_acta_offline(rid, respuesta("Diferente"), {"S1": "Pablo"})
    assert repo.reunion(rid)["estado"] == "transcrita"


def test_rechazo_no_persiste_y_guardas_estado_papelera(repo, repo_app, repo_panel):
    rid = transcrita(repo)
    with pytest.raises(ErrorResumen):
        repo_app.guardar_acta_offline(rid, {"stop_reason": "refusal"}, {})
    assert repo_panel.a_papelera(rid, "pablo") is True
    with pytest.raises(ValueError, match="reunión no disponible"):
        repo_app.guardar_acta_offline(rid, respuesta(), {"S1": "Pablo"})
    with repo.conexion() as c:
        assert c.execute("SELECT count(*) FROM actas_resumen").fetchone()[0] == 0


def test_permisos_y_borrado_en_cascada(repo, repo_app, repo_panel):
    rid = transcrita(repo)
    repo_app.guardar_acta_offline(rid, respuesta(), {"S1": "Pablo"})
    with repo.conexion() as c:
        permisos = c.execute(
            "SELECT has_table_privilege('actas_panel', 'actas_resumen', 'SELECT'), "
            "has_table_privilege('actas_app', 'actas_resumen', 'UPDATE'), "
            "has_table_privilege('actas_app', 'actas_resumen', 'DELETE')"
        ).fetchone()
        assert permisos == (False, False, False)
    assert repo_panel.a_papelera(rid, "pablo") is True
    with repo.conexion() as c:
        c.execute("UPDATE reuniones SET papelera_en = now() - interval '8 days' WHERE id = %s", (rid,))
    assert repo_app.purgar_actas() == 1
    with repo.conexion() as c:
        assert c.execute("SELECT count(*) FROM actas_resumen").fetchone()[0] == 0


def test_rechaza_reuniones_caducadas_o_no_transcritas(repo, repo_app):
    with pytest.raises(ValueError, match="reunión no disponible"):
        repo_app.guardar_acta_offline("00000000-0000-4000-8000-00000000aaaa", respuesta(), {"S1": "Pablo"})
    pendiente = repo.pedir(Peticion(("pablo",), "v1"), "pablo")
    with pytest.raises(ValueError, match="reunión no disponible"):
        repo_app.guardar_acta_offline(pendiente, respuesta(), {"S1": "Pablo"})
    rid = transcrita(repo)
    with repo.conexion() as c:
        c.execute("UPDATE reuniones SET fin = now() - interval '12 months 1 day' WHERE id = %s", (rid,))
    with pytest.raises(ValueError, match="reunión no disponible"):
        repo_app.guardar_acta_offline(rid, respuesta(), {"S1": "Pablo"})


def test_error_de_base_revierte_insercion(repo, repo_app):
    rid = transcrita(repo)
    with repo.conexion() as c:
        c.execute("CREATE FUNCTION fallo_prueba() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'fallo'; END $$")
        c.execute("CREATE TRIGGER fallo_prueba AFTER INSERT ON actas_resumen FOR EACH ROW EXECUTE FUNCTION fallo_prueba()")
    with pytest.raises(psycopg.errors.RaiseException, match="fallo"):
        repo_app.guardar_acta_offline(rid, respuesta(), {"S1": "Pablo"})
    with repo.conexion() as c:
        assert c.execute("SELECT count(*) FROM actas_resumen").fetchone()[0] == 0


@pytest.mark.parametrize("accion", ["papelera", "purga"])
def test_carrera_con_papelera_o_purga_rechaza_escritura(repo, repo_app, dsn, accion):
    rid = transcrita(repo)
    actor = Repositorio(repo_app._dsn, dsn[1], ajustes={"application_name": "actas_test_carrera", "statement_timeout": "5000"})
    with ThreadPoolExecutor(max_workers=1) as pool, repo.conexion() as c:
        if accion == "purga":
            c.execute("UPDATE reuniones SET fin = now() - interval '13 months' WHERE id = %s", (rid,))
        else:
            c.execute("SELECT id FROM reuniones WHERE id = %s FOR UPDATE", (rid,))
        futuro = pool.submit(actor.guardar_acta_offline, rid, respuesta(), {"S1": "Pablo"})
        limite = time.monotonic() + 4
        espera = False
        while time.monotonic() < limite:
            with repo.conexion() as observador:
                espera = observador.execute(
                    "SELECT EXISTS (SELECT 1 FROM pg_stat_activity "
                    "WHERE application_name = 'actas_test_carrera' AND wait_event_type = 'Lock')"
                ).fetchone()[0]
            if espera:
                break
            time.sleep(0.02)
        assert espera, "la escritura no llegó a esperar el bloqueo de la reunión"
        if accion == "papelera":
            c.execute("SELECT a_papelera(%s, 'pablo')", (rid,))
        else:
            c.execute("SELECT purgar_actas()")
        c.commit()
        with pytest.raises(ValueError, match="reunión no disponible"):
            futuro.result(timeout=5)
    with repo.conexion() as c:
        assert c.execute("SELECT count(*) FROM actas_resumen").fetchone()[0] == 0
