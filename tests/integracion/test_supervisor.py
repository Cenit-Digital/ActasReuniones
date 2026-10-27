"""@a6, @a7, @a8, @a10, @a24 y @a25: el supervisor de punta a punta con PostgreSQL de verdad y la plataforma y el grabador
falsos (sin Chromium ni red)."""

import os
import time
from pathlib import Path

import pytest

from actas import salas
from actas.conformidad import Peticion
from actas.estados import TOPE_GRABACION_S, Estado
from actas.grabador import Sala, sala_de_reunion
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
        GrabacionFalsa.creadas.append(self)

    def empezar(self):
        self.destino.mkdir(parents=True, exist_ok=True)
        self.empezada = True

    def reanudar(self):
        self.reanudada = True

    def vistos(self):
        return self.ver

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


def test_al_arrancar_sin_sala_la_reunion_pasa_igual_a_grabada(repo, tmp_path):
    sup, usadas, _ = _con_salas(repo, tmp_path)
    rid = repo.pedir(Peticion(("socioa",), "v1"))
    repo.mover(rid, Estado.PEDIDA, Estado.GRABANDO)
    sup.arrancar()
    assert usadas == []
    assert (repo.reunion(rid)["estado"], repo.reunion(rid)["motivo"]) == ("grabada", "reinicio_supervisor")
