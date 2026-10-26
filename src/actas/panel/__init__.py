"""Panel de actas de F2 (KubernetesInfrastructure#287, ADR 0015 decisión 8): grabar, parar, consultar y buscar, detrás de
NetBird y BasicAuth en Traefik. `python -m actas.panel`, en la misma imagen que el supervisor.

- Escribe solo con `Repositorio.pedir` y `Repositorio.pedir_parada`, las mismas funciones que `actas.sh`: @a6 y el trigger
  diferido de conformidades aplican igual por las dos vías. El rol `actas_panel` no puede hacer nada más (migración 0002).
- Quién pulsa: la cabecera `X-Actas-Usuario`, que pone el Middleware `basicauth` de Traefik (`headerField`, con `removeHeader`
  para que la contraseña no llegue aquí). Solo se cree si además llega `X-Actas-Proxy` con el secreto que añade otro middleware
  de la misma ruta (el patrón de la consola): la NetworkPolicy no es la única barrera. Sin las dos, 401 y nada se escribe.
- CSRF: `origen.permitido` antes de leer el formulario de cualquier POST; y `origen.lectura_permitida` para todo (XS-Search).
- Sin JavaScript y con CSP estricta; sin registro de accesos ni texto de las peticiones en el registro (@a32).

Plantillas: Starlette 1.7.0, docs/templates.md: «When using the `directory` argument, Starlette enables autoescape by default
for `.html`, `.htm`, and `.xml` templates using `jinja2.select_autoescape()`». El único `Markup` es el de `busqueda.resaltar`.
"""

import functools
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import anyio
import anyio.to_thread
from starlette.applications import Starlette
from starlette.datastructures import MutableHeaders
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import PlainTextResponse, RedirectResponse, Response
from starlette.routing import Route
from starlette.templating import Jinja2Templates
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from actas import busqueda, presentacion
from actas.base import Repositorio, es_uuid
from actas.conformidad import ConformidadNoValida
from actas.formulario import usuario, validar_grabar, version_de_fichero
from actas.origen import del_proxy, lectura_permitida, permitido
from actas.registro import Registro

AQUI = Path(__file__).resolve().parent
TEXTOS = AQUI.parent / "textos"
CABECERA_USUARIO = "x-actas-usuario"
CABECERA_PROXY = "x-actas-proxy"
CABECERAS = {
    "content-security-policy": (
        "default-src 'none'; style-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'"
    ),
    "x-content-type-options": "nosniff",
    "referrer-policy": "no-referrer",
    "cache-control": "no-store",
    "cross-origin-resource-policy": "same-origin",
    "cross-origin-opener-policy": "same-origin",
}
TOPE_CUERPO = 16 * 1024
TOPE_CAMPOS = 32
TOPE_LISTA = 100
RUTAS_SIN_USUARIO = frozenset({"/salud"})


def cargar_textos(raiz: Path | None = None) -> dict[str, str]:
    """{versión: texto} de `textos/informativo-<versión>.md`: dentro de la imagen van junto al paquete; en el repo, en textos/."""
    raiz = raiz or (TEXTOS if TEXTOS.is_dir() else Path(__file__).resolve().parents[3] / "textos")
    textos = {}
    for p in sorted(raiz.glob("informativo-*.md")):
        version = version_de_fichero(p.name)
        if version:
            textos[version] = p.read_text(encoding="utf-8")
    if not textos:
        raise FileNotFoundError("ningún texto informativo")
    return textos


