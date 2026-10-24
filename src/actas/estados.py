"""Estados de una reunión en F1 (ADR 0015, decisión 6) y la parada por tope (@a7)."""

from enum import StrEnum

TOPE_GRABACION_S = 3 * 3600


class Estado(StrEnum):
    PEDIDA = "pedida"
    GRABANDO = "grabando"
    GRABADA = "grabada"
    TRANSCRIBIENDO = "transcribiendo"
    TRANSCRITA = "transcrita"
    ERROR = "error"


class TransicionNoValida(ValueError):
    pass


# ERROR → GRABADA es el reintento (`actas.sh reintentar`): vuelve a enviar el audio que se conservó.
_PERMITIDAS = {
    Estado.PEDIDA: {Estado.GRABANDO, Estado.ERROR},
    Estado.GRABANDO: {Estado.GRABADA, Estado.ERROR},
    Estado.GRABADA: {Estado.TRANSCRIBIENDO, Estado.ERROR},
    Estado.TRANSCRIBIENDO: {Estado.TRANSCRITA, Estado.ERROR},
    Estado.TRANSCRITA: set(),
    Estado.ERROR: {Estado.GRABADA},
}


def transicion(desde: Estado, hasta: Estado) -> Estado:
    if hasta not in _PERMITIDAS[desde]:
        raise TransicionNoValida(f"{desde} → {hasta}")
    return hasta


def motivo_parada(inicio_s: float, ahora_s: float, parar_pedido: bool) -> str | None:
    """None mientras se sigue grabando; si no, el motivo que se anota en la reunión."""
    if parar_pedido:
        return "pedida"
    if ahora_s - inicio_s >= TOPE_GRABACION_S:
        return "tope_3h"
    return None
