"""Defensa CSRF del panel (@a31). El navegador repite la credencial de BasicAuth en cualquier petición al panel, así que un POST
solo se acepta si viene del propio panel. OWASP, «Cross-Site Request Forgery Prevention Cheat Sheet» (2026-10-26):
`Sec-Fetch-Site` es «the primary signal for CSRF protection» y `Origin` el respaldo obligatorio; `Origin: null` no prueba nada.

- Si hay `Origin`, tiene que ser exactamente el del panel (`null`, otro esquema, otro puerto o una barra final no valen).
- Si hay `Sec-Fetch-Site`, tiene que ser `same-origin` (`same-site` y `none` no valen).
- Si falta `Sec-Fetch-Site`, hace falta `Origin` (navegadores sin Fetch Metadata). Sin ninguna de las dos, se rechaza.
"""

from collections.abc import Mapping


def permitido(cabeceras: Mapping[str, str], origen_panel: str) -> bool:
    origen = cabeceras.get("origin")
    if origen is not None and origen != origen_panel:
        return False
    sitio = cabeceras.get("sec-fetch-site")
    if sitio is not None:
        return sitio == "same-origin"
    return origen == origen_panel
