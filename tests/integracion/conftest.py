"""PostgreSQL de pruebas: `export ACTAS_DSN_PRUEBAS="$(scripts/pg-pruebas.sh arrancar)"`. Sin él, estos tests se saltan
(la CI los ejecuta siempre: ver harness-ci.yml)."""

import os
import uuid

import psycopg
import pytest

from actas import base


@pytest.fixture
def dsn():
    dsn = os.environ.get("ACTAS_DSN_PRUEBAS")
    if not dsn:
        pytest.skip("sin ACTAS_DSN_PRUEBAS")
    esquema = "actas_" + uuid.uuid4().hex[:8]
    with psycopg.connect(dsn, autocommit=True) as c:
        c.execute(f"CREATE SCHEMA {esquema}")
    try:
        yield dsn, esquema
    finally:
        with psycopg.connect(dsn, autocommit=True) as c:
            c.execute(f"DROP SCHEMA {esquema} CASCADE")


@pytest.fixture
def repo(dsn):
    url, esquema = dsn
    base.migrar(url, esquema)
    r = base.Repositorio(url, esquema)
    yield r
    r.cerrar()
