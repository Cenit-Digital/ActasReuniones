"""Estados de una reunión (ADR 0015, decisión 6), la parada por tope (@a7) y, desde V3 (KubernetesInfrastructure#298, ADR 0023
decisión 5), las reuniones programadas y canceladas, el tope de cada reunión y «si no entra nadie»."""

from enum import StrEnum

TOPE_GRABACION_S = 3 * 3600


class Estado(StrEnum):
    PEDIDA = "pedida"
    GRABANDO = "grabando"
    GRABADA = "grabada"
    TRANSCRIBIENDO = "transcribiendo"
    TRANSCRITA = "transcrita"
    ERROR = "error"
    PROGRAMADA = "programada"
    CANCELADA = "cancelada"


class TransicionNoValida(ValueError):
    pass


# ERROR → GRABADA es el reintento (`actas.sh reintentar` o el panel): vuelve a enviar el audio que se conservó.
# PROGRAMADA → GRABANDO a su hora, → ERROR si no se puede (conformidad, sala, llegó tarde) y → CANCELADA desde el panel.
# GRABANDO → CANCELADA: no entró ningún socio conforme en su espera (el audio se borra).
_PERMITIDAS = {
    Estado.PEDIDA: {Estado.GRABANDO, Estado.ERROR},
    Estado.GRABANDO: {Estado.GRABADA, Estado.ERROR, Estado.CANCELADA},
    Estado.GRABADA: {Estado.TRANSCRIBIENDO, Estado.ERROR},
    Estado.TRANSCRIBIENDO: {Estado.TRANSCRITA, Estado.ERROR},
    Estado.TRANSCRITA: set(),
    Estado.ERROR: {Estado.GRABADA},
    Estado.PROGRAMADA: {Estado.GRABANDO, Estado.ERROR, Estado.CANCELADA},
    Estado.CANCELADA: set(),
}
# Los que pueden ir a la papelera: nada sigue en marcha en ellos (una `grabada` en la papelera se seguiría enviando).
ESTADOS_FINALES = frozenset({Estado.TRANSCRITA, Estado.ERROR, Estado.CANCELADA})


def transicion(desde: Estado, hasta: Estado) -> Estado:
    if hasta not in _PERMITIDAS[desde]:
        raise TransicionNoValida(f"{desde} → {hasta}")
    return hasta


def motivo_parada(inicio_s: float, ahora_s: float, parar_pedido: bool, tope_s: int = TOPE_GRABACION_S) -> str | None:
    """None mientras se sigue grabando; si no, el motivo que se anota en la reunión. `tope_s`: el de la reunión, que nunca pasa
    de las 3 h de F1."""
    if parar_pedido:
        return "pedida"
    if ahora_s - inicio_s >= min(tope_s, TOPE_GRABACION_S):
        return "tope_3h" if tope_s >= TOPE_GRABACION_S else "tope"
    return None


def nadie_entro(segundos: float, espera_s: int | None, alguno_visto: bool) -> bool:
    """Pasada la espera de una reunión programada, ningún socio conforme ha publicado en la sala: se cancela. Sin espera (las de
    «Grabar ahora»), nunca."""
    return espera_s is not None and not alguno_visto and segundos >= espera_s
