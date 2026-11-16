"""La antigüedad se mide desde el cambio de estado, no desde otra modificación de la reunión."""

from actas.conformidad import Peticion
from actas.estados import Estado


def test_reuniones_atascadas_y_cambio_de_estado(repo):
    rid = repo.pedir(Peticion(("socioa",), "v1"))
    with repo.conexion() as c:
        c.execute("UPDATE reuniones SET estado_desde = now() - interval '7 hours' WHERE id = %s", (rid,))
        c.execute("UPDATE reuniones SET actualizado_en = now() WHERE id = %s", (rid,))
    assert repo.cuenta_atascadas() == 1
    repo.mover(rid, Estado.PEDIDA, Estado.GRABANDO)
    assert repo.cuenta_atascadas() == 0
    with repo.conexion() as c:
        c.execute("UPDATE reuniones SET estado_desde = now() - interval '7 hours' WHERE id = %s", (rid,))
        c.execute("UPDATE reuniones SET estado = 'error' WHERE id = %s", (rid,))
    assert repo.cuenta_atascadas() == 0
