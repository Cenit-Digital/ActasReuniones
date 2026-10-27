"""Órdenes de `scripts/actas.sh` (KubernetesInfrastructure), que las ejecuta con `kubectl exec` en el contenedor del
supervisor: escriben la petición en la base y el supervisor la atiende. Hasta F2 es la única forma de grabar.

  python -m actas.cli grabar SOCIO[,SOCIO...] VERSION [SALA]
                                                        socios conformes (streamIDs), versión del texto informativo y
                                                        sala (su nombre en VDO.Ninja); sin SALA, la única que haya
  python -m actas.cli parar                             para la grabación activa
  python -m actas.cli estado                            las últimas reuniones (id, estado, motivo, socios)
  python -m actas.cli reintentar ID                     una reunión en `error` vuelve a enviarse a la plataforma
"""

import os
import sys

from actas.base import Repositorio
from actas.conformidad import ConformidadNoValida, validar

_ARGUMENTOS = {"grabar": (3, 4), "parar": (1,), "estado": (1,), "reintentar": (2,)}


def main(args: list[str], repo: Repositorio | None = None) -> int:
    orden = args[0] if args else ""
    if len(args) not in _ARGUMENTOS.get(orden, ()):
        print(__doc__, file=sys.stderr)
        return 2
    repo = repo or Repositorio(os.environ["ACTAS_DSN"])
    if orden == "grabar":
        try:
            peticion = validar([s for s in args[1].split(",") if s], args[2])
            sala = _sala(repo, args[3] if len(args) == 4 else None)
        except ConformidadNoValida as e:
            print(f"rechazada: {e}", file=sys.stderr)
            return 1
        print(repo.pedir(peticion, sala_id=sala))
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


def _sala(repo: Repositorio, room: str | None) -> str:
    """El id de la sala en la que se graba (V2): la indicada por su nombre en VDO.Ninja o, sin indicarla, la única."""
    salas = repo.ids_de_salas()
    if room is not None:
        elegidas = [sid for sid, r in salas if r == room]
        if not elegidas:
            raise ConformidadNoValida("no existe la sala indicada: créala en el panel")
        return elegidas[0]
    if not salas:
        raise ConformidadNoValida("no hay ninguna sala: créala en el panel («Salas y socios»)")
    if len(salas) > 1:
        raise ConformidadNoValida("hay varias salas: indica en cuál se graba (su nombre en VDO.Ninja)")
    return salas[0][0]


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
