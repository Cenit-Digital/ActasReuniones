"""@a11: ningún secreto llega al registro del supervisor."""

from actas.registro import Registro, redactar


def test_redacta_cada_secreto_tal_cual_y_codificado_en_url():
    secretos = ["clave sala+é", "tok3n"]
    texto = "https://x/?room=r&password=clave%20sala%2B%C3%A9 Bearer tok3n y clave sala+é"
    assert redactar(texto, secretos) == "https://x/?room=r&password=*** Bearer *** y ***"


def test_un_secreto_vacio_no_redacta_todo():
    assert redactar("hola", ["", "  "]) == "hola"


def test_los_secretos_mas_largos_primero():
    assert redactar("abcdef", ["abc", "abcdef"]) == "***"


def test_sin_secretos_no_cambia():
    assert redactar("texto", []) == "texto"


def test_el_registro_quita_los_caracteres_de_control(capsys):
    Registro(["tok"])("descarga", "completed\n2026-01-01T00:00:00Z falso\x1b[31m", "Bearer tok")
    err = capsys.readouterr().err
    assert err.count("\n") == 1 and "\x1b" not in err and "tok" not in err
