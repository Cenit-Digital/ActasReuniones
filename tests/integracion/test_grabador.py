"""El grabador con un Chromium real (la misma imagen que en el clúster, en la CI) y una sala falsa servida en local: abre
una página por socio con la URL de VDO.Ninja, lee los streams de la sala y, al parar, cada página descarga su
`<id>_<ms>.webm` en el directorio de la reunión. `ACTAS_CHROMIUM` = ruta del binario; sin ella, el test se salta."""

import functools
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from actas.cdp import Cdp
from actas.grabador import Grabacion, Sala
from actas.pistas import pistas_de
from actas.registro import Registro

SALA_FALSA = Path(__file__).parent / "sala_falsa"


@pytest.fixture
def sala_falsa():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(SimpleHTTPRequestHandler, directory=str(SALA_FALSA)))
    srv.RequestHandlerClass.log_message = lambda *a: None
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}/"
    srv.shutdown()


def paginas_de(cdp, base):
    return [t for t in cdp.enviar("Target.getTargets")["targetInfos"] if t["url"].startswith(base)]


def test_grabar_vistos_y_parada_ordenada(chromium, sala_falsa, tmp_path):
    sala = Sala("salaprueba", "clave secreta", base=sala_falsa + "?publican=socioa,x7kq2lm&retardo=1500&")
    lineas: list[str] = []
    cdp = Cdp(chromium, Registro([sala.clave]))
    g = Grabacion(cdp, sala, ("socioa", "sociob"), tmp_path / "reunion", lambda *p: lineas.append(" ".join(map(str, p))))
    g.empezar()
    time.sleep(2)
    assert g.vistos() == {"socioa": ["socioa", "x7kq2lm"], "sociob": ["socioa", "x7kq2lm"]}
    assert g.parar() is True
    ficheros = sorted(p.name for p in (tmp_path / "reunion").iterdir())
    assert [p.socio for p in pistas_de(ficheros, ["socioa", "sociob"])] == sorted(["socioa", "sociob"])
    assert (tmp_path / "reunion" / ficheros[0]).read_bytes().startswith(b"opus de ")
    assert not any("clave" in linea for linea in lineas)
    assert not paginas_de(cdp, sala_falsa)  # las páginas de la sala se cerraron
    cdp.cerrar()


def test_parar_sin_ninguna_grabacion_no_es_un_exito(chromium, sala_falsa, tmp_path):
    sala = Sala("salaprueba", "clave", base=sala_falsa + "?sinpar&")
    cdp = Cdp(chromium, Registro())
    g = Grabacion(cdp, sala, ("socioa",), tmp_path / "r", lambda *p: None)
    g.empezar()
    time.sleep(1)
    assert g.parar() is False
    cdp.cerrar()


def test_si_falla_una_pagina_al_empezar_se_cierran_las_ya_abiertas(chromium, sala_falsa, tmp_path):
    sala = Sala("salaprueba", "clave", base=sala_falsa + "?")
    cdp = Cdp(chromium, Registro())
    original, n = cdp.pagina, []

    def pagina(*a, **k):
        n.append(1)
        if len(n) == 2:
            raise RuntimeError("Target.createTarget: error de CDP")
        return original(*a, **k)

    cdp.pagina = pagina
    g = Grabacion(cdp, sala, ("socioa", "sociob"), tmp_path / "r", lambda *p: None)
    with pytest.raises(RuntimeError):
        g.empezar()
    assert not paginas_de(cdp, sala_falsa)
    assert cdp.enviar("Browser.setDownloadBehavior", {"behavior": "deny"}) == {}  # Chromium sigue usable
    cdp.cerrar()


def test_reanudar_y_parar_las_paginas_de_un_supervisor_anterior(chromium, sala_falsa, tmp_path):
    sala = Sala("salaprueba", "clave", base=sala_falsa + "?retardo=500&")
    cdp = Cdp(chromium, Registro())
    primera = Grabacion(cdp, sala, ("socioa",), tmp_path / "r", lambda *p: None)
    primera.empezar()  # y el supervisor «muere» sin parar
    time.sleep(1)
    cdp.cerrar()
    cdp2 = Cdp(chromium, Registro())
    rescate = Grabacion(cdp2, sala, ("socioa",), tmp_path / "r", lambda *p: None)
    rescate.reanudar()
    assert list(rescate.paginas) == ["socioa"]
    assert rescate.parar() is True
    assert [p.name.split("_")[0] for p in (tmp_path / "r").iterdir()] == ["socioa"]
    cdp2.cerrar()


