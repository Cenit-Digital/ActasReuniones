-- MCP de solo lectura para Hermes (ADR 0004). La aplica actas_owner al arrancar. Solo añade: se puede aplicar dos veces.
-- Una fila por llamada a una herramienta: qué herramienta, cómo acabó y cuánto tardó. Nunca los argumentos ni lo devuelto (ni el
-- id de la reunión: lo manda el agente). `eventos` no sirve: es de las reuniones, el panel solo la lee y su lista de tipos es otra.
CREATE TABLE IF NOT EXISTS auditoria_mcp (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    momento     timestamptz NOT NULL DEFAULT now(),
    origen      text        NOT NULL DEFAULT 'mcp' CHECK (origen = 'mcp'),
    herramienta text        NOT NULL CHECK (herramienta ~ '^[a-z_]{1,64}$'),
    resultado   text        NOT NULL CHECK (resultado IN ('ok', 'error')),
    duracion_ms integer     NOT NULL CHECK (duracion_ms >= 0)
);
CREATE INDEX IF NOT EXISTS auditoria_mcp_momento ON auditoria_mcp (momento);

-- El panel (que aloja el MCP) solo inserta; nadie modifica ni borra una fila (la limpia el dueño). actas_app no la toca.
REVOKE ALL ON auditoria_mcp FROM PUBLIC, actas_app, actas_panel;
GRANT INSERT ON auditoria_mcp TO actas_panel;
