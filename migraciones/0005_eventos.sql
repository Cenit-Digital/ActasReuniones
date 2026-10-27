-- Registros, diagnóstico y reintentar: V4 de KubernetesInfrastructure#298 (ADR 0023, decisión 7). Lo aplica actas_owner.
-- Solo añade: ni toca filas existentes ni quita privilegios. Las migraciones 0003 (V2) y 0004 (V3) pueden aplicarse después que
-- esta en una base ya migrada (base.migrar aplica por nombre las que faltan).
--
-- 1. Historial de cada reunión. Lo escribe el supervisor (actas_app, por los privilegios por defecto del inquilino): cada cambio
-- de estado en la misma transacción que el UPDATE (@a54), las respuestas de transcribir, el aviso de socios, la purga del audio y
-- los reintentos. `detalle` solo admite la lista blanca (@a55): claves conocidas, y valores enteros, booleanos, nulos o códigos
-- cortos sin espacios. La misma lista está en src/actas/eventos.py, que además rechaza cualquier valor con un secreto (la
-- contraseña de la sala solo la conoce el proceso). IMMUTABLE: solo mira su argumento (doc de CREATE FUNCTION, PostgreSQL 18).
CREATE FUNCTION evento_detalle_valido(d jsonb) RETURNS boolean
LANGUAGE sql IMMUTABLE PARALLEL SAFE RETURN
    jsonb_typeof(d) = 'object'
    AND NOT EXISTS (
        SELECT 1 FROM jsonb_each(d) AS e(clave, valor)
        WHERE e.clave NOT IN ('desde', 'hasta', 'motivo', 'causa', 'completas', 'socios', 'pistas', 'segmentos', 'ficheros',
                              'bytes', 'codigo', 'accion', 'intento', 'faltan', 'usuario', 'resultado')
           OR NOT CASE jsonb_typeof(e.valor)
                    WHEN 'null' THEN true
                    WHEN 'boolean' THEN true
                    WHEN 'number' THEN e.valor::text ~ '^-?[0-9]{1,18}$'
                    WHEN 'string' THEN (e.valor #>> '{}') ~ '^[A-Za-z0-9._@:-]{0,64}$'
                    ELSE false
                  END
    );

CREATE TABLE eventos (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    reunion_id  uuid REFERENCES reuniones (id) ON DELETE CASCADE,  -- nulo: el evento no es de ninguna reunión
    momento     timestamptz NOT NULL DEFAULT clock_timestamp(),  -- no now(): dos eventos de una transacción, en su orden
    tipo        text NOT NULL
                CHECK (tipo IN ('estado', 'envio', 'consulta', 'aviso', 'audio_borrado', 'reintento')),
    detalle     jsonb NOT NULL DEFAULT '{}' CHECK (evento_detalle_valido(detalle))
);
CREATE INDEX eventos_reunion ON eventos (reunion_id, momento);
CREATE INDEX eventos_momento ON eventos (momento);

-- 2. Latido del supervisor: una sola fila que reescribe en cada vuelta (cada 5 s). Su edad la calcula el panel con now() de la
-- base. Claves: versión de Chromium (nula si no responde), imagen (sha-<commit>), ocupación y tamaño del tmpfs, la última
-- respuesta de transcribir y las reuniones que aún tienen audio en el tmpfs (lo que decide si «Reintentar» tiene sentido).
CREATE FUNCTION latido_detalle_valido(d jsonb) RETURNS boolean
LANGUAGE sql IMMUTABLE PARALLEL SAFE RETURN
    jsonb_typeof(d) = 'object'
    AND NOT EXISTS (
        SELECT 1 FROM jsonb_each(d) AS e(clave, valor)
        WHERE NOT CASE
            WHEN e.clave IN ('chromium', 'imagen') THEN
                jsonb_typeof(e.valor) = 'null' OR (e.valor #>> '{}') ~ '^[A-Za-z0-9._/:-]{0,80}$'
            WHEN e.clave IN ('grabaciones_bytes', 'grabaciones_total', 'transcribir_codigo') THEN
                jsonb_typeof(e.valor) = 'null' OR e.valor::text ~ '^[0-9]{1,18}$'
            WHEN e.clave = 'con_audio' THEN
                jsonb_typeof(e.valor) = 'array' AND jsonb_array_length(e.valor) <= 1000 AND NOT EXISTS (
                    SELECT 1 FROM jsonb_array_elements(e.valor) AS a(x)
                    WHERE jsonb_typeof(a.x) <> 'string'
                       OR (a.x #>> '{}') !~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
                )
            ELSE false
        END
    );

CREATE TABLE latido (
    unico    boolean PRIMARY KEY DEFAULT true CHECK (unico),
    momento  timestamptz NOT NULL DEFAULT now(),
    detalle  jsonb NOT NULL CHECK (latido_detalle_valido(detalle))
);

-- 3. «Reintentar» desde el panel (@a57), como «Parar»: el panel solo anota la petición y quién la hizo (X-Actas-Usuario), y el
-- supervisor la atiende (error → grabada) y la limpia en el mismo UPDATE. Solo se puede pedir en una reunión en error.
ALTER TABLE reuniones
    ADD COLUMN reintento_pedido_en  timestamptz,
    ADD COLUMN reintento_pedido_por text CHECK (reintento_pedido_por ~ '^[A-Za-z0-9._@-]{1,64}$');

CREATE FUNCTION reintento_solo_en_error() RETURNS trigger
LANGUAGE plpgsql SET search_path FROM CURRENT AS $$
BEGIN
    IF NEW.reintento_pedido_en IS NOT NULL AND OLD.reintento_pedido_en IS NULL AND OLD.estado <> 'error' THEN
        RAISE EXCEPTION 'solo se reintenta una reunión en error' USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END
$$;
CREATE TRIGGER reuniones_reintento_solo_en_error
    BEFORE UPDATE OF reintento_pedido_en ON reuniones
    FOR EACH ROW EXECUTE FUNCTION reintento_solo_en_error();

-- El panel no recibe UPDATE de ninguna columna nueva: la puerta @a33 (`actas-gate.sh f2` de KubernetesInfrastructure) exige
-- que su único UPDATE sea el de la parada. Pide el reintento con esta función, propiedad de actas_owner (SECURITY DEFINER,
-- doc de CREATE FUNCTION de PostgreSQL 18), que solo hace eso: true si lo anota, false si la reunión no está en error o ya
-- tiene una petición, y NULL si no existe. search_path fijo con pg_temp explícito y el último, como las de 0003 (doc de CREATE
-- FUNCTION, «Writing SECURITY DEFINER Functions Safely»): una tabla temporal no puede suplantar `reuniones`.
CREATE FUNCTION pedir_reintento(p_reunion uuid, p_usuario text) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER AS $$
BEGIN
    UPDATE reuniones SET reintento_pedido_en = now(), reintento_pedido_por = p_usuario
    WHERE id = p_reunion AND estado = 'error' AND reintento_pedido_en IS NULL;
    IF FOUND THEN
        RETURN true;
    END IF;
    RETURN CASE WHEN EXISTS (SELECT 1 FROM reuniones WHERE id = p_reunion) THEN false END;
END
$$;
DO $$ BEGIN
    EXECUTE format('ALTER FUNCTION pedir_reintento(uuid, text) SET search_path = %I, pg_temp', current_schema());
END $$;
REVOKE ALL ON FUNCTION pedir_reintento(uuid, text) FROM PUBLIC;

-- 4. Mínimo privilegio del panel (@a33): lee el historial y el latido, y pide reintentos solo por la función. Sin INSERT en
-- eventos (la contraseña vista, @a45, la anota V2 en su propia tabla `salas_eventos`).
GRANT SELECT ON eventos, latido TO actas_panel;
GRANT EXECUTE ON FUNCTION pedir_reintento(uuid, text) TO actas_panel;
