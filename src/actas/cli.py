"""Órdenes de `scripts/actas.sh` (KubernetesInfrastructure), que las ejecuta con `kubectl exec` en el contenedor del
supervisor: escriben la petición en la base y el supervisor la atiende. Hasta F2 es la única forma de grabar.

  python -m actas.cli grabar SOCIO[,SOCIO...] VERSION   socios conformes (streamIDs) y versión del texto informativo
  python -m actas.cli parar                             para la grabación activa
  python -m actas.cli estado                            las últimas reuniones (id, estado, motivo, socios)
  python -m actas.cli reintentar ID                     una reunión en `error` vuelve a enviarse a la plataforma
"""

import os
import sys

from actas.base import Repositorio
from actas.conformidad import ConformidadNoValida, validar

_ARGUMENTOS = {"grabar": 3, "parar": 1, "estado": 1, "reintentar": 2}


def main(args: list[str], repo: Repositorio | None = None) -> int:
    orden = args[0] if args else ""
    if _ARGUMENTOS.get(orden) != len(args):
        print(__doc__, file=sys.stderr)
        return 2
    repo = repo or Repositorio(os.environ["ACTAS_DSN"])
    if orden == "grabar" and len(args) == 3:
        try:
            peticion = validar([s for s in args[1].split(",") if s], args[2])
        except ConformidadNoValida as e:
            print(f"rechazada: {e}", file=sys.stderr)
            return 1
        print(repo.pedir(peticion))
        return 0
    if orden == "parar" and len(args) == 1:
        rid = repo.pedir_parada()
        print(rid or "no hay ninguna grabación activa")
        return 0 if rid else 1
    if orden == "estado" and len(args) == 1:
        with repo.conexion() as c:
            filas = c.execute(
                "SELECT id, estado, coalesce(motivo, ''), array_to_string(socios, ','), creado_en "
                "FROM reuniones ORDER BY creado_en DESC LIMIT 10"
            ).fetchall()
        for f in filas:
            print(f"{f[0]}  {f[1]:<15} {f[2]:<20} {f[3]}  {f[4]:%Y-%m-%d %H:%M}")
        return 0
    if orden == "reintentar" and len(args) == 2:
        ok = repo.reintentar(args[1])
        print("reintentando" if ok else "esa reunión no está en error")
        return 0 if ok else 1
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
