-- Programar, modificar, cancelar, papelera y purga: V3 de KubernetesInfrastructure#298 (ADR 0023, decisiones 5 y 6). Lo aplica
-- actas_owner.
--
-- Numerada 0006, no 0004 (el número que reservaba el plan): amplía los tipos de `eventos`, que crea la 0005, y en una base nueva
-- una 0004 correría antes que ella (base.migrar aplica por nombre, en orden, las que faltan). Lo decidió Pablo el 2026-10-27 en
-- #298; el hueco 0004 queda sin usar. Solo añade columnas, objetos y privilegios, y amplía dos CHECK: la imagen anterior sigue
-- funcionando con ella (ADR 0023, «Vuelta atrás»).
--
-- La puerta @a33 (`actas-gate.sh f2`) exige que actas_panel no tenga más UPDATE que el de la parada ni ningún DELETE: el panel
-- programa, modifica, cancela, manda a la papelera y recupera solo por las funciones SECURITY DEFINER de abajo, propiedad de
-- actas_owner. Ningún rol de aplicación tiene DELETE (comprobado en la base viva el 2026-10-27; los privilegios por defecto del
-- inquilino son SELECT, INSERT y UPDATE): se borra solo con `borrar_reunion`, que nadie más que el dueño ejecuta, desde
-- `purgar_actas`, que ejecuta el supervisor una vez al día. Doc de CREATE FUNCTION (PostgreSQL 18), «Writing SECURITY DEFINER
-- Functions Safely»: search_path fijo, con pg_temp explícito y el último, y EXECUTE quitado a PUBLIC antes de darlo.

-- 1. Lo programado de cada reunión. `tope_min`: el de «Parar como mucho a las», nunca más de las 3 h de F1 (@a7). `espera_min`:
-- cuánto se espera a empezar y a que entre algún socio. `repetir_dia`: el día del mes de una serie mensual, para no correrse
-- (31 → 28 de febrero → 31 de marzo). `anterior_id`: la reunión de la serie de la que nace (@a53), y `repetida_en`, cuándo se
-- creó su siguiente (si la siguiente se borra, no se vuelve a crear). `papelera_*`: «Eliminar» (ADR 0023, decisión 6).
ALTER TABLE reuniones
    ADD COLUMN titulo          text CHECK (char_length(titulo) BETWEEN 1 AND 120 AND titulo !~ '[[:cntrl:]]'),
    ADD COLUMN programada_para timestamptz,
    ADD COLUMN tope_min        integer NOT NULL DEFAULT 180 CHECK (tope_min BETWEEN 1 AND 180),
    ADD COLUMN repetir         text NOT NULL DEFAULT 'no' CHECK (repetir IN ('no', 'semanal', 'mensual')),
    ADD COLUMN repetir_dia     integer CHECK (repetir_dia BETWEEN 1 AND 31),
    ADD COLUMN espera_min      integer CHECK (espera_min BETWEEN 1 AND 120),
    ADD COLUMN anterior_id     uuid REFERENCES reuniones (id) ON DELETE SET NULL,
    ADD COLUMN repetida_en     timestamptz,
    ADD COLUMN papelera_en     timestamptz,
    ADD COLUMN papelera_por    text CHECK (papelera_por ~ '^[A-Za-z0-9._@-]{1,64}$');

-- 2. Estados nuevos y sus reglas. Solo va a la papelera una reunión terminada: una `grabada` se seguiría enviando.
ALTER TABLE reuniones
    DROP CONSTRAINT reuniones_estado_check,
    ADD CONSTRAINT reuniones_estado_check CHECK (estado IN ('pedida', 'grabando', 'grabada', 'transcribiendo', 'transcrita',
                                                            'error', 'programada', 'cancelada')),
    ADD CONSTRAINT reuniones_programada_con_hora
        CHECK (estado <> 'programada' OR (programada_para IS NOT NULL AND espera_min IS NOT NULL)),
    ADD CONSTRAINT reuniones_papelera_terminada
        CHECK (papelera_en IS NULL OR (estado IN ('transcrita', 'error', 'cancelada') AND papelera_por IS NOT NULL));
