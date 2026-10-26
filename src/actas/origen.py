"""Defensa CSRF del panel (@a31). El navegador repite la credencial de BasicAuth en cualquier petición al panel, así que un POST
solo se acepta si viene del propio panel. OWASP, «Cross-Site Request Forgery Prevention Cheat Sheet» (2026-10-26):
`Sec-Fetch-Site` es «the primary signal for CSRF protection» y `Origin` el respaldo obligatorio; `Origin: null` no prueba nada.

- Si hay `Origin`, tiene que ser exactamente el del panel (`null`, otro esquema, otro puerto o una barra final no valen).
- Si hay `Sec-Fetch-Site`, tiene que ser `same-origin` (`same-site` y `none` no valen).
- Si falta `Sec-Fetch-Site`, hace falta `Origin` (navegadores sin Fetch Metadata). Sin ninguna de las dos, se rechaza.
"""

import hmac
from collections.abc import Mapping


def permitido(cabeceras: Mapping[str, str], origen_panel: str) -> bool:
    origen = cabeceras.get("origin")
    if origen is not None and origen != origen_panel:
        return False
    sitio = cabeceras.get("sec-fetch-site")
    if sitio is not None:
        return sitio == "same-origin"
    return origen == origen_panel


_NAVEGACION = {"sec-fetch-mode": "navigate", "sec-fetch-dest": "document"}


def lectura_permitida(cabeceras: Mapping[str, str]) -> bool:
    """Aislamiento de recursos con Fetch Metadata para cualquier método (revisión de seguridad de #287, M2): una web ajena no
    puede pedir una página del panel en segundo plano con la credencial de BasicAuth (p. ej. medir lo que tarda /buscar). Se
    admite lo que no trae `Sec-Fetch-Site`, lo del propio panel, lo que abre la persona (`none`) y la navegación de nivel
    superior desde un enlace."""
    sitio = cabeceras.get("sec-fetch-site")
    if sitio is None or sitio in ("same-origin", "none"):
        return True
    return sitio in ("cross-site", "same-site") and all(cabeceras.get(k) == v for k, v in _NAVEGACION.items())


def del_proxy(recibido: str | None, secreto: str) -> bool:
    """La petición pasó por la ruta de Traefik (revisión de seguridad de #287, M1, el patrón de la consola): su middleware añade
    un secreto compartido que ningún otro camino al pod conoce."""
    return bool(secreto) and recibido is not None and hmac.compare_digest(recibido.encode(), secreto.encode())
