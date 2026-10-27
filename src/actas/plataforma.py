"""Cliente de la API interna de la plataforma de transcripción (ADR 0017, D8), en `transcribir-api.transcribir.svc:8081`,
sin Traefik y con token de servicio. Solo biblioteca estándar.

La subida va en flujo y con Content-Length: el cuerpo multipart no se arma en memoria (una pista de 3 h son ~110 MB y el
contenedor tiene 256Mi). Cada pista lleva detrás su `interlocutores` (el streamID, nunca el nombre) y su `desfases_ms`; la
`referencia` es el UUID de la reunión, nunca el nombre de la sala (minimización).
"""

import http.client
import json
import os
import secrets
import stat
import urllib.parse
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from actas.pistas import Pista, PistasNoValidas

RUTA = "/api/interno/actas/trabajos"
_TROZO = 1 << 20
MAX_PISTA_BYTES = 1 << 30  # ~10 h de Opus a ~81 kbps: muy por encima del tope de 3 h
MAX_RESPUESTA_BYTES = 32 << 20  # una transcripción de 3 h con sus palabras ocupa unos pocos MB


class Plataforma:
    def __init__(self, url: str, token: str, tiempo_s: float = 60.0) -> None:
        partes = urllib.parse.urlsplit(url)
        if partes.scheme != "http" or not partes.hostname:
            raise ValueError("URL interna http://host:puerto")
        self._host, self._puerto = partes.hostname, partes.port or 80
        self._token = token
        self._tiempo_s = tiempo_s

    def _pedir(self, metodo: str, ruta: str, cuerpo: Any = None, cabeceras: dict[str, str] | None = None) -> tuple[int, Any]:
        """(código, JSON o None). Código 0 si no hubo respuesta: el llamante decide si reintenta."""
        c = http.client.HTTPConnection(self._host, self._puerto, timeout=self._tiempo_s)
        try:
            c.request(metodo, ruta, body=cuerpo, headers={"Authorization": f"Bearer {self._token}", **(cabeceras or {})})
            r = c.getresponse()
            datos = r.read(MAX_RESPUESTA_BYTES + 1)
            if len(datos) > MAX_RESPUESTA_BYTES:
                return r.status, None
            try:
                return r.status, json.loads(datos) if datos else None
            except ValueError:
                return r.status, None
        except (OSError, http.client.HTTPException):
            return 0, None
        finally:
            c.close()

    def crear(self, directorio: Path, pistas: list[Pista], referencia: str, idioma: str = "es") -> tuple[int, Any]:
        """Sube las pistas. Lanza PistasNoValidas si alguna no es un fichero regular del propio directorio (ver _abrir)."""
        abiertas = _abrir(directorio, pistas)
        try:
            limite = "actas-" + secrets.token_hex(16)
            partes: list[bytes | tuple[int, int]] = [_campo(limite, "referencia", referencia), _campo(limite, "idioma", idioma)]
            for p, (fd, tamano) in zip(pistas, abiertas, strict=True):
                partes += [
                    _cabecera_fichero(limite, p.fichero),
                    (fd, tamano),
                    b"\r\n",
                    _campo(limite, "interlocutores", p.socio),
                    _campo(limite, "desfases_ms", str(p.desfase_ms)),
                ]
            partes.append(f"--{limite}--\r\n".encode())
            longitud = sum(x[1] if isinstance(x, tuple) else len(x) for x in partes)
            return self._pedir(
                "POST",
                RUTA,
                _flujo(partes),
                {"Content-Type": f"multipart/form-data; boundary={limite}", "Content-Length": str(longitud)},
            )
        finally:
            for fd, _ in abiertas:
                os.close(fd)

    def estado(self, trabajo_id: str) -> tuple[int, Any]:
        return self._pedir("GET", f"{RUTA}/{uuid.UUID(trabajo_id)}")


def _campo(limite: str, nombre: str, valor: str) -> bytes:
    return (
        f'--{limite}\r\nContent-Disposition: form-data; name="{nombre}"\r\nContent-Type: text/plain; charset=utf-8\r\n\r\n'
        f"{valor}\r\n"
    ).encode()


def _cabecera_fichero(limite: str, fichero: str) -> bytes:
    # El nombre es `<id>_<ms>.webm`, ya validado por pistas.pistas_de: sin comillas ni saltos de línea.
    return (
        f'--{limite}\r\nContent-Disposition: form-data; name="pistas"; filename="{fichero}"\r\nContent-Type: audio/webm\r\n\r\n'
    ).encode()


def _abrir(directorio: Path, pistas: list[Pista]) -> list[tuple[int, int]]:
    """(descriptor, tamaño) de cada pista. El tmpfs lo escribe Chromium, que procesa audio de terceros sin sandbox: no se
    siguen enlaces (ni el directorio ni las pistas), no se abre nada que no sea un fichero regular (un FIFO bloquearía) y se
    envía exactamente el tamaño leído con fstat, desde el mismo descriptor."""
    abiertas: list[tuple[int, int]] = []
    try:
        dfd = os.open(directorio, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except OSError as e:
        raise PistasNoValidas("el directorio de la reunión no es un directorio propio", "directorio") from e
    try:
        for p in pistas:
            try:
                fd = os.open(p.fichero, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=dfd)
            except OSError as e:
                raise PistasNoValidas("pista que no se puede abrir sin seguir enlaces", "fichero") from e
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode) or not 0 < st.st_size <= MAX_PISTA_BYTES:
                os.close(fd)
                raise PistasNoValidas("pista que no es un fichero regular con audio", "fichero")
            abiertas.append((fd, st.st_size))
    except PistasNoValidas:
        for fd, _ in abiertas:
            os.close(fd)
        raise
    finally:
        os.close(dfd)
    return abiertas


def _flujo(partes: list[bytes | tuple[int, int]]) -> Iterator[bytes]:
    for x in partes:
        if isinstance(x, tuple):
            fd, quedan = x
            os.lseek(fd, 0, os.SEEK_SET)
            while quedan > 0:
                trozo = os.read(fd, min(_TROZO, quedan))
                if not trozo:  # el fichero encogió: se rellena para no romper el Content-Length (la plataforma lo rechazará)
                    trozo = b"\0" * quedan
                yield trozo
                quedan -= len(trozo)
        else:
            yield x