CREATE UNIQUE INDEX reuniones_una_siguiente ON reuniones (anterior_id);
CREATE INDEX reuniones_programadas ON reuniones (programada_para) WHERE estado = 'programada';

-- 3. El historial de los cambios (el estado ya lo anota cada transición): `modificada` y `papelera` (eliminada o recuperada),
-- con el usuario de BasicAuth. Sin claves nuevas en la lista blanca de `detalle` (@a55).
ALTER TABLE eventos
    DROP CONSTRAINT eventos_tipo_check,
    ADD CONSTRAINT eventos_tipo_check
        CHECK (tipo IN ('estado', 'envio', 'consulta', 'aviso', 'audio_borrado', 'reintento', 'modificada', 'papelera'));

-- 4. Quién mandó a la papelera lo que se borra (nulo en la purga de 12 meses). Sin contenido: ni título ni socios.
ALTER TABLE purgas ADD COLUMN usuario text CHECK (usuario ~ '^[A-Za-z0-9._@-]{1,64}$');

-- 5. @a6 en la base, con programadas. Una programada aún no graba (la siguiente de una serie nace sin conformidades, @a53), y una
-- cancelada o un error sin grabación nunca grabaron: la comprobación espera al paso a `grabando`, que ahora también la dispara
-- (UPDATE OF estado). Pablo, 2026-10-27: si falta la conformidad de un solo socio, no se graba.
CREATE OR REPLACE FUNCTION comprobar_conformidades() RETURNS trigger
LANGUAGE plpgsql SET search_path FROM CURRENT AS $$
BEGIN
    IF NEW.estado IN ('programada', 'cancelada') OR (NEW.estado = 'error' AND NEW.inicio IS NULL) THEN
        RETURN NULL;
    END IF;
    IF EXISTS (
        SELECT 1 FROM unnest(NEW.socios) AS s(socio)
        WHERE NOT EXISTS (
            SELECT 1 FROM conformidades c
            WHERE c.reunion_id = NEW.id AND c.socio = s.socio AND c.texto_version = NEW.texto_version
        )
    ) THEN
        RAISE EXCEPTION 'reunión sin la conformidad de cada socio' USING ERRCODE = 'check_violation';
    END IF;
    RETURN NULL;
END
$$;
DROP TRIGGER reuniones_con_conformidades ON reuniones;
CREATE CONSTRAINT TRIGGER reuniones_con_conformidades
    AFTER INSERT OR UPDATE OF socios, texto_version, estado ON reuniones
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION comprobar_conformidades();

-- 6. B1 de #287 con programadas: las conformidades se siguen escribiendo con su reunión (una `pedida` en la transacción que la
-- crea) y, en una programada, solo el dueño, es decir, `programar` y `modificar_programada`: ni el panel ni el supervisor
-- añaden por su cuenta conformidades a una reunión, programada o pasada.
CREATE OR REPLACE FUNCTION conformidad_con_su_reunion() RETURNS trigger
LANGUAGE plpgsql SET search_path FROM CURRENT AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM reuniones r
        WHERE r.id = NEW.reunion_id
          AND ((r.estado = 'pedida' AND r.creado_en = now())
               OR (r.estado = 'programada'
                   AND (SELECT c.relowner FROM pg_class c WHERE c.oid = TG_RELID)
                       = (SELECT o.oid FROM pg_roles o WHERE o.rolname = current_user)))
    ) THEN
        RAISE EXCEPTION 'conformidad fuera de la petición de su reunión' USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END
$$;

