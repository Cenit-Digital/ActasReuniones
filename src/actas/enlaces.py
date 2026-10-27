"""Enlace de cada socio a su sala (@a44; ADR 0023 de KubernetesInfrastructure, decisión 3).

Es el enlace corto que crea VDO.Ninja y el de `url_invitado` en `scripts/actas_f0/navegador.py` de KubernetesInfrastructure:
`?room&hash&push&label`, **sin la contraseña**: el socio la teclea en el aviso de VDO.Ninja y `&hash` solo sirve para
comprobarla. Sin `&salt`: las salas usan siempre la del sitio, y VDO.Ninja solo lo añade si es otra (lib.js#L48744).
"""

import hashlib
import urllib.parse

BASE = "https://reuniones.cenitdigital.es/"
# session.salt del index.html de ReunionesVdoNinja: la de los enlaces de los socios. Con otra, el grabador entra en otra sala.
SAL_SITIO = "reuniones.cenitdigital.es"


def hash_sala(clave: str, salt: str = SAL_SITIO, n: int = 4) -> str:
    """Los n primeros hex de SHA-256(encodeURIComponent(clave.trim()) + salt): `sanitizePassword` (lib.js:3689) y
    `generateHash` de VDO.Ninja v30.2, como `hash_sala` de `scripts/actas_f0/analisis.py`."""
    codificada = urllib.parse.quote(clave.strip(), safe="-_.!~*'()")  # lo mismo que encodeURIComponent
    return hashlib.sha256((codificada + salt).encode()).hexdigest()[:n]


def enlace(room: str, hash_: str, push: str, label: str) -> str:
    """Con el `hash` ya calculado (el panel lo guarda al crear la sala y no descifra la contraseña para pintar enlaces)."""
    return BASE + "?" + urllib.parse.urlencode({"room": room, "hash": hash_, "push": push, "label": label})


def enlace_socio(room: str, clave: str, push: str, label: str) -> str:
    return enlace(room, hash_sala(clave), push, label)
