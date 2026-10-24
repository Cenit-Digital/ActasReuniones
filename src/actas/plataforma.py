"""Cliente de la API interna de la plataforma de transcripción (ADR 0017, D8), en `transcribir-api.transcribir.svc:8081`,
sin Traefik y con token de servicio. Solo biblioteca estándar.

La subida va en flujo y con Content-Length: el cuerpo multipart no se arma en memoria (una pista de 3 h son ~110 MB y el
contenedor tiene 256Mi). Cada pista lleva detrás su `interlocutores` (el streamID, nunca el nombre) y su `desfases_ms`; la
`referencia` es el UUID de la reunión, nunca el nombre de la sala (minimización).
"""

import http.client
import json
import secrets
import urllib.parse
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from actas.pistas import Pista

RUTA = "/api/interno/actas/trabajos"
_TROZO = 1 << 20


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
            datos = r.read()
            try:
                return r.status, json.loads(datos) if datos else None
            except ValueError:
                return r.status, None
        except (OSError, http.client.HTTPException):
            return 0, None
        finally:
            c.close()

    def crear(self, directorio: Path, pistas: list[Pista], referencia: str, idioma: str = "es") -> tuple[int, Any]:
        limite = "actas-" + secrets.token_hex(16)
        partes: list[bytes | Path] = [_campo(limite, "referencia", referencia), _campo(limite, "idioma", idioma)]
        for p in pistas:
            partes += [
                _cabecera_fichero(limite, p.fichero),
                directorio / p.fichero,
                b"\r\n",
                _campo(limite, "interlocutores", p.socio),
                _campo(limite, "desfases_ms", str(p.desfase_ms)),
            ]
        partes.append(f"--{limite}--\r\n".encode())
        longitud = sum(x.stat().st_size if isinstance(x, Path) else len(x) for x in partes)
        return self._pedir(
            "POST",
            RUTA,
            _flujo(partes),
            {"Content-Type": f"multipart/form-data; boundary={limite}", "Content-Length": str(longitud)},
        )

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


def _flujo(partes: list[bytes | Path]) -> Iterator[bytes]:
    for x in partes:
        if isinstance(x, Path):
            with x.open("rb") as f:
                while trozo := f.read(_TROZO):
                    yield trozo
        else:
            yield x
