"""El registro del proceso redacta la contraseña de la sala, el token, las dos contraseñas de la base y la clave de las salas
(@a11, @a24, V2)."""

from actas.__main__ import registro_del_entorno


def test_registro_redacta_todos_los_secretos(capsys):
    entorno = {"CLAVE": "clave-sala", "PGPASSWORD": "pg-app", "ACTAS_MIGRACIONES_PASSWORD": "pg-owner"}
    registro_del_entorno(entorno, "tok3n", "bWFlc3RyYQ==\n")("x", "clave-sala", "tok3n", "pg-app", "pg-owner", "bWFlc3RyYQ==")
    err = capsys.readouterr().err
    assert err.strip().endswith("x *** *** *** *** ***")
