"""Un solo supervisor a la vez (actas.turno): el de un pod nuevo espera a que termine el de un pod que drena, con un candado
consultivo de PostgreSQL de verdad."""

import threading

import psycopg

from actas.drenaje import Drenaje
from actas.metricas import Metricas
from actas.registro import Registro
from actas.turno import esperar_turno

CLAVE = 0x7072756562  # una clave propia: los tests no chocan con un supervisor de verdad


class FinTrasVueltas(threading.Event):
    """El SIGTERM del proceso: llega tras unas vueltas de espera; en cada una puede pasar algo."""

    def __init__(self, vueltas, en_cada=lambda n: None):
        super().__init__()
        self.vueltas, self.en_cada, self.n = vueltas, en_cada, 0

    def wait(self, timeout=None):
        self.n += 1
        self.en_cada(self.n)
        if self.n >= self.vueltas:
            self.set()
        return self.is_set()


def _conectar(dsn):
    url, _ = dsn
    return lambda: psycopg.connect(url, autocommit=True)


def test_sin_otro_supervisor_toma_el_candado_enseguida(dsn, tmp_path):
    c = esperar_turno(_conectar(dsn), Drenaje(tmp_path), Metricas(), Registro(), FinTrasVueltas(1), clave=CLAVE)
    assert c is not None
    c.close()


def test_espera_mientras_el_otro_vive_y_toma_el_relevo_cuando_sale(dsn, tmp_path):
    viejo = _conectar(dsn)()
    viejo.execute("SELECT pg_advisory_lock(%s)", (CLAVE,))
    metricas = Metricas()

    def en_cada(n):
        assert metricas.ultimo_paso_s > 0  # sigue vivo para la sonda mientras espera
        if n == 3:
            viejo.close()  # el pod viejo terminó de drenar y su proceso salió

    fin = FinTrasVueltas(10, en_cada)
    c = esperar_turno(_conectar(dsn), Drenaje(tmp_path), metricas, Registro(), fin, clave=CLAVE)
    assert c is not None and fin.n == 3
    c.close()


def test_si_su_propio_pod_se_para_mientras_espera_da_el_drenaje_por_hecho(dsn, tmp_path):
    viejo = _conectar(dsn)()
    viejo.execute("SELECT pg_advisory_lock(%s)", (CLAVE,))
    d = Drenaje(tmp_path)
    try:
        fin = FinTrasVueltas(10, lambda n: d.pedir() if n == 2 else None)
        assert esperar_turno(_conectar(dsn), d, Metricas(), Registro(), fin, clave=CLAVE) is None
        assert d.hecho() and fin.n == 2  # el preStop de este pod no espera horas a un bucle que no ha empezado
    finally:
        viejo.close()


def test_sigterm_mientras_espera_sale_sin_el_candado(dsn, tmp_path):
    viejo = _conectar(dsn)()
    viejo.execute("SELECT pg_advisory_lock(%s)", (CLAVE,))
    try:
        assert esperar_turno(_conectar(dsn), Drenaje(tmp_path), Metricas(), Registro(), FinTrasVueltas(2), clave=CLAVE) is None
    finally:
        viejo.close()
