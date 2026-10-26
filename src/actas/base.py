"""Archivo y bus de peticiones de las actas en el PostgreSQL compartido (ADR 0019): inquilino `actas`, esquema `actas`.

El panel de F2 y `actas.sh` solo escriben peticiones; el supervisor las atiende (ADR 0015, decisión 6). Cada cambio de
estado es un UPDATE condicionado al estado de origen, así que dos procesos no pueden mover la misma reunión a la vez.
Los errores de la base se registran solo por su tipo: un INSERT de un segmento lleva texto (ADR 0019, D8).
"""

import re
import uuid
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import psycopg
import psycopg.conninfo
from psycopg import sql
from psycopg.rows import dict_row

from actas.conformidad import Peticion
from actas.estados import Estado, TransicionNoValida, transicion

_ESQUEMA = re.compile(r"[a-z][a-z0-9_]{0,30}")
MIGRACIONES = Path(__file__).resolve().parent / "migraciones"


def _migraciones() -> list[tuple[str, str]]:
    # Dentro de la imagen van junto al paquete; en el repo, en migraciones/ (las dos rutas tienen los mismos ficheros).
    raiz = MIGRACIONES if MIGRACIONES.is_dir() else Path(__file__).resolve().parents[2] / "migraciones"
    return [(p.name, p.read_text(encoding="utf-8")) for p in sorted(raiz.glob("*.sql"))]


def _esquema(nombre: str) -> sql.Identifier:
    if not _ESQUEMA.fullmatch(nombre):
        raise ValueError("nombre de esquema no válido")
    return sql.Identifier(nombre)


def migrar(dsn: str, esquema: str = "actas", password: str | None = None) -> list[str]:
    """Aplica las migraciones pendientes, cada una en su transacción. Devuelve las aplicadas. La contraseña va como parámetro
    aparte, nunca interpolada en el conninfo."""
    aplicadas = []
    with psycopg.connect(psycopg.conninfo.make_conninfo(dsn, password=password)) as c:
        c.execute(sql.SQL("SET search_path = {}").format(_esquema(esquema)))
        c.execute(
            "CREATE TABLE IF NOT EXISTS esquema_migraciones "
            "(nombre text PRIMARY KEY, aplicada_en timestamptz NOT NULL DEFAULT now())"
        )
        c.commit()
        hechas = {f[0] for f in c.execute("SELECT nombre FROM esquema_migraciones").fetchall()}
        for nombre, texto in _migraciones():
            if nombre in hechas:
                continue
            with c.transaction():
                c.execute(texto.encode())
                c.execute("INSERT INTO esquema_migraciones (nombre) VALUES (%s)", (nombre,))
            aplicadas.append(nombre)
    return aplicadas


