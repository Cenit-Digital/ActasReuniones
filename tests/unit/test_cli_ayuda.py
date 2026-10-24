"""`actas.cli` sin una orden válida muestra la ayuda y sale con 2, sin tocar la base (ni necesitar ACTAS_DSN)."""

import pytest

from actas import cli


@pytest.mark.parametrize("args", [[], ["borrar-todo"], ["grabar", "socioa"], ["reintentar"]])
def test_ayuda_sin_base(args, capsys, monkeypatch):
    monkeypatch.delenv("ACTAS_DSN", raising=False)
    assert cli.main(args) == 2
    assert "python -m actas.cli grabar" in capsys.readouterr().err
