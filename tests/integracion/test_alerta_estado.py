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


def test_migracion_historica_usa_ultimo_evento_o_actualizacion(dsn, monkeypatch):
    from actas import base

    url, esquema = dsn
    migraciones = base._migraciones()
    monkeypatch.setattr(base, "_migraciones", lambda: migraciones[:-1])
    base.migrar(url, esquema)
    repo = base.Repositorio(url, esquema)
    con_evento = repo.pedir(Peticion(("socioa",), "v1"))
    sin_evento = repo.pedir(Peticion(("sociob",), "v1"))
    repo.mover(con_evento, Estado.PEDIDA, Estado.GRABANDO)
    with repo.conexion() as c:
        c.execute("UPDATE eventos SET momento = now() - interval '7 hours' WHERE reunion_id = %s", (con_evento,))
        c.execute("UPDATE reuniones SET actualizado_en = now() WHERE id = %s", (con_evento,))
        c.execute("UPDATE reuniones SET actualizado_en = now() - interval '8 hours' WHERE id = %s", (sin_evento,))
    monkeypatch.setattr(base, "_migraciones", lambda: migraciones)
    assert base.migrar(url, esquema) == ["0008_estado_desde.sql"]
    assert repo.cuenta_atascadas() == 2