-- 7. @a49: lo programado solo cambia mientras la reunión está `programada`. Un trigger, porque actas_app (el supervisor) tiene
-- UPDATE de tabla; el panel no tiene UPDATE de ninguna de estas columnas. La vida de la reunión (estado, motivo, inicio, fin,
-- parada, reintento, trabajo, papelera) no se congela.
CREATE FUNCTION programacion_congelada() RETURNS trigger
LANGUAGE plpgsql SET search_path FROM CURRENT AS $$
BEGIN
    IF OLD.estado <> 'programada'
       AND (NEW.titulo, NEW.sala_id, NEW.programada_para, NEW.tope_min, NEW.repetir, NEW.repetir_dia, NEW.espera_min,
            NEW.socios, NEW.texto_version)
           IS DISTINCT FROM
           (OLD.titulo, OLD.sala_id, OLD.programada_para, OLD.tope_min, OLD.repetir, OLD.repetir_dia, OLD.espera_min,
            OLD.socios, OLD.texto_version) THEN
        RAISE EXCEPTION 'solo se modifica una reunión programada' USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END
$$;
CREATE TRIGGER reuniones_programacion_congelada
    BEFORE UPDATE ON reuniones
    FOR EACH ROW EXECUTE FUNCTION programacion_congelada();

-- Una reunión nace `pedida` («Grabar ahora», actas.sh) o `programada` (el panel o la siguiente de una serie): nadie inserta una
-- ya grabada o transcrita.
CREATE FUNCTION reunion_nace_pedida_o_programada() RETURNS trigger
LANGUAGE plpgsql SET search_path FROM CURRENT AS $$
BEGIN
    IF NEW.estado NOT IN ('pedida', 'programada') THEN
        RAISE EXCEPTION 'una reunión nace pedida o programada' USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END
$$;
CREATE TRIGGER reuniones_nace_pedida_o_programada
    BEFORE INSERT ON reuniones
    FOR EACH ROW EXECUTE FUNCTION reunion_nace_pedida_o_programada();

-- 8. Programar (el panel): la reunión y una conformidad por socio, en la misma transacción. Solo en el futuro.
CREATE FUNCTION programar(p_titulo text, p_sala uuid, p_para timestamptz, p_tope integer, p_repetir text, p_espera integer,
                          p_socios text[], p_version text, p_usuario text) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE
    rid uuid;
BEGIN
    IF p_para IS NULL OR p_para <= now() OR p_sala IS NULL THEN
        RAISE EXCEPTION 'programar: sin sala o en el pasado' USING ERRCODE = 'check_violation';
    END IF;
    INSERT INTO reuniones (estado, titulo, sala_id, programada_para, tope_min, repetir, repetir_dia, espera_min, socios,
                           texto_version, pedido_por)
    VALUES ('programada', p_titulo, p_sala, p_para, p_tope, p_repetir,
            CASE WHEN p_repetir = 'mensual' THEN extract(day FROM p_para AT TIME ZONE 'Europe/Madrid')::integer END,
            p_espera, p_socios, p_version, p_usuario)
    RETURNING id INTO rid;
    INSERT INTO conformidades (reunion_id, socio, texto_version) SELECT rid, s, p_version FROM unnest(p_socios) AS s;
    RETURN rid;
END
$$;

-- 9. @a49, modificar (el panel): todo lo programado, solo mientras está `programada` y a una hora futura. Las conformidades se
-- reescriben con los socios marcados. True si se guarda, false si ya no está programada y NULL si no existe.
CREATE FUNCTION modificar_programada(p_id uuid, p_titulo text, p_sala uuid, p_para timestamptz, p_tope integer, p_repetir text,
                                     p_espera integer, p_socios text[], p_version text, p_usuario text) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER AS $$
