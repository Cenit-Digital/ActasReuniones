"""Lista blanca de los eventos de una reunión (@a55; ADR 0023 de KubernetesInfrastructure, decisión 7). Un evento solo dice qué
pasó con códigos y números: nunca texto de la reunión, nombres de fichero, mensajes de excepción ni secretos.

La base impone otra vez los tipos, las claves y la forma de los valores (CHECK de `migraciones/0005_eventos.sql`; los tipos,
desde V3, en la 0006): las listas tienen que ser las mismas, lo comprueba tests/unit/test_eventos.py. La contraseña de la
sala y el token solo los conoce el proceso: que ningún valor sea uno de ellos (o lo contenga, si el secreto tiene al menos 8
caracteres: uno más corto podría aparecer por azar dentro de un código y bloquear un cambio de estado) se comprueba aquí, antes
de escribir.
"""

import re
from collections.abc import Iterable, Mapping
from typing import Any

TIPOS = frozenset(
    {
        "estado",  # cada cambio de estado de la reunión (@a54)
        "envio",  # respuesta de transcribir al subir las pistas
        "consulta",  # respuesta de transcribir al consultar el trabajo (solo las que no son un 200 en curso)
        "aviso",  # cambia el número de socios conformes que no publican en la sala (@a25)
        "audio_borrado",  # purga del audio del tmpfs (@a10)
        "reintento",  # el supervisor atiende un «Reintentar» del panel (@a57)
        "modificada",  # el panel modifica una reunión programada (@a49, V3; lo anota la función de la base)
        "papelera",  # el panel la manda a la papelera o la recupera (@a51, V3; ídem)
    }
)
CLAVES = frozenset(
    {
        "desde",
        "hasta",
        "motivo",
        "causa",
        "completas",
        "socios",
        "pistas",
        "segmentos",
        "ficheros",
        "bytes",
        "codigo",
        "accion",
        "intento",
        "faltan",
        "usuario",
        "resultado",
    }
)
_SECRETO_LARGO = 8
# Códigos, estados y usuarios de BasicAuth (`formulario.usuario`): ni espacios ni frases.
_CADENA = re.compile(r"[A-Za-z0-9._@:-]{0,64}", re.ASCII)


class EventoNoValido(ValueError):
    pass


def validar(tipo: str, detalle: Mapping[str, Any], secretos: Iterable[str]) -> dict[str, Any]:
    if tipo not in TIPOS:
        raise EventoNoValido("tipo de evento fuera de la lista blanca")
    fuera = set(detalle) - CLAVES
    if fuera:
        raise EventoNoValido("clave de evento fuera de la lista blanca")
    secretos = [s for s in secretos if s.strip()]
    for valor in detalle.values():
        if valor is None or isinstance(valor, bool | int):
            continue
        if not isinstance(valor, str) or not _CADENA.fullmatch(valor):
            raise EventoNoValido("valor de evento que no es un código ni un número")
        if any(valor == s or (len(s) >= _SECRETO_LARGO and s in valor) for s in secretos):
            raise EventoNoValido("valor de evento con un secreto")
    return dict(detalle)
