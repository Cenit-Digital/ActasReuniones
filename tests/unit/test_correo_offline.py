"""Preparación local del mensaje F4; no se conecta a ningún servidor."""

from email import policy
from email.parser import BytesParser

import pytest

from actas.correo_offline import ErrorCorreo, preparar_correo


def test_mensaje_fijo_sin_adjuntos_con_acta_y_enlace_al_panel() -> None:
    rid = "12345678-1234-4234-8234-123456789abc"
    contenido = "Resumen: se aprobó el presupuesto.\nPendientes: preparar el contrato."
    mensaje = BytesParser(policy=policy.default).parsebytes(preparar_correo(rid, contenido))

    assert mensaje["From"] == "info@cenitdigital.es"
    assert mensaje["To"] == "info@cenitdigital.es"
    assert mensaje["Subject"] == "Acta de la reunión"
    assert mensaje.get_content_type() == "text/plain"
    assert not mensaje.is_multipart()
    assert list(mensaje.iter_attachments()) == []
    assert contenido in mensaje.get_content().replace("\r\n", "\n")
    assert f"https://actas.cenitdigital.es/reuniones/{rid}" in mensaje.get_content()


@pytest.mark.parametrize(
    "rid",
    [
        "https://otro.example/reuniones/12345678-1234-4234-8234-123456789abc",
        "12345678123442348234123456789abc",
        "12345678-1234-4234-8234-123456789ABC",
        "12345678-1234-4234-8234-123456789abc\r\nBcc: otro@example.com",
        "12345678-1234-4234-8234-123456789abc/../../otra",
        "",
    ],
)
def test_rechaza_identificador_no_canonico_o_inyectado(rid: str) -> None:
    with pytest.raises(ErrorCorreo):
        preparar_correo(rid, "acta")


@pytest.mark.parametrize("acta", ["", " \n", "texto\x00inválido", "\ud800"])
def test_rechaza_acta_vacia_o_no_codificable(acta: str) -> None:
    with pytest.raises(ErrorCorreo):
        preparar_correo("12345678-1234-4234-8234-123456789abc", acta)


def test_saltos_en_el_acta_no_crean_cabeceras() -> None:
    mensaje = BytesParser(policy=policy.default).parsebytes(
        preparar_correo("12345678-1234-4234-8234-123456789abc", "Acuerdo\r\nBcc: otro@example.com")
    )
    assert mensaje["Bcc"] is None
    assert "Bcc: otro@example.com" in mensaje.get_content()


def test_presupuesto_es_en_bytes_y_el_error_no_filtra_el_acta() -> None:
    contenido = "secreto" + "á" * 500_000
    with pytest.raises(ErrorCorreo) as error:
        preparar_correo("12345678-1234-4234-8234-123456789abc", contenido)
    assert "secreto" not in str(error.value)
