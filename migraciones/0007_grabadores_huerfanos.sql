-- Grabadores huérfanos (reuniones del 2026-10-28 y del 2026-10-30): tres claves nuevas en el historial. Lo aplica actas_owner.
-- Solo amplía la lista blanca de `evento_detalle_valido` (0005): toda fila que ya pasaba el CHECK lo sigue pasando, y la imagen
-- anterior no escribe ninguna de las claves nuevas. Las mismas claves están en src/actas/eventos.py (tests/unit/test_eventos.py).
--   rescatadas: descargas a medias que el grabador rescató al parar (webm válido hasta el último trozo escrito).
--   perdidas: descargas a medias que no se envían a transcribir.
--   sin_grabar: socios conformes que publican en la sala y cuya página no graba.
-- CREATE OR REPLACE con la misma firma conserva el CHECK que la usa (doc de CREATE FUNCTION, PostgreSQL 18).
CREATE OR REPLACE FUNCTION evento_detalle_valido(d jsonb) RETURNS boolean
LANGUAGE sql IMMUTABLE PARALLEL SAFE RETURN
    jsonb_typeof(d) = 'object'
    AND NOT EXISTS (
        SELECT 1 FROM jsonb_each(d) AS e(clave, valor)
        WHERE e.clave NOT IN ('desde', 'hasta', 'motivo', 'causa', 'completas', 'socios', 'pistas', 'segmentos', 'ficheros',
                              'bytes', 'codigo', 'accion', 'intento', 'faltan', 'usuario', 'resultado',
                              'rescatadas', 'perdidas', 'sin_grabar')
           OR NOT CASE jsonb_typeof(e.valor)
                    WHEN 'null' THEN true
                    WHEN 'boolean' THEN true
                    WHEN 'number' THEN e.valor::text ~ '^-?[0-9]{1,18}$'
                    WHEN 'string' THEN (e.valor #>> '{}') ~ '^[A-Za-z0-9._@:-]{0,64}$'
                    ELSE false
                  END
    );
