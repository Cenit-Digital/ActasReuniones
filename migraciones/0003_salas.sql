-- Salas, socios y su auditoría: V2 del panel (KubernetesInfrastructure#298, ADR 0023 decisiones 3 y 4). Lo aplica actas_owner.
--
-- Puede aplicarse después de una migración posterior (V4 usa la 0005 y puede desplegarse antes): solo crea objetos nuevos,
-- añade una columna a `reuniones` y da permisos sobre lo suyo; no quita ninguno que no haya creado aquí.
--
-- La puerta `actas-gate.sh f2` (@a33) exige que actas_panel no tenga UPDATE salvo en `reuniones.parar_pedido_en` y
-- `actualizado_en`, ni DELETE ni TRUNCATE: el panel solo inserta por columnas o ejecuta las dos funciones SECURITY DEFINER de
-- abajo. La auditoría solo la escriben una de ellas y un trigger, también SECURITY DEFINER. Doc de CREATE FUNCTION
-- (PostgreSQL 18), «Writing SECURITY DEFINER Functions Safely»: search_path fijo y EXECUTE quitado a PUBLIC antes de darlo
-- («by default, execute privilege is granted to PUBLIC for newly created functions»).

-- 1. Salas de VDO.Ninja. `room` cabe sin cambios en `sanitizeRoomName` de VDO.Ninja v30.2 (\w, como mucho 30). `cifrada`: nonce
-- de 12 bytes + contraseña cifrada con AES-GCM + etiqueta de 16 (actas.salas), con el room como dato asociado. `hash`: el de
-- los enlaces de los socios (actas.enlaces.hash_sala), que se calcula al crearla para no descifrar al pintar los enlaces.
CREATE TABLE salas (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    nombre      text NOT NULL UNIQUE CHECK (char_length(nombre) BETWEEN 1 AND 64 AND nombre !~ '[[:cntrl:]]'),
    room        text NOT NULL UNIQUE CHECK (room ~ '^[A-Za-z0-9_]{1,30}$'),
    hash        text NOT NULL CHECK (hash ~ '^[0-9a-f]{4}$'),
    cifrada     bytea NOT NULL CHECK (octet_length(cifrada) > 28),
    creada_en   timestamptz NOT NULL DEFAULT now(),
    creada_por  text NOT NULL CHECK (creada_por ~ '^[A-Za-z0-9._@-]{1,64}$')
);

-- 2. Auditoría de las salas (@a45): quién la creó y quién vio su contraseña, y cuándo. Nunca el valor.
CREATE TABLE salas_eventos (
    id       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    sala_id  uuid NOT NULL REFERENCES salas (id),
    tipo     text NOT NULL CHECK (tipo IN ('sala_creada', 'clave_vista')),
    usuario  text NOT NULL CHECK (usuario ~ '^[A-Za-z0-9._@-]{1,64}$'),
    momento  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX salas_eventos_sala ON salas_eventos (sala_id, momento);

-- 3. Socios (sustituyen al ConfigMap actas-socios). `push`: su streamID en VDO.Ninja y en `reuniones.socios`, sin guiones
-- (@a47: VDO.Ninja los cambia por «_»), el mismo formato que `conformidades.socio`. El correo es opcional (dato personal).
CREATE TABLE socios (
    push       text PRIMARY KEY CHECK (push ~ '^[a-z0-9]{1,32}$'),
    nombre     text NOT NULL CHECK (char_length(nombre) BETWEEN 1 AND 64 AND nombre !~ '[[:cntrl:]]'),
    correo     text CHECK (char_length(correo) <= 254 AND correo ~ '^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$'),
    activo     boolean NOT NULL DEFAULT true,
    creado_en  timestamptz NOT NULL DEFAULT now()
);

-- 4. La sala de cada reunión (@a46). NULL en las de antes de V2: el supervisor no las graba sin sala.
ALTER TABLE reuniones ADD COLUMN sala_id uuid REFERENCES salas (id);

-- 5. Ver la contraseña de una sala (@a45): la única forma que tiene el panel de leer `cifrada`, y siempre deja su fila
-- `clave_vista` en la misma transacción (la auditoría no depende del panel). NULL si la sala no existe.
CREATE FUNCTION ver_clave_sala(p_sala uuid, p_usuario text) RETURNS bytea
LANGUAGE plpgsql SECURITY DEFINER SET search_path FROM CURRENT AS $$
DECLARE
    c bytea;
BEGIN
    SELECT s.cifrada INTO c FROM salas s WHERE s.id = p_sala;
    IF c IS NULL THEN
        RETURN NULL;
    END IF;
    INSERT INTO salas_eventos (sala_id, tipo, usuario) VALUES (p_sala, 'clave_vista', p_usuario);
    RETURN c;
END
$$;

-- 6. Quién creó cada sala, desde la propia base: así el panel no necesita escribir en la auditoría (no puede inventarla).
CREATE FUNCTION anotar_sala_creada() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path FROM CURRENT AS $$
BEGIN
    INSERT INTO salas_eventos (sala_id, tipo, usuario) VALUES (NEW.id, 'sala_creada', NEW.creada_por);
    RETURN NULL;
END
$$;
CREATE TRIGGER salas_anotar_creada AFTER INSERT ON salas FOR EACH ROW EXECUTE FUNCTION anotar_sala_creada();

-- 7. Dar de baja o de alta a un socio sin UPDATE de tabla para el panel. True si existe.
CREATE FUNCTION socio_activo(p_push text, p_activo boolean) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path FROM CURRENT AS $$
BEGIN
    UPDATE socios SET activo = p_activo WHERE push = p_push;
    RETURN FOUND;
END
$$;

-- 8. Permisos. actas_app (supervisor y actas.sh) recibe SELECT, INSERT y UPDATE de cada tabla nueva por los privilegios por
-- defecto del inquilino (KubernetesInfrastructure, kubernetes/postgres/inquilinos.sql): aquí se le deja solo lo que necesita,
-- leer las salas para grabar. La auditoría no la puede tocar.
REVOKE ALL ON salas, salas_eventos, socios FROM actas_app, actas_panel;
GRANT SELECT ON salas TO actas_app;

GRANT SELECT (id, nombre, room, hash, creada_en, creada_por) ON salas TO actas_panel;
GRANT INSERT (nombre, room, hash, cifrada, creada_por) ON salas TO actas_panel;
GRANT SELECT ON salas_eventos TO actas_panel;
GRANT SELECT ON socios TO actas_panel;
GRANT INSERT (push, nombre, correo) ON socios TO actas_panel;
GRANT INSERT (sala_id) ON reuniones TO actas_panel;

REVOKE ALL ON FUNCTION ver_clave_sala(uuid, text), socio_activo(text, boolean), anotar_sala_creada() FROM PUBLIC, actas_app;
GRANT EXECUTE ON FUNCTION ver_clave_sala(uuid, text), socio_activo(text, boolean) TO actas_panel;
