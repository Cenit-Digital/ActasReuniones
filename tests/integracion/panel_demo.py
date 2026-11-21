"""Panel de demostración para la puerta de diseño (`impeccable-gate.mjs --rendered`) y para las capturas.

Sirve el panel real (`crear_app`) con el repositorio de mentira de los tests de navegador (`panel_falso.RepoFalso`): sin
PostgreSQL, sin red y con datos fijos. En producción Traefik añade `X-Actas-Proxy` (su secreto) y `X-Actas-Usuario` (el socio
autenticado); la puerta pide cada ruta sin cabeceras propias, así que un envoltorio ASGI las añade a toda petición HTTP, igual que
`tests/integracion/test_panel_navegador.py` las pone por CDP. No es código de producción: vive en `tests/` y pytest no lo recoge.

    PYTHONPATH=src:tests/integracion uv run --locked python tests/integracion/panel_demo.py --puerto 4310
"""

from __future__ import annotations

import argparse

from panel_falso import MAESTRA, RID_PAPELERA, RID_PISTAS, RIDS, SALA, RepoFalso
from starlette.types import ASGIApp, Receive, Scope, Send

from actas.formulario import version_vigente
from actas.panel import CABECERA_PROXY, CABECERA_USUARIO, cargar_textos, crear_app
from actas.registro import Registro

SECRETO = "secreto-de-la-demo"
USUARIO = "pablo"
COMPARTIR = f"/reuniones/{RIDS['transcrita']}/compartir"

# Las pantallas que la demo sirve con 200, las mismas que audita axe en test_panel_navegador.py salvo las que no responden 2xx
# («no existe», 404, y el 400 de «Compartir»): son las de `ui.routes` en harness.config.json (un test lo comprueba).
RUTAS = [
    "/",
    f"/reuniones/{RIDS['transcrita']}",
    f"/reuniones/{RIDS['error']}",
    f"/reuniones/{RID_PISTAS}",
    f"/reuniones/{RIDS['grabando']}",
    "/buscar?q=presupuesto",
    "/buscar",
    "/grabar",
    "/salas",
    "/salas/nueva",
    f"/salas/{SALA}",
    f"/salas/{SALA}/clave",
    "/programacion",
    f"/reuniones/{RIDS['programada']}",
    f"/reuniones/{RIDS['programada']}/modificar",
    f"/reuniones/{RIDS['programada']}/cancelar",
    f"/reuniones/{RIDS['transcrita']}/eliminar",
    "/papelera",
    f"/reuniones/{RID_PAPELERA}",
    COMPARTIR,
    f"{COMPARTIR}?que=transcripcion&que=enlace_sala&socio=pablo&socio=roberto",
]


class ConCabecerasDelProxy:
    """Añade a toda petición HTTP las dos cabeceras que pone Traefik delante del panel."""

    def __init__(self, app: ASGIApp) -> None:
        self._app = app
        self._cabeceras = [(CABECERA_PROXY.encode(), SECRETO.encode()), (CABECERA_USUARIO.encode(), USUARIO.encode())]

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            propias = {k for k, _ in self._cabeceras}
            cabeceras = [(k, v) for k, v in scope.get("headers", []) if k not in propias]
            scope = {**scope, "headers": [*cabeceras, *self._cabeceras]}
        await self._app(scope, receive, send)


def crear_demo(origen: str) -> ASGIApp:
    textos = cargar_textos()
    app = crear_app(RepoFalso(), MAESTRA, textos, version_vigente(textos, None), origen, SECRETO, Registro())
    return ConCabecerasDelProxy(app)


def main() -> None:  # pragma: no cover (proceso)
    import uvicorn

    argumentos = argparse.ArgumentParser(description=__doc__)
    argumentos.add_argument("--puerto", type=int, default=4310)
    puerto = argumentos.parse_args().puerto
    app = crear_demo(f"http://127.0.0.1:{puerto}")
    uvicorn.run(app, host="127.0.0.1", port=puerto, log_level="warning", access_log=False, lifespan="off")


if __name__ == "__main__":  # pragma: no cover
    main()
