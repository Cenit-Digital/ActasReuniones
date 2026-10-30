"""@a6, @a7, @a8, @a10, @a24 y @a25: el supervisor de punta a punta con PostgreSQL de verdad y la plataforma y el grabador
falsos (sin Chromium ni red)."""

import os
import time
from pathlib import Path

import pytest

from actas import salas
from actas.conformidad import Peticion
from actas.estados import TOPE_GRABACION_S, Estado
from actas.grabador import Sala, Vigilancia, sala_de_reunion
from actas.metricas import Metricas
from actas.purga import PLAZO_AUDIO_S
from actas.registro import Registro
from actas.sondeo import PLAZO_S
from actas.supervisor import Supervisor

TID = "1b4e28ba-2fa1-11d2-883f-0016d3cca427"


class GrabacionFalsa:
    creadas: list["GrabacionFalsa"] = []

    def __init__(self, socios, destino: Path):
        self.socios, self.destino = socios, destino
        self.empezada = self.parada = False
        self.viva_ = True
        self.fallo_al_parar = False
        self.reanudada = False
        self.ver: dict[str, list[str]] = {s: [s] for s in socios}
        self.grabando: dict[str, Vigilancia] = {s: Vigilancia(1, True) for s in socios}
        self.vigiladas = 0
        self.rescatadas = 0
        GrabacionFalsa.creadas.append(self)

    def empezar(self):
        self.destino.mkdir(parents=True, exist_ok=True)
        self.empezada = True

    def reanudar(self):
        self.reanudada = True

    def vistos(self):
        return self.ver

    def vigilar(self):
        self.vigiladas += 1
        return self.grabando

    def viva(self):
        return self.viva_

    def parar(self):
        self.parada = True
        if self.fallo_al_parar:
            raise RuntimeError("Chromium ha terminado")
        for n, s in enumerate(self.socios):
            (self.destino / f"{s}_{1000 + 500 * n}.webm").write_bytes(b"opus")
        return True


class PlataformaFalsa:
    def __init__(self):
        self.creaciones: list[tuple] = []
        self.respuesta_crear = (201, {"id": TID})
        self.respuestas_estado = [(200, {"trabajo": {"estado": "en_cola"}})]

    def crear(self, directorio, pistas, referencia):
        from actas.plataforma import _abrir  # las mismas comprobaciones de fichero que la de verdad

        for fd, _ in _abrir(directorio, pistas):
            os.close(fd)
        self.creaciones.append((directorio, pistas, referencia))
        return self.respuesta_crear

    def estado(self, trabajo_id):
        if isinstance(self.respuestas_estado[0], Exception):
            raise self.respuestas_estado[0]
        return self.respuestas_estado.pop(0) if len(self.respuestas_estado) > 1 else self.respuestas_estado[0]


class Reloj:
    def __init__(self):
        self.t = time.time()  # real: el plazo del audio se cuenta desde las fechas de la base

    def __call__(self):
        return self.t