BEGIN
    IF p_para IS NULL OR p_para <= now() OR p_sala IS NULL THEN
        RAISE EXCEPTION 'modificar: sin sala o en el pasado' USING ERRCODE = 'check_violation';
    END IF;
    UPDATE reuniones
    SET titulo = p_titulo, sala_id = p_sala, programada_para = p_para, tope_min = p_tope, repetir = p_repetir,
        repetir_dia = CASE WHEN p_repetir = 'mensual' THEN extract(day FROM p_para AT TIME ZONE 'Europe/Madrid')::integer END,
        espera_min = p_espera, socios = p_socios, texto_version = p_version, actualizado_en = now()
    WHERE id = p_id AND estado = 'programada';
    IF NOT FOUND THEN
        RETURN CASE WHEN EXISTS (SELECT 1 FROM reuniones WHERE id = p_id) THEN false END;
    END IF;
    DELETE FROM conformidades WHERE reunion_id = p_id;
    INSERT INTO conformidades (reunion_id, socio, texto_version) SELECT p_id, s, p_version FROM unnest(p_socios) AS s;
    INSERT INTO eventos (reunion_id, tipo, detalle) VALUES (p_id, 'modificada', jsonb_build_object('usuario', p_usuario));
    RETURN true;
END
$$;

-- 10. @a50, cancelar (el panel): no borra nada. `p_serie`: tampoco se crea la siguiente de la serie.
CREATE FUNCTION cancelar_reunion(p_id uuid, p_usuario text, p_serie boolean) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER AS $$
BEGIN
    UPDATE reuniones
    SET estado = 'cancelada', motivo = 'panel', actualizado_en = now(), repetir = CASE WHEN p_serie THEN 'no' ELSE repetir END
    WHERE id = p_id AND estado = 'programada';
    IF NOT FOUND THEN
        RETURN CASE WHEN EXISTS (SELECT 1 FROM reuniones WHERE id = p_id) THEN false END;
    END IF;
    INSERT INTO eventos (reunion_id, tipo, detalle)
    VALUES (p_id, 'estado', jsonb_build_object('desde', 'programada', 'hasta', 'cancelada', 'usuario', p_usuario)
                            || CASE WHEN p_serie THEN '{"accion": "serie"}'::jsonb ELSE '{}'::jsonb END);
    RETURN true;
END
$$;

-- 11. «Eliminar» y «Recuperar» (el panel, ADR 0023 decisión 6): la papelera, 7 días.
CREATE FUNCTION a_papelera(p_id uuid, p_usuario text) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER AS $$
BEGIN
    UPDATE reuniones SET papelera_en = now(), papelera_por = p_usuario
    WHERE id = p_id AND estado IN ('transcrita', 'error', 'cancelada') AND papelera_en IS NULL;
    IF NOT FOUND THEN
        RETURN CASE WHEN EXISTS (SELECT 1 FROM reuniones WHERE id = p_id) THEN false END;
    END IF;
    INSERT INTO eventos (reunion_id, tipo, detalle)
    VALUES (p_id, 'papelera', jsonb_build_object('accion', 'eliminada', 'usuario', p_usuario));
    RETURN true;
END
$$;

CREATE FUNCTION recuperar(p_id uuid, p_usuario text) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER AS $$
BEGIN
    UPDATE reuniones SET papelera_en = NULL, papelera_por = NULL WHERE id = p_id AND papelera_en IS NOT NULL;
    IF NOT FOUND THEN
        RETURN CASE WHEN EXISTS (SELECT 1 FROM reuniones WHERE id = p_id) THEN false END;
    END IF;
    INSERT INTO eventos (reunion_id, tipo, detalle)
    VALUES (p_id, 'papelera', jsonb_build_object('accion', 'recuperada', 'usuario', p_usuario));
    RETURN true;
END
$$;

