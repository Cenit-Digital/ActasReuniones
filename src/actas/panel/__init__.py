"""Panel de actas de F2 (KubernetesInfrastructure#287, ADR 0015 decisión 8): grabar, parar, consultar y buscar, detrás de
NetBird y BasicAuth en Traefik. `python -m actas.panel`, en la misma imagen que el supervisor.

- Escribe solo con `Repositorio.pedir` y `Repositorio.pedir_parada`, las mismas funciones que `actas.sh`: @a6 y el trigger
  diferido de conformidades aplican igual por las dos vías. El rol `actas_panel` no puede hacer nada más (migración 0002).
- Quién pulsa: la cabecera `X-Actas-Usuario`, que pone el Middleware `basicauth` de Traefik (`headerField`, con `removeHeader`
  para que la contraseña no llegue aquí). Solo se cree si además llega `X-Actas-Proxy` con el secreto que añade otro middleware
  de la misma ruta (el patrón de la consola): la NetworkPolicy no es la única barrera. Sin las dos, 401 y nada se escribe.
- CSRF: `origen.permitido` antes de leer el formulario de cualquier POST; y `origen.lectura_permitida` para todo (XS-Search).
- CSP estricta (ADR 0023 de KubernetesInfrastructure, D2): solo recursos propios, sin nada en línea; el único JavaScript es
  `tema.js`, el botón del tema. Sin registro de accesos ni texto de las peticiones en el registro (@a32).
- Maquetación v2 (V1 de KubernetesInfrastructure#298): los tokens «Terracota Clásica» de transcribir en `estatico/estilo.css`
  y sus fuentes autoalojadas (SIL OFL 1.1, con sus licencias en `estatico/fuentes/`).

Plantillas: Starlette 1.7.0, docs/templates.md: «When using the `directory` argument, Starlette enables autoescape by default
for `.html`, `.htm`, and `.xml` templates using `jinja2.select_autoescape()`»; Jinja2 3.1.6, docs/api.rst: es «a recommended
setup that enables autoescaping for templates ending in '.html', '.htm' and '.xml'». El único `Markup` (MarkupSafe 3.0.4) es
el de `busqueda.resaltar`.
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
# La ficha del trabajo en transcribir: su web enruta por hash, `#/trabajos/<id>` (PlataformaParaTranscribirAudios,
# web/src/lib/ruta.ts, `enlace('editor', id)`).
TRANSCRIBIR = "https://transcribir.cenitdigital.es"
# Referrer-Policy `same-origin`, en la cabecera y en el <meta> de base.html, y nunca `no-referrer`: Fetch Standard, «append a
# request `Origin` header», para un POST que no es CORS (un <form method="post"> es "navigate") «switch on request's referrer
# policy: "no-referrer": Set serializedOrigin to `null`», y `origen.permitido` rechaza `Origin: null` (@a31): era el 403 de
# «Grabar» en la prueba real de #287. En "same-origin", «If request's origin is not same origin with request's current URL's
# origin, then set serializedOrigin to `null`»: un POST del propio panel lleva su origen, y a otros orígenes no va ningún
# `Referer` (Referrer Policy de W3C, §3.3: «Cross-origin-referrer requests [...] will contain no referrer information»).
# Traefik añade `strict-origin-when-cross-origin`: si se suma a esta cabecera, «the value of the latest one will be used»
# (§11.1); y el <meta>, que se aplica después, manda sobre las dos («set element's node document's policy container's referrer
# policy», HTML). Ninguna combinación da `null` en un POST https al mismo origen (tests/unit/test_referrer_panel.py).
CABECERAS = {
    "content-security-policy": (
        "default-src 'none'; script-src 'self'; style-src 'self'; font-src 'self'; img-src 'self'; connect-src 'self'; "
        "form-action 'self'; frame-ancestors 'none'; base-uri 'none'"
    ),
    "x-content-type-options": "nosniff",
    "referrer-policy": "same-origin",
    "cache-control": "no-store",
    "cross-origin-resource-policy": "same-origin",
    "cross-origin-opener-policy": "same-origin",
}
TOPE_CUERPO = 16 * 1024
TOPE_CAMPOS = 32
TOPE_LISTA = 100
RUTAS_SIN_USUARIO = frozenset({"/salud"})
# Sin datos personales: el navegador los guarda un día (las páginas, no-store). Una imagen nueva los cambia como mucho al día.
CACHE_ESTATICOS = "private, max-age=86400"
# Los estáticos, cargados al arrancar: (fichero bajo estatico/, tipo). Nada más se sirve de esa carpeta.
ESTATICOS = {
    "/estilo.css": ("estilo.css", "text/css; charset=utf-8"),
    "/tema.js": ("tema.js", "text/javascript; charset=utf-8"),
    **{
        f"/fuentes/{f}": (f"fuentes/{f}", "font/woff2")
        for f in [
            "manrope-latin.woff2",
            "manrope-latin-ext.woff2",
            "gilda-display-400-latin.woff2",
            "gilda-display-400-latin-ext.woff2",
            "jetbrains-mono-latin.woff2",
            "jetbrains-mono-latin-ext.woff2",
        ]
    },
    **{
        f"/fuentes/{f}": (f"fuentes/{f}", "text/plain; charset=utf-8")
        for f in ["OFL-manrope.txt", "OFL-gildadisplay.txt", "OFL-jetbrainsmono.txt"]
    },
}


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
    POST, tope de peticiones en curso, y los errores sin traza (el mensaje de una excepción de la base puede llevar el texto de
    una fila).

    El tope cuenta peticiones, no conexiones, y no se aplica a /salud ni a los estáticos (se sirven de memoria al momento, y
    una página pide nueve a la vez). Era el `limit_concurrency` de uvicorn, que cuenta también
    las conexiones keep-alive ociosas (protocols/http/h11_impl.py: «len(self.connections) >= self.limit_concurrency» da 503):
    con 16 abiertas desde Traefik, la sonda de vida recibía 503 y el kubelet paraba el contenedor (el reinicio ordenado de las
    22:10 UTC del 2026-10-26, KubernetesInfrastructure#287).

    Un error en una ruta lo responde el ServerErrorMiddleware de Starlette (500 «Internal Server Error», sin detalle con
    debug=False) y lo vuelve a lanzar «to allow servers to log the error»: aquí se registra solo su tipo y no sigue hasta
    uvicorn, que lo escribiría con su traza. El 500 propio solo sale si el error es anterior a la respuesta de Starlette."""

    def __init__(self, app: ASGIApp, origen: str, secreto: str, registro: Registro, tope: int) -> None:
        self.app, self.origen, self.secreto, self.registro, self.tope = app, origen, secreto, registro, tope
        self.en_curso = 0

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        estatico = scope["path"] in ESTATICOS
        libre = estatico or scope["path"] in RUTAS_SIN_USUARIO
        empezada = False

        async def enviar(mensaje: Message) -> None:
            nonlocal empezada
            if mensaje["type"] == "http.response.start":
                empezada = True
                cabeceras = MutableHeaders(scope=mensaje)
                for k, v in CABECERAS.items():
                    cabeceras[k] = v
                if estatico and mensaje["status"] == 200:
                    cabeceras["cache-control"] = CACHE_ESTATICOS
            await send(mensaje)

        if not libre and self.en_curso >= self.tope:
            ocupado = PlainTextResponse("Panel ocupado, prueba otra vez", status_code=503, headers={"retry-after": "1"})
            await ocupado(scope, receive, enviar)
            return
        self.en_curso += not libre
        try:
            peticion = Request(scope)
            rechazo = self._rechazo(peticion)
            await (rechazo or self.app)(scope, receive, enviar)
        except Exception as e:  # noqa: BLE001 — sin traza ni mensaje: solo el tipo
            self.registro("petición fallida:", type(e).__name__)
            if not empezada:
                await PlainTextResponse("Error interno", status_code=500)(scope, receive, enviar)
        finally:
            self.en_curso -= not libre

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
        return None


