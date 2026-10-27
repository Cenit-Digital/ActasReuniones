"""Salas de VDO.Ninja en la base (ADR 0023 de KubernetesInfrastructure, decisión 3; V2 de #298).

- `room` y contraseña aleatorias con `secrets`. El `room` cabe en VDO.Ninja v30.2 sin cambios: `sanitizeRoomName` (lib.js:3666)
  cambia lo que no es `\\w` por «_» y recorta a 30 caracteres. La contraseña la teclea el socio: sin caracteres ambiguos.
- La contraseña se guarda cifrada con AES-256-GCM (cryptography 50.0.2, `AESGCM`): nonce aleatorio de 12 bytes delante del
  texto cifrado y el `room` como dato asociado, para que la contraseña cifrada de una sala no valga en otra. La clave maestra son
  32 bytes en base64 del Secret `actas-salas-clave`, montado en el panel y en el supervisor.
- Nada de este módulo escribe en el registro: la contraseña y la clave nunca salen de aquí más que en los valores devueltos.
"""

import base64
import binascii
import os
import re
import secrets

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ROOM = re.compile(r"[A-Za-z0-9_]{1,30}")
ALFABETO_ROOM = "abcdefghijklmnopqrstuvwxyz0123456789"
# Sin l, i, o, 0 ni 1: el socio la lee en un mensaje y la teclea en el aviso de VDO.Ninja.
ALFABETO_CLAVE = "abcdefghjkmnpqrstuvwxyz23456789"
LARGO_ROOM = 16
LARGO_CLAVE = 16
LARGO_NONCE = 12
LARGO_MAESTRA = 32
TOPE_NOMBRE = 64
_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")


class ClaveNoValida(ValueError):
    """La clave maestra no sirve o la contraseña cifrada no se puede descifrar con ella."""


class SalaNoDisponible(Exception):
    """La reunión no tiene sala o su contraseña no se puede descifrar: el supervisor no la graba (motivo `sala`)."""


class SalaNoValida(ValueError):
    """El nombre visible de la sala no es válido: 400 y ninguna fila nueva."""


def clave_maestra(texto: str) -> bytes:
    try:
        clave = base64.b64decode(texto.strip(), validate=True)
    except (binascii.Error, ValueError):
        raise ClaveNoValida("la clave de las salas no es base64") from None
    if len(clave) != LARGO_MAESTRA:
        raise ClaveNoValida(f"la clave de las salas tiene que tener {LARGO_MAESTRA} bytes")
    return clave


def nuevo_room() -> str:
    return "".join(secrets.choice(ALFABETO_ROOM) for _ in range(LARGO_ROOM))


def nueva_clave() -> str:
    return "".join(secrets.choice(ALFABETO_CLAVE) for _ in range(LARGO_CLAVE))


def cifrar(maestra: bytes, room: str, clave: str, nonce: bytes | None = None) -> bytes:
    """nonce (12 bytes) + texto cifrado con su etiqueta. `nonce` solo para los tests: por defecto, aleatorio."""
    nonce = os.urandom(LARGO_NONCE) if nonce is None else nonce
    if len(nonce) != LARGO_NONCE:
        raise ValueError(f"el nonce tiene {LARGO_NONCE} bytes")
    return nonce + AESGCM(maestra).encrypt(nonce, clave.encode(), room.encode())


def descifrar(maestra: bytes, room: str, cifrada: bytes) -> str:
    nonce, resto = cifrada[:LARGO_NONCE], cifrada[LARGO_NONCE:]
    try:
        return AESGCM(maestra).decrypt(nonce, resto, room.encode()).decode()
    except (InvalidTag, ValueError):
        raise ClaveNoValida("la contraseña de la sala no se puede descifrar con esta clave") from None


def nombre_de_sala(nombre: str) -> str:
    limpio = nombre.strip()
    if not 1 <= len(limpio) <= TOPE_NOMBRE or _CONTROL.search(limpio):
        raise SalaNoValida(f"el nombre de la sala, de 1 a {TOPE_NOMBRE} caracteres y sin saltos de línea")
    return limpio
