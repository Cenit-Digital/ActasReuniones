-- La edad del estado no es la edad de actualizado_en: el panel puede modificar esa columna sin cambiar el estado.
-- Para reuniones anteriores usamos el último evento de transición conocido; si no existe, actualizado_en es el mejor
-- límite disponible. Las nuevas transiciones, incluso las ejecutadas por funciones SQL, quedan registradas por el trigger.
ALTER TABLE reuniones ADD COLUMN estado_desde timestamptz;
UPDATE reuniones r SET estado_desde = COALESCE(
    (SELECT max(e.momento) FROM eventos e
     WHERE e.reunion_id = r.id AND e.tipo = 'estado' AND e.detalle->>'hasta' = r.estado),
    r.actualizado_en
);
ALTER TABLE reuniones ALTER COLUMN estado_desde SET DEFAULT now();
ALTER TABLE reuniones ALTER COLUMN estado_desde SET NOT NULL;

CREATE FUNCTION marcar_cambio_estado() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.estado IS DISTINCT FROM OLD.estado THEN
        NEW.estado_desde := clock_timestamp();
    END IF;
    RETURN NEW;
END
$$;
CREATE TRIGGER reuniones_marcar_cambio_estado BEFORE UPDATE OF estado ON reuniones
    FOR EACH ROW EXECUTE FUNCTION marcar_cambio_estado();
