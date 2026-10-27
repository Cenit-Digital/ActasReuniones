"""Un repositorio de mentira con todas las pantallas y todos los estados del panel, para los tests sin base (TestClient) y los de
Chromium (formularios y axe), también «Salas y socios» (V2) y la programación y la papelera (V3). Apunta lo que piden «Grabar»,
«Parar», «Reintentar», «Programar», «Modificar», «Cancelar», «Eliminar» y «Recuperar»."""

from datetime import UTC, datetime, timedelta
from typing import Any

from actas.busqueda import FIN, INICIO
from actas.planificador import MADRID

SOCIOS = {"pablo": "Pablo", "roberto": "Roberto"}
SALA = "5a1a0000-0000-4000-8000-000000000001"
TRABAJO = "11111111-2222-4333-8444-555555555555"
MAESTRA = bytes(range(32))
ESTADOS = ["grabando", "programada", "transcribiendo", "error", "transcrita", "cancelada", "pedida", "grabada"]
RIDS = {e: f"00000000-0000-4000-8000-00000000000{i}" for i, e in enumerate(ESTADOS, start=1)}
# La forma de la reunión real 17d9d6ae (producción, 2026-10-27): `error: pistas`, 6 s grabando, parada pedida a los 4 s y
# anterior al historial de eventos (V4 de KubernetesInfrastructure#298).
RID_PISTAS = "00000000-0000-4000-8000-000000000017"
_BASE = datetime(2026, 10, 26, 18, 0)
IMAGEN = "sha-0123456789abcdef0123456789abcdef01234567"
CHROMIUM = "HeadlessChrome/141.0.7390.37"
# V3: la programada, el jueves a las 17:30 de Madrid de dentro de una semana (siempre en el futuro), y una en la papelera.
PARA = datetime.combine(datetime.now(MADRID).date() + timedelta(days=7), datetime.min.time(), MADRID).replace(hour=17, minute=30)
RID_PAPELERA = "00000000-0000-4000-8000-0000000000aa"
TITULO = "Socios · seguimiento semanal"


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
        "titulo": TITULO if e in ("transcrita", "programada") else None,
        "programada_para": PARA if e == "programada" else None,
        "tope_min": 120 if e == "programada" else 180,
        "repetir": "semanal" if e == "programada" else "no",
        "espera_min": 15 if e == "programada" else None,
        "anterior_id": None,
        "papelera_en": None,
        "papelera_por": None,
    }


def _papelera() -> dict[str, Any]:
    r = _reunion(9, "cancelada") | {"id": RID_PAPELERA, "titulo": "Prueba de V3"}
    return r | {"papelera_en": datetime(2026, 10, 27, 10, 0, tzinfo=UTC), "papelera_por": "pablo", "estado": "transcrita"}


def _pistas() -> dict[str, Any]:
    creado = datetime(2026, 10, 27, 11, 10, 5)
    return {
        "id": RID_PISTAS,
        "creado_en": creado,
        "inicio": creado + timedelta(seconds=4.64),
        "fin": creado + timedelta(seconds=10.51),
        "parar_pedido_en": creado + timedelta(seconds=8.21),
        "reintento_pedido_en": None,
        "reintento_pedido_por": None,
        "actualizado_en": creado + timedelta(seconds=10.55),
        "estado": "error",
        "motivo": "pistas",
        "socios": ["andres", "pablo", "roberto"],
        "pedido_por": "pablo",
        "trabajo_id": None,
    }


