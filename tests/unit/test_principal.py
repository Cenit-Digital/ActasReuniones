"""El registro del proceso redacta la contraseña de la sala, el token, las dos contraseñas de la base y la clave de las salas
(@a11, @a24, V2)."""

from actas.__main__ import registro_del_entorno
from actas.registro import Registro


def test_registro_redacta_todos_los_secretos(capsys):
    entorno = {"CLAVE": "clave-sala", "PGPASSWORD": "pg-app", "ACTAS_MIGRACIONES_PASSWORD": "pg-owner"}
    registro_del_entorno(entorno, "tok3n", "bWFlc3RyYQ==\n")("x", "clave-sala", "tok3n", "pg-app", "pg-owner", "bWFlc3RyYQ==")
    err = capsys.readouterr().err
    assert err.strip().endswith("x *** *** *** *** ***")


def test_una_grabacion_sin_sala_se_retoma_con_la_sala_de_rescate(tmp_path):
    from actas.__main__ import nueva_grabacion
    from actas.grabador import SALA_RESCATE, Sala

    g = nueva_grabacion("http://127.0.0.1:1", None, ("socioa",), tmp_path, Registro())
    assert g._args[1] is SALA_RESCATE
    sala = Sala("salav2", "clave")
    assert nueva_grabacion("http://127.0.0.1:1", sala, ("socioa",), tmp_path, Registro())._args[1] is sala
