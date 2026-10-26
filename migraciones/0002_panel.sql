-- Panel de F2 (KubernetesInfrastructure#287, ADR 0015 decisión 8). Lo aplica actas_owner, dueño del esquema y de las tablas.
--
-- 1. Quién pulsó «Grabar»: el usuario de BasicAuth que Traefik pone en X-Actas-Usuario (headerField). NULL para actas.sh.
ALTER TABLE reuniones ADD COLUMN pedido_por text CHECK (pedido_por ~ '^[A-Za-z0-9._@-]{1,64}$');

-- 2. Mínimo privilegio del rol del panel (@a33). El rol lo crea KubernetesInfrastructure (Job inquilinos) ANTES de desplegar
-- la imagen con esta migración: si no existe, la migración falla y el supervisor no arranca. Los privilegios por defecto del
-- inquilino solo van a actas_app, así que aquí se dan uno a uno. Doc de GRANT (PostgreSQL 18): un privilegio de tabla se suma
-- al de columna, de modo que primero se quita todo lo de tabla (REVOKE de tabla quita también los de columna) y la escritura se
-- da solo por columna: INSERT de lo que pide el panel (el resto, por defecto: estado `pedida`) y UPDATE de la parada.
-- Sin DELETE, TRUNCATE ni DDL (no es dueño de nada ni tiene CREATE en el esquema).
DO $$ BEGIN EXECUTE format('GRANT USAGE ON SCHEMA %I TO actas_panel', current_schema()); END $$;
REVOKE ALL ON reuniones, conformidades, segmentos, purgas, esquema_migraciones FROM actas_panel;
GRANT SELECT ON reuniones, conformidades, segmentos TO actas_panel;
GRANT INSERT (socios, texto_version, pedido_por) ON reuniones TO actas_panel;
GRANT INSERT (reunion_id, socio, texto_version) ON conformidades TO actas_panel;
GRANT UPDATE (parar_pedido_en, actualizado_en) ON reuniones TO actas_panel;
