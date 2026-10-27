"""Un repositorio de mentira con todas las pantallas y todos los estados del panel, para los tests sin base (TestClient) y los de
Chromium (formularios y axe), también «Salas y socios» (V2). Apunta lo que piden «Grabar» y «Parar»."""

from datetime import datetime, timedelta
from typing import Any

from actas.busqueda import FIN, INICIO

SOCIOS = {"pablo": "Pablo", "roberto": "Roberto"}
SALA = "5a1a0000-0000-4000-8000-000000000001"
TRABAJO = "11111111-2222-4333-8444-555555555555"
MAESTRA = bytes(range(32))
ESTADOS = ["grabando", "programada", "transcribiendo", "error", "transcrita", "cancelada", "pedida", "grabada"]
RIDS = {e: f"00000000-0000-4000-8000-00000000000{i}" for i, e in enumerate(ESTADOS, start=1)}
_BASE = datetime(2026, 10, 26, 18, 0)


def _reunion(i: int, e: str) -> dict[str, Any]:
    inicio = _BASE - timedelta(days=i)
    return {
        "id": RIDS[e],
        "creado_en": inicio,
        "inicio": inicio,
        "fin": inicio + timedelta(minutes=55, seconds=31),
        "estado": e,
        "motivo": "plazo_envio" if e == "error" else None,
        "socios": ["pablo", "roberto"],
        "pedido_por": "pablo",
        "trabajo_id": TRABAJO if e == "transcrita" else None,
        "sala_id": SALA,
    }


class RepoFalso:
    def __init__(self, activa: bool = True) -> None:
        self.activa = activa
        self.pedidas: list[tuple[object, str]] = []
        self.paradas = 0
        self.trabajos: list[str] = []
        self.salas_pedidas: list[str | None] = []

    def ultimas(self, _limite: int) -> list[dict[str, Any]]:
        return [_reunion(i, e) for i, e in enumerate(ESTADOS)]

    def hay_grabacion(self) -> bool:
        return self.activa

    def detalle(self, rid: str) -> tuple[dict[str, Any], list[tuple[str, str]], list[tuple[str, int, int, str]]]:
        por_id = {r["id"]: r for r in self.ultimas(0)}
        if rid not in por_id:
            raise KeyError(rid)
        segmentos = [
            ("pablo", 192_000, 200_000, "Empezamos por el presupuesto del trimestre, que es lo más urgente."),
            ("roberto", 280_000, 290_000, "De acuerdo. Traigo las cifras de marketing para revisarlas juntos."),
            ("invitado", 425_000, 430_000, "Cerramos el presupuesto el jueves y lo mandamos a la gestoría."),
        ]
        return por_id[rid], [("pablo", "2026-10-26"), ("roberto", "2026-10-26")], segmentos

    def buscar(self, *_: object) -> list[dict[str, Any]]:
        return [
            {
                "reunion_id": RIDS["transcrita"],
                "creado_en": _BASE,
                "hablante": "pablo",
                "inicio_ms": 192_000,
                "fragmento": f"Empezamos por el {INICIO}presupuesto{FIN} del trimestre",
            }
        ]

    def reunion_de_trabajo(self, trabajo: str) -> str | None:
        self.trabajos.append(trabajo)
        return RIDS["transcrita"] if trabajo == TRABAJO else None

    def pedir(self, pedida: object, usuario: str, sala: str | None = None) -> str:
        self.pedidas.append((pedida, usuario))
        self.salas_pedidas.append(sala)
        return RIDS["grabando"]

    def socios(self) -> list[dict[str, Any]]:
        return [{"push": p, "nombre": n, "correo": None, "activo": True} for p, n in SOCIOS.items()] + [
            {"push": "antiguo", "nombre": "Antiguo", "correo": "antiguo@cenitdigital.es", "activo": False}
        ]

    def salas(self) -> list[dict[str, Any]]:
        return [{**self.sala(SALA), "reuniones": 12, "ultima": _BASE}]

    def sala(self, sid: str) -> dict[str, Any]:
        if sid != SALA:
            raise KeyError(sid)
        return {
            "id": SALA,
            "nombre": "Socios · semanal",
            "room": "k3v9q2m7x4t8w1za",
            "hash": "3931",
            "creada_en": _BASE,
            "creada_por": "pablo",
        }

    def eventos_de_sala(self, _sid: str) -> list[dict[str, Any]]:
        return [
            {"tipo": "sala_creada", "usuario": "pablo", "momento": _BASE},
            {"tipo": "clave_vista", "usuario": "pablo", "momento": _BASE},
        ]

    def ver_clave(self, sid: str, _usuario: str) -> bytes | None:
        from actas import salas

        return salas.cifrar(MAESTRA, "k3v9q2m7x4t8w1za", "k7m2p9qx4tz8wb3n") if sid == SALA else None

    def pedir_parada(self) -> str | None:
        self.paradas += 1
        return RIDS["grabando"] if self.activa else None
