"""La parada ordenada con StreamSaver (VDO.Ninja v30.2): la descarga EMPIEZA al empezar a grabar (Browser.downloadWillBegin) y
termina al parar (downloadProgress completed). La parada espera a que no quede ninguna a medias, no a descargas nuevas
(prueba de punta a punta de #223: esperaba 45 s y daba la parada por incompleta con todo descargado)."""

import time
from pathlib import Path

import pytest

from actas.grabador import Grabacion, Sala, Vigilancia


class CdpFalso:
    def __init__(self, descargas_al_empezar, completar_al_parar=True):
        self.manejadores = []
        self.nombres = {}
        self.vivo = True
        self._al_empezar = descargas_al_empezar
        self._completar = completar_al_parar
        self.guids = []

    def _emitir(self, metodo, **params):
        for h in list(self.manejadores):
            h({"method": metodo, "params": params})

    def enviar(self, metodo, params=None, sesion=None, espera=30):
        if metodo == "Target.getTargets":
            return {"targetInfos": []}
        return {}

    def pagina(self, url, antes=(), nombre=""):
        if self._al_empezar:
            guid = f"g{len(self.guids)}"
            self.guids.append(guid)
            self._emitir("Browser.downloadWillBegin", guid=guid, suggestedFilename=f"{nombre}_1.webm")
        return (f"t-{nombre}", f"s-{nombre}")

    def evaluar(self, sesion, expr, espera=30):
        if self._completar:
            for guid in self.guids:
                self._emitir("Browser.downloadProgress", guid=guid, state="completed", receivedBytes=10)
        return 1

    def cerrar_pagina(self, target):
        pass


def grabacion(cdp, tmp_path):
    return Grabacion(cdp, Sala("s", "c"), ("socioa", "sociob"), Path(tmp_path) / "r", lambda *p: None)


def test_descargas_empezadas_al_grabar_y_completadas_al_parar(tmp_path, monkeypatch):
    monkeypatch.setattr("actas.grabador.ESPERA_DESCARGAS_S", 3)
    g = grabacion(CdpFalso(descargas_al_empezar=True), tmp_path)
    g.empezar()
    t0 = time.monotonic()
    assert g.parar() is True
    assert time.monotonic() - t0 < 2  # no agota el plazo


def test_una_descarga_que_no_termina_no_es_un_exito(tmp_path, monkeypatch):
    monkeypatch.setattr("actas.grabador.ESPERA_DESCARGAS_S", 1)
    g = grabacion(CdpFalso(descargas_al_empezar=True, completar_al_parar=False), tmp_path)
    g.empezar()
    assert g.parar() is False


def test_sin_descargas_no_es_un_exito(tmp_path, monkeypatch):
    monkeypatch.setattr("actas.grabador.ESPERA_DESCARGAS_S", 1)
    g = grabacion(CdpFalso(descargas_al_empezar=False, completar_al_parar=False), tmp_path)
    g.empezar()
    assert g.parar() is False


EBML = bytes.fromhex("1a45dfa3")


def test_una_descarga_a_medias_se_rescata_antes_de_cerrar_y_no_es_un_exito(tmp_path, monkeypatch):
    """@a64. Reunión del 2026-10-30: la parada no encontró grabadores y quedaron dos `.crdownload` de 55 min que se
    ignoraron. Ahora se enlazan a su nombre final (webm válido hasta el último trozo) antes de cerrar las páginas."""
    monkeypatch.setattr("actas.grabador.ESPERA_DESCARGAS_S", 1)
    cdp = CdpFalso(descargas_al_empezar=True, completar_al_parar=False)
    cerradas_con: list[list[str]] = []
    cdp.cerrar_pagina = lambda t: cerradas_con.append(sorted(p.name for p in (Path(tmp_path) / "r").iterdir()))
    g = grabacion(cdp, tmp_path)
    g.empezar()
    d = Path(tmp_path) / "r"
    (d / "socioa_1.webm.crdownload").write_bytes(EBML + b"opus")
    assert g.parar() is False  # puede faltar el final: nunca es un éxito
    assert g.rescatadas == 1
    assert sorted(p.name for p in d.iterdir()) == ["socioa_1.webm"]
    assert (d / "socioa_1.webm").read_bytes() == EBML + b"opus"
    assert "socioa_1.webm" in cerradas_con[0]  # enlazada antes de cerrar: Chromium no puede borrarla