class RepoFalso:
    def __init__(self, activa: bool = True) -> None:
        self.activa = activa
        self.pedidas: list[tuple[object, str]] = []
        self.paradas = 0
        self.trabajos: list[str] = []
        self.salas_pedidas: list[str | None] = []
        self.reintentos: list[tuple[str, str]] = []
        self.programaciones: list[tuple[object, str]] = []
        self.modificaciones: list[tuple[str, object, str]] = []
        self.cancelaciones: list[tuple[str, str, bool]] = []
        self.papeleras: list[tuple[str, str]] = []
        self.recuperaciones: list[tuple[str, str]] = []
        self.titulos_pedidos: list[tuple[str | None, int]] = []
        # El latido: fresco, con el audio de la reunión en error (`plazo_envio`) aún en el tmpfs.
        self.latido: dict[str, Any] | None = {
            "chromium": CHROMIUM,
            "imagen": IMAGEN,
            "grabaciones_bytes": 50_331_648,
            "grabaciones_total": 805_306_368,
            "con_audio": [RIDS["error"]],
            "transcribir_codigo": 503,
        }
        self.latido_hace_s = 4.0
        self.fallos_transcribir_1h = 2

    def ultimas(self, _limite: int) -> list[dict[str, Any]]:
        return [_reunion(i, e) for i, e in enumerate(ESTADOS)]

    def hay_grabacion(self) -> bool:
        return self.activa

    def detalle(self, rid: str) -> tuple[dict[str, Any], list[tuple[str, str]], list[tuple[str, int, int, str]]]:
        por_id = {r["id"]: r for r in self.ultimas(0)} | {RID_PISTAS: _pistas(), RID_PAPELERA: _papelera()}
        if rid not in por_id:
            raise KeyError(rid)
        segmentos = [
            ("pablo", 192_000, 200_000, "Empezamos por el presupuesto del trimestre, que es lo más urgente."),
            ("roberto", 280_000, 290_000, "De acuerdo. Traigo las cifras de marketing para revisarlas juntos."),
            ("invitado", 425_000, 430_000, "Cerramos el presupuesto el jueves y lo mandamos a la gestoría."),
        ]
        if rid == RIDS["programada"]:  # V3: solo Pablo ha dado ya su conformidad, con el texto vigente
            return por_id[rid], self.conformidades(rid), []
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

    def pedir(self, pedida: object, usuario: str, sala: str | None = None, titulo: str | None = None, tope_min: int = 180) -> str:
        self.pedidas.append((pedida, usuario))
        self.salas_pedidas.append(sala)
        self.titulos_pedidos.append((titulo, tope_min))
        return RIDS["grabando"]

    # ── V3 ──

    def _existe(self, rid: str) -> bool:
        return rid in RIDS.values() or rid in (RID_PISTAS, RID_PAPELERA)

    def programar(self, p: object, usuario: str) -> str:
        self.programaciones.append((p, usuario))
        return RIDS["programada"]

    def modificar_programada(self, rid: str, p: object, usuario: str) -> bool | None:
        self.modificaciones.append((rid, p, usuario))
        return rid == RIDS["programada"] if self._existe(rid) else None

    def cancelar(self, rid: str, usuario: str, serie: bool = False) -> bool | None:
        self.cancelaciones.append((rid, usuario, serie))
        return rid == RIDS["programada"] if self._existe(rid) else None

    def a_papelera(self, rid: str, usuario: str) -> bool | None:
        self.papeleras.append((rid, usuario))
        return rid in (RIDS["transcrita"], RIDS["error"], RIDS["cancelada"]) if self._existe(rid) else None

    def recuperar(self, rid: str, usuario: str) -> bool | None:
        self.recuperaciones.append((rid, usuario))
        return rid == RID_PAPELERA if self._existe(rid) else None

    def programadas(self) -> list[dict[str, Any]]:
        return [r | {"conformes": 1} for r in self.ultimas(0) if r["estado"] == "programada"]

    def conformidades(self, rid: str) -> list[tuple[str, str]]:
        return [("pablo", "v1")] if rid == RIDS["programada"] else []

    def papelera(self) -> list[dict[str, Any]]:
        r = _papelera()
        return [r | {"borrado_en": r["papelera_en"] + timedelta(days=7)}]

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

    def diagnostico(self, rid: str) -> dict[str, Any]:
        eventos: list[dict[str, Any]] = []
        if rid == RIDS["error"]:
            t = _BASE - timedelta(days=ESTADOS.index("error"))
            eventos = [
                {"momento": t, "tipo": "estado", "detalle": {"desde": "pedida", "hasta": "grabando", "socios": 2}},
                {
                    "momento": t + timedelta(minutes=55, seconds=31),
                    "tipo": "estado",
                    "detalle": {"desde": "grabando", "hasta": "grabada", "motivo": "pedida", "completas": True},
                },
                {
                    "momento": t + timedelta(minutes=55, seconds=36),
                    "tipo": "envio",
                    "detalle": {"codigo": 503, "accion": "reintentar", "intento": 0},
                },
                {
                    "momento": t + timedelta(hours=12, minutes=56),
                    "tipo": "estado",
                    "detalle": {"desde": "grabada", "hasta": "error", "motivo": "plazo_envio"},
                },
            ]
        return {
            "eventos": eventos,
            "latido": self.latido,
            "latido_hace_s": self.latido_hace_s if self.latido is not None else None,
            "fallos_transcribir_1h": self.fallos_transcribir_1h,
        }

    def pedir_reintento(self, rid: str, usuario: str) -> bool | None:
        self.reintentos.append((rid, usuario))
        if rid not in RIDS.values() and rid != RID_PISTAS:
            return None
        return rid == RIDS["error"]
