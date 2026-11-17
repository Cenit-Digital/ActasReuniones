-- Preparación F3: ningún proceso consume estos datos hasta completar la integración.
-- Los datos tienen la misma vida que la reunión: la purga del padre borra también el acta.
CREATE TABLE actas_resumen (
    reunion_id uuid PRIMARY KEY REFERENCES reuniones (id) ON DELETE CASCADE,
    contenido jsonb NOT NULL CHECK (jsonb_typeof(contenido) = 'object'),
    creado_en timestamptz NOT NULL DEFAULT now()
);

REVOKE ALL ON actas_resumen FROM PUBLIC, actas_panel, actas_app;
GRANT SELECT, INSERT ON actas_resumen TO actas_app;
