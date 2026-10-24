"""Migraciones del archivo de actas: `python -m actas.migrar`, en el initContainer del pod (KubernetesInfrastructure,
kubernetes/apps/actas). Es el único proceso con la contraseña de actas_owner: el supervisor, de larga duración, solo tiene la de
actas_app, sin DDL (revisión de seguridad de #223, M2).

  ACTAS_DSN_MIGRACIONES       libpq del rol actas_owner
  ACTAS_MIGRACIONES_PASSWORD  su contraseña (Secret postgres-owner)
"""

import os
import sys

from actas import base
from actas.registro import Registro


def main() -> int:
    clave = os.environ.get("ACTAS_MIGRACIONES_PASSWORD", "")
    registro = Registro([clave])
    try:
        aplicadas = base.migrar(os.environ["ACTAS_DSN_MIGRACIONES"], password=clave or None)
    except Exception as e:  # noqa: BLE001 — sin traza: el mensaje de la base puede llevar datos de conexión
        registro("las migraciones fallaron:", type(e).__name__)
        return 1
    registro("migraciones aplicadas:", ", ".join(aplicadas) or "ninguna")
    return 0


if __name__ == "__main__":
    sys.exit(main())
