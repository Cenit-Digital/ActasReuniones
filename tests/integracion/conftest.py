"""PostgreSQL de pruebas: `export ACTAS_DSN_PRUEBAS="$(scripts/pg-pruebas.sh arrancar)"`. Sin él, estos tests se saltan
(la CI los ejecuta siempre: ver harness-ci.yml). Y el Chromium de los tests del grabador y del panel (`ACTAS_CHROMIUM`)."""

import os
import subprocess
import tempfile
import time
import urllib.request
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
        # El rol del supervisor y los privilegios por defecto del inquilino, como en KubernetesInfrastructure
        # (kubernetes/postgres/inquilinos.sql): lo que crea el dueño del esquema llega a actas_app con SELECT, INSERT y UPDATE.
        c.execute(
            "DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'actas_app') THEN "
            "CREATE ROLE actas_app LOGIN NOINHERIT PASSWORD 'pruebas'; END IF; END $$"
        )
        c.execute(f"GRANT USAGE ON SCHEMA {esquema} TO actas_app")
        c.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA {esquema} GRANT SELECT, INSERT, UPDATE ON TABLES TO actas_app")
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


@pytest.fixture
def chromium():
    """El navegador de los tests de Chromium (grabador y panel): `ACTAS_CHROMIUM` = ruta del binario; sin ella, se salta."""
    binario = os.environ.get("ACTAS_CHROMIUM")
    if not binario:
        pytest.skip("sin ACTAS_CHROMIUM")
    perfil = tempfile.mkdtemp()
    proc = subprocess.Popen(  # noqa: S603
        [
            binario,
            "--headless=new",
            "--no-sandbox",
            "--disable-gpu",
            "--remote-debugging-port=9333",
            f"--user-data-dir={perfil}",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(100):
        try:
            urllib.request.urlopen("http://127.0.0.1:9333/json/version", timeout=1)  # noqa: S310
            break
        except OSError:
            time.sleep(0.1)
    yield "http://127.0.0.1:9333"
    proc.terminate()
    proc.wait(10)


@pytest.fixture
def repo_app(dsn, repo):
    """El repositorio con el rol del supervisor (y de `actas.sh`), sobre el mismo esquema ya migrado."""
    url, esquema = dsn
    r = base.Repositorio(psycopg.conninfo.make_conninfo(url, user="actas_app", password="pruebas"), esquema)
    yield r
    r.cerrar()
