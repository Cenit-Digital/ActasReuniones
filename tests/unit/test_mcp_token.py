from __future__ import annotations

import stat
from pathlib import Path

import pytest

from actas import mcp_token
from actas.mcp_guarda import hash_token, token_valido


def test_emitir_guarda_el_token_en_0600_y_devuelve_su_hash(tmp_path: Path) -> None:
    ruta = tmp_path / "t.token"
    sha = mcp_token.emitir(ruta)
    token = ruta.read_text(encoding="utf-8").strip()
    assert stat.S_IMODE(ruta.stat().st_mode) == 0o600
    assert token.startswith("tmcp_") and len(token) > 40
    assert sha == hash_token(token) and token_valido(token, sha)


def test_la_cli_solo_imprime_el_hash(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    ruta = tmp_path / "t.token"
    assert mcp_token.main(["emitir", "--fichero", str(ruta)]) == 0
    salida, errores = capsys.readouterr()
    token = ruta.read_text(encoding="utf-8").strip()
    assert token not in salida + errores and salida.strip() == hash_token(token)


def test_no_sobrescribe_un_token_existente(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    ruta = tmp_path / "t.token"
    ruta.write_text("viejo", encoding="utf-8")
    assert mcp_token.main(["emitir", "--fichero", str(ruta)]) == 1
    assert ruta.read_text(encoding="utf-8") == "viejo" and capsys.readouterr().out == ""