@pytest.mark.parametrize(
    ("nombre", "contenido"),
    [
        ("socioa_1.webm.crdownload", b""),  # vacía
        ("socioa_1.webm.crdownload", b"no es webm"),
        ("Unconfirmed 1.crdownload", EBML),  # sin nombre de grabación
    ],
)
def test_lo_que_no_es_un_webm_a_medias_no_se_rescata(tmp_path, monkeypatch, nombre, contenido):
    monkeypatch.setattr("actas.grabador.ESPERA_DESCARGAS_S", 0)
    g = grabacion(CdpFalso(descargas_al_empezar=True, completar_al_parar=False), tmp_path)
    g.empezar()
    (Path(tmp_path) / "r" / nombre).write_bytes(contenido)
    assert g.parar() is False
    assert g.rescatadas == 0
    assert sorted(p.name for p in (Path(tmp_path) / "r").iterdir()) == [nombre]


def test_no_se_pisa_una_pista_que_ya_termino(tmp_path, monkeypatch):
    monkeypatch.setattr("actas.grabador.ESPERA_DESCARGAS_S", 0)
    g = grabacion(CdpFalso(descargas_al_empezar=True, completar_al_parar=False), tmp_path)
    g.empezar()
    d = Path(tmp_path) / "r"
    (d / "socioa_1.webm").write_bytes(EBML + b"entera")
    (d / "socioa_1.webm.crdownload").write_bytes(EBML + b"otra")
    g.parar()
    assert g.rescatadas == 0
    assert (d / "socioa_1.webm").read_bytes() == EBML + b"entera"
    assert (d / "socioa_1.webm.crdownload").exists()


def test_un_enlace_simbolico_no_se_rescata(tmp_path, monkeypatch):
    monkeypatch.setattr("actas.grabador.ESPERA_DESCARGAS_S", 0)
    fuera = Path(tmp_path) / "fuera"
    fuera.write_bytes(EBML)
    g = grabacion(CdpFalso(descargas_al_empezar=True, completar_al_parar=False), tmp_path)
    g.empezar()
    (Path(tmp_path) / "r" / "socioa_1.webm.crdownload").symlink_to(fuera)
    g.parar()
    assert g.rescatadas == 0 and not (Path(tmp_path) / "r" / "socioa_1.webm").exists()


def test_vigilar_dice_si_el_socio_esta_conectado(tmp_path):
    cdp = CdpFalso(descargas_al_empezar=False)
    g = Grabacion(cdp, Sala("s", "c"), ("socioa",), Path(tmp_path) / "r", lambda *p: None)
    g.empezar()
    cdp.evaluar = lambda *a, **k: {"grabando": 0, "parados": 0, "pares": 1}
    assert g.vigilar() == {"socioa": Vigilancia(0, True)}


def test_vigilar_cuenta_cero_si_la_pagina_no_responde(tmp_path):
    lineas: list[str] = []
    cdp = CdpFalso(descargas_al_empezar=False)
    g = Grabacion(cdp, Sala("s", "c"), ("socioa",), Path(tmp_path) / "r", lambda *p: lineas.append(" ".join(map(str, p))))
    g.empezar()

    def falla(*a, **k):
        raise TimeoutError

    cdp.evaluar = falla
    assert g.vigilar() == {"socioa": Vigilancia(0, False)}
    assert lineas[-1] == "socioa vigilar grabadores: TimeoutError"


def test_vigilar_anota_los_huerfanos_parados(tmp_path):
    lineas: list[str] = []
    cdp = CdpFalso(descargas_al_empezar=False)
    g = Grabacion(cdp, Sala("s", "c"), ("socioa",), Path(tmp_path) / "r", lambda *p: lineas.append(" ".join(map(str, p))))
    g.empezar()
    cdp.evaluar = lambda *a, **k: {"grabando": 0, "parados": 1, "pares": 0}
    assert g.vigilar() == {"socioa": Vigilancia(0, False)}
    assert lineas[-1] == "socioa grabaciones huérfanas paradas: 1"
