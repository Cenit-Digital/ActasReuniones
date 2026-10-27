"""Migración 0003 contra PostgreSQL 18.6 (V2 de KubernetesInfrastructure#298): salas con la contraseña cifrada (@a43), su
auditoría (@a45), la sala de cada reunión (@a46) y los socios (@a47); y el mínimo privilegio del panel y del supervisor.

La puerta `actas-gate.sh f2` (@a33) exige que `actas_panel` no tenga UPDATE salvo en `reuniones.parar_pedido_en` y
`actualizado_en`, ni DELETE en nada: el panel solo inserta por columnas o ejecuta funciones SECURITY DEFINER."""

import psycopg
import pytest

from actas import base, salas
from actas.conformidad import Peticion
from actas.formulario import Socio

Denegado = psycopg.errors.InsufficientPrivilege
MAESTRA = bytes(range(32))
OTRA = bytes(range(1, 33))


def _sala(repo, nombre="Socios semanal", usuario="pablo"):
    room, clave = salas.nuevo_room(), salas.nueva_clave()
    sid = repo.crear_sala(nombre, room, "abcd", salas.cifrar(MAESTRA, room, clave), usuario)
    return sid, room, clave


def test_migrar_aplica_la_0003(dsn):
    url, esquema = dsn
    assert base.migrar(url, esquema)[:3] == ["0001_esquema.sql", "0002_panel.sql", "0003_salas.sql"]


def test_la_0003_se_aplica_igual_despues_de_otra_migracion_posterior(dsn, monkeypatch):
    # Si V4 (0005) se despliega antes, la 0003 se aplica después de ella: no puede quitarle nada.
    url, esquema = dsn
    todas = base._migraciones()
    posterior = (
        "0005_otra.sql",
        "CREATE TABLE otra (x int); GRANT SELECT ON otra TO actas_panel; GRANT UPDATE (motivo) ON reuniones TO actas_panel;",
    )
    monkeypatch.setattr(base, "_migraciones", lambda: [m for m in todas if m[0] < "0003"] + [posterior])
    base.migrar(url, esquema)
    monkeypatch.setattr(base, "_migraciones", lambda: [m for m in todas if m[0] < "0004"] + [posterior])
    assert base.migrar(url, esquema) == ["0003_salas.sql"]
    with psycopg.connect(url) as c:
        assert c.execute(
            "SELECT has_table_privilege('actas_panel', %s, 'SELECT'), "
            "has_column_privilege('actas_panel', %s, 'motivo', 'UPDATE')",
            (f"{esquema}.otra", f"{esquema}.reuniones"),
        ).fetchone() == (True, True)


# ── @a43 ─────────────────────────────────────────────────────────────────────────────────────────────────────────────


def test_crear_sala_desde_el_panel_guarda_la_contrasena_cifrada(repo_panel, repo, dsn):
    sid, room, clave = _sala(repo_panel)
    s = repo_panel.sala(sid)
    assert (s["nombre"], s["room"], s["hash"], s["creada_por"]) == ("Socios semanal", room, "abcd", "pablo")
    # El valor en claro no aparece en ninguna columna de ninguna tabla del esquema.
    _, esquema = dsn
    with repo.conexion() as c:
        volcado = c.execute(
            "SELECT string_agg(t::text, ' ') "
            "FROM (SELECT s::text AS t FROM salas s UNION ALL SELECT e::text FROM salas_eventos e) x"
        ).fetchone()[0]
    assert clave not in volcado
    assert clave.encode().hex() not in volcado


def test_descifrar_con_otra_clave_falla(repo_panel, repo):
    sid, room, _ = _sala(repo_panel)
    cifrada = repo.cifrada_de_sala(sid)[1]
    with pytest.raises(salas.ClaveNoValida):
        salas.descifrar(OTRA, room, cifrada)


def test_crear_sala_anota_quien_la_creo(repo_panel):
    sid, _, _ = _sala(repo_panel, usuario="pablo")
    assert [(e["tipo"], e["usuario"]) for e in repo_panel.eventos_de_sala(sid)] == [("sala_creada", "pablo")]


@pytest.mark.parametrize(
    ("nombre", "room", "hash_", "cifrada"),
    [
        ("", "sala1", "abcd", bytes(40)),
        ("x" * 65, "sala1", "abcd", bytes(40)),
        ("Sala", "con-guion", "abcd", bytes(40)),
        ("Sala", "x" * 31, "abcd", bytes(40)),
        ("Sala", "sala1", "ABCD", bytes(40)),
        ("Sala", "sala1", "abc", bytes(40)),
        ("Sala", "sala1", "abcd", bytes(28)),
    ],
)
def test_la_base_rechaza_una_sala_mal_formada(repo_panel, nombre, room, hash_, cifrada):
    with pytest.raises(psycopg.errors.CheckViolation):
        repo_panel.crear_sala(nombre, room, hash_, cifrada, "pablo")


