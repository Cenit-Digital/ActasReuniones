"""@a29: el formulario «Grabar» del panel (socios ⊆ conocidos, versión del texto informativo) y el usuario de BasicAuth."""

import pytest

from actas.conformidad import ConformidadNoValida, Peticion
from actas.formulario import (
    FormularioNoValido,
    Socio,
    usuario,
    validar_grabar,
    validar_socio,
    version_de_fichero,
)

CONOCIDOS = ("andres", "pablo", "roberto")
VERSIONES = ("2026-10-26",)


def test_socios_validos_dan_la_peticion_ordenada():
    assert validar_grabar(["roberto", "pablo"], "2026-10-26", CONOCIDOS, VERSIONES) == Peticion(
        ("pablo", "roberto"), "2026-10-26"
    )


def test_sin_ningun_socio_se_rechaza():
    with pytest.raises(ConformidadNoValida):
        validar_grabar([], "2026-10-26", CONOCIDOS, VERSIONES)


def test_un_socio_fuera_de_la_lista_se_rechaza():
    with pytest.raises(FormularioNoValido):
        validar_grabar(["pablo", "intruso"], "2026-10-26", CONOCIDOS, VERSIONES)


@pytest.mark.parametrize("socio", ["Pablo", "pablo ", "pa-blo", ""])
def test_un_streamid_mal_formado_se_rechaza(socio):
    with pytest.raises(ConformidadNoValida):
        validar_grabar(["pablo", socio], "2026-10-26", CONOCIDOS, VERSIONES)


@pytest.mark.parametrize("version", ["", "v 1", "v1;DROP", "x" * 41, "2026-10-25"])
def test_una_version_no_valida_o_que_no_es_la_del_texto_se_rechaza(version):
    with pytest.raises(ConformidadNoValida):
        validar_grabar(["pablo"], version, CONOCIDOS, (*VERSIONES, "x" * 41))


def test_el_formulario_no_valido_es_una_conformidad_no_valida():
    assert issubclass(FormularioNoValido, ConformidadNoValida)


@pytest.mark.parametrize("valor", ["panel", "pablo.hurtado", "a@b-c_d", "x" * 64])
def test_usuario_de_basicauth(valor):
    assert usuario(valor) == valor


@pytest.mark.parametrize("valor", [None, "", " ", "x" * 65, "pablo\n", "pa blo", "pablo<", "ñ"])
def test_usuario_ausente_o_raro_es_none(valor):
    assert usuario(valor) is None


def test_alta_de_socio():
    assert validar_socio(" pablo ", " Pablo ", "") == Socio("pablo", "Pablo", None)
    assert validar_socio("andres", "Andrés", " andres@cenitdigital.es ") == Socio("andres", "Andrés", "andres@cenitdigital.es")


@pytest.mark.parametrize("push", ["socio-pablo", "-pablo", "pablo-"])
def test_alta_de_socio_con_guiones_se_rechaza(push):
    # @a47: la lección de F0, VDO.Ninja cambia «-» por «_» y el streamID acaba en nombres de fichero.
    with pytest.raises(FormularioNoValido, match="sin guiones"):
        validar_socio(push, "Pablo", "")


@pytest.mark.parametrize("push", ["", "Pablo", "socio_pablo", "socio pablo", "x" * 33, "pablé"])
def test_alta_de_socio_con_un_push_mal_formado_se_rechaza(push):
    with pytest.raises(FormularioNoValido, match="identificador"):
        validar_socio(push, "Pablo", "")


@pytest.mark.parametrize("nombre", ["", "   ", "x" * 65, "Pa\nblo"])
def test_alta_de_socio_con_un_nombre_no_valido_se_rechaza(nombre):
    with pytest.raises(FormularioNoValido, match="nombre"):
        validar_socio("pablo", nombre, "")


@pytest.mark.parametrize(
    "correo", ["pablo", "pablo@", "@cenit.es", "pa blo@cenit.es", "pablo@cenit", "a@b@c.es", "x" * 250 + "@c.es"]
)
def test_alta_de_socio_con_un_correo_no_valido_se_rechaza(correo):
    with pytest.raises(FormularioNoValido, match="correo"):
        validar_socio("pablo", "Pablo", correo)


def test_nombre_y_push_en_su_tope():
    assert validar_socio("p" * 32, "n" * 64, "").push == "p" * 32


@pytest.mark.parametrize(
    ("nombre", "version"),
    [
        ("informativo-2026-10-26.md", "2026-10-26"),
        ("informativo-v1.2_b.md", "v1.2_b"),
        ("informativo-.md", None),
        ("informativo-v 1.md", None),
        ("otro-v1.md", None),
        ("informativo-v1.txt", None),
        ("xinformativo-v1.md", None),
        ("informativo-v1.md.bak", None),
    ],
)
def test_version_de_fichero(nombre, version):
    assert version_de_fichero(nombre) == version


def test_version_vigente_explicita():
    from actas.formulario import version_vigente

    assert version_vigente({"v9": "", "v10": ""}, "v10") == "v10"


def test_version_vigente_unica_sin_configurar():
    from actas.formulario import version_vigente

    assert version_vigente({"2026-10-26": ""}, None) == "2026-10-26"
    assert version_vigente({"2026-10-26": ""}, "") == "2026-10-26"


@pytest.mark.parametrize(("textos", "pedida"), [({"v9": "", "v10": ""}, None), ({"v1": ""}, "v2"), ({}, None)])
def test_version_vigente_ambigua_o_desconocida_no_arranca_el_panel(textos, pedida):
    from actas.formulario import TextoNoValido, version_vigente

    with pytest.raises(TextoNoValido):
        version_vigente(textos, pedida)
