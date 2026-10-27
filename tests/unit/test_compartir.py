"""@a58 (textos): «Copiar mensaje» y `mailto:` de «Compartir», nivel 1 (ADR 0023 de KubernetesInfrastructure, decisión 8). El
mensaje de cada socio lleva la transcripción entera o su enlace a la sala, y nunca la contraseña: el módulo ni la recibe."""

import inspect
import urllib.parse

import pytest

from actas import compartir
from actas.compartir import CompartirNoValido, Destinatario, elegir, mailto, preparar, texto_transcripcion

FECHA = "2026-10-19 16:00"
SEGMENTOS = [
    ("pablo", 192_000, 200_000, "Empezamos por el presupuesto."),
    ("roberto", 3_725_000, 3_730_000, "De acuerdo & sin <prisa>."),
]
NOMBRES = {"pablo": "Pablo", "roberto": "Roberto"}
ENLACE = "https://reuniones.cenitdigital.es/?room=k3v9q2m7x4t8w1za&hash=3931&push=roberto&label=Roberto"
ROBERTO = Destinatario("roberto", "Roberto", "roberto@cenitdigital.es")


def test_la_transcripcion_es_el_texto_entero_con_tiempo_y_nombre():
    texto = texto_transcripcion(SEGMENTOS, NOMBRES)
    assert texto == "[00:03:12] Pablo: Empezamos por el presupuesto.\n[01:02:05] Roberto: De acuerdo & sin <prisa>."


def test_un_hablante_sin_nombre_va_con_su_identificador():
    assert texto_transcripcion([("invitado", 0, 1, "Hola.")], NOMBRES) == "[00:00:00] invitado: Hola."


def test_mensaje_con_la_transcripcion():
    (m,) = preparar(FECHA, {"transcripcion"}, [ROBERTO], texto_transcripcion(SEGMENTOS, NOMBRES), {})
    assert m.texto.startswith("Hola, Roberto:\n\n")
    assert "reunión de socios del 2026-10-19 16:00" in m.texto
    assert "[01:02:05] Roberto: De acuerdo & sin <prisa>." in m.texto
    assert "corrija o se borre" in m.texto
    assert "reuniones.cenitdigital.es" not in m.texto
    assert m.asunto == "Transcripción de la reunión del 2026-10-19 16:00"


def test_mensaje_con_el_enlace_de_la_sala_dice_que_la_contrasena_va_por_otro_canal():
    (m,) = preparar(FECHA, {"enlace_sala"}, [ROBERTO], None, {"roberto": ENLACE})
    assert ENLACE in m.texto
    assert "contraseña de la sala te llega por otro canal" in m.texto
    assert "[00:" not in m.texto
    assert m.asunto == "Tu enlace a la sala de las reuniones"


def test_cada_socio_recibe_su_propio_enlace():
    pablo = Destinatario("pablo", "Pablo", None)
    otro = ENLACE.replace("roberto", "pablo").replace("Roberto", "Pablo")
    mp, mr = preparar(FECHA, {"enlace_sala"}, [pablo, ROBERTO], None, {"pablo": otro, "roberto": ENLACE})
    assert otro in mp.texto and ENLACE not in mp.texto
    assert ENLACE in mr.texto and otro not in mr.texto


def test_la_contrasena_no_es_algo_que_se_pueda_compartir():
    """@a58: el enlace y la contraseña nunca en el mismo mensaje. Aquí, por construcción: ni es una opción ni es un argumento."""
    assert set(compartir.QUE) == {"transcripcion", "enlace_sala"}
    assert not any("clave" in p or "contrase" in p for p in inspect.signature(preparar).parameters)
    with pytest.raises(CompartirNoValido):
        elegir(["clave"], ["roberto"], {"transcripcion", "enlace_sala"}, {"roberto"})


