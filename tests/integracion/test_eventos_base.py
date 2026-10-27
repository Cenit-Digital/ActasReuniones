"""@a55 en la base (lista blanca de `eventos.detalle` con un CHECK), el latido del supervisor, la petición de reintento del panel
(@a57) y el mínimo privilegio del panel sobre lo nuevo de la migración 0005 (V4 de KubernetesInfrastructure#298)."""

import psycopg
import pytest
from psycopg.types.json import Jsonb

from actas import base
from actas.conformidad import Peticion
from actas.estados import Estado
from actas.eventos import EventoNoValido

Denegado = (psycopg.errors.InsufficientPrivilege, psycopg.errors.RaiseException, psycopg.errors.CheckViolation)


def _en_error(repo, motivo="plazo_envio"):
    rid = repo.pedir(Peticion(("pablo",), "v1"))
    repo.mover(rid, Estado.PEDIDA, Estado.GRABANDO, inicio=True)
    repo.mover(rid, Estado.GRABANDO, Estado.GRABADA, motivo="pedida", fin=True)
    repo.mover(rid, Estado.GRABADA, Estado.ERROR, motivo=motivo)
    return rid


# ── @a55: la base solo admite la lista blanca ──────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "detalle",
    [
        {"texto": "lo que dijo un socio"},  # clave fuera de la lista blanca
        {"motivo": ["lista"]},  # no escalar
        {"motivo": {"anidado": 1}},
        {"motivo": "con espacios y frases"},  # una cadena que no es un código
        {"motivo": "x" * 65},
        ["no", "es", "un", "objeto"],
        "cadena",
    ],
)
def test_la_base_rechaza_un_detalle_fuera_de_la_lista_blanca(repo, detalle):
    with pytest.raises(psycopg.errors.CheckViolation), repo.conexion() as c:
        c.execute("INSERT INTO eventos (tipo, detalle) VALUES ('estado', %s)", (Jsonb(detalle),))


def test_la_base_rechaza_un_tipo_fuera_de_la_lista_blanca(repo):
    with pytest.raises(psycopg.errors.CheckViolation), repo.conexion() as c:
        c.execute("INSERT INTO eventos (tipo, detalle) VALUES ('depuracion', '{}')")


def test_la_base_admite_un_evento_de_la_lista_blanca(repo):
    rid = repo.pedir(Peticion(("pablo",), "v1"))
    repo.anotar_evento(rid, "envio", {"codigo": 503, "accion": "reintentar", "intento": 1})
    assert [(e["tipo"], e["detalle"]) for e in repo.eventos(rid)] == [
        ("envio", {"codigo": 503, "accion": "reintentar", "intento": 1})
    ]


def test_el_repositorio_rechaza_la_contrasena_de_la_sala_y_no_inserta_nada(dsn, repo):
    url, esquema = dsn
    con_secretos = base.Repositorio(url, esquema, secretos=["Cl4ve-Sala"])
    rid = repo.pedir(Peticion(("pablo",), "v1"))
    with pytest.raises(EventoNoValido):
        con_secretos.anotar_evento(rid, "estado", {"motivo": "Cl4ve-Sala"})
    assert repo.eventos(rid) == []


def test_un_cambio_de_estado_con_detalle_no_valido_no_se_aplica(dsn, repo):
    """El evento va en la misma transacción que el cambio de estado: o los dos, o ninguno."""
    url, esquema = dsn
    con_secretos = base.Repositorio(url, esquema, secretos=["Cl4ve-Sala"])
    rid = repo.pedir(Peticion(("pablo",), "v1"))
    with pytest.raises(EventoNoValido):
        con_secretos.mover(rid, Estado.PEDIDA, Estado.ERROR, motivo="conformidad", detalle={"causa": "Cl4ve-Sala"})
    assert repo.reunion(rid)["estado"] == "pedida" and repo.eventos(rid) == []


def test_cada_cambio_de_estado_deja_su_evento_en_la_misma_transaccion(repo):
    rid = _en_error(repo)
    assert [(e["tipo"], e["detalle"]) for e in repo.eventos(rid)] == [
        ("estado", {"desde": "pedida", "hasta": "grabando"}),
        ("estado", {"desde": "grabando", "hasta": "grabada", "motivo": "pedida"}),
        ("estado", {"desde": "grabada", "hasta": "error", "motivo": "plazo_envio"}),
    ]


