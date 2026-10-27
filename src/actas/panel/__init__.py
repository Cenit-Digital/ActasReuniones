"""Panel de actas de F2 (KubernetesInfrastructure#287, ADR 0015 decisión 8): grabar, parar, consultar y buscar, detrás de
NetBird y BasicAuth en Traefik. `python -m actas.panel`, en la misma imagen que el supervisor.

- Escribe solo con `Repositorio.pedir` y `Repositorio.pedir_parada`, las mismas funciones que `actas.sh`: @a6 y el trigger
  diferido de conformidades aplican igual por las dos vías. El rol `actas_panel` no puede hacer nada más (migración 0002).
- «Salas y socios» (V2 de #298, migración 0003): crea salas con `room` y contraseña aleatorias, cifradas con la clave del
  Secret `actas-salas-clave` (`salas`); enseña el enlace de cada socio sin la contraseña (`enlaces`, @a44); y la contraseña
  solo tras confirmarlo con un POST, que la base anota como `clave_vista` antes de dar el valor cifrado (@a45). Da de alta y de
  baja socios (@a47). La base no deja al panel leer la contraseña cifrada de otra forma ni cambiar nada (sin UPDATE).
- «Reintentar» de una reunión en error (V4, migración 0005): solo por la función `pedir_reintento` (SECURITY DEFINER).
- Programar, modificar (@a49), cancelar (@a50), eliminar a la papelera escribiendo el título y recuperar (@a51): V3, migración
  0006, solo por sus funciones SECURITY DEFINER. «Grabar ahora» guarda además el título y el tope por columnas. El borrado de
  verdad lo hace la purga diaria del supervisor: el panel no puede borrar nada.
- Diagnóstico (V4 de KubernetesInfrastructure#298, ADR 0023 decisión 7): el motivo en lenguaje claro (`diagnostico.py`), el
  historial de eventos y las comprobaciones del latido, todo desde la base. Los registros crudos de los pods, en la consola:
  el panel no tiene permisos sobre Kubernetes.
- «Compartir» (V5 nivel 1, decisión 8; `compartir.py`) y «Copiar diagnóstico para Claude» (V6 parte a, decisión 9;
  `para_claude.py`): solo preparan texto, que se ve en un `<textarea readonly>` y copia `copiar.js`. Nada se escribe.
- Quién pulsa: la cabecera `X-Actas-Usuario`, que pone el Middleware `basicauth` de Traefik (`headerField`, con `removeHeader`
  para que la contraseña no llegue aquí). Solo se cree si además llega `X-Actas-Proxy` con el secreto que añade otro middleware
  de la misma ruta (el patrón de la consola): la NetworkPolicy no es la única barrera. Sin las dos, 401 y nada se escribe.
- CSRF: `origen.permitido` antes de leer el formulario de cualquier POST; y `origen.lectura_permitida` para todo (XS-Search).
- CSP estricta (ADR 0023 de KubernetesInfrastructure, D2): solo recursos propios, sin nada en línea; el único JavaScript es
  `tema.js`, el botón del tema, y `copiar.js`, los botones «Copiar». Sin registro de accesos ni texto de las peticiones en el
  registro (@a32).
- Maquetación v2 (V1 de KubernetesInfrastructure#298): los tokens «Terracota Clásica» de transcribir en `estatico/estilo.css`
  y sus fuentes autoalojadas (SIL OFL 1.1, con sus licencias en `estatico/fuentes/`).

Plantillas: Starlette 1.7.0, docs/templates.md: «When using the `directory` argument, Starlette enables autoescape by default
for `.html`, `.htm`, and `.xml` templates using `jinja2.select_autoescape()`»; Jinja2 3.1.6, docs/api.rst: es «a recommended
setup that enables autoescaping for templates ending in '.html', '.htm' and '.xml'». El único `Markup` (MarkupSafe 3.0.4) es
el de `busqueda.resaltar`.
"""

import functools
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import anyio
import anyio.to_thread
import psycopg
from starlette.applications import Starlette
from starlette.datastructures import MutableHeaders
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import PlainTextResponse, RedirectResponse, Response
from starlette.routing import Route
from starlette.templating import Jinja2Templates
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from actas import busqueda, compartir, diagnostico, enlaces, para_claude, planificador, presentacion, salas
from actas.base import Repositorio, es_uuid
from actas.conformidad import ConformidadNoValida, Peticion
from actas.estados import ESTADOS_FINALES, Estado
from actas.formulario import FormularioNoValido, usuario, validar_grabar, validar_socio, version_de_fichero
from actas.origen import del_proxy, lectura_permitida, permitido
from actas.registro import Registro