class _Guardia:
    """Delante de todas las rutas: cabeceras de seguridad en cada respuesta, usuario de Traefik, CSRF y tope del cuerpo de los
    POST, y los errores sin traza (el mensaje de una excepción de la base puede llevar el texto de una fila).

    Un error en una ruta lo responde el ServerErrorMiddleware de Starlette (500 «Internal Server Error», sin detalle con
    debug=False) y lo vuelve a lanzar «to allow servers to log the error»: aquí se registra solo su tipo y no sigue hasta
    uvicorn, que lo escribiría con su traza. El 500 propio solo sale si el error es anterior a la respuesta de Starlette."""

    def __init__(self, app: ASGIApp, origen: str, secreto: str, registro: Registro) -> None:
        self.app, self.origen, self.secreto, self.registro = app, origen, secreto, registro

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        empezada = False

        async def enviar(mensaje: Message) -> None:
            nonlocal empezada
            if mensaje["type"] == "http.response.start":
                empezada = True
                cabeceras = MutableHeaders(scope=mensaje)
                for k, v in CABECERAS.items():
                    cabeceras[k] = v
            await send(mensaje)

        try:
            peticion = Request(scope)
            rechazo = self._rechazo(peticion)
            if rechazo is None and peticion.method == "POST":
                receive, rechazo = await _cuerpo_con_tope(receive)
            await (rechazo or self.app)(scope, receive, enviar)
        except Exception as e:  # noqa: BLE001 — sin traza ni mensaje: solo el tipo
            self.registro("petición fallida:", type(e).__name__)
            if not empezada:
                await PlainTextResponse("Error interno", status_code=500)(scope, receive, enviar)

    def _rechazo(self, peticion: Request) -> Response | None:
        if peticion.url.path in RUTAS_SIN_USUARIO:
            return None
        if not del_proxy(peticion.headers.get(CABECERA_PROXY), self.secreto):
            return PlainTextResponse("Solo por la ruta de Traefik", status_code=401)
        if usuario(peticion.headers.get(CABECERA_USUARIO)) is None:
            return PlainTextResponse("Falta el usuario de BasicAuth", status_code=401)
        if not lectura_permitida(peticion.headers):
            return PlainTextResponse("Petición de otro origen", status_code=403)
        if peticion.method == "POST":
            if not permitido(peticion.headers, self.origen):
                return PlainTextResponse("Petición de otro origen", status_code=403)
            longitud = peticion.headers.get("content-length", "")
            if longitud.isdigit() and int(longitud) > TOPE_CUERPO:
                return _demasiado_grande()
        return None


def _demasiado_grande() -> Response:
    return PlainTextResponse("Formulario demasiado grande", status_code=413)


async def _cuerpo_con_tope(receive: Receive) -> tuple[Receive, Response | None]:
    """Lee el cuerpo entero, como mucho TOPE_CUERPO bytes, y lo vuelve a entregar a la aplicación. Cuenta los bytes en vez de
    fiarse de Content-Length: Traefik reenvía por trozos cuando no conoce la longitud."""
    trozos: list[bytes] = []
    total = 0
    while True:
        mensaje = await receive()
        if mensaje["type"] != "http.request":
            return receive, PlainTextResponse("Petición interrumpida", status_code=400)
        trozo = mensaje.get("body", b"")
        total += len(trozo)
        if total > TOPE_CUERPO:
            return receive, _demasiado_grande()
        trozos.append(trozo)
        if not mensaje.get("more_body", False):
            break
    entregado = False

    async def repetir() -> Message:
        nonlocal entregado
        if entregado:
            return await receive()
        entregado = True
        return {"type": "http.request", "body": b"".join(trozos), "more_body": False}

    return repetir, None


