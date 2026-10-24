"""La parada ordenada con StreamSaver (VDO.Ninja v30.2): la descarga EMPIEZA al empezar a grabar (Browser.downloadWillBegin) y
termina al parar (downloadProgress completed). La parada espera a que no quede ninguna a medias, no a descargas nuevas
(prueba de punta a punta de #223: esperaba 45 s y daba la parada por incompleta con todo descargado)."""

import time
from pathlib import Path

from actas.grabador import Grabacion, Sala


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
