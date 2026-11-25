"""CLI del token del MCP: `python -m actas.mcp_token emitir --fichero RUTA`.

Genera un token nuevo, lo escribe SOLO en el fichero (permisos 0600, sin sobrescribir uno existente) y
muestra únicamente su SHA-256: ese hash es lo que va al Secret `ACTAS_MCP_TOKEN_SHA256` de la API.
El token no se imprime nunca y no se toca ninguna base de datos (ADR 0004). Para rotarlo: borrar el
fichero, emitir otro y cambiar el hash del Secret; el token anterior deja de valer en cuanto la API
arranca con el hash nuevo.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from actas.mcp_guarda import hash_token, nuevo_token


def emitir(fichero: Path) -> str:
    """Escribe un token nuevo en `fichero` (0600, creación exclusiva) y devuelve su SHA-256."""
    token = nuevo_token()
    descriptor = os.open(fichero, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as salida:
        salida.write(token + "\n")
    return hash_token(token)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="actas.mcp_token", description=__doc__)
    sub = parser.add_subparsers(dest="orden", required=True)
    e = sub.add_parser("emitir", help="genera un token, lo guarda en un fichero 0600 y muestra su SHA-256")
    e.add_argument("--fichero", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        print(emitir(args.fichero))
    except FileExistsError:
        print("El fichero ya existe: bórralo antes de emitir otro token.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