def test_los_eventos_se_borran_con_su_reunion(repo):
    rid = _en_error(repo)
    with repo.conexion() as c:
        c.execute("DELETE FROM reuniones WHERE id = %s", (rid,))
        assert c.execute("SELECT count(*) FROM eventos").fetchone() == (0,)


# ── Latido ─────────────────────────────────────────────────────────────────────────────────────────────────────────────


def test_el_latido_es_una_sola_fila_con_su_edad_segun_la_base(repo):
    assert repo.latido() is None
    repo.latir({"chromium": "HeadlessChrome/141.0.7390.37", "imagen": "sha-abc", "grabaciones_bytes": 10})
    repo.latir({"chromium": None, "imagen": "sha-abc", "grabaciones_bytes": 20})
    detalle, hace_s = repo.latido()
    assert detalle["grabaciones_bytes"] == 20 and detalle["chromium"] is None
    assert 0 <= hace_s < 5
    with repo.conexion() as c:
        assert c.execute("SELECT count(*) FROM latido").fetchone() == (1,)


@pytest.mark.parametrize(
    "detalle",
    [{"otra": 1}, {"con_audio": ["no-es-un-uuid"]}, {"imagen": "salto\nde línea"}, {"con_audio": "x"}],
)
def test_la_base_rechaza_un_latido_fuera_de_su_lista_blanca(repo, detalle):
    with pytest.raises(psycopg.errors.CheckViolation):
        repo.latir(detalle)


def test_el_latido_lista_las_reuniones_con_audio(repo):
    rid = repo.pedir(Peticion(("pablo",), "v1"))
    repo.latir({"con_audio": [rid]})
    assert repo.latido()[0]["con_audio"] == [rid]


# ── @a57: el panel pide el reintento; el supervisor lo atiende ─────────────────────────────────────────────────────────


def test_el_panel_pide_el_reintento_de_una_reunion_en_error(repo_panel, repo):
    rid = _en_error(repo)
    assert repo_panel.pedir_reintento(rid, "pablo")
    r = repo.reunion(rid)
    assert r["reintento_pedido_en"] is not None and r["reintento_pedido_por"] == "pablo"
    assert [x["id"] for x in repo.reintentos_pedidos()] == [rid]
    assert not repo_panel.pedir_reintento(rid, "pablo")  # ya pedido: no se pisa


def test_el_panel_no_pide_reintento_de_una_reunion_que_no_esta_en_error(repo_panel, repo):
    rid = repo.pedir(Peticion(("pablo",), "v1"))
    assert not repo_panel.pedir_reintento(rid, "pablo")
    with pytest.raises(Denegado), repo_panel.conexion() as c:  # ni por UPDATE directo: no tiene ese privilegio
        c.execute("UPDATE reuniones SET reintento_pedido_en = now() WHERE id = %s", (rid,))
    with pytest.raises(Denegado), repo.conexion() as c:  # ni el supervisor: el trigger solo lo deja en una reunión en error
        c.execute("UPDATE reuniones SET reintento_pedido_en = now() WHERE id = %s", (rid,))


def test_atender_un_reintento_lo_vuelve_a_enviar_y_limpia_la_peticion(repo_panel, repo):
    rid = _en_error(repo)
    repo_panel.pedir_reintento(rid, "pablo")
    repo.atender_reintento(rid, reenviar=True, resultado="reenviada")
    r = repo.reunion(rid)
    assert (r["estado"], r["motivo"], r["reintento_pedido_en"]) == ("grabada", "reintento", None)
    assert repo.reintentos_pedidos() == []
    tipos = [(e["tipo"], e["detalle"]) for e in repo.eventos(rid)][-2:]
    assert tipos == [
        ("estado", {"desde": "error", "hasta": "grabada", "motivo": "reintento"}),
        ("reintento", {"usuario": "pablo", "resultado": "reenviada"}),
    ]


