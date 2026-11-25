"""Autenticación y rechazos de `/mcp` (ADR 0004): el token, su hash y la guarda ASGI delante del SDK.

Rechazos, en este orden: método ≠ POST (405, `Allow: POST`), `Host` fuera de la lista (403, DNS rebinding),
cualquier `Origin` (403: Hermes no es un navegador) y Bearer ausente o distinto del emitido (401). Nunca se
compara el token en claro: se compara su SHA-256 con `hmac.compare_digest`.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Receive, Scope, Send

PREFIJO_TOKEN = "tmcp_"  # noqa: S105 — prefijo público del formato, no un secreto
CABECERAS = {"Cache-Control": "no-store"}
# Alias a nivel de módulo: si se muta, la importación falla (a diferencia de una anotación, que no se evalúa).
Cabeceras = dict[str, str] | None
Rechazo = Response | None


def nuevo_token() -> str:
    return PREFIJO_TOKEN + secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def token_valido(recibido: str, esperado_sha256: str) -> bool:
    """Compara los SHA-256 en tiempo constante: ni el token ni su hash se comparan con `==`."""
    return hmac.compare_digest(hash_token(recibido).encode(), esperado_sha256.encode())


def _rechazo(status: int, titulo: str, cabeceras: Cabeceras = None) -> Response:
    return JSONResponse(
        {"type": "about:blank", "title": titulo, "status": status},
        status_code=status,
        media_type="application/problem+json",
        headers=CABECERAS | (cabeceras or {}),
    )


class GuardaMcp:
    """ASGI delante del SDK: método, Host, Origin y Bearer."""

    def __init__(self, app: ASGIApp, hosts: tuple[str, ...], token_sha256: str) -> None:
        self.app, self.hosts, self.token_sha256 = app, frozenset(hosts), token_sha256

    def _rechazar(self, request: Request) -> Rechazo:
        if request.method != "POST":
            return _rechazo(405, "Método no permitido", {"Allow": "POST"})
        if request.headers.get("host", "") not in self.hosts:
            return _rechazo(403, "Host no admitido")
        if "origin" in request.headers:
            return _rechazo(403, "Origin no admitido")
        autorizacion = request.headers.get("authorization", "")
        esquema, _, token = autorizacion.partition(" ")
        if esquema.lower() != "bearer" or not token.strip() or not token_valido(token.strip(), self.token_sha256):
            return _rechazo(401, "Token no válido", {"WWW-Authenticate": "Bearer"})
        return None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return
        respuesta = self._rechazar(Request(scope))
        if respuesta is not None:
            await respuesta(scope, receive, send)
            return
        await self.app(scope, receive, send)