@pytest.fixture
def entorno(repo, tmp_path):
    GrabacionFalsa.creadas = []
    reloj, plataforma, metricas = Reloj(), PlataformaFalsa(), Metricas()
    sup = Supervisor(
        repo=repo,
        plataforma=plataforma,
        sala_de=lambda r: None,
        nueva_grabacion=lambda sala, socios, destino: GrabacionFalsa(socios, destino),
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
        c.execute("SET session_replication_role = replica")
        rid = str(
            c.execute("INSERT INTO reuniones (socios, texto_version) VALUES ('{socio-a}', 'v1') RETURNING id").fetchone()[0]
        )
    sup.paso()
    assert GrabacionFalsa.creadas == []
    assert repo.reunion(rid)["estado"] == "error"


def test_tope_de_tres_horas(entorno):
    sup, repo, plataforma, metricas, reloj, _ = entorno
    rid = repo.pedir(Peticion(("socioa",), "v1"))
    sup.paso()
    reloj.t += TOPE_GRABACION_S
    sup.paso()
    r = repo.reunion(rid)
    assert r["estado"] == "transcribiendo" and GrabacionFalsa.creadas[0].parada
    assert metricas.tope_total == 1
    plataforma.respuestas_estado = [listo([{"hablante_id": "h1", "inicio_ms": 0, "fin_ms": 5, "texto": "hola"}])]
    reloj.t += 60
    sup.paso()
    r = repo.reunion(rid)
    assert (r["estado"], r["motivo"]) == ("transcrita", "tope_3h")  # el motivo de la parada se conserva en el archivo


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


@pytest.mark.parametrize(
    ("respuesta", "avance", "motivo"),
    [
        ((200, {"trabajo": {"estado": "error"}}), 60, "plataforma_error"),
        ((200, {"trabajo": {"estado": "cancelado"}}), 60, "plataforma_cancelado"),
        ((200, {"trabajo": {"estado": "en_cola"}}), PLAZO_S, "plazo"),
    ],
)
def test_plataforma_sin_texto_pasa_a_error_y_conserva_el_audio(entorno, respuesta, avance, motivo):
    sup, repo, plataforma, metricas, reloj, raiz = entorno
    rid = repo.pedir(Peticion(("socioa",), "v1"))
    sup.paso()
    repo.pedir_parada()
    sup.paso()
    plataforma.respuestas_estado = [respuesta]
    reloj.t += avance
    sup.paso()
    r = repo.reunion(rid)
    assert (r["estado"], r["motivo"]) == ("error", motivo)
    assert list((raiz / rid).iterdir())
    assert metricas.errores_total == 1


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


def test_un_socio_que_publica_y_no_se_graba_se_avisa_en_el_historial(entorno):
    """@a65. Grabadores huérfanos: la vigilancia de cada minuto para los huérfanos (vigilar) y avisa si un socio conectado no
    tiene ningún grabador en dos vigilancias seguidas, con su evento (el panel lo pinta en rojo) y su métrica."""
    sup, repo, _, metricas, reloj, _ = entorno
    rid = repo.pedir(Peticion(("socioa", "sociob"), "v1"))
    sup.paso()
    g = GrabacionFalsa.creadas[0]
    g.grabando = {"socioa": Vigilancia(1, True), "sociob": Vigilancia(0, True)}
    reloj.t += 61
    sup.paso()
    assert g.vigiladas == 1
    assert metricas.socios_sin_grabar == 0  # una sola vigilancia: puede que acabe de entrar
    reloj.t += 61
    sup.paso()
    assert metricas.socios_sin_grabar == 1
    assert repo.eventos(rid)[-1]["detalle"] == {"faltan": 0, "sin_grabar": 1}
    reloj.t += 61
    sup.paso()  # sin cambios: no se repite el evento
    assert [e["tipo"] for e in repo.eventos(rid)].count("aviso") == 1
    g.grabando = {"socioa": Vigilancia(1, True), "sociob": Vigilancia(1, True)}
    reloj.t += 61
    sup.paso()
    assert metricas.socios_sin_grabar == 0
    assert repo.eventos(rid)[-1]["detalle"] == {"faltan": 0, "sin_grabar": 0}
    repo.pedir_parada()
    sup.paso()
    assert metricas.socios_sin_grabar == 0


def test_un_socio_que_colgo_no_cuenta_como_sin_grabar(entorno):
    """El que colgó: la sala lo anunció (vistos lo sigue teniendo) pero su página ya no tiene par. No es audio perdido."""
    sup, repo, _, metricas, reloj, _ = entorno
    rid = repo.pedir(Peticion(("socioa",), "v1"))
    sup.paso()
    g = GrabacionFalsa.creadas[0]
    g.grabando = {"socioa": Vigilancia(0, False)}
    for _ in range(3):
        reloj.t += 61
        sup.paso()
    assert metricas.socios_sin_grabar == 0
    assert all("sin_grabar" not in e["detalle"] for e in repo.eventos(rid))


def test_lo_rescatado_al_parar_queda_en_el_historial_y_se_envia(entorno):
    """@a64. Reunión del 2026-10-30: con las descargas rescatadas, la reunión se envía en vez de acabar en `error: pistas`."""
    sup, repo, plataforma, _, _, raiz = entorno
    rid = repo.pedir(Peticion(("socioa", "sociob"), "v1"))
    sup.paso()
    g = GrabacionFalsa.creadas[0]

    def parar():
        for s in g.socios:
            (raiz / rid / f"{s}_1000.webm").write_bytes(b"opus")
        g.rescatadas = 2
        return False

    g.parar = parar
    repo.pedir_parada()
    sup.paso()
    estados = [e["detalle"] for e in repo.eventos(rid) if e["tipo"] == "estado"]
    assert {"desde": "grabando", "hasta": "grabada", "motivo": "pedida", "completas": False, "rescatadas": 2} in estados
    assert repo.reunion(rid)["estado"] == "transcribiendo" and len(plataforma.creaciones) == 1


def test_una_descarga_a_medias_que_no_se_envia_queda_en_el_historial(entorno):
    """@a64. Reunión del 2026-10-28: una pista se quedó en `.crdownload` y se envió el resto sin decir nada. Ahora se dice."""
    sup, repo, plataforma, _, _, raiz = entorno
    rid = repo.pedir(Peticion(("socioa", "sociob"), "v1"))
    sup.paso()
    g = GrabacionFalsa.creadas[0]

    def parar():
        (raiz / rid / "socioa_1000.webm").write_bytes(b"opus")
        (raiz / rid / "sociob_1500.webm.crdownload").write_bytes(b"sin cabecera")
        return False

    g.parar = parar
    repo.pedir_parada()
    sup.paso()
    estados = [e["detalle"] for e in repo.eventos(rid) if e["tipo"] == "estado"]
    assert {"desde": "grabada", "hasta": "transcribiendo", "pistas": 1, "perdidas": 1} in estados
    ((_, pistas, _),) = plataforma.creaciones
    assert [p.socio for p in pistas] == ["socioa"]


def test_sin_ninguna_pista_el_error_dice_cuantas_quedaron_a_medias(entorno):
    """@a64. La reunión del 2026-10-30 tal como acabó: solo `.crdownload` que no se pudieron rescatar."""
    sup, repo, plataforma, _, _, raiz = entorno
    rid = repo.pedir(Peticion(("socioa", "sociob"), "v1"))
    sup.paso()
    g = GrabacionFalsa.creadas[0]

    def parar():
        for s in g.socios:
            (raiz / rid / f"{s}_1000.webm.crdownload").write_bytes(b"x")
        return False

    g.parar = parar
    repo.pedir_parada()
    sup.paso()
    assert repo.eventos(rid)[-1]["detalle"] == {
        "desde": "grabada",
        "hasta": "error",
        "motivo": "pistas",
        "causa": "ninguna_pista",
        "ficheros": 2,
        "perdidas": 2,
    }
    assert plataforma.creaciones == []


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
    os.utime(raiz / rid)  # Chromium puede tocar el directorio: el plazo no se cuenta desde su mtime, sino desde la base
    reloj.t += PLAZO_AUDIO_S + 3600
    # El mtime solo cuenta para lo que no es de ninguna reunión: el de la reunión dice «recién tocado» y aun así se borra.
    sup.purgar(mtime=lambda p: reloj.t - PLAZO_AUDIO_S - 1 if p.name == "no-es-una-reunion" else reloj.t)
    assert not (raiz / rid).exists() and not huerfano.exists()
    with repo.conexion() as c:
        assert sorted(f[0] for f in c.execute("SELECT motivo FROM purgas").fetchall()) == ["huerfano", "plazo_7d"]


def test_purga_con_enlaces_no_sigue_nada_ni_se_rompe(entorno, tmp_path_factory):
    sup, repo, _, _, reloj, raiz = entorno
    fuera = tmp_path_factory.mktemp("fuera")
    (fuera / "importante").write_text("no se toca")
    raiz.mkdir(exist_ok=True)
    (raiz / "enlace-a-dir").symlink_to(fuera, target_is_directory=True)
    (raiz / "enlace-a-fichero").symlink_to(fuera / "importante")
    (raiz / "otro-huerfano").mkdir()
    (raiz / "otro-huerfano" / "dentro").symlink_to(fuera, target_is_directory=True)
    sup.purgar()
    assert (fuera / "importante").read_text() == "no se toca"
    assert sorted(p.name for p in raiz.iterdir()) == []


def test_una_pista_que_es_un_enlace_no_se_envia(entorno, tmp_path_factory):
    sup, repo, plataforma, _, _, raiz = entorno
    secreto = tmp_path_factory.mktemp("secretos") / "token"
    secreto.write_text("tok3n")
    rid = repo.pedir(Peticion(("socioa",), "v1"))
    sup.paso()
    GrabacionFalsa.creadas[0].parar = lambda: (raiz / rid / "socioa_1000.webm").symlink_to(secreto) or True
    repo.pedir_parada()
    sup.paso()
    assert (repo.reunion(rid)["estado"], repo.reunion(rid)["motivo"]) == ("error", "pistas")
    assert plataforma.creaciones == []


def test_una_excepcion_con_una_reunion_no_tumba_el_bucle(entorno):
    sup, repo, plataforma, metricas, reloj, _ = entorno
    rid = repo.pedir(Peticion(("socioa",), "v1"))
    sup.paso()
    repo.pedir_parada()
    sup.paso()
    plataforma.respuestas_estado = [KeyError("forma inesperada")]
    reloj.t += 60
    sup.paso()  # no lanza
    r = repo.reunion(rid)
    assert (r["estado"], r["motivo"]) == ("error", "interno")
    assert metricas.ultimo_paso_s == reloj.t


def test_segmento_con_forma_rara_pasa_a_error(entorno):
    sup, repo, plataforma, _, reloj, _ = entorno
    rid = repo.pedir(Peticion(("socioa",), "v1"))
    sup.paso()
    repo.pedir_parada()
    sup.paso()
    plataforma.respuestas_estado = [listo(["no soy un segmento"])]
    reloj.t += 60
    sup.paso()
    assert repo.reunion(rid)["motivo"] == "transcripcion"


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


def test_si_parar_falla_la_reunion_no_se_queda_grabando(entorno):
    sup, repo, *_ = entorno
    rid = repo.pedir(Peticion(("socioa",), "v1"))
    sup.paso()
    GrabacionFalsa.creadas[0].fallo_al_parar = True
    repo.pedir_parada()
    sup.paso()
    r = repo.reunion(rid)
    # Pasa a grabada y, sin ningún fichero descargado, a error por pistas al intentar enviarla (en la misma vuelta).
    assert (r["estado"], r["motivo"], sup.activa) == ("error", "pistas", None)


def test_chromium_caido_para_la_grabacion_con_su_motivo(entorno):
    sup, repo, plataforma, metricas, _, _ = entorno
    plataforma.respuesta_crear = (503, None)  # se queda en grabada para leer el motivo
    rid = repo.pedir(Peticion(("socioa",), "v1"))
    sup.paso()
    GrabacionFalsa.creadas[0].viva_ = False
    sup.paso()
    r = repo.reunion(rid)
    assert (r["estado"], r["motivo"]) == ("grabada", "grabador_caido")
    assert metricas.errores_total == 1


def test_401_no_deja_el_token_en_el_registro(repo, tmp_path, capsys):
    GrabacionFalsa.creadas = []
    plataforma = PlataformaFalsa()
    plataforma.respuesta_crear = (401, {"detail": "Token de servicio no válido: tok3n-secreto"})
    sup = Supervisor(
        repo=repo,
        plataforma=plataforma,
        sala_de=lambda r: None,
        nueva_grabacion=lambda sala, s, d: GrabacionFalsa(s, d),
        raiz=tmp_path,
        registro=Registro(["tok3n-secreto"]),
        metricas=Metricas(),
        reloj=Reloj(),
    )
    rid = repo.pedir(Peticion(("socioa",), "v1"))
    sup.paso()
    repo.pedir_parada()
    sup.paso()
    err = capsys.readouterr().err
    assert repo.reunion(rid)["motivo"] == "token"
    assert "reunión en error: token" in err and "tok3n-secreto" not in err


def test_envio_sin_respuesta_tiene_plazo(entorno):
    sup, repo, plataforma, _, reloj, raiz = entorno
    plataforma.respuesta_crear = (0, None)
    rid = repo.pedir(Peticion(("socioa",), "v1"))
    sup.paso()
    repo.pedir_parada()
    sup.paso()
    assert repo.reunion(rid)["estado"] == "grabada"
    reloj.t += PLAZO_S
    sup.paso()
    r = repo.reunion(rid)
    assert (r["estado"], r["motivo"]) == ("error", "plazo_envio")
    assert list((raiz / rid).iterdir())


def test_sin_filas_de_conformidad_no_se_graba(entorno):
    sup, repo, *_ = entorno
    with repo.conexion() as c:  # la base lo impide (trigger); el supervisor lo comprueba además, por si se salta el trigger
        c.execute("SET session_replication_role = replica")
        rid = str(c.execute("INSERT INTO reuniones (socios, texto_version) VALUES ('{socioa}', 'v1') RETURNING id").fetchone()[0])
    sup.paso()
    assert GrabacionFalsa.creadas == []
    assert (repo.reunion(rid)["estado"], repo.reunion(rid)["motivo"]) == ("error", "conformidad")


def test_conformidad_de_otra_version_no_vale(entorno):
    sup, repo, *_ = entorno
    rid = repo.pedir(Peticion(("socioa",), "v1"))
    with repo.conexion() as c:
        c.execute("SET session_replication_role = replica")
        c.execute("UPDATE reuniones SET texto_version = 'v2' WHERE id = %s", (rid,))
    sup.paso()
    assert GrabacionFalsa.creadas == [] and repo.reunion(rid)["estado"] == "error"


class RepoQueFallaUnaVez:
    """Envuelve el repositorio: el primer mover hacia `hasta` lanza un error de la base."""

    def __init__(self, repo, hasta):
        self._repo, self._hasta, self.fallos = repo, hasta, 0

    def __getattr__(self, nombre):
        return getattr(self._repo, nombre)

    def mover(self, rid, desde, hasta, **k):
        if hasta.value == self._hasta and self.fallos == 0:
            self.fallos += 1
            raise OSError("base caída un momento")
        return self._repo.mover(rid, desde, hasta, **k)


def test_si_la_base_falla_al_parar_se_reintenta_y_no_se_atasca(repo, tmp_path):
    GrabacionFalsa.creadas = []
    plataforma = PlataformaFalsa()
    plataforma.respuesta_crear = (503, None)
    envuelto = RepoQueFallaUnaVez(repo, "grabada")
    sup = Supervisor(
        repo=envuelto,
        plataforma=plataforma,
        sala_de=lambda r: None,
        nueva_grabacion=lambda sala, s, d: GrabacionFalsa(s, d),
        raiz=tmp_path,
        registro=Registro(),
        metricas=Metricas(),
        reloj=Reloj(),
    )
    rid = repo.pedir(Peticion(("socioa",), "v1"))
    sup.paso()
    repo.pedir_parada()
    with pytest.raises(OSError):
        sup.paso()
    assert repo.reunion(rid)["estado"] == "grabando"
    sup.paso()  # la vuelta siguiente reintenta el cambio de estado sin volver a parar el grabador
    assert repo.reunion(rid)["estado"] == "grabada" and envuelto.fallos == 1
    assert len(GrabacionFalsa.creadas) == 1
    otra = repo.pedir(Peticion(("sociob",), "v1"))
    sup.paso()
    assert repo.reunion(otra)["estado"] == "grabando"


def test_una_fila_grabando_sin_grabador_se_recupera(entorno):
    sup, repo, plataforma, *_ = entorno
    plataforma.respuesta_crear = (503, None)
    rid = repo.pedir(Peticion(("socioa",), "v1"))
    repo.mover(rid, Estado.PEDIDA, Estado.GRABANDO)  # p. ej., el error al empezar no llegó a la base
    (entorno[5] / rid).mkdir()
    (entorno[5] / rid / "socioa_1000.webm").write_bytes(b"opus")  # lo que llegó a grabarse
    sup.paso()
    assert (repo.reunion(rid)["estado"], repo.reunion(rid)["motivo"]) == ("grabada", "sin_grabador")
    assert entorno[3].errores_total == 1  # una grabación cortada avisa (ActasReunionEnError)


def test_al_arrancar_se_rescata_la_grabacion_en_curso(entorno):
    sup, repo, plataforma, _, reloj, raiz = entorno
    plataforma.respuesta_crear = (503, None)
    rid = repo.pedir(Peticion(("socioa",), "v1"))
    sup.paso()  # el contenedor supervisor se reinicia aquí; Chromium sigue grabando
    otro = Supervisor(
        repo=repo,
        plataforma=plataforma,
        sala_de=lambda r: None,
        nueva_grabacion=lambda sala, s, d: GrabacionFalsa(s, d),
        raiz=raiz,
        registro=Registro(),
        metricas=Metricas(),
        reloj=reloj,
    )
    otro.arrancar()
    rescate = GrabacionFalsa.creadas[-1]
    assert rescate.reanudada and rescate.parada and not rescate.empezada
    r = repo.reunion(rid)
    assert (r["estado"], r["motivo"]) == ("grabada", "reinicio_supervisor")
    assert list((raiz / rid).iterdir())  # lo grabado se descargó y se enviará


def test_un_fallo_pasajero_de_la_base_al_guardar_no_pierde_la_transcripcion(repo, tmp_path):
    import psycopg

    GrabacionFalsa.creadas = []
    plataforma = PlataformaFalsa()

    class RepoQueFallaAlGuardar(RepoQueFallaUnaVez):
        def guardar_transcripcion(self, rid, segmentos):
            if self.fallos == 0:
                self.fallos += 1
                raise psycopg.OperationalError("conexión perdida")
            return self._repo.guardar_transcripcion(rid, segmentos)

    envuelto = RepoQueFallaAlGuardar(repo, "ninguno")
    reloj = Reloj()
    sup = Supervisor(
        repo=envuelto,
        plataforma=plataforma,
        sala_de=lambda r: None,
        nueva_grabacion=lambda sala, s, d: GrabacionFalsa(s, d),
        raiz=tmp_path,
        registro=Registro(),
        metricas=Metricas(),
        reloj=reloj,
    )
    rid = repo.pedir(Peticion(("socioa",), "v1"))
    sup.paso()
    repo.pedir_parada()
    sup.paso()
    plataforma.respuestas_estado = [listo([{"hablante_id": "h1", "inicio_ms": 0, "fin_ms": 5, "texto": "hola"}])]
    reloj.t += 60
    with pytest.raises(psycopg.OperationalError):
        sup.paso()
    assert repo.reunion(rid)["estado"] == "transcribiendo"
    reloj.t += 60
    sup.paso()
    assert repo.reunion(rid)["estado"] == "transcrita"


def test_ocupacion_del_tmpfs_en_las_metricas(entorno):
    sup, repo, plataforma, metricas, reloj, raiz = entorno
    plataforma.respuesta_crear = (503, None)
    repo.pedir(Peticion(("socioa",), "v1"))
    sup.paso()
    repo.pedir_parada()
    sup.paso()  # la falsa deja un fichero de 4 bytes
    assert metricas.grabaciones_bytes == 4


# ── @a46: la sala de cada reunión (V2 de KubernetesInfrastructure#298) ───────────────────────────────────────────────

MAESTRA = bytes(range(32))


def _con_salas(repo, tmp_path, maestra=MAESTRA):
    GrabacionFalsa.creadas = []
    registro = Registro()
    salas_usadas = []

    def nueva(sala, socios, destino):
        salas_usadas.append(sala)
        return GrabacionFalsa(socios, destino)

    sup = Supervisor(
        repo=repo,
        plataforma=PlataformaFalsa(),
        sala_de=lambda r: sala_de_reunion(r, repo.cifrada_de_sala, maestra, registro),
        nueva_grabacion=nueva,
        raiz=tmp_path,
        registro=registro,
        metricas=Metricas(),
        reloj=Reloj(),
    )
    return sup, salas_usadas, registro


def _sala_en_la_base(repo, room="salav2abc", clave="k7m2p9qx4tz8wb3n"):
    return repo.crear_sala(f"Sala {room}", room, "3931", salas.cifrar(MAESTRA, room, clave), "pablo")


def test_el_supervisor_graba_en_la_sala_de_la_reunion_y_no_en_la_del_entorno(repo, tmp_path, monkeypatch):
    monkeypatch.setenv("SALA", "saladelentorno")
    monkeypatch.setenv("CLAVE", "clavedelentorno")
    sup, usadas, _ = _con_salas(repo, tmp_path)
    sid = _sala_en_la_base(repo)
    rid = repo.pedir(Peticion(("socioa",), "v1"), sala_id=sid)
    sup.paso()
    assert repo.reunion(rid)["estado"] == "grabando"
    assert usadas == [Sala("salav2abc", "k7m2p9qx4tz8wb3n")]
    assert "saladelentorno" not in usadas[0].url("socioa") and "clavedelentorno" not in usadas[0].url("socioa")


def test_cada_reunion_con_su_sala(repo, tmp_path):
    sup, usadas, _ = _con_salas(repo, tmp_path)
    s1, s2 = _sala_en_la_base(repo, "salauno", "claveuno"), _sala_en_la_base(repo, "salados", "clavedos")
    for sid in (s1, s2):
        repo.pedir(Peticion(("socioa",), "v1"), sala_id=sid)
        sup.paso()
        repo.pedir_parada()
        sup.paso()
    assert [(s.nombre, s.clave) for s in usadas] == [("salauno", "claveuno"), ("salados", "clavedos")]


def test_una_reunion_sin_sala_no_se_graba(repo, tmp_path):
    sup, usadas, _ = _con_salas(repo, tmp_path)
    rid = repo.pedir(Peticion(("socioa",), "v1"))
    sup.paso()
    r = repo.reunion(rid)
    assert (r["estado"], r["motivo"]) == ("error", "sala")
    assert usadas == [] and GrabacionFalsa.creadas == []


def test_una_sala_que_no_se_descifra_no_se_graba(repo, tmp_path):
    sup, usadas, _ = _con_salas(repo, tmp_path, maestra=bytes(range(1, 33)))
    rid = repo.pedir(Peticion(("socioa",), "v1"), sala_id=_sala_en_la_base(repo))
    sup.paso()
    assert (repo.reunion(rid)["estado"], repo.reunion(rid)["motivo"]) == ("error", "sala")
    assert usadas == []


def test_la_contrasena_descifrada_no_llega_al_registro(repo, tmp_path, capsys):
    sup, _, registro = _con_salas(repo, tmp_path)
    repo.pedir(Peticion(("socioa",), "v1"), sala_id=_sala_en_la_base(repo))
    sup.paso()
    registro("una línea con k7m2p9qx4tz8wb3n dentro")
    err = capsys.readouterr().err
    assert "k7m2p9qx4tz8wb3n" not in err and "***" in err


def test_al_arrancar_rescata_con_la_sala_de_la_reunion(repo, tmp_path):
    sup, usadas, _ = _con_salas(repo, tmp_path)
    rid = repo.pedir(Peticion(("socioa",), "v1"), sala_id=_sala_en_la_base(repo))
    repo.mover(rid, Estado.PEDIDA, Estado.GRABANDO)
    sup.arrancar()
    assert usadas == [Sala("salav2abc", "k7m2p9qx4tz8wb3n")] and GrabacionFalsa.creadas[0].reanudada
    assert repo.reunion(rid)["estado"] == "grabada"


def test_al_arrancar_una_grabacion_sin_sala_se_retoma_igual(repo, tmp_path):
    # Pedida por la imagen anterior a V2 (sin sala_id): sus páginas se paran de forma ordenada para no perder lo grabado.
    sup, usadas, _ = _con_salas(repo, tmp_path)
    rid = repo.pedir(Peticion(("socioa",), "v1"))
    repo.mover(rid, Estado.PEDIDA, Estado.GRABANDO)
    sup.arrancar()
    assert usadas == [None] and GrabacionFalsa.creadas[0].reanudada and GrabacionFalsa.creadas[0].parada
    assert (repo.reunion(rid)["estado"], repo.reunion(rid)["motivo"]) == ("grabada", "reinicio_supervisor")


# ── V4 de KubernetesInfrastructure#298: eventos (@a54), latido y reintento desde el panel (@a57) ─────────────────────────


def _historial(repo, rid):
    return [(e["tipo"], e["detalle"]) for e in repo.eventos(rid)]


def test_cada_transicion_del_ciclo_completo_deja_su_evento(entorno):
    sup, repo, plataforma, _, reloj, raiz = entorno
    rid = repo.pedir(Peticion(("socioa", "sociob"), "v1"))
    sup.paso()
    repo.pedir_parada()
    sup.paso()
    plataforma.respuestas_estado = [
        listo([{"hablante_id": "h1", "inicio_ms": 0, "fin_ms": 1000, "texto": "Hola."}]),
    ]
    reloj.t += 60
    sup.paso()
    assert _historial(repo, rid) == [
        ("estado", {"desde": "pedida", "hasta": "grabando", "socios": 2}),
        ("estado", {"desde": "grabando", "hasta": "grabada", "motivo": "pedida", "completas": True}),
        ("estado", {"desde": "grabada", "hasta": "transcribiendo", "pistas": 2}),
        ("envio", {"codigo": 201, "accion": "seguir", "intento": 0}),
        ("estado", {"desde": "transcribiendo", "hasta": "transcrita", "segmentos": 1}),
        ("audio_borrado", {"motivo": "transcrita", "ficheros": 2, "bytes": 8}),
    ]


def test_un_error_de_pistas_anota_su_causa(entorno):
    sup, repo, _, _, _, raiz = entorno
    rid = repo.pedir(Peticion(("socioa",), "v1"))
    repo.mover(rid, Estado.PEDIDA, Estado.GRABANDO, inicio=True)
    repo.mover(rid, Estado.GRABANDO, Estado.GRABADA, motivo="pedida", fin=True)  # sin ningún fichero: el caso de 17d9d6ae
    sup.paso()
    assert repo.reunion(rid)["motivo"] == "pistas"
    assert _historial(repo, rid)[-1] == (
        "estado",
        {"desde": "grabada", "hasta": "error", "motivo": "pistas", "causa": "ninguna_pista", "ficheros": 0},
    )


def test_un_error_de_conformidad_al_empezar_deja_su_evento(entorno):
    sup, repo, *_ = entorno
    rid = repo.pedir(Peticion(("socioa",), "v1"))
    with repo.conexion() as c:
        c.execute("DELETE FROM conformidades WHERE reunion_id = %s", (rid,))
    sup.paso()
    assert _historial(repo, rid) == [("estado", {"desde": "pedida", "hasta": "error", "motivo": "conformidad"})]


def test_si_chromium_no_empieza_queda_el_evento_del_grabador(entorno, monkeypatch):
    sup, repo, *_ = entorno

    def falla(self):
        raise RuntimeError("sin Chromium")

    monkeypatch.setattr(GrabacionFalsa, "empezar", falla)
    rid = repo.pedir(Peticion(("socioa",), "v1"))
    sup.paso()
    assert [d.get("motivo") for _, d in _historial(repo, rid)] == [None, "grabador"]


def test_las_respuestas_de_transcribir_quedan_en_el_historial(entorno):
    sup, repo, plataforma, _, reloj, _ = entorno
    plataforma.respuesta_crear = (503, None)
    rid = repo.pedir(Peticion(("socioa",), "v1"))
    sup.paso()
    repo.pedir_parada()
    sup.paso()
    plataforma.respuesta_crear = (201, {"id": TID})
    plataforma.respuestas_estado = [(502, None), (200, {"trabajo": {"estado": "error"}})]
    reloj.t += 60
    sup.paso()  # envío aceptado
    reloj.t += 60
    sup.paso()  # 502 en la consulta
    reloj.t += 60
    sup.paso()  # error de la plataforma
    eventos = [(t, d) for t, d in _historial(repo, rid) if t in ("envio", "consulta")]
    assert eventos == [
        ("envio", {"codigo": 503, "accion": "reintentar", "intento": 0}),
        ("envio", {"codigo": 201, "accion": "seguir", "intento": 1}),
        ("consulta", {"codigo": 502, "accion": "seguir"}),
        ("consulta", {"codigo": 200, "accion": "error", "motivo": "plataforma_error"}),
    ]


def test_el_aviso_de_socios_queda_en_el_historial_solo_al_cambiar(entorno):
    sup, repo, _, _, reloj, _ = entorno
    rid = repo.pedir(Peticion(("sociopablo",), "v1"))
    sup.paso()
    GrabacionFalsa.creadas[0].ver = {"sociopablo": ["x7kq2lm"]}
    for _ in range(3):
        reloj.t += 61
        sup.paso()
    GrabacionFalsa.creadas[0].ver = {"sociopablo": ["sociopablo"]}
    reloj.t += 61
    sup.paso()
    assert [d for t, d in _historial(repo, rid) if t == "aviso"] == [{"faltan": 1}, {"faltan": 0}]


def test_el_rescate_al_arrancar_y_la_fila_huerfana_dejan_su_evento(entorno):
    sup, repo, plataforma, _, reloj, raiz = entorno
    plataforma.respuesta_crear = (503, None)
    huerfana = repo.pedir(Peticion(("socioa",), "v1"))
    repo.mover(huerfana, Estado.PEDIDA, Estado.GRABANDO)
    sup.paso()
    assert ("estado", {"desde": "grabando", "hasta": "grabada", "motivo": "sin_grabador"}) in _historial(repo, huerfana)
    en_curso = repo.pedir(Peticion(("socioa",), "v1"))
    sup.paso()
    Supervisor(
        repo=repo,
        plataforma=plataforma,
        sala_de=lambda r: None,
        nueva_grabacion=lambda sala, s, d: GrabacionFalsa(s, d),
        raiz=raiz,
        registro=Registro(),
        metricas=Metricas(),
        reloj=reloj,
    ).arrancar()
    assert ("estado", {"desde": "grabando", "hasta": "grabada", "motivo": "reinicio_supervisor"}) in _historial(repo, en_curso)


def test_cada_vuelta_deja_el_latido(repo, tmp_path):
    plataforma = PlataformaFalsa()
    plataforma.respuesta_crear = (503, None)
    reloj = Reloj()
    sup = Supervisor(
        repo=repo,
        plataforma=plataforma,
        sala_de=lambda r: None,
        nueva_grabacion=lambda sala, socios, destino: GrabacionFalsa(socios, destino),
        raiz=tmp_path,
        registro=Registro(),
        metricas=Metricas(),
        reloj=reloj,
        chromium=lambda: "HeadlessChrome/141.0.7390.37",
        imagen="sha-0123456789abcdef0123456789abcdef01234567",
    )
    rid = repo.pedir(Peticion(("socioa",), "v1"))
    sup.paso()
    repo.pedir_parada()
    sup.paso()
    detalle, hace_s = repo.latido()
    assert 0 <= hace_s < 5
    assert detalle["chromium"] == "HeadlessChrome/141.0.7390.37"
    assert detalle["imagen"] == "sha-0123456789abcdef0123456789abcdef01234567"
    assert detalle["grabaciones_bytes"] == 4 and detalle["grabaciones_total"] > 0
    assert detalle["con_audio"] == [rid]
    assert detalle["transcribir_codigo"] == 503


def test_sin_chromium_el_latido_lo_dice(repo, tmp_path):
    def caido():
        raise OSError("conexión rechazada")

    sup = Supervisor(
        repo=repo,
        plataforma=PlataformaFalsa(),
        sala_de=lambda r: None,
        nueva_grabacion=lambda sala, s, d: GrabacionFalsa(s, d),
        raiz=tmp_path,
        registro=Registro(),
        metricas=Metricas(),
        chromium=caido,
    )
    sup.paso()
    assert repo.latido()[0]["chromium"] is None


def test_reintento_pedido_desde_el_panel_con_audio(entorno, repo_panel):
    """@a57: sin terminal. Error con el audio aún en el tmpfs → «Reintentar» → `grabada` → se reenvía."""
    sup, repo, plataforma, *_ = entorno
    plataforma.respuesta_crear = (401, None)
    rid = repo.pedir(Peticion(("socioa",), "v1"))
    sup.paso()
    repo.pedir_parada()
    sup.paso()
    assert repo.reunion(rid)["estado"] == "error"
    plataforma.respuesta_crear = (201, {"id": TID})
    assert repo_panel.pedir_reintento(rid, "pablo")
    sup.paso()
    r = repo.reunion(rid)
    assert (r["estado"], r["reintento_pedido_en"]) == ("transcribiendo", None)
    assert len(plataforma.creaciones) == 2
    assert ("reintento", {"usuario": "pablo", "resultado": "reenviada"}) in _historial(repo, rid)


def test_reintento_pedido_sin_audio_no_mueve_la_reunion(entorno, repo_panel):
    sup, repo, *_ = entorno
    rid = repo.pedir(Peticion(("socioa",), "v1"))
    repo.mover(rid, Estado.PEDIDA, Estado.GRABANDO, inicio=True)
    repo.mover(rid, Estado.GRABANDO, Estado.GRABADA, motivo="pedida", fin=True)
    sup.paso()  # error: pistas (ninguna)
    assert repo_panel.pedir_reintento(rid, "pablo")
    sup.paso()
    r = repo.reunion(rid)
    assert (r["estado"], r["motivo"], r["reintento_pedido_en"]) == ("error", "pistas", None)
    assert _historial(repo, rid)[-1] == ("reintento", {"usuario": "pablo", "resultado": "ninguna_pista"})


def test_un_reintento_que_falla_no_para_la_vuelta(entorno, repo_panel, monkeypatch):
    """Revisión de V4: un fallo inesperado al atender un reintento descarta la petición; la vuelta sigue enviando y latiendo."""
    sup, repo, plataforma, *_ = entorno
    plataforma.respuesta_crear = (401, None)
    rid = repo.pedir(Peticion(("socioa",), "v1"))
    sup.paso()
    repo.pedir_parada()
    sup.paso()
    assert repo_panel.pedir_reintento(rid, "pablo")

    def falla(_rid):
        raise PermissionError("tmpfs")

    monkeypatch.setattr(sup, "_nombres", falla)
    otra = repo.pedir(Peticion(("socioa",), "v1"))
    sup.paso()  # empieza a grabar la otra pese al reintento roto
    r = repo.reunion(rid)
    assert (r["estado"], r["reintento_pedido_en"]) == ("error", None)
    assert _historial(repo, rid)[-1] == ("reintento", {"usuario": "pablo", "resultado": "interno"})
    assert repo.reunion(otra)["estado"] == "grabando"
    assert repo.latido() is not None


# ── V3: programadas (@a48), su tope y su espera, la serie (@a53) y la purga diaria (@a51, @a52) ─────────────────────────


def _programada(repo, **cambios):
    from datetime import UTC, datetime, timedelta

    from actas.planificador import Programacion

    sala = cambios.pop("sala_id", None) or repo.crear_sala(
        f"s{len(repo.salas())}", f"room{len(repo.salas())}", "abcd", b"\x00" * 40, "pablo"
    )
    datos = {
        "titulo": "Socios",
        "sala_id": sala,
        "para": datetime.now(UTC) + timedelta(days=1),
        "tope_min": 120,
        "repetir": "no",
        "espera_min": 15,
        "socios": ("socioa", "sociob"),
        "version": "v1",
    }
    datos.update(cambios)
    return repo.programar(Programacion(**datos), "pablo")


def _vence(repo, rid, hace="1 second"):
    """Su hora llega: la base decide (now()), no el reloj del supervisor."""
    with repo.conexion() as c:
        c.execute(
            "UPDATE reuniones SET programada_para = now() - %s::interval, repetir_hora = CASE WHEN repetir <> 'no' "
            "THEN ((now() - %s::interval) AT TIME ZONE 'Europe/Madrid')::time END WHERE id = %s",
            (hace, hace, rid),
        )


def test_a48_a_su_hora_pasa_a_grabando_en_la_siguiente_vuelta(entorno):
    sup, repo, *_ = entorno
    rid = _programada(repo)
    sup.paso()
    assert repo.reunion(rid)["estado"] == "programada" and GrabacionFalsa.creadas == []
    _vence(repo, rid)
    sup.paso()  # una vuelta: cada 5 s, así que ≤ 10 s
    r = repo.reunion(rid)
    assert r["estado"] == "grabando" and r["inicio"] is not None
    assert GrabacionFalsa.creadas[0].socios == ("socioa", "sociob") and GrabacionFalsa.creadas[0].empezada
    assert repo.eventos(rid)[-1]["detalle"] == {"desde": "programada", "hasta": "grabando", "socios": 2}


def test_a48_sin_la_conformidad_de_todos_pasa_a_error(entorno):
    sup, repo, *_ = entorno
    rid = _programada(repo)
    with repo.conexion() as c:
        c.execute("DELETE FROM conformidades WHERE reunion_id = %s AND socio = 'sociob'", (rid,))
    _vence(repo, rid)
    sup.paso()
    r = repo.reunion(rid)
    assert (r["estado"], r["motivo"]) == ("error", "conformidad") and GrabacionFalsa.creadas == []
    assert repo.eventos(rid)[-1]["detalle"] == {"desde": "programada", "hasta": "error", "motivo": "conformidad"}


def test_a48_una_pedida_va_antes_que_una_programada(entorno):
    sup, repo, *_ = entorno
    prog = _programada(repo)
    _vence(repo, prog)
    pedida = repo.pedir(Peticion(("socioa",), "v1"))
    sup.paso()
    assert (repo.reunion(pedida)["estado"], repo.reunion(prog)["estado"]) == ("grabando", "programada")


def test_a48_con_otra_grabacion_en_marcha_espera_y_empieza_al_acabar(entorno):
    sup, repo, plataforma, *_ = entorno
    plataforma.respuesta_crear = (503, None)
    pedida = repo.pedir(Peticion(("socioa",), "v1"))
    sup.paso()
    prog = _programada(repo)
    _vence(repo, prog, "5 minutes")
    sup.paso()
    assert repo.reunion(prog)["estado"] == "programada"
    repo.pedir_parada()
    sup.paso()  # para la primera
    sup.paso()  # y empieza la programada, aún dentro de su espera
    assert (repo.reunion(pedida)["estado"], repo.reunion(prog)["estado"]) == ("grabada", "grabando")


def test_a48_pasada_su_espera_sin_poder_empezar_pasa_a_error(entorno):
    sup, repo, *_ = entorno
    repo.pedir(Peticion(("socioa",), "v1"))
    sup.paso()  # otra grabación en marcha
    prog = _programada(repo, espera_min=15)
    _vence(repo, prog, "15 minutes 1 second")
    sup.paso()
    r = repo.reunion(prog)
    assert (r["estado"], r["motivo"]) == ("error", "no_empezo")


def test_a48_si_el_supervisor_estuvo_parado_no_graba_tarde(entorno):
    sup, repo, *_ = entorno
    prog = _programada(repo, espera_min=30)
    _vence(repo, prog, "2 hours")
    sup.paso()
    assert repo.reunion(prog)["estado"] == "error" and GrabacionFalsa.creadas == []


def test_el_tope_de_cada_reunion(entorno):
    sup, repo, plataforma, _, reloj, _ = entorno
    plataforma.respuesta_crear = (503, None)
    rid = _programada(repo, tope_min=60)
    _vence(repo, rid)
    sup.paso()
    reloj.t += 3599
    sup.paso()
    assert repo.reunion(rid)["estado"] == "grabando"
    reloj.t += 1
    sup.paso()
    assert (repo.reunion(rid)["estado"], repo.reunion(rid)["motivo"]) == ("grabada", "tope")


def test_grabar_ahora_con_su_tope(entorno):
    sup, repo, plataforma, _, reloj, _ = entorno
    plataforma.respuesta_crear = (503, None)
    rid = repo.pedir(Peticion(("socioa",), "v1"), tope_min=60)
    sup.paso()
    reloj.t += 3600
    sup.paso()
    assert (repo.reunion(rid)["estado"], repo.reunion(rid)["motivo"]) == ("grabada", "tope")


def test_si_no_entra_nadie_se_cancela_y_se_borra_el_audio(entorno):
    sup, repo, _, metricas, reloj, raiz = entorno
    rid = _programada(repo, espera_min=15)
    _vence(repo, rid)
    sup.paso()
    g = GrabacionFalsa.creadas[0]
    g.ver = {"socioa": [], "sociob": []}
    for _ in range(14):
        reloj.t += 60
        sup.paso()
    assert repo.reunion(rid)["estado"] == "grabando"
    reloj.t += 60
    sup.paso()
    r = repo.reunion(rid)
    assert (r["estado"], r["motivo"]) == ("cancelada", "nadie_entro") and r["fin"] is not None
    assert g.parada and not (raiz / rid).exists() and metricas.grabando == 0
    with repo.conexion() as c:
        assert c.execute("SELECT motivo FROM purgas WHERE reunion_id = %s", (rid,)).fetchall() == [("nadie_entro",)]
    assert {"desde": "grabando", "hasta": "cancelada", "motivo": "nadie_entro"} in [e["detalle"] for e in repo.eventos(rid)]


def test_si_entro_alguien_no_se_cancela_aunque_luego_salga(entorno):
    sup, repo, _, _, reloj, _ = entorno
    rid = _programada(repo, espera_min=15)
    _vence(repo, rid)
    sup.paso()
    g = GrabacionFalsa.creadas[0]
    g.ver = {"socioa": ["socioa"], "sociob": []}
    reloj.t += 60
    sup.paso()
    g.ver = {"socioa": [], "sociob": []}
    for _ in range(30):
        reloj.t += 60
        sup.paso()
    assert repo.reunion(rid)["estado"] == "grabando"


def test_grabar_ahora_no_se_cancela_aunque_no_entre_nadie(entorno):
    sup, repo, _, _, reloj, _ = entorno
    rid = repo.pedir(Peticion(("socioa",), "v1"))
    sup.paso()
    GrabacionFalsa.creadas[0].ver = {"socioa": []}
    for _ in range(61):
        reloj.t += 60
        sup.paso()
    assert repo.reunion(rid)["estado"] == "grabando"


def test_a53_al_empezar_una_semanal_se_crea_la_siguiente_sin_conformidades(entorno):
    from datetime import timedelta

    from actas.planificador import MADRID

    sup, repo, *_ = entorno
    rid = _programada(repo, repetir="semanal", tope_min=60, espera_min=30)
    _vence(repo, rid, "1 minute")
    sup.paso()
    r = repo.reunion(rid)
    assert r["estado"] == "grabando" and r["repetida_en"] is not None
    (sig,) = repo.programadas()
    assert (sig["anterior_id"], sig["sala_id"], sig["tope_min"], sig["espera_min"], list(sig["socios"])) == (
        rid,
        r["sala_id"],
        60,
        30,
        ["socioa", "sociob"],
    )
    local = r["programada_para"].astimezone(MADRID)
    assert sig["programada_para"].astimezone(MADRID) == local + timedelta(days=7)
    assert repo.conformidades(sig["id"]) == []
    sup.paso()
    assert len(repo.programadas()) == 1  # una sola


def test_a53_tambien_si_no_pudo_empezar(entorno):
    sup, repo, *_ = entorno
    rid = _programada(repo, repetir="mensual")
    with repo.conexion() as c:
        c.execute("DELETE FROM conformidades WHERE reunion_id = %s", (rid,))
    _vence(repo, rid)
    sup.paso()
    assert repo.reunion(rid)["estado"] == "error"
    (sig,) = repo.programadas()
    assert sig["anterior_id"] == rid and sig["repetir"] == "mensual"


def test_a53_la_siguiente_sin_conformidades_no_graba(entorno):
    sup, repo, *_ = entorno
    rid = _programada(repo, repetir="semanal")
    _vence(repo, rid)
    sup.paso()
    repo.pedir_parada()
    sup.paso()
    (sig,) = repo.programadas()
    _vence(repo, sig["id"])
    sup.paso()
    assert (repo.reunion(sig["id"])["estado"], repo.reunion(sig["id"])["motivo"]) == ("error", "conformidad")


def test_la_purga_de_actas_corre_al_arrancar_y_una_vez_al_dia(entorno, repo_panel):
    sup, repo, _, _, reloj, _ = entorno
    rid = repo.pedir(Peticion(("socioa",), "v1"))
    repo.mover(rid, Estado.PEDIDA, Estado.ERROR, motivo="conformidad")
    repo_panel.a_papelera(rid, "pablo")
    with repo.conexion() as c:
        c.execute("UPDATE reuniones SET papelera_en = now() - interval '8 days' WHERE id = %s", (rid,))
    otra = repo.pedir(Peticion(("socioa",), "v1"))
    repo.mover(otra, Estado.PEDIDA, Estado.ERROR, motivo="conformidad")
    sup.paso()
    with pytest.raises(KeyError):
        repo.reunion(rid)
    repo_panel.a_papelera(otra, "pablo")
    with repo.conexion() as c:
        c.execute("UPDATE reuniones SET papelera_en = now() - interval '8 days' WHERE id = %s", (otra,))
    reloj.t += 23 * 3600
    sup.paso()
    assert repo.reunion(otra)["papelera_en"] is not None  # aún no ha pasado un día
    reloj.t += 3600
    sup.paso()
    with pytest.raises(KeyError):
        repo.reunion(otra)


def test_si_se_modifica_al_ir_a_empezar_no_graba_lo_viejo(entorno, monkeypatch):
    """Revisión de V3: el panel cambia la sala entre la lectura del supervisor y su paso a grabando. No se graba con lo leído:
    la vuelta siguiente vuelve a leerla."""
    sup, repo, *_ = entorno
    rid = _programada(repo)
    _vence(repo, rid)
    original = sup.nueva_grabacion

    otra = repo.crear_sala("otra", "roomotra", "abcd", b"\x00" * 40, "pablo")

    def modificar_entre_medias(sala, socios, destino):
        with repo.conexion() as c:
            c.execute("UPDATE reuniones SET sala_id = %s WHERE id = %s", (otra, rid))
        return original(sala, socios, destino)

    monkeypatch.setattr(sup, "nueva_grabacion", modificar_entre_medias)
    sup.paso()
    assert repo.reunion(rid)["estado"] == "programada" and not GrabacionFalsa.creadas[0].empezada
    monkeypatch.setattr(sup, "nueva_grabacion", original)
    sup.paso()
    assert (repo.reunion(rid)["estado"], repo.reunion(rid)["sala_id"]) == ("grabando", otra)


def test_el_tope_propio_tambien_cuenta_en_las_metricas(entorno):
    sup, repo, plataforma, metricas, reloj, _ = entorno
    plataforma.respuesta_crear = (503, None)
    repo.pedir(Peticion(("socioa",), "v1"), tope_min=60)
    sup.paso()
    reloj.t += 3600
    sup.paso()
    assert metricas.tope_total == 1


def test_si_borrar_el_audio_de_una_cancelada_falla_la_vuelta_sigue(entorno, monkeypatch):
    sup, repo, _, _, reloj, _ = entorno
    rid = _programada(repo, espera_min=15)
    _vence(repo, rid)
    sup.paso()
    GrabacionFalsa.creadas[0].ver = {"socioa": [], "sociob": []}
    latidos = []
    monkeypatch.setattr(sup, "_borrar", lambda *_: (_ for _ in ()).throw(OSError("tmpfs")))
    monkeypatch.setattr(sup, "_latir", lambda con_audio: latidos.append(con_audio))
    reloj.t += 16 * 60
    sup.paso()
    assert repo.reunion(rid)["estado"] == "cancelada" and latidos


def test_reintentar_por_actas_sh_una_que_nunca_grabo_no_revienta(repo):
    from datetime import UTC, datetime, timedelta

    from actas.planificador import Programacion

    sala = repo.crear_sala("r", "roomr", "abcd", b"\x00" * 40, "pablo")
    p = Programacion("S", sala, datetime.now(UTC) + timedelta(days=1), 60, "no", 15, ("socioa",), "v1")
    rid = repo.programar(p, "pablo")
    with repo.conexion() as c:
        c.execute("DELETE FROM conformidades WHERE reunion_id = %s", (rid,))
    repo.mover(rid, Estado.PROGRAMADA, Estado.ERROR, motivo="conformidad")
    assert repo.reintentar(rid) is False
    assert repo.reunion(rid)["estado"] == "error"


def test_a53_la_siguiente_usa_la_hora_original_de_la_serie(entorno):
    """Revisión de V3: tras una que cayó en el salto de marzo, la serie vuelve a su hora."""
    from datetime import time

    from actas.planificador import MADRID

    sup, repo, *_ = entorno
    rid = _programada(repo, repetir="semanal")
    _vence(repo, rid)
    with repo.conexion() as c:
        c.execute("UPDATE reuniones SET repetir_hora = '06:15' WHERE id = %s", (rid,))
    sup.paso()
    (sig,) = repo.programadas()
    assert sig["programada_para"].astimezone(MADRID).time() == time(6, 15)


# ── Drenaje: parar el pod (despliegue, rollout o borrado) sin perder el audio del tmpfs ────────────────────────────────────


@pytest.fixture
def drenaje(entorno, tmp_path_factory):
    from actas.drenaje import Drenaje

    d = Drenaje(tmp_path_factory.mktemp("marcas"))
    entorno[0].drenaje = d
    return d


def test_drenando_no_empieza_ninguna_grabacion_y_queda_hecho(entorno, drenaje):
    sup, repo, _, metricas, *_ = entorno
    drenaje.pedir()
    rid = repo.pedir(Peticion(("socioa",), "v1"))
    sup.paso()
    assert GrabacionFalsa.creadas == []
    assert repo.reunion(rid)["estado"] == "pedida"  # la empieza el pod nuevo
    assert drenaje.hecho() and metricas.drenaje == 2


def test_drenando_la_grabacion_en_curso_sigue_hasta_parar_y_se_envia_antes_de_dar_el_drenaje_por_hecho(entorno, drenaje):
    sup, repo, plataforma, metricas, reloj, _ = entorno
    rid = repo.pedir(Peticion(("socioa", "sociob"), "v1"))
    sup.paso()
    drenaje.pedir()  # llega el rollout a mitad de la reunión
    for _ in range(3):
        reloj.t += 60
        sup.paso()
    g = GrabacionFalsa.creadas[0]
    assert not g.parada and repo.reunion(rid)["estado"] == "grabando"  # un despliegue no corta la reunión
    assert not drenaje.hecho() and metricas.drenaje == 1 and metricas.grabando == 1
    repo.pedir_parada()
    sup.paso()
    assert g.parada and repo.reunion(rid)["estado"] == "transcribiendo"
    assert len(plataforma.creaciones) == 1 and drenaje.hecho()


def test_drenando_el_tope_tambien_para_y_envia(entorno, drenaje):
    sup, repo, _, _, reloj, _ = entorno
    rid = repo.pedir(Peticion(("socioa",), "v1"))
    sup.paso()
    drenaje.pedir()
    reloj.t += TOPE_GRABACION_S
    sup.paso()
    assert repo.reunion(rid)["estado"] == "transcribiendo" and drenaje.hecho()


def test_drenando_sin_plataforma_espera_a_que_el_audio_este_enviado(entorno, drenaje):
    sup, repo, plataforma, _, reloj, raiz = entorno
    plataforma.respuesta_crear = (503, None)
    rid = repo.pedir(Peticion(("socioa",), "v1"))
    sup.paso()
    drenaje.pedir()
    repo.pedir_parada()
    sup.paso()
    assert repo.reunion(rid)["estado"] == "grabada" and not drenaje.hecho()  # el audio solo está en el tmpfs
    assert (raiz / rid).is_dir()
    plataforma.respuesta_crear = (201, {"id": TID})
    reloj.t += 3600
    sup.paso()
    assert repo.reunion(rid)["estado"] == "transcribiendo" and drenaje.hecho()


def test_drenando_no_empieza_una_programada_cuya_hora_llega(entorno, drenaje):
    sup, repo, *_ = entorno
    rid = _programada(repo)
    _vence(repo, rid)
    drenaje.pedir()
    sup.paso()
    assert GrabacionFalsa.creadas == [] and repo.reunion(rid)["estado"] == "programada"