def test_room_y_nombre_unicos(repo_panel):
    _, room, _ = _sala(repo_panel, nombre="A")
    with pytest.raises(psycopg.errors.UniqueViolation):
        repo_panel.crear_sala("B", room, "abcd", bytes(40), "pablo")
    with pytest.raises(psycopg.errors.UniqueViolation):
        repo_panel.crear_sala("A", "otraroom", "abcd", bytes(40), "pablo")


# ── @a45 ─────────────────────────────────────────────────────────────────────────────────────────────────────────────


def test_ver_la_contrasena_anota_clave_vista_sin_el_valor(repo_panel):
    sid, room, clave = _sala(repo_panel)
    cifrada = repo_panel.ver_clave(sid, "pablo")
    assert salas.descifrar(MAESTRA, room, cifrada) == clave
    eventos = repo_panel.eventos_de_sala(sid)
    assert [(e["tipo"], e["usuario"]) for e in eventos] == [("sala_creada", "pablo"), ("clave_vista", "pablo")]
    assert all(clave not in str(e) for e in eventos)


def test_ver_la_contrasena_de_una_sala_que_no_existe(repo_panel):
    assert repo_panel.ver_clave("00000000-0000-4000-8000-000000000000", "pablo") is None


def test_el_panel_no_lee_la_contrasena_cifrada_sin_anotarlo(repo_panel):
    _sala(repo_panel)
    with pytest.raises(Denegado), repo_panel.conexion() as c:
        c.execute("SELECT cifrada FROM salas")


def test_ver_la_contrasena_exige_un_usuario_valido(repo_panel):
    sid, _, _ = _sala(repo_panel)
    with pytest.raises(psycopg.errors.CheckViolation):
        repo_panel.ver_clave(sid, "pa blo")


# ── @a46 ─────────────────────────────────────────────────────────────────────────────────────────────────────────────


def test_la_reunion_guarda_su_sala_y_el_supervisor_la_lee(repo_panel, repo_app):
    sid, room, clave = _sala(repo_panel)
    rid = repo_panel.pedir(Peticion(("pablo",), "v1"), "pablo", sala_id=sid)
    assert repo_app.reunion(rid)["sala_id"] == sid
    leida_room, cifrada = repo_app.cifrada_de_sala(sid)
    assert leida_room == room and salas.descifrar(MAESTRA, room, cifrada) == clave


def test_una_reunion_con_una_sala_que_no_existe_se_rechaza(repo_panel):
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        repo_panel.pedir(Peticion(("pablo",), "v1"), "pablo", sala_id="00000000-0000-4000-8000-000000000000")


def test_cifrada_de_una_sala_que_no_existe(repo_app):
    assert repo_app.cifrada_de_sala("00000000-0000-4000-8000-000000000000") is None


# ── @a47 ─────────────────────────────────────────────────────────────────────────────────────────────────────────────


def test_alta_de_socios_desde_el_panel(repo_panel):
    repo_panel.alta_socio(Socio("pablo", "Pablo", None))
    repo_panel.alta_socio(Socio("andres", "Andrés", "andres@cenitdigital.es"))
    assert [(s["push"], s["nombre"], s["correo"], s["activo"]) for s in repo_panel.socios()] == [
        ("andres", "Andrés", "andres@cenitdigital.es", True),
        ("pablo", "Pablo", None, True),
    ]


@pytest.mark.parametrize("push", ["socio-pablo", "Pablo", "", "x" * 33])
def test_la_base_tambien_rechaza_un_push_con_guiones_o_mal_formado(repo_panel, push):
    with pytest.raises(psycopg.errors.CheckViolation):
        repo_panel.alta_socio(Socio(push, "Pablo", None))


def test_un_socio_no_se_da_de_alta_dos_veces(repo_panel):
    repo_panel.alta_socio(Socio("pablo", "Pablo", None))
    with pytest.raises(psycopg.errors.UniqueViolation):
        repo_panel.alta_socio(Socio("pablo", "Otro", None))


def test_dar_de_baja_y_de_alta_un_socio(repo_panel):
    repo_panel.alta_socio(Socio("pablo", "Pablo", None))
    assert repo_panel.socio_activo("pablo", False) is True
    assert [s["activo"] for s in repo_panel.socios()] == [False]
    assert repo_panel.socio_activo("pablo", True) is True
    assert repo_panel.socio_activo("nadie", False) is False