AQUI = Path(__file__).resolve().parent
TEXTOS = AQUI.parent / "textos"
CABECERA_USUARIO = "x-actas-usuario"
CABECERA_PROXY = "x-actas-proxy"
# La ficha del trabajo en transcribir: su web enruta por hash, `#/trabajos/<id>` (PlataformaParaTranscribirAudios,
# web/src/lib/ruta.ts, `enlace('editor', id)`).
TRANSCRIBIR = "https://transcribir.cenitdigital.es"
# Los registros de los pods de `actas` en la consola: su web enruta `#/cargas/<espacio>` a «Cargas de trabajo» con ese espacio
# (PlataformaWebObservabilidadInfra, apps/web/src/interfaz/rutas.ts y App.tsx, `espacioInicial`), con «logs» por pod.
CONSOLA = "https://consola.cenitdigital.es/#/cargas/actas"
# El glifo de cada nivel del historial y de las comprobaciones (el texto va siempre al lado).
GLIFO_NIVEL = {"ok": "visto", "aviso": "medio", "error": "cruz", "info": "espera"}
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
        # ADR 0023, D2, sin `img-src` ni `connect-src`: nada los usa (los glifos son SVG en línea y no hay fetch), y sin ellos
        # vale `default-src 'none'`. Los abrirá la fase que los necesite.
        "default-src 'none'; script-src 'self'; style-src 'self'; font-src 'self'; "
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
    "/copiar.js": ("copiar.js", "text/javascript; charset=utf-8"),
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


