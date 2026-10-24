"""El registro del proceso redacta la contraseña de la sala, el token y las dos contraseñas de la base (@a11, @a24)."""

from actas.__main__ import registro_del_entorno


def test_registro_redacta_todos_los_secretos(capsys):
    entorno = {"CLAVE": "clave-sala", "PGPASSWORD": "pg-app", "ACTAS_MIGRACIONES_PASSWORD": "pg-owner"}
    registro_del_entorno(entorno, "tok3n")("x", "clave-sala", "tok3n", "pg-app", "pg-owner")
    err = capsys.readouterr().err
    assert err.strip().endswith("x *** *** *** ***")
