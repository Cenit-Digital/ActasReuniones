-- Archivo de las actas, F1 (ADR 0015 de KubernetesInfrastructure, decisiones 5 y 6). Inquilino `actas` del PostgreSQL
-- compartido (ADR 0019): lo aplica actas_owner en el esquema `actas`; actas_app recibe SELECT, INSERT, UPDATE y DELETE por los
-- privilegios por defecto del inquilino. Sin secuencias: claves uuid (gen_random_uuid, núcleo desde PostgreSQL 13).

CREATE TABLE reuniones (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    creado_en       timestamptz NOT NULL DEFAULT now(),
    actualizado_en  timestamptz NOT NULL DEFAULT now(),
    estado          text NOT NULL DEFAULT 'pedida'
                    CHECK (estado IN ('pedida', 'grabando', 'grabada', 'transcribiendo', 'transcrita', 'error')),
    -- @a6: nunca sin socios conformes (y como mucho las 16 pistas de la plataforma).
    socios          text[] NOT NULL CHECK (cardinality(socios) BETWEEN 1 AND 16),
    texto_version   text NOT NULL CHECK (texto_version ~ '^[A-Za-z0-9._-]{1,40}$'),
    inicio          timestamptz,
    fin             timestamptz,
    parar_pedido_en timestamptz,
    motivo          text,
    trabajo_id      uuid
);
-- Como mucho una grabación activa: el grabador tiene un solo Chromium y un solo directorio de descargas.
CREATE UNIQUE INDEX reuniones_una_activa ON reuniones ((true)) WHERE estado IN ('grabando');

CREATE TABLE conformidades (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    reunion_id    uuid NOT NULL REFERENCES reuniones (id) ON DELETE CASCADE,
    socio         text NOT NULL CHECK (socio ~ '^[a-z0-9]{1,32}$'),
    texto_version text NOT NULL,
    creado_en     timestamptz NOT NULL DEFAULT now(),
    UNIQUE (reunion_id, socio)
);

CREATE TABLE segmentos (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    reunion_id  uuid NOT NULL REFERENCES reuniones (id) ON DELETE CASCADE,
    hablante    text NOT NULL,
    inicio_ms   integer NOT NULL CHECK (inicio_ms >= 0),
    fin_ms      integer NOT NULL CHECK (fin_ms >= inicio_ms),
    texto       text NOT NULL,
    creado_en   timestamptz NOT NULL DEFAULT now(),
    tsv         tsvector GENERATED ALWAYS AS (to_tsvector('spanish', texto)) STORED
);
CREATE INDEX segmentos_reunion ON segmentos (reunion_id, inicio_ms);
CREATE INDEX segmentos_tsv ON segmentos USING gin (tsv);

-- Traza de cada borrado de audio (@a10): sin nombres de fichero ni de socios.
CREATE TABLE purgas (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    reunion_id  uuid,
    motivo      text NOT NULL,
    ficheros    integer NOT NULL,
    bytes       bigint NOT NULL,
    creado_en   timestamptz NOT NULL DEFAULT now()
);

-- @a6 en la base: una reunión no existe sin la conformidad de cada uno de sus socios, con la misma versión del texto
-- informativo. Diferido: la reunión y sus conformidades se insertan en la misma transacción (Repositorio.pedir).
CREATE FUNCTION comprobar_conformidades() RETURNS trigger
LANGUAGE plpgsql SET search_path FROM CURRENT AS $$
BEGIN
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
CREATE CONSTRAINT TRIGGER reuniones_con_conformidades
    AFTER INSERT OR UPDATE OF socios, texto_version ON reuniones
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION comprobar_conformidades();
