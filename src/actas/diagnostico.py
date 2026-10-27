"""Diagnóstico de una reunión en error en lenguaje claro (@a56; ADR 0023 de KubernetesInfrastructure, decisión 7): qué pasó, qué
hacer y si «Reintentar» (@a57) puede arreglarlo; y cada evento del historial en una línea.

Cubre todos los motivos que anota el supervisor (supervisor.py y sondeo.py). Uno que no conoce no se explica: se dice tal cual y
se manda a los registros de la consola. Reintentar solo vuelve a enviar el audio que se conserva, así que no se ofrece cuando el
error es anterior a la grabación (`conformidad`, `sala`, `grabador`) ni cuando el audio mismo es el problema (`pistas`).
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from actas.presentacion import SIN_DATO, hhmmss
from actas.sondeo import PLAZO_S

LATIDO_MAX_S = 30  # @a56: el supervisor da una vuelta cada 5 s; más de 30 s sin latido es que no está vivo
_MIB = 1 << 20


@dataclass(frozen=True)
class Diagnostico:
    titulo: str
    que_paso: str
    que_hacer: str
    reintentable: bool


_PLAZO = f"{PLAZO_S // 3600} h"
_CONSOLA = "Si se repite, mira los registros del supervisor en la consola."
_REINTENTAR = "Pulsa «Reintentar» mientras el audio se conserve (como mucho 7 días desde la grabación)."
_SIN_AUDIO = "No hay audio que reenviar: «Reintentar» no sirve."

_CAUSAS_PISTAS = {
    "ninguna_pista": "En la carpeta de la reunión no había ninguna pista de audio.",
    "partida": "VDO.Ninja partió una grabación en trozos y el supervisor no sabe colocarlos en el tiempo.",
    "no_grabacion": "En la carpeta de la reunión había un fichero que no es una grabación de VDO.Ninja.",
    "no_conforme": "Había una pista de alguien que no es un socio conforme de esta reunión, así que no se envía nada.",
    "demasiadas": "Había más de 16 pistas, el máximo que admite transcribir.",
    "fichero": "Alguna pista no es un fichero normal con audio (vacía, un enlace u otro tipo de fichero).",
    "directorio": "La carpeta de la reunión no es una carpeta normal del supervisor.",
}

_FIJOS = {
    "conformidad": Diagnostico(
        "No se grabó: faltaba alguna conformidad",
        "Al ir a grabar, el supervisor comprobó que algún socio no tenía su conformidad con el texto informativo de esta "
        "reunión, así que no grabó a nadie.",
        "Vuelve a pedir la grabación desde «Grabar», marcando solo a los socios conformes. En una reunión programada (y en "
        "cada repetición de una serie, que nace sin conformidades), márcalas en «Modificar» antes de su hora. " + _SIN_AUDIO,
        False,
    ),
    "no_empezo": Diagnostico(
        "No se grabó: no pudo empezar a su hora",
        "Llegó su hora, pero en su espera el supervisor no pudo empezar: otra grabación seguía en marcha o el supervisor "
        "estuvo parado. Pasada la espera ya no se graba.",
        "Si la reunión sigue en marcha, pide la grabación desde «Grabar». Mira abajo si el supervisor da señales de vida. "
        + _SIN_AUDIO,
        False,
    ),
    "grabador": Diagnostico(
        "No se pudo empezar a grabar",
        "Chromium no respondió al abrir las páginas de la sala, así que no se grabó nada.",
        "Mira abajo si Chromium responde. Cuando responda, vuelve a pedir la grabación desde «Grabar». " + _SIN_AUDIO,
        False,
    ),
    "sala": Diagnostico(
        "No se grabó: la reunión no tiene una sala que se pueda usar",
        "Al ir a grabar, el supervisor no encontró la sala de la reunión o no pudo descifrar su contraseña, así que no grabó a "
        "nadie.",
        "Vuelve a pedir la grabación desde «Grabar» eligiendo una sala. Si vuelve a pasar con una sala que existe, la clave de "
        "las salas del supervisor no es la del panel: es tarea del operador. " + _SIN_AUDIO,
        False,
    ),
    "plazo_envio": Diagnostico(
        "La grabación terminó, pero no se pudo enviar a transcribir",
        f"El supervisor intentó subir las pistas durante {_PLAZO} y transcribir no las aceptó.",
        "Comprueba abajo que transcribir responde. " + _REINTENTAR,
        True,
    ),
    "plazo": Diagnostico(
        "Transcribir no terminó a tiempo",
        f"Las pistas se enviaron, pero transcribir no dio el texto en {_PLAZO}.",
        "Comprueba en transcribir si el trabajo sigue en cola. " + _REINTENTAR,
        True,
    ),
    "transcripcion": Diagnostico(
        "La transcripción llegó con una forma que el supervisor no acepta",
        "Transcribir terminó, pero su respuesta no casa con los socios de la reunión o no tiene la forma esperada.",
        _REINTENTAR + " " + _CONSOLA,
        True,
    ),
    "interno": Diagnostico(
        "Fallo inesperado del supervisor",
        "El supervisor tuvo un fallo que no esperaba con esta reunión y la apartó para no bloquear las demás.",
        _REINTENTAR + " " + _CONSOLA,
        True,
    ),
    "token": Diagnostico(
        "Transcribir no reconoce al supervisor",
        "Transcribir rechazó el token de servicio del supervisor (HTTP 401): no vale, caducó o se cambió.",
        "Renovar el token es tarea del operador (Secret del supervisor). Después, " + _REINTENTAR[0].lower() + _REINTENTAR[1:],
        True,
    ),
    "respuesta_sin_id": Diagnostico(
        "Transcribir respondió algo que el supervisor no entiende",
        "Transcribir aceptó el envío, pero su respuesta no traía el número del trabajo.",
        _REINTENTAR + " " + _CONSOLA,
        True,
    ),
    "respuesta_no_valida": Diagnostico(
        "Transcribir respondió algo que el supervisor no entiende",
        "Al consultar el trabajo, la respuesta de transcribir no tenía la forma esperada.",
        _REINTENTAR + " " + _CONSOLA,
        True,
    ),
    "estado_desconocido": Diagnostico(
        "Transcribir respondió algo que el supervisor no entiende",
        "Transcribir devolvió un estado del trabajo que el supervisor no conoce.",
        _REINTENTAR + " " + _CONSOLA,
        True,
    ),
    "listo_sin_texto": Diagnostico(
        "Transcribir terminó sin texto",
        "Transcribir dio el trabajo por terminado, pero sin la transcripción.",
        _REINTENTAR + " " + _CONSOLA,
        True,
    ),
    "trabajo_no_encontrado": Diagnostico(
        "Transcribir ya no tiene el trabajo",
        "Al consultar el trabajo, transcribir respondió que no existe (HTTP 404).",
        "«Reintentar» lo vuelve a enviar. " + _REINTENTAR,
        True,
    ),
    "plataforma_error": Diagnostico(
        "Transcribir falló al transcribir",
        "Transcribir aceptó las pistas, pero su trabajo terminó en error.",
        "Mira el trabajo en transcribir. " + _REINTENTAR,
        True,
    ),
    "plataforma_cancelado": Diagnostico(
        "El trabajo se canceló en transcribir",
        "Alguien canceló el trabajo de esta reunión en transcribir.",
        "Si quieres el texto, " + _REINTENTAR[0].lower() + _REINTENTAR[1:],
        True,
    ),
    "plataforma": Diagnostico(
        "Transcribir dio un error",
        "Transcribir respondió con un error sin más detalle.",
        _REINTENTAR + " " + _CONSOLA,
        True,
    ),
}


def segundos(s: float | None) -> str:
    """Como `presentacion.duracion` (segundos enteros, sin redondear): la ficha no dice 6 s arriba y 00:00:05 al lado."""
    if s is None:
        return SIN_DATO
    if s < 60:
        return f"{int(s)} s"
    return hhmmss(int(s * 1000))


def diagnosticar(
    motivo: str | None,
    *,
    duracion_s: float | None = None,
    parada_s: float | None = None,
    causa: str | None = None,
    con_historial: bool = True,
) -> Diagnostico:
    """`duracion_s`: lo que duró la grabación; `parada_s`: cuándo se pidió parar, desde el inicio; `causa`: la de un error de
    pistas, del evento del cambio a error; `con_historial`: si la reunión tiene eventos (las anteriores a V4 no los tienen)."""
    if motivo is None:
        return Diagnostico("Error sin motivo anotado", "El supervisor no anotó por qué.", _CONSOLA, False)
    if motivo == "pistas":
        return _pistas(duracion_s, parada_s, causa, con_historial)
    if motivo.startswith("rechazada_"):
        codigo = motivo.removeprefix("rechazada_")
        return Diagnostico(
            "Transcribir rechazó el envío",
            f"Transcribir respondió con un error de la petición (HTTP {codigo}).",
            _REINTENTAR + " " + _CONSOLA,
            True,
        )
    fijo = _FIJOS.get(motivo)
    if fijo is not None:
        return fijo
    return Diagnostico(
        f"Error «{motivo}»",
        "Este motivo no tiene explicación en el panel.",
        "Mira los registros del supervisor en la consola.",
        False,
    )


def _pistas(duracion_s: float | None, parada_s: float | None, causa: str | None, con_historial: bool) -> Diagnostico:
    partes = []
    if duracion_s is not None:
        partes.append(f"La grabación duró {segundos(duracion_s)}")
        if parada_s is not None:
            partes[-1] += f" y la parada se pidió a los {segundos(parada_s)} de empezar"
        partes[-1] += "."
    if causa in _CAUSAS_PISTAS:
        partes.append(_CAUSAS_PISTAS[causa])
    elif not con_historial:
        partes.append(
            "Esta reunión es anterior al historial de eventos, así que no consta qué falló en las pistas: solo que no se "
            "pudieron enviar."
        )
    else:
        partes.append("Las pistas no se pudieron enviar tal cual.")
    corta = duracion_s is not None and duracion_s < 60
    que_hacer = "Reintentar no lo arregla: volvería a encontrar las mismas pistas. "
    que_hacer += "Si fue una prueba, no hace falta hacer nada. " if corta else ""
    que_hacer += "Si era una reunión de verdad, mira los registros del supervisor en la consola y vuelve a grabar."
    titulo = "La grabación terminó, pero sus pistas no se pueden enviar a transcribir"
    return Diagnostico(titulo, " ".join(partes), que_hacer, False)


# ── Historial ───────────────────────────────────────────────────────────────────────────────────────────────────────────

_PARADAS = {
    "pedida": "Grabación parada a petición",
    "tope_3h": "Parada por el tope de 3 h",
    "tope": "Parada al llegar a su tope",
    "grabador_caido": "Parada porque Chromium dejó de responder",
    "terminado": "Parada porque el supervisor se reinició",
    "reinicio_supervisor": "Recuperada tras un reinicio del supervisor",
    "sin_grabador": "Recuperada sin grabador",
}


def _http(codigo: Any) -> str:
    return "sin respuesta" if codigo == 0 else f"HTTP {codigo}"


def linea_evento(tipo: str, d: Mapping[str, Any]) -> tuple[str, str]:
    """(texto, nivel) de un evento: nivel `ok`, `aviso`, `error` o `info` (el glifo y el color de la línea)."""
    if tipo == "estado":
        return _linea_estado(d)
    if tipo in ("envio", "consulta"):
        que = "Envío a transcribir" if tipo == "envio" else "Consulta a transcribir"
        if d.get("accion") == "error":
            que_paso = "Transcribir rechazó el envío" if tipo == "envio" else "Transcribir devolvió un error"
            return f"{que_paso} · {d.get('motivo') or _http(d.get('codigo'))}", "error"
        if d.get("codigo") in (200, 201):
            return "Transcribir aceptó el envío", "ok"
        intento = f" · intento {int(d['intento']) + 1}" if isinstance(d.get("intento"), int) else ""
        return f"{que} {_http(d.get('codigo'))}, se reintenta{intento}", "aviso"
    if tipo == "aviso":
        n = d.get("faltan") or 0
        if not n:
            return "Ya publican todos los socios conformes", "ok"
        return (f"{n} socio conforme no publica" if n == 1 else f"{n} socios conformes no publican") + " en la sala", "aviso"
    if tipo == "audio_borrado":
        return f"Audio borrado ({d.get('motivo')}) · {d.get('ficheros')} ficheros", "info"
    if tipo == "modificada":
        return f"Modificada por {d.get('usuario') or 'alguien'}", "info"
    if tipo == "papelera":
        por = d.get("usuario") or "alguien"
        if d.get("accion") == "recuperada":
            return f"Recuperada de la papelera por {por}", "ok"
        return f"A la papelera por {por}: se borra a los 7 días", "aviso"
    if tipo == "reintento":
        por = d.get("usuario") or "alguien"
        if d.get("resultado") == "reenviada":
            return f"Reintento pedido por {por}: se vuelve a enviar", "ok"
        if d.get("resultado") == "interno":
            return f"Reintento pedido por {por}: el supervisor falló al atenderlo (mira la consola)", "error"
        if d.get("resultado") == "ninguna_pista":
            return f"Reintento pedido por {por}: no queda audio que enviar", "error"
        return f"Reintento pedido por {por}: las pistas siguen sin poder enviarse ({d.get('resultado')})", "error"
    return tipo, "info"


def _linea_estado(d: Mapping[str, Any]) -> tuple[str, str]:
    desde, hasta, motivo = d.get("desde"), d.get("hasta"), d.get("motivo")
    if hasta == "grabando":
        texto = "Empezó a grabar a su hora" if desde == "programada" else "Empezó a grabar"
        return f"{texto} · {d.get('socios')} socios" if d.get("socios") else texto, "ok"
    if hasta == "cancelada":
        if motivo == "nadie_entro":
            return "Cancelada: no entró ningún socio conforme en su espera (el audio se borra)", "aviso"
        texto = f"Cancelada por {d.get('usuario') or 'alguien'}"
        return texto + (", con las siguientes de la serie" if d.get("accion") == "serie" else ""), "info"
    if desde == "grabando" and hasta == "grabada":
        texto = _PARADAS.get(str(motivo), f"Grabación parada ({motivo})")
        if d.get("completas") is False:
            return texto + " · alguna descarga no terminó", "aviso"
        return texto, "ok" if motivo in ("pedida", None) else "aviso"
    if hasta == "transcribiendo":
        return f"Enviada a transcribir · {d.get('pistas')} pistas" if d.get("pistas") else "Enviada a transcribir", "ok"
    if hasta == "transcrita":
        return f"Transcrita · {d.get('segmentos')} segmentos" if d.get("segmentos") is not None else "Transcrita", "ok"
    if hasta == "error":
        causa = d.get("causa")
        texto = f"Pasó a error ({motivo})"
        if causa:
            texto += " · " + _CAUSAS_PISTAS.get(str(causa), str(causa)).rstrip(".").lower()
        return texto, "error"
    if desde == "error" and hasta == "grabada":
        return "Se vuelve a enviar (reintento)", "ok"
    return f"{desde} → {hasta}", "info"


# ── Comprobaciones ──────────────────────────────────────────────────────────────────────────────────────────────────────


def comprobaciones(latido: Mapping[str, Any] | None, hace_s: float | None, fallos_1h: int) -> list[tuple[str, str]]:
    """(texto, nivel) de cada comprobación (@a56): latido, Chromium, transcribir, espacio del tmpfs y versiones."""
    if latido is None or hace_s is None:
        return [("Supervisor sin latido: aún no ha escrito ninguno", "error")]
    salida = []
    vivo = hace_s < LATIDO_MAX_S
    if vivo:
        salida.append((f"Supervisor vivo · última vuelta hace {segundos(hace_s)}", "ok"))
    else:
        salida.append((f"Supervisor sin latido reciente · hace {segundos(hace_s)}", "error"))
    chromium = latido.get("chromium")
    salida.append((f"Chromium responde · {chromium}", "ok") if chromium else ("Chromium no responde", "error"))
    codigo = latido.get("transcribir_codigo")
    if codigo is None:
        ultima = ""
    else:
        ultima = " · el último intento no tuvo respuesta" if codigo == 0 else f" · última respuesta HTTP {codigo}"
    if fallos_1h:
        fallos = "1 fallo" if fallos_1h == 1 else f"{fallos_1h} fallos"
        salida.append((f"Transcribir · {fallos} en la última hora{ultima}", "aviso"))
    elif codigo is None:
        salida.append(("Transcribir · sin envíos ni consultas desde que arrancó el supervisor", "info"))
    else:
        salida.append((f"Transcribir responde{ultima}", "ok" if codigo in (200, 201) else "aviso"))
    usados, total = latido.get("grabaciones_bytes"), latido.get("grabaciones_total")
    if usados is not None and total:
        pct = round(100 * usados / total)
        texto = f"Espacio de grabación · {round(usados / _MIB)} MiB de {round(total / _MIB)} MiB ({pct} %)"
        salida.append((texto, "ok" if pct < 80 else "aviso"))
    elif usados is not None:
        salida.append((f"Espacio de grabación · {round(usados / _MIB)} MiB usados", "info"))
    versiones = f"Imagen {latido.get('imagen') or 'sin versión anotada'}"
    salida.append((versiones + (f" · Chromium {chromium}" if chromium else ""), "info"))
    if vivo:
        return salida
    # Sin latido reciente, lo demás es de la última vuelta: ni verde ni rojo, y dicho.
    return salida[:1] + [(f"{texto} · dato del último latido", "info") for texto, _ in salida[1:]]
