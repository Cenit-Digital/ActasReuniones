"""@a6, @a8 y @a10 contra PostgreSQL de verdad: el bus de peticiones y el archivo de la reunión."""

import psycopg
import pytest

from actas import base
from actas.conformidad import Peticion
from actas.estados import Estado, TransicionNoValida


def test_migrar_es_idempotente(dsn):
    url, esquema = dsn
    assert base.migrar(url, esquema) == ["0001_esquema.sql"]
    assert base.migrar(url, esquema) == []


def test_pedir_guarda_una_conformidad_por_socio_con_version(repo):
    rid = repo.pedir(Peticion(("sociopablo", "socioroberto"), "v1"))
    r = repo.reunion(rid)
    assert r["estado"] == "pedida" and r["socios"] == ["sociopablo", "socioroberto"]
    assert repo.conformidades(rid) == [("sociopablo", "v1"), ("socioroberto", "v1")]


def test_la_base_rechaza_una_reunion_sin_socios(repo):
    with pytest.raises(psycopg.errors.CheckViolation), repo.conexion() as c:
        c.execute("INSERT INTO reuniones (socios, texto_version) VALUES ('{}', 'v1')")


def test_siguiente_pedida_por_orden_de_llegada(repo):
    a = repo.pedir(Peticion(("socioa",), "v1"))
    repo.pedir(Peticion(("sociob",), "v1"))
    assert repo.siguiente(Estado.PEDIDA)["id"] == a


def test_mover_comprueba_el_estado_de_origen(repo):
    rid = repo.pedir(Peticion(("socioa",), "v1"))
    repo.mover(rid, Estado.PEDIDA, Estado.GRABANDO, inicio=True)
    assert repo.reunion(rid)["inicio"] is not None
    with pytest.raises(TransicionNoValida):
        repo.mover(rid, Estado.PEDIDA, Estado.GRABANDO)  # ya no está en pedida
    with pytest.raises(TransicionNoValida):
        repo.mover(rid, Estado.GRABANDO, Estado.TRANSCRITA)  # no es una transición del modelo


def test_solo_una_grabacion_activa(repo):
    a = repo.pedir(Peticion(("socioa",), "v1"))
    b = repo.pedir(Peticion(("sociob",), "v1"))
    repo.mover(a, Estado.PEDIDA, Estado.GRABANDO)
    with pytest.raises(psycopg.errors.UniqueViolation):
        repo.mover(b, Estado.PEDIDA, Estado.GRABANDO)


def test_pedir_parada_de_la_grabacion_activa(repo):
    rid = repo.pedir(Peticion(("socioa",), "v1"))
    assert repo.pedir_parada() is None
    repo.mover(rid, Estado.PEDIDA, Estado.GRABANDO)
    assert repo.pedir_parada() == rid
    assert repo.reunion(rid)["parar_pedido_en"] is not None


def test_guardar_transcripcion_copia_segmentos_y_pasa_a_transcrita(repo):
    rid = repo.pedir(Peticion(("socioa", "sociob"), "v1"))
    for d, h in [
        (Estado.PEDIDA, Estado.GRABANDO),
        (Estado.GRABANDO, Estado.GRABADA),
        (Estado.GRABADA, Estado.TRANSCRIBIENDO),
    ]:
        repo.mover(rid, d, h)
    segmentos = [
        {"hablante": "sociob", "inicio_ms": 5000, "fin_ms": 6000, "texto": "el presupuesto de octubre"},
        {"hablante": "socioa", "inicio_ms": 1000, "fin_ms": 2000, "texto": "Doy mi conformidad para grabar"},
    ]
    repo.guardar_transcripcion(rid, segmentos)
    assert repo.reunion(rid)["estado"] == "transcrita"
    assert [s[0] for s in repo.segmentos(rid)] == ["socioa", "sociob"]
    with repo.conexion() as c:
        n = c.execute("SELECT count(*) FROM segmentos WHERE tsv @@ plainto_tsquery('spanish', 'presupuestos')").fetchone()
    assert n == (1,)


def test_guardar_transcripcion_reintentada_no_duplica(repo):
    rid = repo.pedir(Peticion(("socioa",), "v1"))
    for d, h in [
        (Estado.PEDIDA, Estado.GRABANDO),
        (Estado.GRABANDO, Estado.GRABADA),
        (Estado.GRABADA, Estado.TRANSCRIBIENDO),
    ]:
        repo.mover(rid, d, h)
    seg = [{"hablante": "socioa", "inicio_ms": 0, "fin_ms": 1, "texto": "hola"}]
    repo.guardar_transcripcion(rid, seg)
    with pytest.raises(TransicionNoValida):
        repo.guardar_transcripcion(rid, seg)
    assert len(repo.segmentos(rid)) == 1


def test_error_y_reintento(repo):
    rid = repo.pedir(Peticion(("socioa",), "v1"))
    repo.mover(rid, Estado.PEDIDA, Estado.GRABANDO)
    repo.mover(rid, Estado.GRABANDO, Estado.GRABADA)
    repo.mover(rid, Estado.GRABADA, Estado.ERROR, motivo="token")
    assert repo.reunion(rid)["motivo"] == "token"
    assert repo.reintentar(rid) is True
    assert repo.reunion(rid)["estado"] == "grabada"
    assert repo.reintentar(rid) is False


def test_traza_de_purga_sin_nombres(repo):
    repo.anotar_purga(None, "huerfano", 2, 1234)
    with repo.conexion() as c:
        assert c.execute("SELECT motivo, ficheros, bytes FROM purgas").fetchall() == [("huerfano", 2, 1234)]


def test_cuenta_por_estado(repo):
    repo.pedir(Peticion(("socioa",), "v1"))
    assert repo.cuenta_por_estado() == {"pedida": 1}
