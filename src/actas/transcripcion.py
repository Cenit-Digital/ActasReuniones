"""De la transcripción de la plataforma (`GET /api/interno/actas/trabajos/{id}` con `listo`; esquema `Transcripcion` del
contrato) a los segmentos que se guardan en `actas` 12 meses. En el modo por pistas el hablante es el dueño de la pista:
su `etiqueta` es el `interlocutores` que se envió, el streamID del socio."""

from typing import Any


class TranscripcionNoValida(ValueError):
    pass


def segmentos_de(transcripcion: dict[str, Any], conformes: list[str]) -> list[dict[str, Any]]:
    hablantes = transcripcion.get("hablantes")
    segmentos = transcripcion.get("segmentos")
    if not isinstance(hablantes, list) or not isinstance(segmentos, list):
        raise TranscripcionNoValida("forma inesperada")
    etiquetas = {h.get("id"): h.get("etiqueta") for h in hablantes if isinstance(h, dict)}
    salida = []
    for s in segmentos:
        hablante = etiquetas.get(s.get("hablante_id"))
        if hablante not in conformes:
            raise TranscripcionNoValida("hablante que no es un socio conforme")
        inicio, fin, texto = s.get("inicio_ms"), s.get("fin_ms"), s.get("texto")
        if type(inicio) is not int or type(fin) is not int or not 0 <= inicio <= fin or not isinstance(texto, str):
            raise TranscripcionNoValida("tiempos o texto no válidos")
        if texto.strip():
            salida.append({"hablante": hablante, "inicio_ms": inicio, "fin_ms": fin, "texto": texto.strip()})
    return sorted(salida, key=lambda x: (x["inicio_ms"], x["fin_ms"]))
