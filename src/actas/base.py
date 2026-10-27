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
from psycopg.types.json import Jsonb

from actas import eventos
from actas.conformidad import Peticion
from actas.estados import Estado, TransicionNoValida, transicion
from actas.formulario import Socio

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
    def __init__(
        self,
        dsn: str,
        esquema: str = "actas",
        ajustes: Mapping[str, str] | None = None,
        secretos: Sequence[str] = (),
    ) -> None:
        """`ajustes`: parámetros de la sesión (set_config) en cada conexión; el panel pide TimeZone y statement_timeout.
        `secretos`: los que ningún evento puede llevar (@a55; los mismos que redacta el registro del supervisor)."""
        self._dsn = dsn
        self._esquema = _esquema(esquema)
        self._ajustes = dict(ajustes or {})
        self._secretos = secretos  # sin copiar: el registro añade la contraseña de cada sala al descifrarla (V2)

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

    def pedir(self, peticion: Peticion, pedido_por: str | None = None, sala_id: str | None = None) -> str:
        """@a6: la reunión y una conformidad por socio, en la misma transacción. `pedido_por`: el usuario del panel (F2).
        `sala_id`: la sala en la que se graba (V2); sin ella, el supervisor no la graba."""
        with self.conexion() as c:
            fila = c.execute(
                "INSERT INTO reuniones (socios, texto_version, pedido_por, sala_id) VALUES (%s, %s, %s, %s) RETURNING id",
                (list(peticion.socios), peticion.version, pedido_por, sala_id),
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
        detalle: Mapping[str, Any] | None = None,
    ) -> None:
        """`detalle`: lo que se añade al evento del cambio de estado (p. ej., la causa de un error de pistas)."""
        transicion(desde, hasta)
        with self.conexion() as c:
            self._mover(c, rid, desde, hasta, motivo, inicio, fin, trabajo_id, detalle)

    def _mover(
        self,
        c: psycopg.Connection[Any],
        rid: str,
        desde: Estado,
        hasta: Estado,
        motivo: str | None = None,
        inicio: bool = False,
        fin: bool = False,
        trabajo_id: str | None = None,
        detalle: Mapping[str, Any] | None = None,
    ) -> None:
        """El cambio de estado y su evento (@a54), en la misma transacción: o los dos, o ninguno. Salir de `error`, por la vía
        que sea (el panel o `actas.sh reintentar`), consume la petición de «Reintentar» que hubiera."""
        evento = {"desde": desde.value, "hasta": hasta.value, **({"motivo": motivo} if motivo else {}), **(detalle or {})}
        evento = eventos.validar("estado", evento, self._secretos)
        cur = c.execute(
            """UPDATE reuniones SET estado = %s, actualizado_en = now(), motivo = COALESCE(%s, motivo),
                   inicio = CASE WHEN %s THEN now() ELSE inicio END,
                   fin = CASE WHEN %s THEN now() ELSE fin END,
                   trabajo_id = COALESCE(%s, trabajo_id),
                   reintento_pedido_en = CASE WHEN %s THEN NULL ELSE reintento_pedido_en END
               WHERE id = %s AND estado = %s""",
            (hasta.value, motivo, inicio, fin, trabajo_id, desde == Estado.ERROR, rid, desde.value),
        )
        if cur.rowcount != 1:
            raise TransicionNoValida(f"la reunión no estaba en {desde}")
        self._evento(c, rid, "estado", evento)

    def _evento(self, c: psycopg.Connection[Any], rid: str | None, tipo: str, detalle: Mapping[str, Any]) -> None:
        c.execute(
            "INSERT INTO eventos (reunion_id, tipo, detalle) VALUES (%s, %s, %s)",
            (rid, tipo, Jsonb(eventos.validar(tipo, detalle, self._secretos))),
        )

    def anotar_evento(self, rid: str | None, tipo: str, detalle: Mapping[str, Any]) -> None:
        """@a55: solo la lista blanca y ningún secreto (eventos.validar en `_evento` y el CHECK de la base)."""
        with self.conexion() as c:
            self._evento(c, rid, tipo, detalle)

    def eventos(self, rid: str) -> list[dict[str, Any]]:
        with self.conexion() as c, c.cursor(row_factory=dict_row) as cur:
            filas = cur.execute(
                "SELECT momento, tipo, detalle FROM eventos WHERE reunion_id = %s ORDER BY momento, id", (rid,)
            ).fetchall()
        return [_fila(f) for f in filas]

    def latir(self, detalle: Mapping[str, Any]) -> None:
        """El latido del supervisor: una sola fila, reescrita en cada vuelta."""
        with self.conexion() as c:
            c.execute(
                "INSERT INTO latido (unico, momento, detalle) VALUES (true, now(), %s) "
                "ON CONFLICT (unico) DO UPDATE SET momento = excluded.momento, detalle = excluded.detalle",
                (Jsonb(dict(detalle)),),
            )

    def latido(self) -> tuple[dict[str, Any], float] | None:
        """(detalle, segundos desde el último latido según el reloj de la base) o None si el supervisor nunca latió."""
        with self.conexion() as c:
            fila = c.execute("SELECT detalle, extract(epoch FROM now() - momento)::float8 FROM latido").fetchone()
        return (fila[0], float(fila[1])) if fila else None

    def diagnostico(self, rid: str) -> dict[str, Any]:
        """Lo que el panel enseña de una reunión (@a56) con una sola conexión: su historial, el latido y los fallos de transcribir
        de la última hora (envíos y consultas sin un 200 o 201, o que acabaron en error)."""
        with self.conexion() as c, c.cursor(row_factory=dict_row) as cur:
            historial = cur.execute(
                "SELECT momento, tipo, detalle FROM eventos WHERE reunion_id = %s ORDER BY momento, id", (rid,)
            ).fetchall()
            latido = c.execute("SELECT detalle, extract(epoch FROM now() - momento)::float8 FROM latido").fetchone()
            fallos = c.execute(
                """SELECT count(*) FROM eventos
                   WHERE tipo IN ('envio', 'consulta') AND momento > now() - interval '1 hour'
                     AND (detalle->>'accion' IN ('reintentar', 'error')
                          OR detalle->'codigo' NOT IN ('200'::jsonb, '201'::jsonb))"""
            ).fetchone()
        return {
            "eventos": [_fila(f) for f in historial],
            "latido": latido[0] if latido else None,
            "latido_hace_s": float(latido[1]) if latido else None,
            "fallos_transcribir_1h": int(fallos[0]) if fallos else 0,
        }

    def pedir_reintento(self, rid: str, usuario: str) -> bool | None:
        """«Reintentar» del panel (@a57): solo en una reunión en error y sin otra petición pendiente. None si no existe. Por la
        función `pedir_reintento` de la migración 0005: el rol del panel no tiene UPDATE de esas columnas."""
        with self.conexion() as c:
            fila = c.execute("SELECT pedir_reintento(%s, %s)", (rid, usuario)).fetchone()
        return fila[0] if fila else None

    def reintentos_pedidos(self) -> list[dict[str, Any]]:
        with self.conexion() as c, c.cursor(row_factory=dict_row) as cur:
            filas = cur.execute(
                "SELECT * FROM reuniones WHERE estado = 'error' AND reintento_pedido_en IS NOT NULL "
                "ORDER BY reintento_pedido_en, id"
            ).fetchall()
        return [_fila(f) for f in filas]

    def atender_reintento(self, rid: str, reenviar: bool, resultado: str) -> None:
        """El supervisor atiende la petición: con `reenviar`, error → grabada; si no, la reunión sigue en error. En los dos
        casos la petición se limpia y queda el evento `reintento` con quién lo pidió, en la misma transacción."""
        with self.conexion() as c:
            fila = c.execute(
                "SELECT reintento_pedido_por FROM reuniones WHERE id = %s AND estado = 'error' FOR UPDATE", (rid,)
            ).fetchone()
            if fila is None:
                return
            if reenviar:
                self._mover(c, rid, Estado.ERROR, Estado.GRABADA, motivo="reintento")
            else:
                c.execute("UPDATE reuniones SET reintento_pedido_en = NULL WHERE id = %s", (rid,))
            self._evento(c, rid, "reintento", {"usuario": fila[0], "resultado": resultado})

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
            self._mover(c, rid, Estado.TRANSCRIBIENDO, Estado.TRANSCRITA, detalle={"segmentos": len(segmentos)})
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

    def reunion_de_trabajo(self, trabajo_id: str) -> str | None:
        """La reunión que envió ese trabajo a transcribir (enlace de vuelta de su web, @a62); la más nueva si hubiera varias."""
        with self.conexion() as c:
            fila = c.execute(
                "SELECT id::text FROM reuniones WHERE trabajo_id = %s ORDER BY creado_en DESC, id DESC LIMIT 1", (trabajo_id,)
            ).fetchone()
        return fila[0] if fila else None

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

    def buscar(self, q: str, limite: int, quitar: str, poner: str, opciones: str) -> list[dict[str, Any]]:
        """@a22: los segmentos que casan con `websearch_to_tsquery('spanish', q)` (índice GIN de `tsv`), como mucho `limite`, y
        su resaltado. `ts_headline` va fuera del LIMIT («can be slow») y sobre `translate(texto, quitar, poner)`: sin centinelas
        propios y con `<`, `>` y `&` ocultos (busqueda.QUITAR y busqueda.PONER)."""
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
                          ts_headline('spanish', translate(h.texto, %(quitar)s, %(poner)s), q.q, %(opciones)s) AS fragmento
                   FROM hallados h, q
                   ORDER BY h.creado_en DESC, h.reunion_id, h.inicio_ms""",
                {"q": q, "limite": limite, "quitar": quitar, "poner": poner, "opciones": opciones},
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
        """La traza de la purga y, si es de una reunión, su evento `audio_borrado` en el historial."""
        with self.conexion() as c:
            c.execute(
                "INSERT INTO purgas (reunion_id, motivo, ficheros, bytes) VALUES (%s, %s, %s, %s)",
                (rid, motivo, ficheros, octetos),
            )
            if rid is not None:  # un directorio con nombre de uuid que no es de ninguna reunión no deja evento
                detalle = eventos.validar(
                    "audio_borrado", {"motivo": motivo, "ficheros": ficheros, "bytes": octetos}, self._secretos
                )
                c.execute(
                    "INSERT INTO eventos (reunion_id, tipo, detalle) SELECT id, 'audio_borrado', %s FROM reuniones WHERE id = %s",
                    (Jsonb(detalle), rid),
                )

    # ── Salas y socios (V2 de KubernetesInfrastructure#298, migración 0003) ──────────────────────────────────────────

    def crear_sala(self, nombre: str, room: str, hash_: str, cifrada: bytes, creada_por: str) -> str:
        """@a43: la contraseña llega ya cifrada (actas.salas). La fila `sala_creada` la pone un trigger de la base."""
        with self.conexion() as c:
            fila = c.execute(
                "INSERT INTO salas (nombre, room, hash, cifrada, creada_por) VALUES (%s, %s, %s, %s, %s) RETURNING id",
                (nombre, room, hash_, cifrada, creada_por),
            ).fetchone()
        assert fila is not None
        return str(fila[0])

    def salas(self) -> list[dict[str, Any]]:
        """Las salas, con cuántas reuniones se grabaron en cada una y la última, de la más usada a la menos."""
        with self.conexion() as c, c.cursor(row_factory=dict_row) as cur:
            filas = cur.execute(
                """SELECT s.id, s.nombre, s.room, s.hash, s.creada_en, s.creada_por,
                          count(r.id) AS reuniones, max(r.creado_en) AS ultima
                   FROM salas s LEFT JOIN reuniones r ON r.sala_id = s.id
                   GROUP BY s.id ORDER BY max(r.creado_en) DESC NULLS LAST, s.creada_en DESC"""
            ).fetchall()
        return [_fila(f) for f in filas]

    def sala(self, sid: str) -> dict[str, Any]:
        with self.conexion() as c, c.cursor(row_factory=dict_row) as cur:
            fila = cur.execute("SELECT id, nombre, room, hash, creada_en, creada_por FROM salas WHERE id = %s", (sid,)).fetchone()
        if fila is None:
            raise KeyError(sid)
        return _fila(fila)

    def ver_clave(self, sid: str, usuario: str) -> bytes | None:
        """@a45: la contraseña cifrada, y la fila `clave_vista` anotada en la misma transacción por la base. None si no existe."""
        with self.conexion() as c:
            fila = c.execute("SELECT ver_clave_sala(%s, %s)", (sid, usuario)).fetchone()
        return bytes(fila[0]) if fila and fila[0] is not None else None

    def eventos_de_sala(self, sid: str) -> list[dict[str, Any]]:
        with self.conexion() as c, c.cursor(row_factory=dict_row) as cur:
            filas = cur.execute(
                "SELECT tipo, usuario, momento FROM salas_eventos WHERE sala_id = %s ORDER BY momento, id", (sid,)
            ).fetchall()
        return [_fila(f) for f in filas]

    def cifrada_de_sala(self, sid: str) -> tuple[str, bytes] | None:
        """(room, contraseña cifrada) para el supervisor (@a46). Sin auditoría: es el grabador, no una persona."""
        with self.conexion() as c:
            fila = c.execute("SELECT room, cifrada FROM salas WHERE id = %s", (sid,)).fetchone()
        return (fila[0], bytes(fila[1])) if fila else None

    def ids_de_salas(self) -> list[tuple[str, str]]:
        """(id, room) de todas las salas: `actas.sh grabar` sin sala usa la única que haya."""
        with self.conexion() as c:
            filas = c.execute("SELECT id::text, room FROM salas ORDER BY creada_en").fetchall()
        return [(f[0], f[1]) for f in filas]

    def alta_socio(self, socio: Socio) -> None:
        with self.conexion() as c:
            c.execute("INSERT INTO socios (push, nombre, correo) VALUES (%s, %s, %s)", (socio.push, socio.nombre, socio.correo))

    def socios(self) -> list[dict[str, Any]]:
        """Todos, también los dados de baja: sus nombres siguen haciendo falta en las reuniones pasadas."""
        with self.conexion() as c, c.cursor(row_factory=dict_row) as cur:
            filas = cur.execute("SELECT push, nombre, correo, activo FROM socios ORDER BY push").fetchall()
        return [_fila(f) for f in filas]

    def socio_activo(self, push: str, activo: bool) -> bool:
        with self.conexion() as c:
            fila = c.execute("SELECT socio_activo(%s, %s)", (push, activo)).fetchone()
        return bool(fila and fila[0])

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
