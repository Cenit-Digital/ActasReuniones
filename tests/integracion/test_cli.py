"""@a6: `actas.sh grabar` sin socios se rechaza; con la lista, la petición queda en la base."""

from actas import cli


def test_grabar_sin_socios_se_rechaza(repo, capsys):
    assert cli.main(["grabar", ",", "v1"], repo) == 1
    assert "ningún socio" in capsys.readouterr().err
    assert repo.cuenta_por_estado() == {}


def test_grabar_con_socios_pide_y_parar_sin_activa(repo, capsys):
    assert cli.main(["grabar", "sociopablo,socioroberto", "v1"], repo) == 0
    rid = capsys.readouterr().out.strip()
    assert repo.conformidades(rid) == [("sociopablo", "v1"), ("socioroberto", "v1")]
    assert cli.main(["parar"], repo) == 1


def test_estado_y_reintentar(repo, capsys):
    cli.main(["grabar", "socioa", "v1"], repo)
    rid = capsys.readouterr().out.strip()
    assert cli.main(["estado"], repo) == 0
    assert rid in capsys.readouterr().out
    assert cli.main(["reintentar", rid], repo) == 1


def test_orden_desconocida(repo):
    assert cli.main(["borrar-todo"], repo) == 2
