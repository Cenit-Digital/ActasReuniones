# Regla MCP-first

Todo servicio nuevo de Cénit nace conectado a la malla: **si un repo expone una API, publica también su servidor MCP**, para que
Hermes (y cualquier agente) pueda usarlo por la centralita del Nodo con permisos por capas. La especificación completa está en
`Cenit-Digital/EcosistemaAgentes`, `contenido/especificaciones/regla-mcp-first.md`.

## Qué comprueba `bin/harness init`

Solo con `"api": true` en `harness.config.json` (por defecto es `false`: plantillas, webs estáticas e imágenes de CI no cambian).
Sale la sección «MCP-first» y comprueba lo siguiente:

1. **El servidor.** Existe la carpeta del servidor MCP (`mcp/`, o la que fije `mcp.dir`) con algo más que el catálogo.
   - El servidor habla Streamable HTTP, sin estado, con Bearer y una lista de hosts permitidos.
   - Eso no lo puede comprobar un motor agnóstico del lenguaje: lo comprueba tu test.
2. **El catálogo.** `<mcp.dir>/catalogo.json` es un objeto `{ "herramienta": capa }` con al menos una herramienta.
   - Las capas son las de la centralita (`L`, `E`, `⚠` o `✕`), en cadena o como `{ "capa": "L", "motivo": "…" }`.
   - Significado de cada capa:

     | Capa | Qué es | Cómo se usa |
     |---|---|---|
     | `L` | lectura | libre |
     | `E` | escritura reversible | con el botón del socio |
     | `⚠` | irreversible | con solicitud de aprobación (C6) |
     | `✕` | nunca | no se expone |
3. **El test.** Hay al menos un fichero de test (con «test» o «spec» en el nombre) en `paths.tests`, `paths.src` o la carpeta MCP
   que use `catalogo.json`.
   - Ese test es el que hace cumplir el contrato: falla si `tools/list` anuncia una herramienta que no está en el catálogo, o si
     una `L` no lleva `readOnlyHint: true`.

Si falta algo, `init` dice exactamente qué y enlaza este documento.

## Ejemplo

```jsonc
// harness.config.json
{ "api": true, "mcp": { "dir": "mcp" } }
```

```json
// mcp/catalogo.json
{ "listar_citas": "L", "crear_bloqueo": "E", "cancelar_cita": "⚠" }
```

## Excepción temporal (repos que ya tienen API y aún no tienen MCP)

```jsonc
{ "api": true,
  "mcp": { "exception": { "until": "2026-12-31", "reason": "el MCP llega con la centralita", "issue": "Cenit-Digital/Repo#N" } } }
```

- Hasta `until` (incluido, en UTC), `init` informa de la excepción y no exige el MCP.
- Al día siguiente falla con la fecha. Para que pase, hay dos caminos: publicar el MCP y quitar la excepción, o renovar la fecha
  con un motivo nuevo.
- `until` debe ser una fecha real (AAAA-MM-DD). Una excepción sin fecha no vale, porque no caducaría nunca.
