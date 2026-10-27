"""Salas de V2 (KubernetesInfrastructure#298, @a43): room y contraseña aleatorias, cifrado AES-GCM con la sala como dato
asociado y la clave maestra del Secret `actas-salas-clave`."""

import base64
import math

import pytest

from actas import salas

MAESTRA = bytes(range(32))
OTRA = bytes(range(1, 33))


def test_clave_maestra_de_32_bytes_en_base64():
    assert salas.clave_maestra(base64.b64encode(MAESTRA).decode() + "\n") == MAESTRA


@pytest.mark.parametrize(
    "texto",
    [
        "",
        base64.b64encode(bytes(31)).decode(),
        base64.b64encode(bytes(33)).decode(),
        "no es base64!",
        base64.b64encode(MAESTRA).decode()[:-1],
    ],
)
def test_clave_maestra_no_valida(texto):
    with pytest.raises(salas.ClaveNoValida):
        salas.clave_maestra(texto)


def test_room_aleatorio_valido_para_vdo_ninja():
    rooms = {salas.nuevo_room() for _ in range(50)}
    assert len(rooms) == 50
    for r in rooms:
        assert len(r) == salas.LARGO_ROOM
        assert salas.ROOM.fullmatch(r)
        assert set(r) <= set(salas.ALFABETO_ROOM)


def test_room_cabe_en_vdo_ninja():
    # lib.js:3666 de VDO.Ninja v30.2 (sanitizeRoomName): \W pasa a «_» y recorta a 30 caracteres.
    assert salas.ROOM.fullmatch("a" * 30)
    assert not salas.ROOM.fullmatch("a" * 31)
    assert not salas.ROOM.fullmatch("con-guion")
    assert not salas.ROOM.fullmatch("")
    assert salas.ROOM.fullmatch("Con_Mayus_9")


def test_contrasena_aleatoria_sin_caracteres_ambiguos():
    claves = {salas.nueva_clave() for _ in range(50)}
    assert len(claves) == 50
    for c in claves:
        assert len(c) == salas.LARGO_CLAVE
        assert set(c) <= set(salas.ALFABETO_CLAVE)
    assert not set("l1IoO0") & set(salas.ALFABETO_CLAVE)


def test_alfabetos_con_azar_suficiente():
    # 16 caracteres de 36 y de 31 símbolos: más de 78 bits cada uno.
    assert len(salas.ALFABETO_ROOM) == 36
    assert len(salas.ALFABETO_CLAVE) == 31
    assert (salas.LARGO_ROOM, salas.LARGO_CLAVE) == (16, 16)
    assert salas.LARGO_ROOM * math.log2(len(salas.ALFABETO_ROOM)) > 78
    assert salas.LARGO_CLAVE * math.log2(len(salas.ALFABETO_CLAVE)) > 78


def test_clave_maestra_con_caracteres_fuera_de_base64_no_vale():
    # Sin `validate=True`, b64decode descartaría el «!» y daría igualmente 32 bytes.
    texto = base64.b64encode(MAESTRA).decode()
    with pytest.raises(salas.ClaveNoValida):
        salas.clave_maestra(texto[:4] + "!" + texto[4:])


def test_cifrar_y_descifrar():
    cifrada = salas.cifrar(MAESTRA, "sala1", "k7m2p9qx4tz8wb3n")
    assert salas.descifrar(MAESTRA, "sala1", cifrada) == "k7m2p9qx4tz8wb3n"


def test_el_valor_en_claro_no_esta_en_lo_cifrado():
    cifrada = salas.cifrar(MAESTRA, "sala1", "k7m2p9qx4tz8wb3n")
    assert b"k7m2p9qx4tz8wb3n" not in cifrada
    assert len(cifrada) == salas.LARGO_NONCE + len("k7m2p9qx4tz8wb3n") + 16


def test_cada_cifrado_con_su_nonce():
    assert salas.cifrar(MAESTRA, "sala1", "x") != salas.cifrar(MAESTRA, "sala1", "x")


def test_cifrar_con_nonce_dado():
    cifrada = salas.cifrar(MAESTRA, "sala1", "x", nonce=bytes(12))
    assert cifrada[:12] == bytes(12)
    assert salas.descifrar(MAESTRA, "sala1", cifrada) == "x"


def test_descifrar_con_otra_clave_falla():
    cifrada = salas.cifrar(MAESTRA, "sala1", "k7m2p9qx4tz8wb3n")
    with pytest.raises(salas.ClaveNoValida):
        salas.descifrar(OTRA, "sala1", cifrada)


def test_descifrar_con_otra_sala_falla():
    # El room va como dato asociado: copiar la contraseña cifrada de una sala a otra no sirve.
    cifrada = salas.cifrar(MAESTRA, "sala1", "k7m2p9qx4tz8wb3n")
    with pytest.raises(salas.ClaveNoValida):
        salas.descifrar(MAESTRA, "sala2", cifrada)


@pytest.mark.parametrize("cifrada", [b"", bytes(12), bytes(27)])
def test_descifrar_algo_demasiado_corto_falla(cifrada):
    with pytest.raises(salas.ClaveNoValida):
        salas.descifrar(MAESTRA, "sala1", cifrada)


def test_descifrar_alterado_falla():
    cifrada = bytearray(salas.cifrar(MAESTRA, "sala1", "k7m2p9qx4tz8wb3n"))
    cifrada[-1] ^= 1
    with pytest.raises(salas.ClaveNoValida):
        salas.descifrar(MAESTRA, "sala1", bytes(cifrada))


@pytest.mark.parametrize("largo", [11, 13])
def test_nonce_de_12_bytes(largo):
    with pytest.raises(ValueError):
        salas.cifrar(MAESTRA, "sala1", "x", nonce=bytes(largo))


@pytest.mark.parametrize(("nombre", "esperado"), [("  Socios semanal ", "Socios semanal"), ("a", "a"), ("ñ" * 64, "ñ" * 64)])
def test_nombre_de_sala(nombre, esperado):
    assert salas.nombre_de_sala(nombre) == esperado


@pytest.mark.parametrize("nombre", ["", "   ", "x" * 65, "con\nsalto", "con\x00nulo", "tab\tulador"])
def test_nombre_de_sala_no_valido(nombre):
    with pytest.raises(salas.SalaNoValida):
        salas.nombre_de_sala(nombre)