def test_un_reintento_sin_audio_se_descarta_y_la_reunion_sigue_en_error(repo_panel, repo):
    rid = _en_error(repo)
    repo_panel.pedir_reintento(rid, "pablo")
    repo.atender_reintento(rid, reenviar=False, resultado="ninguna_pista")
    r = repo.reunion(rid)
    assert (r["estado"], r["motivo"], r["reintento_pedido_en"]) == ("error", "plazo_envio", None)
    assert repo.eventos(rid)[-1]["detalle"] == {"usuario": "pablo", "resultado": "ninguna_pista"}


# ── Lo que lee el panel ────────────────────────────────────────────────────────────────────────────────────────────────


def test_el_panel_lee_el_diagnostico(repo_panel, repo):
    rid = _en_error(repo)
    repo.anotar_evento(rid, "envio", {"codigo": 503, "accion": "reintentar", "intento": 0})
    repo.anotar_evento(None, "consulta", {"codigo": 0, "accion": "seguir"})
    repo.anotar_evento(None, "envio", {"codigo": 201, "accion": "seguir"})
    repo.latir({"imagen": "sha-abc", "con_audio": [rid]})
    d = repo_panel.diagnostico(rid)
    assert [e["tipo"] for e in d["eventos"]] == ["estado", "estado", "estado", "envio"]
    assert d["latido"]["imagen"] == "sha-abc" and 0 <= d["latido_hace_s"] < 5
    assert d["fallos_transcribir_1h"] == 2  # el 503 y la consulta sin respuesta; el 201 no cuenta


@pytest.mark.parametrize(
    "orden",
    [
        "INSERT INTO eventos (tipo, detalle) VALUES ('estado', '{}')",
        "UPDATE eventos SET tipo = 'estado'",
        "DELETE FROM eventos",
        "INSERT INTO latido (detalle) VALUES ('{}')",
        "UPDATE latido SET detalle = '{}'",
        "DELETE FROM latido",
        "UPDATE reuniones SET estado = 'grabada'",
        "UPDATE reuniones SET motivo = 'otro'",
        "UPDATE reuniones SET reintento_pedido_por = 'otro'",
    ],
)
def test_minimo_privilegio_del_panel_en_eventos_latido_y_reintento(repo_panel, repo, orden):
    _en_error(repo)
    repo.latir({})
    with pytest.raises(Denegado), repo_panel.conexion() as c:
        c.execute(orden)


def test_reintentar_por_actas_sh_tambien_consume_la_peticion_del_panel(repo_panel, repo):
    rid = _en_error(repo)
    repo_panel.pedir_reintento(rid, "pablo")
    assert repo.reintentar(rid)
    assert repo.reunion(rid)["reintento_pedido_en"] is None and repo.reintentos_pedidos() == []


def test_el_panel_no_borra_una_peticion_de_reintento(repo_panel, repo):
    rid = _en_error(repo)
    repo_panel.pedir_reintento(rid, "pablo")
    with pytest.raises(Denegado), repo_panel.conexion() as c:
        c.execute("UPDATE reuniones SET reintento_pedido_en = NULL WHERE id = %s", (rid,))


def test_pedir_reintento_de_una_reunion_que_no_existe(repo_panel, repo):
    assert repo_panel.pedir_reintento("00000000-0000-4000-8000-0000000000ff", "pablo") is None


def test_un_codigo_que_no_es_un_numero_no_rompe_el_diagnostico(repo_panel, repo):
    rid = _en_error(repo)
    repo.anotar_evento(rid, "envio", {"codigo": "raro", "accion": "seguir"})
    repo.anotar_evento(rid, "envio", {"codigo": 999999999999, "accion": "seguir"})
    assert repo_panel.diagnostico(rid)["fallos_transcribir_1h"] == 2


def test_la_funcion_de_reintento_no_la_ejecuta_cualquiera(repo, dsn):
    _, esquema = dsn
    with repo.conexion() as c:
        fila = c.execute(
            "SELECT has_function_privilege('actas_panel', %s, 'EXECUTE'), "
            "has_function_privilege('public', %s, 'EXECUTE'), "
            "(SELECT prosecdef FROM pg_proc WHERE oid = %s::regprocedure)",
            (f"{esquema}.pedir_reintento(uuid, text)",) * 3,
        ).fetchone()
    assert fila == (True, False, True)