-- 12. @a51: el borrado de verdad. Borra la reunión y, en cascada, sus conformidades, segmentos y eventos, y deja en `purgas` el
-- id, el motivo y quién la mandó a la papelera, sin contenido. Solo la ejecuta el dueño (aquí, `purgar_actas`): ni el panel ni
-- el supervisor eligen qué se borra. Los backups lo alargan unos 6 meses (ADR 0015, decisión 5).
CREATE FUNCTION borrar_reunion(p_id uuid, p_motivo text, p_usuario text) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER AS $$
BEGIN
    DELETE FROM reuniones WHERE id = p_id;
    IF NOT FOUND THEN
        RETURN false;
    END IF;
    INSERT INTO purgas (reunion_id, motivo, ficheros, bytes, usuario) VALUES (p_id, p_motivo, 0, 0, p_usuario);
    RETURN true;
END
$$;

-- 13. @a51 y @a52: la purga diaria (el supervisor). Lo que lleva más de 7 días en la papelera y lo terminado hace más de 12
-- meses (ADR 0015, decisión 5), contado desde el fin de la grabación o, si no grabó, desde su hora o su creación. Lo que está
-- en marcha nunca. Devuelve cuántas borró.
CREATE FUNCTION purgar_actas() RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE
    n integer := 0;
    r record;
BEGIN
    FOR r IN SELECT id, papelera_por FROM reuniones WHERE papelera_en < now() - interval '7 days' ORDER BY papelera_en LOOP
        n := n + borrar_reunion(r.id, 'papelera_7d', r.papelera_por)::integer;
    END LOOP;
    FOR r IN SELECT id FROM reuniones
             WHERE estado IN ('transcrita', 'error', 'cancelada')
               AND coalesce(fin, programada_para, creado_en) < now() - interval '12 months'
             ORDER BY creado_en LOOP
        n := n + borrar_reunion(r.id, 'plazo_12m', NULL)::integer;
    END LOOP;
    RETURN n;
END
$$;

-- 14. search_path fijo, como en 0003 y 0005: una tabla temporal no puede suplantar `reuniones`.
DO $$
BEGIN
    EXECUTE format('ALTER FUNCTION programar(text, uuid, timestamptz, integer, text, integer, text[], text, text) '
                   'SET search_path = %I, pg_temp', current_schema());
    EXECUTE format('ALTER FUNCTION modificar_programada(uuid, text, uuid, timestamptz, integer, text, integer, text[], text, '
                   'text) SET search_path = %I, pg_temp', current_schema());
    EXECUTE format('ALTER FUNCTION cancelar_reunion(uuid, text, boolean) SET search_path = %I, pg_temp', current_schema());
    EXECUTE format('ALTER FUNCTION a_papelera(uuid, text) SET search_path = %I, pg_temp', current_schema());
    EXECUTE format('ALTER FUNCTION recuperar(uuid, text) SET search_path = %I, pg_temp', current_schema());
    EXECUTE format('ALTER FUNCTION borrar_reunion(uuid, text, text) SET search_path = %I, pg_temp', current_schema());
    EXECUTE format('ALTER FUNCTION purgar_actas() SET search_path = %I, pg_temp', current_schema());
END
$$;

-- 15. Permisos. «Grabar ahora» con título y tope: INSERT por columnas, como el resto de `pedir` (0002 y 0003).
REVOKE ALL ON FUNCTION programar(text, uuid, timestamptz, integer, text, integer, text[], text, text),
                       modificar_programada(uuid, text, uuid, timestamptz, integer, text, integer, text[], text, text),
                       cancelar_reunion(uuid, text, boolean), a_papelera(uuid, text), recuperar(uuid, text),
                       borrar_reunion(uuid, text, text), purgar_actas()
    FROM PUBLIC;
GRANT EXECUTE ON FUNCTION programar(text, uuid, timestamptz, integer, text, integer, text[], text, text),
                          modificar_programada(uuid, text, uuid, timestamptz, integer, text, integer, text[], text, text),
                          cancelar_reunion(uuid, text, boolean), a_papelera(uuid, text), recuperar(uuid, text)
    TO actas_panel;
GRANT EXECUTE ON FUNCTION purgar_actas() TO actas_app;
GRANT INSERT (titulo, tope_min) ON reuniones TO actas_panel;