def crear_app(
    repo: Repositorio,
    socios: Mapping[str, str],
    textos: Mapping[str, str],
    vigente: str,
    origen: str,
    secreto: str,
    registro: Registro,
    conexiones: int = 4,
    concurrencia: int = 16,
) -> ASGIApp:
    """`vigente`: la versión del texto informativo que muestra «Grabar» y la única que acepta (formulario.version_vigente).
    `secreto`: el que añade la ruta de Traefik en X-Actas-Proxy. `conexiones`: consultas a la base a la vez (una conexión cada
    una), por debajo del CONNECTION LIMIT de actas_panel. `concurrencia`: peticiones en curso a la vez, salvo /salud (503 por
    encima)."""
    if not secreto:
        raise ValueError("falta el secreto de la ruta de Traefik")
    plantillas = Jinja2Templates(directory=AQUI / "plantillas")
    estaticos = {ruta: ((AQUI / "estatico" / f).read_bytes(), tipo) for ruta, (f, tipo) in ESTATICOS.items()}
    texto = presentacion.bloques(textos[vigente])

    plantillas.env.globals["estado"] = presentacion.estado

    def pagina(peticion: Request, nombre: str, contexto: dict[str, Any], estado: int = 200) -> Response:
        return plantillas.TemplateResponse(peticion, nombre, contexto, status_code=estado)

    def mensaje(peticion: Request, texto: str, estado: int) -> Response:
        return pagina(peticion, "mensaje.html", {"mensaje": texto}, estado)

    hablantes = {s: i % 8 for i, s in enumerate(socios)}  # el color de cada socio, como en transcribir (`--hablante-*`)

    limitador: list[anyio.CapacityLimiter] = []  # se crea dentro del bucle de eventos, en la primera consulta

    async def en_hilo(f: Callable[..., Any], *args: Any) -> Any:
        if not limitador:
            limitador.append(anyio.CapacityLimiter(conexiones))
        return await anyio.to_thread.run_sync(functools.partial(f, *args), limiter=limitador[0])

    async def salud(_: Request) -> Response:
        return PlainTextResponse("ok")

    async def estatico(peticion: Request) -> Response:
        cuerpo, tipo = estaticos[peticion.url.path]
        return Response(cuerpo, headers={"content-type": tipo})

    async def no_existe(peticion: Request, _: Exception) -> Response:
        return mensaje(peticion, "Esa página no existe.", 404)

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
        en_error = [r for r in filas if r["estado"] == "error"]
        return pagina(peticion, "lista.html", {"reuniones": filas, "activa": activa, "en_error": en_error})

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
            "segmentos": [
                (presentacion.hhmmss(ini), presentacion.nombres([h], socios), hablantes.get(h, 7), t)
                for h, ini, _fin, t in segmentos
            ],
            "transcribir": f"{TRANSCRIBIR}/#/trabajos/{r['trabajo_id']}" if r.get("trabajo_id") else None,
        }
        return pagina(peticion, "reunion.html", contexto)

    async def de_trabajo(peticion: Request) -> Response:
        """El enlace de vuelta de transcribir (@a62): su web solo sabe el id del trabajo (PlataformaParaTranscribirAudios#19)."""
        trabajo = peticion.query_params.get("trabajo", "")
        rid = await en_hilo(repo.reunion_de_trabajo, trabajo) if es_uuid(trabajo) else None
        if rid is None:
            return mensaje(peticion, "Ninguna reunión tiene ese trabajo de transcribir.", 404)
        return RedirectResponse(f"/reuniones/{rid}", status_code=303)

    async def buscar(peticion: Request) -> Response:
        crudo = peticion.query_params.get("q")
        q = busqueda.normalizar(crudo)
        hallados = []
        if q is not None:
            filas = await en_hilo(repo.buscar, q, busqueda.LIMITE, busqueda.QUITAR, busqueda.PONER, busqueda.OPCIONES)
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
        # Starlette 1.7.0, docs/requests.md: «You can configure the maximum number of fields or files with `max_files` and
        # `max_fields`», «for security reasons» (lo analiza python-multipart 0.0.32, el analizador que exige `request.form`).
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
            return mensaje(peticion, "No hay ninguna grabación activa.", 409)
        return RedirectResponse(f"/reuniones/{rid}", status_code=303)

    rutas = [
        Route("/salud", salud),
        *[Route(ruta, estatico) for ruta in ESTATICOS],
        Route("/", lista),
        Route("/reuniones", de_trabajo),
        Route("/reuniones/{rid}", reunion),
        Route("/buscar", buscar),
        Route("/grabar", ver_grabar, methods=["GET"]),
        Route("/grabar", grabar, methods=["POST"]),
        Route("/parar", parar, methods=["POST"]),
    ]
    # Starlette 1.7.0, docs/requests.md: «To limit the complete request body [...] configure `max_body_size` on the
    # application» (RequestBodyLimitMiddleware: 413, cuente Content-Length o los trozos que lleguen).
    app = Starlette(debug=False, routes=rutas, max_body_size=TOPE_CUERPO, exception_handlers={404: no_existe})
    return _Guardia(app, origen, secreto, registro, concurrencia)
