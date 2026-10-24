"""@a25: las métricas del supervisor solo llevan números y se sirven en /metricas."""

import urllib.error
import urllib.request

import pytest

from actas.metricas import Metricas, servir


def test_texto_con_los_valores_y_un_estado_por_linea():
    m = Metricas()
    m.aviso_sin_coincidencia = 1
    m.sumar("errores_total", 2)
    m.por_estado = {"error": 2, "transcrita": 5}
    m.grabaciones_bytes = 1234
    t = m.texto()
    assert "actas_aviso_sin_coincidencia 1\n" in t
    assert "actas_errores_total 2\n" in t
    assert 'actas_reuniones{estado="error"} 2\n' in t
    assert 'actas_reuniones{estado="pedida"} 0\n' in t
    assert "actas_grabaciones_bytes 1234\n" in t


def test_servir_solo_metricas():
    m = Metricas()
    srv = servir(m, 0)
    puerto = srv.server_address[1]
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{puerto}/metricas") as r:
            assert r.status == 200 and b"actas_grabando 0" in r.read()
        with pytest.raises(urllib.error.HTTPError):
            urllib.request.urlopen(f"http://127.0.0.1:{puerto}/")
    finally:
        srv.shutdown()


def test_salud_depende_de_la_ultima_vuelta():
    m = Metricas()
    srv = servir(m, 0, reloj=lambda: 1000.0)
    url = f"http://127.0.0.1:{srv.server_address[1]}/salud"
    try:
        with pytest.raises(urllib.error.HTTPError) as e:  # aún no ha dado ninguna vuelta
            urllib.request.urlopen(url)
        assert e.value.code == 503
        m.ultimo_paso_s = 1000.0 - 299
        with urllib.request.urlopen(url) as r:
            assert r.status == 200
        m.ultimo_paso_s = 1000.0 - 301
        with pytest.raises(urllib.error.HTTPError):
            urllib.request.urlopen(url)
    finally:
        srv.shutdown()