class Repositorio:
    def __init__(self, dsn: str, esquema: str = "actas", ajustes: Mapping[str, str] | None = None) -> None:
        """`ajustes`: parámetros de la sesión (set_config) en cada conexión; el panel pide TimeZone y statement_timeout."""
        self._dsn = dsn
        self._esquema = _esquema(esquema)
        self._ajustes = dict(ajustes or {})

    def cerrar(self) -> None:
        """Sin pool: una conexión por operación (como mucho unas pocas por minuto)."""

    @contextmanager
    def conexion(self) -> Iterator[psycopg.Connection[Any]]:
        c = psycopg.connect(self._dsn)
        try:
            with c:  # confirma al salir; si el COMMIT falla (trigger diferido), la conexión se cierra igual en el finally
                c.execute(sql.SQL("SET search_path = {}").format(self._esquema))
                for nombre, valor in self._ajustes.items():
                    c.execute("SELECT set_config(%s, %s, false)", (nombre, valor))
                yield c
        finally:
            c.close()

    def pedir(self, peticion: Peticion, pedido_por: str | None = None) -> str:
        """@a6: la reunión y una conformidad por socio, en la misma transacción. `pedido_por`: el usuario del panel (F2)."""
        with self.conexion() as c:
            fila = c.execute(
                "INSERT INTO reuniones (socios, texto_version, pedido_por) VALUES (%s, %s, %s) RETURNING id",
                (list(peticion.socios), peticion.version, pedido_por),
            ).fetchone()
            assert fila is not None
            rid = str(fila[0])
            with c.cursor() as cur:
                cur.executemany(
                    "INSERT INTO conformidades (reunion_id, socio, texto_version) VALUES (%s, %s, %s)",
                    [(rid, s, peticion.version) for s in peticion.socios],
                )
            return rid

    def reunion(self, rid: str) -> dict[str, Any]:
        with self.conexion() as c, c.cursor(row_factory=dict_row) as cur:
            fila = cur.execute("SELECT * FROM reuniones WHERE id = %s", (rid,)).fetchone()
        if fila is None:
            raise KeyError(rid)
        return _fila(fila)

    def conformidades(self, rid: str) -> list[tuple[str, str]]:
        with self.conexion() as c:
            filas = c.execute(
                "SELECT socio, texto_version FROM conformidades WHERE reunion_id = %s ORDER BY socio", (rid,)
            ).fetchall()
        return [(f[0], f[1]) for f in filas]

    def siguiente(self, estado: Estado) -> dict[str, Any] | None:
        with self.conexion() as c, c.cursor(row_factory=dict_row) as cur:
            fila = cur.execute(
                "SELECT * FROM reuniones WHERE estado = %s ORDER BY creado_en, id LIMIT 1", (estado.value,)
            ).fetchone()
        return _fila(fila) if fila else None

    def en_estado(self, *estados: Estado) -> list[dict[str, Any]]:
        with self.conexion() as c, c.cursor(row_factory=dict_row) as cur:
            filas = cur.execute(
                "SELECT * FROM reuniones WHERE estado = ANY(%s) ORDER BY creado_en", ([e.value for e in estados],)
            ).fetchall()
        return [_fila(f) for f in filas]

    def estados_de(self, ids: Sequence[str]) -> dict[str, tuple[str, float]]:
        """(estado, momento de referencia en epoch) de cada reunión: el fin de la grabación o, si no lo hay, su creación. El
        plazo del audio se cuenta desde aquí y no desde el mtime del directorio, que puede tocar Chromium."""
        validos = [i for i in ids if es_uuid(i)]
        with self.conexion() as c:
            filas = c.execute(
                "SELECT id::text, estado, extract(epoch FROM coalesce(fin, creado_en))::float8 "
                "FROM reuniones WHERE id = ANY(%s::uuid[])",
                (validos,),
            ).fetchall()
        return {f[0]: (f[1], float(f[2])) for f in filas}

    def mover(
        self,
        rid: str,
        desde: Estado,
        hasta: Estado,
        motivo: str | None = None,
        inicio: bool = False,
        fin: bool = False,
        trabajo_id: str | None = None,
    ) -> None:
        transicion(desde, hasta)
        with self.conexion() as c:
            self._mover(c, rid, desde, hasta, motivo, inicio, fin, trabajo_id)

    @staticmethod
    def _mover(
        c: psycopg.Connection[Any],
        rid: str,
        desde: Estado,
        hasta: Estado,
        motivo: str | None = None,
        inicio: bool = False,
        fin: bool = False,
        trabajo_id: str | None = None,
    ) -> None:
        cur = c.execute(
            """UPDATE reuniones SET estado = %s, actualizado_en = now(), motivo = COALESCE(%s, motivo),
                   inicio = CASE WHEN %s THEN now() ELSE inicio END,
                   fin = CASE WHEN %s THEN now() ELSE fin END,
                   trabajo_id = COALESCE(%s, trabajo_id)
               WHERE id = %s AND estado = %s""",
            (hasta.value, motivo, inicio, fin, trabajo_id, rid, desde.value),
        )
        if cur.rowcount != 1:
            raise TransicionNoValida(f"la reunión no estaba en {desde}")

    def pedir_parada(self) -> str | None:
        """La petición de parar la grabación activa. None si no hay ninguna."""
        with self.conexion() as c:
            fila = c.execute(
                "UPDATE reuniones SET parar_pedido_en = COALESCE(parar_pedido_en, now()), actualizado_en = now() "
                "WHERE estado = 'grabando' RETURNING id::text"
            ).fetchone()
        return fila[0] if fila else None

    def guardar_transcripcion(self, rid: str, segmentos: Sequence[dict[str, Any]]) -> None:
        """@a8: los segmentos y el paso a `transcrita` en una sola transacción; reintentar no duplica."""
        with self.conexion() as c:
            self._mover(c, rid, Estado.TRANSCRIBIENDO, Estado.TRANSCRITA)
            with c.cursor() as cur:
                cur.executemany(
                    "INSERT INTO segmentos (reunion_id, hablante, inicio_ms, fin_ms, texto) VALUES (%s, %s, %s, %s, %s)",
                    [
                        (rid, s["hablante"], s["inicio_ms"], s["fin_ms"], s["texto"])
                        for s in sorted(segmentos, key=lambda s: (s["inicio_ms"], s["fin_ms"]))
                    ],
                )

    def segmentos(self, rid: str) -> list[tuple[str, int, int, str]]:
        with self.conexion() as c:
            filas = c.execute(
                "SELECT hablante, inicio_ms, fin_ms, texto FROM segmentos WHERE reunion_id = %s ORDER BY inicio_ms, fin_ms",
                (rid,),
            ).fetchall()
        return [(f[0], f[1], f[2], f[3]) for f in filas]

    def ultimas(self, limite: int) -> list[dict[str, Any]]:
        """Las últimas reuniones, de la más nueva a la más vieja (lista del panel)."""
        with self.conexion() as c, c.cursor(row_factory=dict_row) as cur:
            filas = cur.execute(
                "SELECT id, creado_en, inicio, fin, estado, motivo, socios, pedido_por FROM reuniones "
                "ORDER BY creado_en DESC, id DESC LIMIT %s",
                (limite,),
            ).fetchall()
        return [_fila(f) for f in filas]

    def hay_grabacion(self) -> bool:
        with self.conexion() as c:
            fila = c.execute("SELECT EXISTS (SELECT 1 FROM reuniones WHERE estado = 'grabando')").fetchone()
        return bool(fila and fila[0])

    def detalle(self, rid: str) -> tuple[dict[str, Any], list[tuple[str, str]], list[tuple[str, int, int, str]]]:
        """La reunión, sus conformidades y sus segmentos con una sola conexión (vista de la reunión del panel)."""
        with self.conexion() as c, c.cursor(row_factory=dict_row) as cur:
            fila = cur.execute("SELECT * FROM reuniones WHERE id = %s", (rid,)).fetchone()
            if fila is None:
                raise KeyError(rid)
            conformidades = c.execute(
                "SELECT socio, texto_version FROM conformidades WHERE reunion_id = %s ORDER BY socio", (rid,)
            ).fetchall()
            segmentos = c.execute(
                "SELECT hablante, inicio_ms, fin_ms, texto FROM segmentos WHERE reunion_id = %s ORDER BY inicio_ms, fin_ms",
                (rid,),
            ).fetchall()
        return _fila(fila), [(f[0], f[1]) for f in conformidades], [(f[0], f[1], f[2], f[3]) for f in segmentos]

    def buscar(self, q: str, limite: int, centinelas: str, opciones: str) -> list[dict[str, Any]]:
        """@a22: los segmentos que casan con `websearch_to_tsquery('spanish', q)` (índice GIN de `tsv`), como mucho `limite`, y
        su resaltado. `ts_headline` va fuera del LIMIT («can be slow») y sobre el texto sin los centinelas de `opciones`."""
        with self.conexion() as c, c.cursor(row_factory=dict_row) as cur:
            filas = cur.execute(
                """WITH q AS (SELECT websearch_to_tsquery('spanish', %(q)s) AS q),
                        hallados AS (
                            SELECT s.reunion_id, r.creado_en, s.hablante, s.inicio_ms, s.texto
                            FROM segmentos s JOIN reuniones r ON r.id = s.reunion_id, q
                            WHERE s.tsv @@ q.q
                            ORDER BY r.creado_en DESC, s.reunion_id, s.inicio_ms, s.id
                            LIMIT %(limite)s)
                   SELECT h.reunion_id, h.creado_en, h.hablante, h.inicio_ms,
                          ts_headline('spanish', translate(h.texto, %(centinelas)s, ''), q.q, %(opciones)s) AS fragmento
                   FROM hallados h, q
                   ORDER BY h.creado_en DESC, h.reunion_id, h.inicio_ms""",
                {"q": q, "limite": limite, "centinelas": centinelas, "opciones": opciones},
            ).fetchall()
        return [_fila(f) for f in filas]

    def reintentar(self, rid: str) -> bool:
        """Una reunión en `error` vuelve a `grabada` para enviar otra vez su audio (si aún existe)."""
        try:
            self.mover(rid, Estado.ERROR, Estado.GRABADA, motivo="reintento")
        except TransicionNoValida:
            return False
        return True

    def anotar_purga(self, rid: str | None, motivo: str, ficheros: int, octetos: int) -> None:
        with self.conexion() as c:
            c.execute(
                "INSERT INTO purgas (reunion_id, motivo, ficheros, bytes) VALUES (%s, %s, %s, %s)",
                (rid, motivo, ficheros, octetos),
            )

    def cuenta_por_estado(self) -> dict[str, int]:
        with self.conexion() as c:
            filas = c.execute("SELECT estado, count(*) FROM reuniones GROUP BY estado").fetchall()
        return {f[0]: int(f[1]) for f in filas}


def _fila(fila: dict[str, Any]) -> dict[str, Any]:
    """Los uuid de la base, como texto (es lo que circula por el supervisor y por la API de la plataforma)."""
    return {k: str(v) if isinstance(v, uuid.UUID) else v for k, v in fila.items()}


def es_uuid(texto: str) -> bool:
    try:
        uuid.UUID(texto)
    except ValueError:
        return False
    return True


__all__ = ["Repositorio", "es_uuid", "migrar"]