# ── Mínimo privilegio ────────────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "orden",
    [
        "UPDATE salas SET nombre = 'otra'",
        "UPDATE salas SET cifrada = '\\x00'",
        "DELETE FROM salas",
        "UPDATE socios SET activo = false",
        "UPDATE socios SET nombre = 'otro'",
        "DELETE FROM socios",
        "UPDATE salas_eventos SET usuario = 'otro'",
        "DELETE FROM salas_eventos",
        "TRUNCATE salas_eventos",
        "UPDATE reuniones SET sala_id = NULL",
        "INSERT INTO salas (id, nombre, room, hash, cifrada, creada_por, creada_en) "
        "VALUES (gen_random_uuid(), 'x', 'y', 'abcd', '\\x00', 'pablo', now())",
        "INSERT INTO salas_eventos (sala_id, tipo, usuario) SELECT id, 'clave_vista', 'pablo' FROM salas",
        "INSERT INTO socios (push, nombre, activo) VALUES ('otro', 'Otro', false)",
    ],
)
def test_minimo_privilegio_del_panel_en_salas_y_socios(repo_panel, orden):
    _sala(repo_panel)
    with pytest.raises(Denegado), repo_panel.conexion() as c:
        c.execute(orden)


def test_la_puerta_a33_sigue_en_verde(repo, dsn):
    # La misma consulta de scripts/actas-gate.sh f2 (KubernetesInfrastructure), sobre el esquema de la prueba.
    _, esquema = dsn
    with repo.conexion() as c:
        fila = c.execute(
            """SELECT NOT EXISTS (SELECT FROM pg_class c WHERE c.relnamespace = %(e)s::regnamespace AND c.relkind IN ('r', 'p')
                                  AND has_table_privilege('actas_panel', c.oid, 'DELETE,TRUNCATE')),
                      NOT EXISTS (SELECT FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid
                                  WHERE c.relnamespace = %(e)s::regnamespace AND c.relkind IN ('r', 'p') AND a.attnum > 0
                                  AND NOT a.attisdropped
                                  AND NOT (c.relname = 'reuniones' AND a.attname IN ('parar_pedido_en', 'actualizado_en'))
                                  AND has_column_privilege('actas_panel', c.oid, a.attnum, 'UPDATE'))""",
            {"e": esquema},
        ).fetchone()
    assert fila == (True, True)


def test_las_funciones_nuevas_no_son_de_public(repo, dsn):
    _, esquema = dsn
    with repo.conexion() as c:
        filas = c.execute(
            """SELECT p.proname, has_function_privilege('actas_panel', p.oid, 'EXECUTE'),
                      has_function_privilege('actas_app', p.oid, 'EXECUTE'), p.prosecdef,
                      EXISTS (SELECT FROM aclexplode(p.proacl) a WHERE a.grantee = 0)
               FROM pg_proc p WHERE p.pronamespace = %s::regnamespace
               AND p.proname IN ('ver_clave_sala', 'socio_activo', 'anotar_sala_creada')
               ORDER BY 1""",
            (esquema,),
        ).fetchall()
    assert filas == [
        ("anotar_sala_creada", False, False, True, False),
        ("socio_activo", True, False, True, False),
        ("ver_clave_sala", True, False, True, False),
    ]


def test_el_supervisor_lee_las_salas_pero_no_las_cambia_ni_toca_la_auditoria(repo_app, repo_panel, dsn):
    _, esquema = dsn
    _sala(repo_panel)
    with repo_app.conexion() as c:
        fila = c.execute(
            """SELECT has_table_privilege('actas_app', %(s)s, 'SELECT'),
                      has_table_privilege('actas_app', %(s)s, 'INSERT,UPDATE,DELETE,TRUNCATE'),
                      has_table_privilege('actas_app', %(e)s, 'SELECT,INSERT,UPDATE,DELETE,TRUNCATE'),
                      has_table_privilege('actas_app', %(o)s, 'INSERT,UPDATE,DELETE,TRUNCATE')""",
            {"s": f"{esquema}.salas", "e": f"{esquema}.salas_eventos", "o": f"{esquema}.socios"},
        ).fetchone()
    assert fila == (True, False, False, False)


def test_las_funciones_security_definer_con_search_path_fijo_y_pg_temp_al_final(repo, dsn):
    # Doc de CREATE FUNCTION (PostgreSQL 18), «Writing SECURITY DEFINER Functions Safely»: pg_temp, explícito y el último.
    _, esquema = dsn
    with repo.conexion() as c:
        filas = c.execute(
            "SELECT p.proname, p.proconfig FROM pg_proc p WHERE p.pronamespace = %s::regnamespace AND p.prosecdef ORDER BY 1",
            (esquema,),
        ).fetchall()
    assert [f[0] for f in filas] == [
        "a_papelera",  # V3: la 0006
        "anotar_sala_creada",
        "borrar_reunion",
        "cancelar_reunion",
        "modificar_programada",
        "pedir_reintento",  # V4: la 0005
        "programar",
        "purgar_actas",
        "recuperar",
        "socio_activo",
        "ver_clave_sala",
    ]
    for _, config in filas:
        assert config == [f"search_path={esquema}, pg_temp"]