def test_el_grabador_de_un_socio_que_colgo_se_para_igual_y_su_descarga_termina(chromium, sala_falsa, tmp_path):
    """@a63. Reunión del 2026-10-30: los socios colgaron 9 s antes de «Parar», su par salió de session.rpcs y la
    parada no encontró ningún grabador («grabaciones paradas: 0»): solo quedaron dos `.crdownload`. Con GRABADORES_JS
    la parada los encuentra."""
    sala = Sala("salaprueba", "clave", base=sala_falsa + "?elemento&colgado=300&retardo=300&")
    cdp = Cdp(chromium, Registro())
    g = Grabacion(cdp, sala, ("socioa", "sociob"), tmp_path / "r", lambda *p: None)
    g.empezar()
    time.sleep(1.5)  # ya colgaron
    assert g.parar() is True
    ficheros = sorted(p.name for p in (tmp_path / "r").iterdir())
    assert [p.socio for p in pistas_de(ficheros, ["socioa", "sociob"])] == ["socioa", "sociob"]
    cdp.cerrar()


def test_vigilar_para_el_grabador_huerfano_a_la_segunda_vuelta_y_nunca_el_vigente(chromium, sala_falsa, tmp_path):
    """@a63. El socio que cuelga a mitad de reunión (la del 2026-10-28 perdió así a uno): su grabador se para a la
    segunda vigilancia sin par, y su pista queda entera aunque la reunión siga. El de un socio que sigue en la sala no se toca."""
    colgado = Sala("salaprueba", "clave", base=sala_falsa + "?elemento&colgado=300&")
    vigente = Sala("salaprueba", "clave", base=sala_falsa + "?elemento&")
    cdp = Cdp(chromium, Registro())
    lineas: list[str] = []
    g = Grabacion(cdp, colgado, ("socioa",), tmp_path / "r", lambda *p: lineas.append(" ".join(map(str, p))))
    g.empezar()
    h = Grabacion(cdp, vigente, ("sociob",), tmp_path / "s", lambda *p: None)
    h.empezar()
    time.sleep(1.5)
    paradas = "(window.__paradas || 0)"
    assert g.vigilar() == {"socioa": 1}  # primera vuelta sin par: aún no
    assert cdp.evaluar(g.paginas["socioa"][1], paradas) == 0
    assert g.vigilar() == {"socioa": 0}  # segunda: se para
    assert cdp.evaluar(g.paginas["socioa"][1], paradas) == 1
    assert any("huérfanas paradas: 1" in linea for linea in lineas)
    assert g.vigilar() == {"socioa": 0}  # ya parado: no se para dos veces
    assert cdp.evaluar(g.paginas["socioa"][1], paradas) == 1
    for _ in range(3):
        assert h.vigilar() == {"sociob": 1}
    assert cdp.evaluar(h.paginas["sociob"][1], paradas) == 0
    assert h.parar() is True and g.parar() is True
    assert [p.name.split("_")[0] for p in (tmp_path / "r").iterdir()] == ["socioa"]
    cdp.cerrar()


def test_la_pagina_sigue_viendo_el_recorder_como_vdo_ninja(chromium, sala_falsa, tmp_path):
    """GRABADORES_JS no cambia lo que VDO.Ninja lee: tras `delete video.recorder` el elemento ya no graba, y una grabación
    nueva vuelve a quedar anotada."""
    sala = Sala("salaprueba", "clave", base=sala_falsa + "?elemento&")
    cdp = Cdp(chromium, Registro())
    g = Grabacion(cdp, sala, ("socioa",), tmp_path / "r", lambda *p: None)
    g.empezar()
    time.sleep(1)
    ses = g.paginas["socioa"][1]
    js = """(() => { const v = session.rpcs.u1.videoElement; const antes = typeof v.recorder.stop;
      v.recorder.stop(); const tras = v.recorder; v.recorder = {stop() {}}; const otra = typeof v.recorder.stop;
      return [antes, tras === undefined, otra, window.__grabadores.size, Object.keys(v).includes('recorder')]; })()"""
    assert cdp.evaluar(ses, js) == ["function", True, "function", 1, True]
    g.parar()
    cdp.cerrar()


def test_url_de_la_pagina_espectadora():
    url = Sala("sala", "clave é&x", salt="reuniones.cenitdigital.es").url("sociopablo")
    assert url.startswith(
        "https://reuniones.cenitdigital.es/?room=sala&password=clave%20%C3%A9%26x&salt=reuniones.cenitdigital.es"
    )
    assert url.endswith("&relay&tcp&cleanoutput&scene&view=sociopablo&label=sociopablo&autorecordremote=-64&novideo")


@pytest.mark.parametrize(("room", "clave"), [("", "clave"), ("sala", ""), ("", "")])
def test_sin_room_o_sin_contrasena_no_hay_pagina_espectadora(room, clave):
    # SALA_RESCATE solo sirve para retomar y parar: nunca abre una página (sería la sala pública, sin contraseña).
    with pytest.raises(ValueError):
        Sala(room, clave).url("sociopablo")
