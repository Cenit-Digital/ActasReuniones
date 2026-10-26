"""PostgreSQL de pruebas: `export ACTAS_DSN_PRUEBAS="$(scripts/pg-pruebas.sh arrancar)"`. Sin él, estos tests se saltan
(la CI los ejecuta siempre: ver harness-ci.yml)."""

import os
import uuid

import psycopg
import psycopg.conninfo
import pytest

from actas import base


@pytest.fixture
def dsn():
    dsn = os.environ.get("ACTAS_DSN_PRUEBAS")
    if not dsn:
        pytest.skip("sin ACTAS_DSN_PRUEBAS")
    esquema = "actas_" + uuid.uuid4().hex[:8]
    with psycopg.connect(dsn, autocommit=True) as c:
        # El rol del panel lo crea KubernetesInfrastructure (Job inquilinos) antes de la migración 0002, que le da permisos. Es
        # de todo el clúster: con contraseña, porque en la CI el servidor la exige (scram); en local, con trust, no se mira.
        c.execute(
            "DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'actas_panel') THEN "
            "CREATE ROLE actas_panel LOGIN NOINHERIT PASSWORD 'pruebas'; END IF; END $$"
        )
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


@pytest.fixture
def repo_panel(dsn, repo):
    """El repositorio con el rol del panel, sobre el mismo esquema ya migrado."""
    url, esquema = dsn
    r = base.Repositorio(psycopg.conninfo.make_conninfo(url, user="actas_panel", password="pruebas"), esquema)
    yield r
    r.cerrar()
