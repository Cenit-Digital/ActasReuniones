"""@a6: `actas.sh grabar` sin socios se rechaza; con la lista, la petición queda en la base. Desde V2
(KubernetesInfrastructure#298) cada reunión va con su sala: `grabar SOCIOS VERSION` sigue valiendo si hay una sola, y
`grabar SOCIOS VERSION SALA` elige por su nombre en VDO.Ninja."""

import pytest

from actas import cli


def _sala(repo, room):
    return repo.crear_sala(f"Sala {room}", room, "abcd", bytes(40), "pablo")


def test_grabar_sin_socios_se_rechaza(repo, capsys):
    _sala(repo, "salauno")
    assert cli.main(["grabar", ",", "v1"], repo) == 1
    assert "ningún socio" in capsys.readouterr().err
    assert repo.cuenta_por_estado() == {}


def test_grabar_con_socios_pide_en_la_unica_sala_y_parar_sin_activa(repo, capsys):
    sid = _sala(repo, "salauno")
    assert cli.main(["grabar", "sociopablo,socioroberto", "v1"], repo) == 0
    rid = capsys.readouterr().out.strip()
    assert repo.conformidades(rid) == [("sociopablo", "v1"), ("socioroberto", "v1")]
    assert repo.reunion(rid)["sala_id"] == sid
    assert cli.main(["parar"], repo) == 1


def test_grabar_en_la_sala_indicada(repo, capsys):
    _sala(repo, "salauno")
    dos = _sala(repo, "salados")
    assert cli.main(["grabar", "socioa", "v1", "salados"], repo) == 0
    assert repo.reunion(capsys.readouterr().out.strip())["sala_id"] == dos


@pytest.mark.parametrize(
    ("salas", "args", "error"),
    [
        ([], ["grabar", "socioa", "v1"], "ninguna sala"),
        (["salauno", "salados"], ["grabar", "socioa", "v1"], "varias salas"),
        (["salauno"], ["grabar", "socioa", "v1", "otra"], "no existe la sala"),
    ],
)
def test_grabar_sin_una_sala_clara_se_rechaza(repo, capsys, salas, args, error):
    for room in salas:
        _sala(repo, room)
    assert cli.main(args, repo) == 1
    assert error in capsys.readouterr().err
    assert repo.cuenta_por_estado() == {}


def test_estado_y_reintentar(repo, capsys):
    _sala(repo, "salauno")
    cli.main(["grabar", "socioa", "v1"], repo)
    rid = capsys.readouterr().out.strip()
    assert cli.main(["estado"], repo) == 0
    assert rid in capsys.readouterr().out
    assert cli.main(["reintentar", rid], repo) == 1


def test_orden_desconocida(repo):
    assert cli.main(["borrar-todo"], repo) == 2