def crear_app(
    repo: Repositorio,
    socios: Mapping[str, str],
    textos: Mapping[str, str],
    vigente: str,
    origen: str,
    secreto: str,
    registro: Registro,
    conexiones: int = 4,
) -> ASGIApp:
    """`vigente`: la versión del texto informativo que muestra «Grabar» y la única que acepta (formulario.version_vigente).
    `secreto`: el que añade la ruta de Traefik en X-Actas-Proxy. `conexiones`: consultas a la base a la vez (una conexión cada
    una), por debajo del CONNECTION LIMIT de actas_panel; el tope de uvicorn cuenta conexiones HTTP, no consultas."""
    if not secreto:
        raise ValueError("falta el secreto de la ruta de Traefik")
    plantillas = Jinja2Templates(directory=AQUI / "plantillas")
    estilo = (AQUI / "estatico" / "estilo.css").read_bytes()
    texto = presentacion.bloques(textos[vigente])

    def pagina(peticion: Request, nombre: str, contexto: dict[str, Any], estado: int = 200) -> Response:
        return plantillas.TemplateResponse(peticion, nombre, contexto, status_code=estado)

    limitador: list[anyio.CapacityLimiter] = []  # se crea dentro del bucle de eventos, en la primera consulta

    async def en_hilo(f: Callable[..., Any], *args: Any) -> Any:
        if not limitador:
            limitador.append(anyio.CapacityLimiter(conexiones))
        return await anyio.to_thread.run_sync(functools.partial(f, *args), limiter=limitador[0])

    async def salud(_: Request) -> Response:
        return PlainTextResponse("ok")

    async def hoja(_: Request) -> Response:
        return Response(estilo, media_type="text/css")

    async def lista(peticion: Request) -> Response:
        reuniones = await en_hilo(repo.ultimas, TOPE_LISTA)
        filas = [
            {
                "id": r["id"],
                "fecha": r["creado_en"].strftime("%Y-%m-%d %H:%M"),
                "duracion": presentacion.duracion(r["inicio"], r["fin"]),
                "estado": r["estado"],
                "motivo": r["motivo"] or "",
                "socios": presentacion.nombres(r["socios"], socios),
            }
            for r in reuniones
        ]
        activa = await en_hilo(repo.hay_grabacion)
        return pagina(peticion, "lista.html", {"reuniones": filas, "activa": activa})

    async def reunion(peticion: Request) -> Response:
        rid = peticion.path_params["rid"]
        if not es_uuid(rid):
            raise HTTPException(404)
        try:
            r, conformidades, segmentos = await en_hilo(repo.detalle, rid)
        except KeyError:
            raise HTTPException(404) from None
        contexto = {
            "r": r,
            "fecha": r["creado_en"].strftime("%Y-%m-%d %H:%M"),
            "duracion": presentacion.duracion(r["inicio"], r["fin"]),
            "socios": presentacion.nombres(r["socios"], socios),
            "conformidades": [(presentacion.nombres([s], socios), v) for s, v in conformidades],
            "segmentos": [(presentacion.hhmmss(ini), presentacion.nombres([h], socios), t) for h, ini, _fin, t in segmentos],
        }
        return pagina(peticion, "reunion.html", contexto)

    async def buscar(peticion: Request) -> Response:
        crudo = peticion.query_params.get("q")
        q = busqueda.normalizar(crudo)
        hallados = []
        if q is not None:
            filas = await en_hilo(repo.buscar, q, busqueda.LIMITE, busqueda.INICIO + busqueda.FIN, busqueda.OPCIONES)
            hallados = [
                {
                    "id": h["reunion_id"],
                    "fecha": h["creado_en"].strftime("%Y-%m-%d %H:%M"),
                    "hablante": presentacion.nombres([h["hablante"]], socios),
                    "tiempo": presentacion.hhmmss(h["inicio_ms"]),
                    "fragmento": busqueda.resaltar(h["fragmento"]),
                }
                for h in filas
            ]
        return pagina(peticion, "buscar.html", {"q": q or "", "hallados": hallados, "limite": busqueda.LIMITE})

    async def formulario_grabar(peticion: Request, error: str = "", estado: int = 200) -> Response:
        contexto = {"socios": list(socios.items()), "version": vigente, "texto": texto, "error": error}
        return pagina(peticion, "grabar.html", contexto, estado)

    async def ver_grabar(peticion: Request) -> Response:
        return await formulario_grabar(peticion)

    async def grabar(peticion: Request) -> Response:
        form = await peticion.form(max_files=0, max_fields=TOPE_CAMPOS, max_part_size=TOPE_CUERPO)
        marcados = [s for s in form.getlist("socio") if isinstance(s, str)]
        version = form.get("version")
        try:
            pedida = validar_grabar(marcados, version if isinstance(version, str) else "", socios, (vigente,))
        except ConformidadNoValida as e:
            return await formulario_grabar(peticion, str(e), 400)
        rid = await en_hilo(repo.pedir, pedida, peticion.headers[CABECERA_USUARIO])
        return RedirectResponse(f"/reuniones/{rid}", status_code=303)

    async def parar(peticion: Request) -> Response:
        rid = await en_hilo(repo.pedir_parada)
        if rid is None:
            return pagina(peticion, "mensaje.html", {"mensaje": "No hay ninguna grabación activa."}, 409)
        return RedirectResponse(f"/reuniones/{rid}", status_code=303)

    rutas = [
        Route("/salud", salud),
        Route("/estilo.css", hoja),
        Route("/", lista),
        Route("/reuniones/{rid}", reunion),
        Route("/buscar", buscar),
        Route("/grabar", ver_grabar, methods=["GET"]),
        Route("/grabar", grabar, methods=["POST"]),
        Route("/parar", parar, methods=["POST"]),
    ]
    return _Guardia(Starlette(debug=False, routes=rutas), origen, secreto, registro)
