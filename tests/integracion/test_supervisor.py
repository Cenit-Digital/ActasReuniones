"""@a6, @a7, @a8, @a10, @a24 y @a25: el supervisor de punta a punta con PostgreSQL de verdad y la plataforma y el grabador
falsos (sin Chromium ni red)."""

from pathlib import Path

import pytest

from actas.conformidad import Peticion
from actas.estados import TOPE_GRABACION_S
from actas.metricas import Metricas
from actas.purga import PLAZO_AUDIO_S
from actas.registro import Registro
from actas.supervisor import Supervisor

TID = "1b4e28ba-2fa1-11d2-883f-0016d3cca427"


class GrabacionFalsa:
    creadas: list["GrabacionFalsa"] = []

    def __init__(self, socios, destino: Path):
        self.socios, self.destino = socios, destino
        self.empezada = self.parada = False
        self.ver: dict[str, list[str]] = {s: [s] for s in socios}
        GrabacionFalsa.creadas.append(self)

    def empezar(self):
        self.destino.mkdir(parents=True, exist_ok=True)
        self.empezada = True

    def vistos(self):
        return self.ver

    def parar(self):
        self.parada = True
        for n, s in enumerate(self.socios):
            (self.destino / f"{s}_{1000 + 500 * n}.webm").write_bytes(b"opus")
        return True


class PlataformaFalsa:
    def __init__(self):
        self.creaciones: list[tuple] = []
        self.respuesta_crear = (201, {"id": TID})
        self.respuestas_estado = [(200, {"trabajo": {"estado": "en_cola"}})]

    def crear(self, directorio, pistas, referencia):
        self.creaciones.append((directorio, pistas, referencia))
        return self.respuesta_crear

    def estado(self, trabajo_id):
        return self.respuestas_estado.pop(0) if len(self.respuestas_estado) > 1 else self.respuestas_estado[0]


class Reloj:
    def __init__(self):
        self.t = 1_000_000.0

    def __call__(self):
        return self.t


@pytest.fixture
def entorno(repo, tmp_path):
    GrabacionFalsa.creadas = []
    reloj, plataforma, metricas = Reloj(), PlataformaFalsa(), Metricas()
    sup = Supervisor(
        repo=repo,
        plataforma=plataforma,
        nueva_grabacion=lambda socios, destino: GrabacionFalsa(socios, destino),
        raiz=tmp_path,
        registro=Registro(),
        metricas=metricas,
        reloj=reloj,
    )
    return sup, repo, plataforma, metricas, reloj, tmp_path


def listo(segmentos):
    return (
        200,
        {
            "trabajo": {"estado": "listo"},
            "transcripcion": {
                "hablantes": [{"id": "h1", "etiqueta": "socioa"}, {"id": "h2", "etiqueta": "sociob"}],
                "segmentos": segmentos,
            },
        },
    )


def test_ciclo_completo_grabar_parar_transcribir_y_borrar_el_audio(entorno):
    sup, repo, plataforma, metricas, reloj, raiz = entorno
    rid = repo.pedir(Peticion(("socioa", "sociob"), "v1"))
    sup.paso()
    assert repo.reunion(rid)["estado"] == "grabando"
    g = GrabacionFalsa.creadas[0]
    assert g.empezada and g.socios == ("socioa", "sociob") and g.destino == raiz / rid
    assert metricas.grabando == 1

    repo.pedir_parada()
    sup.paso()  # para, y en la misma vuelta envía a la plataforma
    r = repo.reunion(rid)
    assert r["estado"] == "transcribiendo" and r["trabajo_id"] == TID and r["fin"] is not None
    ((_, pistas, referencia),) = plataforma.creaciones
    assert referencia == rid
    assert [(p.socio, p.desfase_ms) for p in pistas] == [("socioa", 0), ("sociob", 500)]

    plataforma.respuestas_estado = [
        listo(
            [
                {"hablante_id": "h2", "inicio_ms": 600, "fin_ms": 900, "texto": "y yo"},
                {"hablante_id": "h1", "inicio_ms": 100, "fin_ms": 400, "texto": "Doy mi conformidad"},
            ]
        )
    ]
    reloj.t += 3600
    sup.paso()
    assert repo.reunion(rid)["estado"] == "transcrita"
    assert [s[0] for s in repo.segmentos(rid)] == ["socioa", "sociob"]
    assert not (raiz / rid).exists()  # @a10: el audio se borra en cuanto el texto está guardado
    with repo.conexion() as c:
        assert c.execute("SELECT motivo, ficheros FROM purgas").fetchall() == [("transcrita", 2)]
    assert metricas.transcritas_total == 1


def test_peticion_sin_socios_validos_no_abre_paginas(entorno):
    sup, repo, *_ = entorno
    with repo.conexion() as c:  # una fila escrita a mano (el panel de F2 podría equivocarse): el supervisor revalida
        rid = str(
            c.execute("INSERT INTO reuniones (socios, texto_version) VALUES ('{socio-a}', 'v1') RETURNING id").fetchone()[0]
        )
    sup.paso()
    assert GrabacionFalsa.creadas == []
    assert repo.reunion(rid)["estado"] == "error"


