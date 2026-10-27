"""@a56 (textos): cada motivo de error en lenguaje claro, con «qué hacer» y si «Reintentar» tiene sentido; y cada evento del
historial en una línea legible."""

import pytest

from actas.diagnostico import Diagnostico, comprobaciones, diagnosticar, linea_evento, segundos

# Todo lo que el supervisor puede anotar como motivo de error: los de supervisor.py y los de sondeo.py.
MOTIVOS = [
    "conformidad",
    "sala",
    "grabador",
    "pistas",
    "plazo_envio",
    "plazo",
    "transcripcion",
    "interno",
    "token",
    "rechazada_400",
    "rechazada_422",
    "respuesta_sin_id",
    "trabajo_no_encontrado",
    "respuesta_no_valida",
    "listo_sin_texto",
    "plataforma_error",
    "plataforma_cancelado",
    "estado_desconocido",
    "plataforma",
    "no_empezo",  # V3: una programada que pasada su espera no pudo empezar
]
REINTENTABLES = set(MOTIVOS) - {"conformidad", "sala", "grabador", "pistas", "no_empezo"}


@pytest.mark.parametrize("motivo", MOTIVOS)
def test_cada_motivo_tiene_titulo_que_paso_y_que_hacer_sin_jerga(motivo):
    d = diagnosticar(motivo)
    assert isinstance(d, Diagnostico)
    assert d.titulo and d.que_paso and d.que_hacer
    # Lenguaje claro: ningún código (`plazo_envio`, `rechazada_400`…) en la explicación.
    assert "_" not in d.titulo + d.que_paso + d.que_hacer


@pytest.mark.parametrize("motivo", MOTIVOS)
def test_reintentar_solo_donde_reenviar_el_audio_puede_arreglarlo(motivo):
    assert diagnosticar(motivo).reintentable == (motivo in REINTENTABLES)


def test_un_motivo_desconocido_no_se_inventa_una_causa():
    d = diagnosticar("algo_nuevo")
    assert not d.reintentable
    assert "algo_nuevo" in d.titulo
    assert "consola" in d.que_hacer


def test_sin_motivo():
    assert diagnosticar(None).titulo


def test_el_caso_real_17d9d6ae_pistas_6_s_sin_historial():
    """La reunión de producción en `error: pistas`: 5,87 s grabando, parada pedida a los 3,58 s, anterior al historial."""
    d = diagnosticar("pistas", duracion_s=5.87, parada_s=3.58, causa=None, con_historial=False)
    assert not d.reintentable
    assert "duró 5 s" in d.que_paso and "a los 3 s" in d.que_paso
    assert "anterior al historial" in d.que_paso
    assert "Reintentar no" in d.que_hacer
    assert "prueba" in d.que_hacer and "consola" in d.que_hacer


@pytest.mark.parametrize(
    ("causa", "frase"),
    [
        ("ninguna_pista", "ninguna pista"),
        ("partida", "trozos"),
        ("no_grabacion", "no es una grabación"),
        ("no_conforme", "no es un socio conforme"),
        ("demasiadas", "16"),
        ("fichero", "fichero normal"),
        ("directorio", "carpeta"),
    ],
)
def test_pistas_con_su_causa(causa, frase):
    d = diagnosticar("pistas", duracion_s=600, causa=causa)
    assert frase in d.que_paso
    assert "anterior al historial" not in d.que_paso


def test_plazo_envio_dice_el_plazo_real_y_que_reintentar():
    d = diagnosticar("plazo_envio")
    assert "12 h" in d.que_paso and "Reintentar" in d.que_hacer and d.reintentable


def test_token_es_tarea_del_operador():
    assert "operador" in diagnosticar("token").que_hacer


@pytest.mark.parametrize(
    ("s", "texto"), [(0.4, "0 s"), (3.58, "3 s"), (59.9, "59 s"), (60, "00:01:00"), (65.7, "00:01:05"), (None, "—")]
)
def test_segundos(s, texto):
    assert segundos(s) == texto


