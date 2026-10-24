"""Las migraciones van en su propio proceso (initContainer): la contraseña de actas_owner no vive en el supervisor."""

import pytest

from actas import migrar


def test_migrar_usa_solo_las_variables_del_dueno(monkeypatch, capsys):
    llamadas = []
    monkeypatch.setattr(migrar.base, "migrar", lambda dsn, password=None: llamadas.append((dsn, password)) or ["0001.sql"])
    monkeypatch.setenv("ACTAS_DSN_MIGRACIONES", "host=x dbname=actas user=actas_owner")
    monkeypatch.setenv("ACTAS_MIGRACIONES_PASSWORD", "secreta")
    assert migrar.main() == 0
    assert llamadas == [("host=x dbname=actas user=actas_owner", "secreta")]
    err = capsys.readouterr().err
    assert "0001.sql" in err and "secreta" not in err


def test_un_error_sale_con_1_sin_traza(monkeypatch, capsys):
    def falla(dsn, password=None):
        raise RuntimeError("conexión a host=x password=secreta")

    monkeypatch.setattr(migrar.base, "migrar", falla)
    monkeypatch.setenv("ACTAS_DSN_MIGRACIONES", "host=x")
    monkeypatch.setenv("ACTAS_MIGRACIONES_PASSWORD", "secreta")
    assert migrar.main() == 1
    assert "secreta" not in capsys.readouterr().err


def test_el_supervisor_no_migra(monkeypatch):
    import actas.__main__ as principal

    assert "migrar" not in principal.main.__code__.co_names
    with pytest.raises(AttributeError):
        principal.base  # noqa: B018 (el proceso del supervisor ya no importa base para migrar)
