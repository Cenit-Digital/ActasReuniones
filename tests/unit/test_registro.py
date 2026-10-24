"""@a11: ningún secreto llega al registro del supervisor."""

from actas.registro import redactar


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