EVENTOS_SALA = {"sala_creada": "Sala creada", "clave_vista": "Contraseña vista"}
NO_ELIMINABLE = "Solo se elimina una reunión terminada (transcrita, en error o cancelada) que no esté ya en la papelera."
NO_PROGRAMADA = "Esa reunión ya no está programada: solo se modifica antes de empezar."
REPETIR = {"no": "no se repite", "semanal": "cada semana", "mensual": "cada mes"}
# Los valores de «Grabar» antes de rellenarlo: ahora, sin título y con el tope de F1; si se programa, sin repetir y 15 min.
GRABAR_VACIO = {
    "titulo": "",
    "cuando": "ahora",
    "fecha": "",
    "tope": "180",
    "repetir": "no",
    "espera": "15",
    "sala": "",
    "socios": (),
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

        cuenta = False
        try:
            # El tope, después de la autenticación: sin credenciales, 401 aunque esté lleno (y un rechazo no ocupa sitio).
            rechazo = self._rechazo(Request(scope))
            if rechazo is None and not libre and self.en_curso >= self.tope:
                rechazo = PlainTextResponse("Panel ocupado, prueba otra vez", status_code=503, headers={"retry-after": "1"})
            if rechazo is not None:
                await rechazo(scope, receive, enviar)
                return
            cuenta = not libre
            self.en_curso += cuenta
            await self.app(scope, receive, enviar)
        except Exception as e:  # noqa: BLE001 — sin traza ni mensaje: solo el tipo
            self.registro("petición fallida:", type(e).__name__)
            if not empezada:
                await PlainTextResponse("Error interno", status_code=500)(scope, receive, enviar)
        finally:
            self.en_curso -= cuenta

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


def _hora(m: datetime) -> str:
    return m.strftime("%Y-%m-%d %H:%M:%S")


def _fecha(r: Mapping[str, Any]) -> str:
    creado: datetime = r["creado_en"]
    return creado.strftime("%Y-%m-%d %H:%M")


def _madrid(m: datetime) -> str:
    """Una hora con zona, en la de Madrid (la base la da ya en la sesión del panel, TimeZone Europe/Madrid)."""
    return m.astimezone(planificador.MADRID).strftime("%Y-%m-%d %H:%M")


def _nombre(r: Mapping[str, Any]) -> str:
    return r.get("titulo") or f"Reunión del {_fecha(r)}"


def _confirmacion(r: Mapping[str, Any]) -> str:
    """Lo que hay que escribir para eliminarla: su título o, si no tiene (las anteriores a V3), su fecha."""
    return r.get("titulo") or _fecha(r)


def _diagnostico(r: Mapping[str, Any], datos: Mapping[str, Any]) -> dict[str, Any]:
    """Historial de la reunión (sus eventos más lo que dicen sus columnas) y, si está en error, su diagnóstico (@a56) y si se
    ofrece «Reintentar» (@a57): solo con un motivo que se arregle reenviando, el latido fresco y el audio aún en el tmpfs."""
    eventos = datos["eventos"]
    por = r.get("pedido_por") or "actas.sh"
    if r.get("programada_para"):
        texto = "Programada de nuevo, la siguiente de su serie," if r.get("anterior_id") else f"Programada por {por}"
        lineas: list[tuple[datetime, str, str]] = [(r["creado_en"], f"{texto} para el {_madrid(r['programada_para'])}", "info")]
    else:
        lineas = [(r["creado_en"], f"Pedida por {por}", "info")]
    if r.get("parar_pedido_en"):
        lineas.append((r["parar_pedido_en"], "Parada pedida", "info"))
    if r.get("reintento_pedido_en"):
        lineas.append((r["reintento_pedido_en"], f"Reintento pedido por {r.get('reintento_pedido_por')}: pendiente", "info"))
    for e in eventos:
        lineas.append((e["momento"], *diagnostico.linea_evento(e["tipo"], e["detalle"])))
    if not eventos:  # una reunión anterior a V4: lo que se sabe por sus columnas
        if r.get("inicio"):
            lineas.append((r["inicio"], "Empezó a grabar", "info"))
        if r.get("fin"):
            lineas.append((r["fin"], "Terminó la grabación", "info"))
    lineas.sort(key=lambda x: x[0])
    contexto: dict[str, Any] = {
        "historial": [(_hora(m), texto, nivel, GLIFO_NIVEL[nivel]) for m, texto, nivel in lineas],
        "sin_eventos": not eventos,
        "diagnostico": None,
    }
    if r["estado"] != "error":
        return contexto
    inicio, fin, parada = r.get("inicio"), r.get("fin"), r.get("parar_pedido_en")
    a_error = [e["detalle"] for e in eventos if e["tipo"] == "estado" and e["detalle"].get("hasta") == "error"]
    d = diagnostico.diagnosticar(
        r.get("motivo"),
        duracion_s=(fin - inicio).total_seconds() if inicio and fin else None,
        parada_s=(parada - inicio).total_seconds() if inicio and parada else None,
        causa=a_error[-1].get("causa") if a_error else None,
        con_historial=bool(eventos),
    )
    latido, hace_s = datos["latido"], datos["latido_hace_s"]
    vivo = hace_s is not None and hace_s < diagnostico.LATIDO_MAX_S
    con_audio = latido is not None and r["id"] in (latido.get("con_audio") or [])
    nota = ""
    if d.reintentable and r.get("reintento_pedido_en"):
        nota = "Reintento pedido: el supervisor lo atiende en su próxima vuelta (cada 5 s)."
    elif d.reintentable and not vivo:
        nota = "El supervisor no da señales de vida: «Reintentar» se ofrecerá de nuevo cuando las dé."
    elif d.reintentable and not con_audio:
        nota = "El audio de esta reunión ya no está en el supervisor (se borra como mucho a los 7 días): no se puede reintentar."
    contexto["diagnostico"] = d
    contexto["reintentar"] = d.reintentable and vivo and con_audio and not r.get("reintento_pedido_en")
    contexto["nota"] = nota
    contexto["comprobaciones"] = [
        (texto, nivel, GLIFO_NIVEL[nivel])
        for texto, nivel in diagnostico.comprobaciones(latido, hace_s, datos["fallos_transcribir_1h"])
    ]
    return contexto


def crear_app(
    repo: Repositorio,
    maestra: bytes,
    textos: Mapping[str, str],
    vigente: str,
    origen: str,
    secreto: str,
    registro: Registro,
    conexiones: int = 4,
    concurrencia: int = 16,
) -> ASGIApp:
    """`maestra`: la clave de las contraseñas de las salas (Secret `actas-salas-clave`). `vigente`: la versión del texto
    informativo que muestra «Grabar» y la única que acepta (formulario.version_vigente).
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

    limitador: list[anyio.CapacityLimiter] = []  # se crea dentro del bucle de eventos, en la primera consulta

    async def en_hilo(f: Callable[..., Any], *args: Any) -> Any:
        if not limitador:
            limitador.append(anyio.CapacityLimiter(conexiones))
        return await anyio.to_thread.run_sync(functools.partial(f, *args), limiter=limitador[0])

    async def directorio() -> dict[str, str]:
        """{push: nombre} de todos los socios, también los de baja: sus nombres siguen en las reuniones pasadas."""
        return {s["push"]: s["nombre"] for s in await en_hilo(repo.socios)}

    async def formulario(peticion: Request) -> Any:
        # Starlette 1.7.0, docs/requests.md: «You can configure the maximum number of fields or files with `max_files` and
        # `max_fields`», «for security reasons» (lo analiza python-multipart 0.0.32, el analizador que exige `request.form`).
        return await peticion.form(max_files=0, max_fields=TOPE_CAMPOS, max_part_size=TOPE_CUERPO)

    def campo(form: Any, nombre: str) -> str:
        valor = form.get(nombre)
        return valor if isinstance(valor, str) else ""

    async def salud(_: Request) -> Response:
        return PlainTextResponse("ok")

    async def estatico(peticion: Request) -> Response:
        cuerpo, tipo = estaticos[peticion.url.path]
        return Response(cuerpo, headers={"content-type": tipo})

    async def no_existe(peticion: Request, _: Exception) -> Response:
        return mensaje(peticion, "Esa página no existe.", 404)

    async def lista(peticion: Request) -> Response:
        reuniones = await en_hilo(repo.ultimas, TOPE_LISTA)
        socios = await directorio()
        filas = [
            {
                "id": r["id"],
                "fecha": _fecha(r),
                "nombre": _nombre(r),
                "programada": _madrid(r["programada_para"]) if r.get("programada_para") else None,
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
        socios = await directorio()
        hablantes = {s: i % 8 for i, s in enumerate(socios)}  # el color de cada socio, como en transcribir (`--hablante-*`)
        sala = None
        if r.get("sala_id"):
            try:
                sala = await en_hilo(repo.sala, r["sala_id"])
            except KeyError:
                sala = None
        datos = await en_hilo(repo.diagnostico, rid)
        papelera = r.get("papelera_en") is not None
        contexto = {
            "r": r,
            "fecha": _fecha(r),
            "nombre": _nombre(r),
            "programada": _madrid(r["programada_para"]) if r.get("programada_para") else None,
            "repetir": REPETIR.get(r.get("repetir") or "no"),
            "papelera": papelera,
            "eliminable": not papelera and r["estado"] in ESTADOS_FINALES,
            "duracion": presentacion.duracion(r["inicio"], r["fin"]),
            "socios": presentacion.nombres(r["socios"], socios),
            "conformidades": [(presentacion.nombres([s], socios), v) for s, v in conformidades],
            # En la papelera no se enseña lo que dijeron: se ha pedido borrarlo (se puede recuperar).
            "segmentos": []
            if papelera
            else [
                (presentacion.hhmmss(ini), presentacion.nombres([h], socios), hablantes.get(h, 7), t)
                for h, ini, _fin, t in segmentos
            ],
            "transcribir": f"{TRANSCRIBIR}/#/trabajos/{r['trabajo_id']}" if r.get("trabajo_id") else None,
            "sala": sala,
            "consola": CONSOLA,
            **_diagnostico(r, datos),
        }
        if contexto["diagnostico"]:  # @a60
            contexto["para_claude"] = para_claude.bloque(
                r, conformidades, datos["eventos"], contexto["diagnostico"], [c[:2] for c in contexto["comprobaciones"]], socios
            )
        return pagina(peticion, "reunion.html", contexto)

    # ── Compartir (V5 nivel 1) ────────────────────────────────────────────────────────────────────────────────────────

    async def detalle_o_404(peticion: Request) -> tuple[dict[str, Any], list[tuple[str, int, int, str]]]:
        rid = peticion.path_params["rid"]
        if not es_uuid(rid):
            raise HTTPException(404)
        try:
            r, _conformidades, segmentos = await en_hilo(repo.detalle, rid)
        except KeyError:
            raise HTTPException(404) from None
        return r, segmentos

    async def ver_compartir(peticion: Request) -> Response:
        """@a58: el formulario es un GET (sin JavaScript, la misma página enseña los mensajes) y solo lleva lo marcado."""
        r, segmentos = await detalle_o_404(peticion)
        todos = {s["push"]: s for s in await en_hilo(repo.socios)}
        nombres = {p: s["nombre"] for p, s in todos.items()}
        destinatarios = {p: compartir.Destinatario(p, nombres.get(p, p), (todos.get(p) or {}).get("correo")) for p in r["socios"]}
        sala = None
        if r.get("sala_id"):
            try:
                sala = await en_hilo(repo.sala, r["sala_id"])
            except KeyError:
                sala = None
        ofrecido = {q for q, si in (("transcripcion", segmentos), ("enlace_sala", sala)) if si}
        fecha = r["creado_en"].strftime("%Y-%m-%d %H:%M")
        que, marcados = peticion.query_params.getlist("que"), peticion.query_params.getlist("socio")
        contexto: dict[str, Any] = {
            "r": r,
            "fecha": fecha,
            "sala": sala,
            "ofrecido": ofrecido,
            "destinatarios": list(destinatarios.values()),
            "que": set(que),
            "marcados": set(marcados),
            "mensajes": [],
            "error": "",
        }
        if not que and not marcados:
            return pagina(peticion, "compartir.html", contexto)
        try:
            elegido, elegidos = compartir.elegir(que, marcados, ofrecido, destinatarios)
        except compartir.CompartirNoValido as e:
            contexto["error"] = str(e)
            return pagina(peticion, "compartir.html", contexto, 400)
        enlaces_sala = (
            {p: enlaces.enlace(sala["room"], sala["hash"], p, d.nombre) for p, d in destinatarios.items()} if sala else {}
        )
        transcripcion = compartir.texto_transcripcion(segmentos, nombres) if "transcripcion" in elegido else None
        contexto["mensajes"] = compartir.preparar(
            fecha, elegido, [destinatarios[p] for p in elegidos], transcripcion, enlaces_sala
        )
        contexto["elegido"] = elegido
        return pagina(peticion, "compartir.html", contexto)

    async def transcripcion_txt(peticion: Request) -> Response:
        """Para adjuntarla: un `mailto:` no puede adjuntar ficheros y una transcripción larga no cabe en él."""
        r, segmentos = await detalle_o_404(peticion)
        if not segmentos:
            raise HTTPException(404)
        nombre = r["creado_en"].strftime("transcripcion-%Y-%m-%d-%H%M.txt")
        texto = compartir.texto_transcripcion(segmentos, await directorio()) + "\n"
        return PlainTextResponse(texto, headers={"content-disposition": f'attachment; filename="{nombre}"'})

    async def reintentar(peticion: Request) -> Response:
        """@a57: solo anota la petición; el supervisor la atiende en su próxima vuelta si el audio sigue en el tmpfs."""
        rid = peticion.path_params["rid"]
        if not es_uuid(rid):
            raise HTTPException(404)
        pedido = await en_hilo(repo.pedir_reintento, rid, peticion.headers[CABECERA_USUARIO])
        if pedido is None:
            raise HTTPException(404)
        if not pedido:
            return mensaje(peticion, "Esa reunión no está en error o ya tiene un reintento pedido.", 409)
        return RedirectResponse(f"/reuniones/{rid}#diagnostico", status_code=303)

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
            socios = await directorio() if filas else {}
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

    async def formulario_grabar(
        peticion: Request, error: str = "", estado: int = 200, valores: Mapping[str, Any] | None = None
    ) -> Response:
        activos = [(s["push"], s["nombre"]) for s in await en_hilo(repo.socios) if s["activo"]]
        contexto = {
            "socios": activos,
            "salas": await en_hilo(repo.salas),
            "version": vigente,
            "texto": texto,
            "error": error,
            "v": {**GRABAR_VACIO, **(valores or {})},
            "topes": planificador.TOPES_MIN,
            "esperas": planificador.ESPERAS_MIN,
        }
        return pagina(peticion, "grabar.html", contexto, estado)

    def valores(form: Any) -> dict[str, Any]:
        """Lo que se envió, para volver a pintarlo si se rechaza (el formulario no se pierde)."""
        return {
            **{k: campo(form, k) for k in ("titulo", "cuando", "fecha", "tope", "repetir", "espera", "sala")},
            "socios": tuple(s for s in form.getlist("socio") if isinstance(s, str)),
        }

    async def validar_formulario(form: Any) -> tuple[Peticion, str]:
        """La sala y los socios conformes de «Grabar» y «Modificar» (@a29, @a6)."""
        sala = campo(form, "sala")
        if not es_uuid(sala) or sala not in {s["id"] for s in await en_hilo(repo.salas)}:
            raise FormularioNoValido("elige la sala en la que se graba")
        activos = [s["push"] for s in await en_hilo(repo.socios) if s["activo"]]
        marcados = [s for s in form.getlist("socio") if isinstance(s, str)]
        return validar_grabar(marcados, campo(form, "version"), activos, (vigente,)), sala

    def programacion_de(form: Any, pedida: Peticion, sala: str) -> planificador.Programacion:
        return planificador.validar_programacion(
            campo(form, "titulo"),
            sala,
            campo(form, "fecha"),
            campo(form, "tope"),
            campo(form, "repetir"),
            campo(form, "espera"),
            pedida,
            datetime.now(UTC),
        )

    async def ver_grabar(peticion: Request) -> Response:
        return await formulario_grabar(peticion)

    async def grabar(peticion: Request) -> Response:
        """«Grabar ahora» (`pedir`, con título y tope) o «Programar» (la función `programar` de la base, V3)."""
        form = await formulario(peticion)
        quien = peticion.headers[CABECERA_USUARIO]
        cuando = campo(form, "cuando") or "ahora"  # el formulario de F2, sin «cuándo», graba ahora
        try:
            if cuando not in ("ahora", "programar"):
                raise FormularioNoValido("elige si se graba ahora o se programa")
            pedida, sala = await validar_formulario(form)
            if cuando == "programar":
                rid = await en_hilo(repo.programar, programacion_de(form, pedida, sala), quien)
            else:
                titulo = planificador.titulo(campo(form, "titulo"))
                tope = planificador.tope(campo(form, "tope") or str(max(planificador.TOPES_MIN)))
                rid = await en_hilo(repo.pedir, pedida, quien, sala, titulo, tope)
        except ConformidadNoValida as e:
            return await formulario_grabar(peticion, str(e), 400, valores(form))
        except psycopg.errors.CheckViolation:  # la hora pasó entre la comprobación y la base
            return await formulario_grabar(peticion, "la base no lo admite: revisa la hora", 400, valores(form))
        return RedirectResponse(f"/reuniones/{rid}", status_code=303)

    # ── Programación, papelera (V3) ───────────────────────────────────────────────────────────────────────────────────

    async def reunion_o_404(peticion: Request) -> tuple[str, dict[str, Any], list[tuple[str, str]]]:
        rid = peticion.path_params["rid"]
        if not es_uuid(rid):
            raise HTTPException(404)
        try:
            r, conformidades, _segmentos = await en_hilo(repo.detalle, rid)
        except KeyError:
            raise HTTPException(404) from None
        return rid, r, conformidades

    async def ver_programacion(peticion: Request) -> Response:
        nombres_sala = {s["id"]: s["nombre"] for s in await en_hilo(repo.salas)}
        programadas = [
            {
                "id": r["id"],
                "nombre": _nombre(r),
                "cuando": _madrid(r["programada_para"]),
                "sala": nombres_sala.get(r.get("sala_id"), "sin sala"),
                "conformes": r["conformes"],
                "total": len(r["socios"]),
                "repetir": REPETIR.get(r["repetir"], r["repetir"]),
            }
            for r in await en_hilo(repo.programadas)
        ]
        return pagina(peticion, "programacion.html", {"programadas": programadas})

    async def formulario_modificar(
        peticion: Request,
        rid: str,
        r: Mapping[str, Any],
        v: Mapping[str, Any],
        error: str = "",
        estado: int = 200,
    ) -> Response:
        activos = [(s["push"], s["nombre"]) for s in await en_hilo(repo.socios) if s["activo"]]
        contexto = {
            "rid": rid,
            "nombre": _nombre(r),
            "socios": activos,
            "salas": await en_hilo(repo.salas),
            "version": vigente,
            "v": v,
            "error": error,
            "topes": planificador.TOPES_MIN,
            "esperas": planificador.ESPERAS_MIN,
        }
        return pagina(peticion, "modificar.html", contexto, estado)

    async def ver_modificar(peticion: Request) -> Response:
        rid, r, conformidades = await reunion_o_404(peticion)
        if r["estado"] != Estado.PROGRAMADA:
            return mensaje(peticion, NO_PROGRAMADA, 409)
        v = {
            "titulo": r.get("titulo") or "",
            "fecha": r["programada_para"].astimezone(planificador.MADRID).strftime("%Y-%m-%dT%H:%M"),
            "tope": str(r["tope_min"]),
            "repetir": r["repetir"],
            "espera": str(r["espera_min"]),
            "sala": r.get("sala_id") or "",
            # Marcados, solo los que ya dieron su conformidad para esta reunión con el texto vigente: en una repetición, nadie.
            "socios": tuple(s for s, version in conformidades if version == vigente),
        }
        return await formulario_modificar(peticion, rid, r, v)

    async def modificar(peticion: Request) -> Response:
        """@a49: por la función `modificar_programada`, que solo cambia una reunión aún programada."""
        rid, r, _ = await reunion_o_404(peticion)
        form = await formulario(peticion)
        if r["estado"] != Estado.PROGRAMADA:
            return mensaje(peticion, NO_PROGRAMADA, 409)
        try:
            pedida, sala = await validar_formulario(form)
            hecho = await en_hilo(
                repo.modificar_programada, rid, programacion_de(form, pedida, sala), peticion.headers[CABECERA_USUARIO]
            )
        except ConformidadNoValida as e:
            return await formulario_modificar(peticion, rid, r, valores(form), str(e), 400)
        except psycopg.errors.CheckViolation:
            return await formulario_modificar(peticion, rid, r, valores(form), "la base no lo admite: revisa la hora", 400)
        if hecho is None:
            raise HTTPException(404)
        if not hecho:
            return mensaje(peticion, NO_PROGRAMADA, 409)
        return RedirectResponse(f"/reuniones/{rid}", status_code=303)

    async def ver_cancelar(peticion: Request) -> Response:
        rid, r, _ = await reunion_o_404(peticion)
        if r["estado"] != Estado.PROGRAMADA:
            return mensaje(peticion, "Solo se cancela una reunión programada.", 409)
        repite = REPETIR[r["repetir"]] if r.get("repetir") in ("semanal", "mensual") else None
        contexto = {"rid": rid, "nombre": _nombre(r), "cuando": _madrid(r["programada_para"]), "repite": repite}
        return pagina(peticion, "cancelar.html", contexto)

    async def cancelar(peticion: Request) -> Response:
        """@a50: por la función `cancelar_reunion`; no borra nada. `serie=1`: tampoco se programa la siguiente."""
        rid = peticion.path_params["rid"]
        if not es_uuid(rid):
            raise HTTPException(404)
        serie = {"0": False, "1": True}.get(campo(await formulario(peticion), "serie"))
        if serie is None:
            return mensaje(peticion, "Petición no válida.", 400)
        hecho = await en_hilo(repo.cancelar, rid, peticion.headers[CABECERA_USUARIO], serie)
        if hecho is None:
            raise HTTPException(404)
        if not hecho:
            return mensaje(peticion, "Solo se cancela una reunión programada.", 409)
        return RedirectResponse(f"/reuniones/{rid}", status_code=303)

    async def pagina_eliminar(peticion: Request, rid: str, r: Mapping[str, Any], error: str = "", estado: int = 200) -> Response:
        contexto = {"rid": rid, "nombre": _nombre(r), "confirmacion": _confirmacion(r), "error": error}
        return pagina(peticion, "eliminar.html", contexto, estado)

    def eliminable(r: Mapping[str, Any]) -> bool:
        return r["estado"] in ESTADOS_FINALES and r.get("papelera_en") is None

    async def ver_eliminar(peticion: Request) -> Response:
        rid, r, _ = await reunion_o_404(peticion)
        if not eliminable(r):
            return mensaje(peticion, NO_ELIMINABLE, 409)
        return await pagina_eliminar(peticion, rid, r)

    async def eliminar(peticion: Request) -> Response:
        """@a51: a la papelera (función `a_papelera`) si se escribe bien su título; la purga la borra a los 7 días."""
        rid, r, _ = await reunion_o_404(peticion)
        form = await formulario(peticion)
        if not eliminable(r):
            return mensaje(peticion, NO_ELIMINABLE, 409)
        if campo(form, "confirmacion").strip() != _confirmacion(r):
            return await pagina_eliminar(peticion, rid, r, "lo escrito no coincide", 400)
        hecho = await en_hilo(repo.a_papelera, rid, peticion.headers[CABECERA_USUARIO])
        if hecho is None:
            raise HTTPException(404)
        if not hecho:
            return mensaje(peticion, NO_ELIMINABLE, 409)
        return RedirectResponse("/papelera", status_code=303)

    async def ver_papelera(peticion: Request) -> Response:
        reuniones = [
            {
                "id": r["id"],
                "nombre": _nombre(r),
                "estado": r["estado"],
                "eliminada": _madrid(r["papelera_en"]),
                "por": r["papelera_por"],
                "borrado": _madrid(r["borrado_en"]),
            }
            for r in await en_hilo(repo.papelera)
        ]
        return pagina(peticion, "papelera.html", {"reuniones": reuniones})

    async def recuperar(peticion: Request) -> Response:
        rid = peticion.path_params["rid"]
        if not es_uuid(rid):
            raise HTTPException(404)
        hecho = await en_hilo(repo.recuperar, rid, peticion.headers[CABECERA_USUARIO])
        if hecho is None:
            raise HTTPException(404)
        if not hecho:
            return mensaje(peticion, "Esa reunión no está en la papelera.", 409)
        return RedirectResponse(f"/reuniones/{rid}", status_code=303)

    # ── Salas y socios (V2) ───────────────────────────────────────────────────────────────────────────────────────────

    async def ver_salas(peticion: Request, error: str = "", estado: int = 200) -> Response:
        contexto = {"salas": await en_hilo(repo.salas), "socios": await en_hilo(repo.socios), "error": error}
        return pagina(peticion, "salas.html", contexto, estado)

    async def sala_nueva(peticion: Request, error: str = "", estado: int = 200) -> Response:
        return pagina(peticion, "sala_nueva.html", {"error": error}, estado)

    async def crear_sala(peticion: Request) -> Response:
        """@a43: tras confirmar en /salas/nueva. La contraseña en claro solo vive en esta petición."""
        form = await formulario(peticion)
        try:
            nombre = salas.nombre_de_sala(campo(form, "nombre"))
        except salas.SalaNoValida as e:
            return await sala_nueva(peticion, str(e), 400)
        room, clave = salas.nuevo_room(), salas.nueva_clave()
        cifrada = salas.cifrar(maestra, room, clave)
        try:
            sid = await en_hilo(
                repo.crear_sala, nombre, room, enlaces.hash_sala(clave), cifrada, peticion.headers[CABECERA_USUARIO]
            )
        except psycopg.errors.UniqueViolation as e:
            if e.diag.constraint_name != "salas_nombre_key":
                raise  # el room repetido (36^16 posibles): 500 y Pablo lo vuelve a intentar
            return await sala_nueva(peticion, "Ya hay una sala con ese nombre", 400)
        return RedirectResponse(f"/salas/{sid}", status_code=303)

    async def sala_o_404(peticion: Request) -> dict[str, Any]:
        sid = peticion.path_params["sid"]
        if not es_uuid(sid):
            raise HTTPException(404)
        try:
            sala: dict[str, Any] = await en_hilo(repo.sala, sid)
        except KeyError:
            raise HTTPException(404) from None
        return sala

    async def una_sala(peticion: Request, sala: dict[str, Any], clave: str | None = None) -> Response:
        sid = sala["id"]
        activos = [s for s in await en_hilo(repo.socios) if s["activo"]]
        contexto = {
            "sala": sala,
            "creada": sala["creada_en"].strftime("%Y-%m-%d %H:%M"),
            # @a44: sin la contraseña; el `hash` se guardó al crear la sala (el mismo de enlaces.hash_sala).
            "enlaces": [(s["nombre"], enlaces.enlace(sala["room"], sala["hash"], s["push"], s["nombre"])) for s in activos],
            "eventos": [
                (EVENTOS_SALA.get(e["tipo"], e["tipo"]), e["usuario"], e["momento"].strftime("%Y-%m-%d %H:%M"))
                for e in await en_hilo(repo.eventos_de_sala, sid)
            ],
            "clave": clave,
        }
        return pagina(peticion, "sala.html", contexto)

    async def ver_sala(peticion: Request) -> Response:
        return await una_sala(peticion, await sala_o_404(peticion))

    async def confirmar_clave(peticion: Request) -> Response:
        return pagina(peticion, "sala_clave.html", {"sala": await sala_o_404(peticion)})

    async def mostrar_clave(peticion: Request) -> Response:
        """@a45: la base anota `clave_vista` (quién y cuándo) en la misma transacción en la que da el valor cifrado."""
        sala = await sala_o_404(peticion)
        cifrada = await en_hilo(repo.ver_clave, sala["id"], peticion.headers[CABECERA_USUARIO])
        if cifrada is None:
            raise HTTPException(404)
        try:
            clave = salas.descifrar(maestra, sala["room"], cifrada)
        except salas.ClaveNoValida:
            return mensaje(peticion, "La contraseña de esta sala no se puede descifrar con la clave del panel.", 500)
        return await una_sala(peticion, sala, clave)

    async def alta_socio(peticion: Request) -> Response:
        form = await formulario(peticion)
        try:
            socio = validar_socio(campo(form, "push"), campo(form, "nombre"), campo(form, "correo"))
            await en_hilo(repo.alta_socio, socio)
        except FormularioNoValido as e:
            return await ver_salas(peticion, str(e), 400)
        except psycopg.errors.UniqueViolation:
            return await ver_salas(peticion, "Ya hay un socio con ese identificador", 400)
        return RedirectResponse("/salas#socios", status_code=303)

    async def socio_activo(peticion: Request) -> Response:
        form = await formulario(peticion)
        activo = {"1": True, "0": False}.get(campo(form, "activo"))
        if activo is None:
            return await ver_salas(peticion, "petición no válida", 400)
        if not await en_hilo(repo.socio_activo, peticion.path_params["push"], activo):
            raise HTTPException(404)
        return RedirectResponse("/salas#socios", status_code=303)

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
        Route("/reuniones/{rid}/reintentar", reintentar, methods=["POST"]),
        Route("/reuniones/{rid}/compartir", ver_compartir, methods=["GET"]),
        Route("/reuniones/{rid}/transcripcion.txt", transcripcion_txt, methods=["GET"]),
        Route("/reuniones/{rid}/modificar", ver_modificar, methods=["GET"]),
        Route("/reuniones/{rid}/modificar", modificar, methods=["POST"]),
        Route("/reuniones/{rid}/cancelar", ver_cancelar, methods=["GET"]),
        Route("/reuniones/{rid}/cancelar", cancelar, methods=["POST"]),
        Route("/reuniones/{rid}/eliminar", ver_eliminar, methods=["GET"]),
        Route("/reuniones/{rid}/eliminar", eliminar, methods=["POST"]),
        Route("/reuniones/{rid}/recuperar", recuperar, methods=["POST"]),
        Route("/programacion", ver_programacion),
        Route("/papelera", ver_papelera),
        Route("/buscar", buscar),
        Route("/grabar", ver_grabar, methods=["GET"]),
        Route("/grabar", grabar, methods=["POST"]),
        Route("/salas", ver_salas, methods=["GET"]),
        Route("/salas", crear_sala, methods=["POST"]),
        Route("/salas/nueva", sala_nueva, methods=["GET"]),
        Route("/salas/{sid}", ver_sala, methods=["GET"]),
        Route("/salas/{sid}/clave", confirmar_clave, methods=["GET"]),
        Route("/salas/{sid}/clave", mostrar_clave, methods=["POST"]),
        Route("/socios", alta_socio, methods=["POST"]),
        Route("/socios/{push}/activo", socio_activo, methods=["POST"]),
        Route("/parar", parar, methods=["POST"]),
    ]
    # Starlette 1.7.0, docs/requests.md: «To limit the complete request body [...] configure `max_body_size` on the
    # application» (RequestBodyLimitMiddleware: 413, cuente Content-Length o los trozos que lleguen).
    app = Starlette(debug=False, routes=rutas, max_body_size=TOPE_CUERPO, exception_handlers={404: no_existe})
    return _Guardia(app, origen, secreto, registro, concurrencia)
