"""@a60 (textos): «Copiar diagnóstico para Claude» (ADR 0023 de KubernetesInfrastructure, decisión 9, parte a). El bloque lleva
los eventos, el motivo y las versiones; los socios van como S1-S3 y los usuarios del panel como U1…, y no lleva contraseñas,
`hash`, enlaces ni texto de los segmentos: se construye con una lista blanca, no tachando."""

from datetime import datetime, timedelta

from actas.diagnostico import comprobaciones, diagnosticar
from actas.para_claude import bloque

T = datetime(2026, 10, 26, 18, 0)
IMAGEN = "sha-0123456789abcdef0123456789abcdef01234567"
CHROMIUM = "HeadlessChrome/141.0.7390.37"
NOMBRES = {"andres": "Andrés Gil", "pablo": "Pablo Hurtado", "roberto": "Roberto"}
REUNION = {
    "id": "17d9d6ae-0000-4000-8000-000000000017",
    "creado_en": T,
    "inicio": T + timedelta(seconds=5),
    "fin": T + timedelta(minutes=55),
    "parar_pedido_en": T + timedelta(minutes=54),
    "reintento_pedido_en": T + timedelta(hours=13),
    "reintento_pedido_por": "maria",
    "estado": "error",
    "motivo": "plazo_envio",
    "socios": ["andres", "pablo", "roberto"],
    "pedido_por": "pablo",
    "sala_id": "5a1a0000-0000-4000-8000-000000000001",
    "trabajo_id": "11111111-2222-4333-8444-555555555555",
}
EVENTOS = [
    {"momento": T + timedelta(seconds=5), "tipo": "estado", "detalle": {"desde": "pedida", "hasta": "grabando", "socios": 3}},
    {"momento": T + timedelta(minutes=55, seconds=6), "tipo": "envio", "detalle": {"codigo": 503, "accion": "reintentar"}},
    {
        "momento": T + timedelta(hours=12),
        "tipo": "estado",
        "detalle": {"desde": "grabada", "hasta": "error", "motivo": "plazo_envio"},
    },
    {"momento": T + timedelta(hours=12, minutes=1), "tipo": "reintento", "detalle": {"usuario": "pablo", "resultado": "interno"}},
]
LATIDO = {"chromium": CHROMIUM, "imagen": IMAGEN, "grabaciones_bytes": 1 << 20, "grabaciones_total": 768 << 20}


def _bloque(r=REUNION, eventos=EVENTOS):
    return bloque(
        r,
        [("andres", "v1"), ("pablo", "v1"), ("roberto", "v1")],
        eventos,
        diagnosticar(r["motivo"]),
        comprobaciones(LATIDO, 4.0, 1),
        NOMBRES,
    )


def test_lleva_el_motivo_el_diagnostico_los_eventos_y_las_versiones():
    b = _bloque()
    assert "plazo_envio" in b
    assert "La grabación terminó, pero no se pudo enviar a transcribir" in b
    assert "Qué hacer" in b
    assert "2026-10-26 18:00:05 · Empezó a grabar · 3 socios" in b
    assert "HTTP 503, se reintenta" in b
    assert "Pasó a error (plazo_envio)" in b
    assert IMAGEN in b and CHROMIUM in b
    assert "Transcribir · 1 fallo en la última hora" in b
    assert "17d9d6ae" in b


def test_los_socios_van_como_s1_s3_y_los_usuarios_como_u():
    b = _bloque()
    assert "Socios: S1, S2, S3" in b
    assert "S1 (texto v1), S2 (texto v1), S3 (texto v1)" in b
    assert "Pedida por U1" in b  # pablo
    assert "Reintento pedido por U1" in b  # el mismo usuario, el mismo seudónimo
    assert "Reintento pedido por U2: pendiente" in b  # maria
    for nombre in ["andres", "Andrés", "pablo", "Pablo", "Hurtado", "roberto", "Roberto", "maria"]:
        assert nombre.lower() not in b.lower(), nombre


def test_sin_sala_ni_enlaces_ni_identificadores_de_terceros():
    b = _bloque()
    assert REUNION["sala_id"] not in b and REUNION["trabajo_id"] not in b
    assert "http" not in b and "room" not in b and "hash" not in b


def test_un_nombre_que_se_colara_por_un_evento_se_cambia_igualmente():
    """La lista blanca de `eventos` no admite nombres, pero si alguno llegara en un código, sale con su seudónimo."""
    raro = [{"momento": T, "tipo": "estado", "detalle": {"desde": "pedida", "hasta": "error", "motivo": "roberto"}}]
    b = _bloque(eventos=raro)
    assert "roberto" not in b.lower()
    assert "Pasó a error (S3)" in b


def test_una_reunion_anterior_al_historial_lo_dice():
    b = _bloque(eventos=[])
    assert "sin eventos" in b
    assert "Empezó a grabar" in b  # por sus columnas


def test_cierra_con_la_pregunta_para_claude():
    assert _bloque().rstrip().endswith("¿Qué crees que pasó y qué harías?")


def test_un_usuario_con_nombre_de_palabra_comun_no_cambia_el_texto_fijo():
    r = {**REUNION, "pedido_por": "panel", "reintento_pedido_por": "actas"}
    b = _bloque(r=r)
    assert "usuarios del panel como U1" in b and "sistema de actas" in b
    assert "Pedida por U1" in b and "Reintento pedido por U2: pendiente" in b


def test_codigos_cortos_y_nombres_corrientes_no_estropean_el_texto():
    """Hallazgo de security_reviewer: con socios `a` («Error») y `s1` («Ana»), tachar en el texto daba «S2, S2» y «pistas S1
    una plataforma». Se comparan valores enteros, no se busca en la prosa."""
    r = {**REUNION, "socios": ["a", "s1"], "reintento_pedido_en": None}
    b = bloque(r, [], EVENTOS, diagnosticar(r["motivo"]), comprobaciones(LATIDO, 4.0, 1), {"a": "Error", "s1": "Ana"})
    assert "Socios: S1, S2" in b
    assert "envía las pistas a una plataforma" in b and "Pasó a error (plazo_envio)" in b


def test_un_reintento_sin_usuario_no_inventa_un_seudonimo():
    b = _bloque(r={**REUNION, "reintento_pedido_por": None})
    assert "Reintento pedido por alguien: pendiente" in b and "U2:" not in b