def test_tope_de_tres_horas(entorno):
    sup, repo, _, metricas, reloj, _ = entorno
    rid = repo.pedir(Peticion(("socioa",), "v1"))
    sup.paso()
    reloj.t += TOPE_GRABACION_S
    sup.paso()
    r = repo.reunion(rid)
    assert r["estado"] == "transcribiendo" and GrabacionFalsa.creadas[0].parada
    assert metricas.tope_total == 1
    with repo.conexion() as c:
        assert c.execute("SELECT motivo FROM reuniones").fetchone() is not None


def test_el_tope_queda_anotado_como_motivo(entorno):
    sup, repo, plataforma, _, reloj, _ = entorno
    plataforma.respuesta_crear = (503, None)  # se queda en grabada para ver el motivo de la parada
    rid = repo.pedir(Peticion(("socioa",), "v1"))
    sup.paso()
    reloj.t += TOPE_GRABACION_S
    sup.paso()
    r = repo.reunion(rid)
    assert (r["estado"], r["motivo"]) == ("grabada", "tope_3h")


def test_token_no_valido_pasa_a_error_y_conserva_el_audio(entorno):
    sup, repo, plataforma, metricas, _, raiz = entorno
    plataforma.respuesta_crear = (401, {"detail": "Token de servicio no válido"})
    rid = repo.pedir(Peticion(("socioa",), "v1"))
    sup.paso()
    repo.pedir_parada()
    sup.paso()
    r = repo.reunion(rid)
    assert (r["estado"], r["motivo"]) == ("error", "token")
    assert metricas.errores_total == 1
    assert list((raiz / rid).iterdir())  # el audio sigue para `actas.sh reintentar`


def test_plataforma_en_error(entorno):
    sup, repo, plataforma, _, reloj, _ = entorno
    rid = repo.pedir(Peticion(("socioa",), "v1"))
    sup.paso()
    repo.pedir_parada()
    sup.paso()
    plataforma.respuestas_estado = [(200, {"trabajo": {"estado": "error"}})]
    reloj.t += 60
    sup.paso()
    assert repo.reunion(rid)["motivo"] == "plataforma_error"


def test_aviso_sin_coincidencia_al_minuto(entorno):
    sup, repo, _, metricas, reloj, _ = entorno
    repo.pedir(Peticion(("sociopablo",), "v1"))
    sup.paso()
    GrabacionFalsa.creadas[0].ver = {"sociopablo": ["x7kq2lm"]}
    reloj.t += 30
    sup.paso()
    assert metricas.aviso_sin_coincidencia == 0
    reloj.t += 31
    sup.paso()
    assert (metricas.aviso_sin_coincidencia, metricas.socios_esperados, metricas.socios_vistos) == (1, 1, 0)
    GrabacionFalsa.creadas[0].ver = {"sociopablo": ["sociopablo", "x7kq2lm"]}
    reloj.t += 61
    sup.paso()
    assert metricas.aviso_sin_coincidencia == 0


def test_purga_de_audio_viejo_y_huerfano(entorno):
    sup, repo, plataforma, _, reloj, raiz = entorno
    plataforma.respuesta_crear = (401, None)
    rid = repo.pedir(Peticion(("socioa",), "v1"))
    sup.paso()
    repo.pedir_parada()
    sup.paso()
    huerfano = raiz / "no-es-una-reunion"
    huerfano.mkdir()
    (huerfano / "x_1.webm").write_bytes(b"x")
    reloj.t += PLAZO_AUDIO_S + 3600
    sup.purgar(mtime=lambda p: reloj.t - PLAZO_AUDIO_S - 1)
    assert not (raiz / rid).exists() and not huerfano.exists()
    with repo.conexion() as c:
        assert sorted(f[0] for f in c.execute("SELECT motivo FROM purgas").fetchall()) == ["huerfano", "plazo_7d"]


def test_al_arrancar_una_grabacion_huerfana_pasa_a_error(entorno):
    sup, repo, *_ = entorno
    rid = repo.pedir(Peticion(("socioa",), "v1"))
    sup.paso()
    otro = Supervisor(
        repo=repo,
        plataforma=PlataformaFalsa(),
        nueva_grabacion=lambda s, d: GrabacionFalsa(s, d),
        raiz=entorno[5],
        registro=Registro(),
        metricas=Metricas(),
        reloj=entorno[4],
    )
    otro.arrancar()
    assert (repo.reunion(rid)["estado"], repo.reunion(rid)["motivo"]) == ("error", "reinicio_supervisor")


def test_reintento_tras_error_vuelve_a_enviar(entorno):
    sup, repo, plataforma, *_ = entorno
    plataforma.respuesta_crear = (401, None)
    rid = repo.pedir(Peticion(("socioa",), "v1"))
    sup.paso()
    repo.pedir_parada()
    sup.paso()
    plataforma.respuesta_crear = (201, {"id": TID})
    assert repo.reintentar(rid)
    sup.paso()
    assert repo.reunion(rid)["estado"] == "transcribiendo" and len(plataforma.creaciones) == 2