def test_mailto_con_el_mismo_contenido_en_rfc_6068():
    (m,) = preparar(FECHA, {"transcripcion"}, [ROBERTO], texto_transcripcion(SEGMENTOS, NOMBRES), {})
    assert m.mailto.startswith("mailto:roberto@cenitdigital.es?subject=")
    consulta = urllib.parse.urlsplit(m.mailto).query
    assert "+" not in consulta  # RFC 6068: el espacio es %20; un «+» sería literal
    assert "%0D%0A" in consulta  # y los saltos de línea, CRLF
    campos = dict(p.split("=", 1) for p in consulta.split("&"))
    assert urllib.parse.unquote(campos["subject"]) == m.asunto
    assert urllib.parse.unquote(campos["body"]).replace("\r\n", "\n") == m.texto
    assert m.mailto_completo


def test_mailto_sin_correo_deja_el_destinatario_vacio():
    assert mailto(None, "Asunto", "Hola").startswith("mailto:?subject=Asunto&body=")


def test_mailto_codifica_el_correo():
    assert mailto("a+b@c.es", "x", "y").startswith("mailto:a%2Bb@c.es?")


def test_una_transcripcion_larga_no_cabe_en_el_mailto_y_va_adjunta():
    larga = "\n".join(f"[00:00:{i % 60:02d}] Pablo: frase número {i} de una reunión larga." for i in range(200))
    (m,) = preparar(FECHA, {"transcripcion", "enlace_sala"}, [ROBERTO], larga, {"roberto": ENLACE})
    assert larga in m.texto  # lo que se copia lleva el texto entero
    assert not m.mailto_completo
    assert len(m.mailto) <= compartir.MAILTO_MAX
    cuerpo = urllib.parse.unquote(urllib.parse.urlsplit(m.mailto).query.split("body=")[1])
    assert "frase número" not in cuerpo
    assert "fichero adjunto" in cuerpo and ENLACE in cuerpo


def test_transcripcion_y_enlace_en_el_mismo_mensaje():
    (m,) = preparar(FECHA, {"transcripcion", "enlace_sala"}, [ROBERTO], "[00:00:01] Pablo: Hola.", {"roberto": ENLACE})
    assert m.texto.count("Hola, Roberto") == 1
    assert "[00:00:01] Pablo: Hola." in m.texto and ENLACE in m.texto
    assert m.asunto == "Reunión del 2026-10-19 16:00: transcripción y enlace a la sala"


@pytest.mark.parametrize(
    ("que", "socios", "error"),
    [
        ([], ["roberto"], "qué"),
        (["transcripcion"], [], "a quién"),
        (["transcripcion"], ["intruso"], "socio"),
        (["enlace_sala"], ["roberto"], "enlace"),  # sin sala, no se ofrece
        (["nada"], ["roberto"], "qué"),
    ],
)
def test_elegir_valida_contra_lo_que_se_ofrece(que, socios, error):
    with pytest.raises(CompartirNoValido, match=error):
        elegir(que, socios, {"transcripcion"}, {"roberto", "pablo"})


def test_elegir_quita_repetidos_y_conserva_el_orden():
    assert elegir(
        ["transcripcion", "transcripcion"], ["roberto", "pablo", "roberto"], {"transcripcion"}, {"pablo", "roberto"}
    ) == (
        {"transcripcion"},
        ["roberto", "pablo"],
    )


def test_un_correo_con_coma_no_se_parte_en_dos_destinatarios():
    """RFC 6068: el `to` es una lista separada por comas; el CHECK de `socios.correo` admite una coma en la parte local."""
    assert mailto("a,b@c.es", "x", "y").startswith("mailto:?subject=")


def test_sin_transcripcion_el_mailto_nunca_dice_que_se_adjunte():
    largo = Destinatario("roberto", "R" * 2000, None)
    (m,) = preparar(FECHA, {"enlace_sala"}, [largo], None, {"roberto": ENLACE})
    assert m.mailto_completo and "adjunto" not in urllib.parse.unquote(m.mailto)