# ── Historial ───────────────────────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("tipo", "detalle", "frase", "nivel"),
    [
        ("estado", {"desde": "pedida", "hasta": "grabando", "socios": 3}, "Empezó a grabar · 3 socios", "ok"),
        ("estado", {"desde": "grabando", "hasta": "grabada", "motivo": "pedida", "completas": True}, "parada a petición", "ok"),
        ("estado", {"desde": "grabando", "hasta": "grabada", "motivo": "tope_3h", "completas": False}, "descarga", "aviso"),
        ("estado", {"desde": "grabada", "hasta": "transcribiendo", "pistas": 3}, "3 pistas", "ok"),
        ("estado", {"desde": "transcribiendo", "hasta": "transcrita", "segmentos": 40}, "40 segmentos", "ok"),
        (
            "estado",
            {"desde": "grabada", "hasta": "error", "motivo": "pistas", "causa": "ninguna_pista"},
            "ninguna pista",
            "error",
        ),
        ("estado", {"desde": "error", "hasta": "grabada", "motivo": "reintento"}, "Se vuelve a enviar", "ok"),
        ("envio", {"codigo": 503, "accion": "reintentar", "intento": 1}, "HTTP 503", "aviso"),
        ("envio", {"codigo": 0, "accion": "reintentar", "intento": 0}, "sin respuesta", "aviso"),
        ("envio", {"codigo": 201, "accion": "seguir"}, "aceptó", "ok"),
        ("envio", {"codigo": 401, "accion": "error", "motivo": "token"}, "rechazó", "error"),
        ("consulta", {"codigo": 502, "accion": "seguir"}, "HTTP 502", "aviso"),
        ("consulta", {"codigo": 200, "accion": "error", "motivo": "plataforma_error"}, "error", "error"),
        ("aviso", {"faltan": 2}, "2 socios conformes no publican", "aviso"),
        ("aviso", {"faltan": 0}, "Ya publican", "ok"),
        ("audio_borrado", {"motivo": "transcrita", "ficheros": 3}, "Audio borrado", "info"),
        ("reintento", {"usuario": "pablo", "resultado": "reenviada"}, "pablo", "ok"),
        ("reintento", {"usuario": "pablo", "resultado": "ninguna_pista"}, "no queda audio", "error"),
        ("reintento", {"usuario": "pablo", "resultado": "interno"}, "falló al atenderlo", "error"),
        # V3: programadas, su tope, canceladas, cambios y papelera.
        ("estado", {"desde": "programada", "hasta": "grabando", "socios": 2}, "Empezó a grabar a su hora · 2 socios", "ok"),
        ("estado", {"desde": "grabando", "hasta": "grabada", "motivo": "tope", "completas": True}, "su tope", "aviso"),
        ("estado", {"desde": "programada", "hasta": "cancelada", "usuario": "pablo"}, "Cancelada por pablo", "info"),
        (
            "estado",
            {"desde": "programada", "hasta": "cancelada", "usuario": "pablo", "accion": "serie"},
            "Cancelada por pablo, con las siguientes de la serie",
            "info",
        ),
        (
            "estado",
            {"desde": "grabando", "hasta": "cancelada", "motivo": "nadie_entro"},
            "no entró ningún socio conforme",
            "aviso",
        ),
        ("estado", {"desde": "programada", "hasta": "error", "motivo": "no_empezo"}, "Pasó a error (no_empezo)", "error"),
        ("modificada", {"usuario": "pablo"}, "Modificada por pablo", "info"),
        ("papelera", {"accion": "eliminada", "usuario": "pablo"}, "A la papelera por pablo", "aviso"),
        ("papelera", {"accion": "recuperada", "usuario": "pablo"}, "Recuperada de la papelera por pablo", "ok"),
        ("audio_borrado", {"motivo": "nadie_entro", "ficheros": 2}, "Audio borrado", "info"),
    ],
)
def test_cada_evento_en_una_linea_legible(tipo, detalle, frase, nivel):
    texto, n = linea_evento(tipo, detalle)
    assert frase in texto
    assert n == nivel


def test_un_evento_desconocido_se_muestra_por_su_tipo():
    assert linea_evento("otro", {}) == ("otro", "info")


# ── Comprobaciones ──────────────────────────────────────────────────────────────────────────────────────────────────────

LATIDO = {
    "chromium": "HeadlessChrome/141.0.7390.37",
    "imagen": "sha-abc",
    "grabaciones_bytes": 700 << 20,
    "grabaciones_total": 768 << 20,
    "transcribir_codigo": 201,
}


def test_comprobaciones_en_verde():
    assert comprobaciones(LATIDO, 4.2, 0) == [
        ("Supervisor vivo · última vuelta hace 4 s", "ok"),
        ("Chromium responde · HeadlessChrome/141.0.7390.37", "ok"),
        ("Transcribir responde · última respuesta HTTP 201", "ok"),
        ("Espacio de grabación · 700 MiB de 768 MiB (91 %)", "aviso"),
        ("Imagen sha-abc · Chromium HeadlessChrome/141.0.7390.37", "info"),
    ]


@pytest.mark.parametrize(("hace_s", "nivel"), [(29.9, "ok"), (30.0, "error")])
def test_latido_de_menos_de_30_s(hace_s, nivel):
    assert comprobaciones(LATIDO, hace_s, 0)[0][1] == nivel


def test_sin_latido():
    assert comprobaciones(None, None, 0) == [("Supervisor sin latido: aún no ha escrito ninguno", "error")]


@pytest.mark.parametrize(
    ("codigo", "fallos", "linea"),
    [
        (None, 0, ("Transcribir · sin envíos ni consultas desde que arrancó el supervisor", "info")),
        (0, 1, ("Transcribir · 1 fallo en la última hora · el último intento no tuvo respuesta", "aviso")),
        (503, 0, ("Transcribir responde · última respuesta HTTP 503", "aviso")),
    ],
)
def test_comprobacion_de_transcribir(codigo, fallos, linea):
    assert comprobaciones({**LATIDO, "transcribir_codigo": codigo}, 1, fallos)[2] == linea


def test_con_el_latido_viejo_lo_demas_no_se_da_por_bueno():
    lineas = comprobaciones(LATIDO, 120, 0)
    assert lineas[0] == ("Supervisor sin latido reciente · hace 00:02:00", "error")
    assert all(n == "info" and t.endswith("· dato del último latido") for t, n in lineas[1:])


def test_no_empezo_explica_la_espera():
    d = diagnosticar("no_empezo")
    assert "espera" in d.que_paso and "Grabar" in d.que_hacer


def test_conformidad_en_una_programada_dice_donde_marcarla():
    assert "Modificar" in diagnosticar("conformidad").que_hacer
