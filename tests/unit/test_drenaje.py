"""Parada ordenada del pod (preStop `python -m actas.drenaje`): pide el drenaje y espera a que el supervisor lo dé por hecho, sin
retrasar el reinicio de un supervisor colgado."""

from actas.drenaje import Drenaje, del_entorno, esperar, salud_local


def test_pide_el_drenaje_y_espera_a_que_el_supervisor_lo_de_por_hecho(tmp_path):
    d = Drenaje(tmp_path)
    vueltas = []

    def dormir(s):
        vueltas.append(s)
        assert d.pedido()  # el supervisor ve la marca mientras el preStop espera
        if len(vueltas) == 3:
            d.anotar_hecho()

    assert esperar(d, lambda: True, dormir) == "drenado"
    assert vueltas == [5, 5, 5]


def test_supervisor_colgado_no_se_espera_ni_se_deja_la_marca(tmp_path):
    d = Drenaje(tmp_path)
    assert esperar(d, lambda: False, lambda s: None) == "sin_supervisor"
    assert not d.pedido()  # un reinicio por la sonda de vida no deja el supervisor sin grabar


def test_si_el_supervisor_se_cuelga_mientras_drena_deja_de_esperar(tmp_path):
    d = Drenaje(tmp_path)
    respuestas = iter([True, True, False])
    assert esperar(d, lambda: next(respuestas), lambda s: None) == "sin_supervisor"


def test_limpiar_quita_las_marcas_de_un_reinicio_del_contenedor(tmp_path):
    d = Drenaje(tmp_path)
    d.pedir()
    d.anotar_hecho()
    d.limpiar()
    assert not d.pedido() and not d.hecho()
    d.limpiar()  # sin marcas no falla


def test_del_entorno_lee_el_directorio_de_las_marcas(tmp_path):
    d = del_entorno({"ACTAS_DRENAJE": str(tmp_path)})
    d.pedir()
    assert (tmp_path / "actas-drenar").exists()


def test_salud_local_sin_supervisor_es_falsa():
    assert salud_local(1)() is False  # nadie escucha en el puerto 1


def test_salud_local_con_el_servidor_de_metricas():
    import time

    from actas.metricas import Metricas, servir

    m = Metricas()
    srv = servir(m, 0)
    try:
        salud = salud_local(srv.server_address[1])
        assert salud() is False  # todavía sin ninguna vuelta: 503
        m.ultimo_paso_s = time.time()
        assert salud() is True
    finally:
        srv.shutdown()
