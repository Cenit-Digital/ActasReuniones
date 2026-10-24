# Configuración — cómo adaptar el arnés a cualquier stack

> La política de trabajo (`AGENTS.md`: niveles, puerta humana, delegación) y los agentes son **fijos**. Lo único que cambia por proyecto son los comandos de tu stack, declarados en `harness.config.json`. Eso hace a la plantilla agnóstica al lenguaje.

## El motor

`.harness/harness.mjs` es un motor de **cero dependencias** (stdlib de Node ≥ 18). Lee `harness.config.json` del directorio actual y ejecuta los comandos que declaras. Se invoca con:

- POSIX/macOS/Linux: `./init.sh`, `bin/harness <cmd>`
- Windows/PowerShell: `pwsh ./init.ps1`, `bin\harness.ps1 <cmd>`
- Directo: `node .harness/harness.mjs <cmd>`

Comandos: `init`, `test`, `mutate [target]`, `verify`, `help`. `verify` es `init` más las comprobaciones que activen las `rules` (comando de tests declarado y mutación completa) y se usa antes de una entrega; el cierre ordinario de una tarea es `init` + `test`.

## Pasos propios de `init`: `scripts/pre-init.sh` y `scripts/pre-init.ps1`

`init.sh` e `init.ps1` son de la plantilla y `scripts/harness-upgrade.mjs --apply` los reemplaza: no los edites. Si tu proyecto necesita un paso previo que no es de ningún stack (por ejemplo, generar un secreto local si falta), ponlo en `scripts/pre-init.sh` (y, para Windows, `scripts/pre-init.ps1`). Son **opcionales y del proyecto**: la plantilla no los trae ni los toca.

- Si el fichero existe, corre **antes** del motor. Si sale con un código distinto de 0, `init` se detiene con ese código y el motor no corre.
- `init.sh` lo lanza con `bash`, así que no necesita bit ejecutable. `init.ps1` lo lanza con `&` y pone `$LASTEXITCODE` a 0 antes.
- `bin/harness init` y `node .harness/harness.mjs init` no lo ejecutan: solo los lanzadores `init.sh` e `init.ps1`. Si el paso debe correr siempre, declara su comando en `commands.install`.

## `harness.config.json` — campos

```jsonc
{
  "$schema": "./harness.schema.json",
  "project": "mi-proyecto",
  "language": "python",          // etiqueta informativa
  "standalone": true,             // false = hereda el arnés raíz (sub-proyecto)
  "commands": {
    "install": "…",               // opcional
    "lint":    "…",               // vacío = se omite
    "test":    "…",               // sale 0 si todo pasa
    "mutate":  "…",               // sale != 0 si no supera el umbral
    "build":   "…"                // opcional
  },
  "paths": { "src": "src", "tests": "tests" },   // solo si tu layout difiere de los defaults
  "mutation": { "threshold": 0.8, "targets": ["src/…"] },
  "rules": {
    "require_tests_to_close": true,
    "require_mutation_to_close": true
  }
}
```

- El motor no lee `feature_list.json`, `progress/` ni `features/`: si tu proyecto los conserva, son tuyos. Si tu `harness.config.json` aún trae `paths.features`, `paths.progress`, `paths.spec`, `paths.feature_list`, `rules.one_feature_at_a_time` o `rules.require_approved_spec_to_implement`, el motor las ignora; puedes borrarlas.
- `require_tests_to_close` y `require_mutation_to_close` rigen solo `verify`. Con `require_tests_to_close: true`, `verify` aborta si `commands.test` está vacío. Con `require_mutation_to_close: true`, `verify` ejecuta `commands.mutate` (todos los `mutation.targets`) y aborta si está vacío o no supera el umbral; con `false` **no ejecuta la mutación**, aunque `commands.mutate` esté declarado. El `harness.config.json` de la plantilla las trae a `false` porque no declara stack; ponlas a `true` cuando declares `commands.test` y `commands.mutate`.

### Tokens en `commands`

- `{{py}}` → el intérprete de Python disponible (`python3` o `python`).
- `{{target}}` → en `commands.mutate`, el módulo a mutar. Con `bin/harness mutate <target>`, ese único módulo; sin argumento (o con `bin/harness verify`) el motor **itera `mutation.targets`** y solo da verde si todos superan el umbral. Con `mutation.targets` vacía se ejecuta el comando una sola vez, sin `{{target}}` (herramientas cuyo alcance se fija en su configuración, p. ej. Cosmic Ray).
- `{{threshold}}` y `{{threshold_pct}}` → `mutation.threshold` en 0–1 (`0.8`) y en 0–100, entero (`80`), para pasárselo a la herramienta de mutación por línea de comandos. Son opcionales: el motor no mide ni aplica el umbral, solo mira el código de salida de `commands.mutate`. Si tu herramienta lo admite por línea de comandos, usa el token; si no (p. ej. Stryker, que lo lee de su fichero de configuración), mantén su valor alineado a mano con `mutation.threshold`. Detalle por herramienta en `docs/mutation-testing.md`.

## Recetas por stack

Los adaptadores por lenguaje están en `.harness/adapters/` (`python.md`, `node.md`, `go.md`, `rust.md`, `java.md` y el genérico `generic.md`): cada uno trae la herramienta de mutación estándar de su stack y cómo le llega el umbral. Las de referencia:

```json
// Node / TypeScript (Vitest + Stryker + ESLint)
"commands": { "install": "pnpm install", "lint": "eslint . && tsc --noEmit",
              "test": "vitest run", "mutate": "stryker run --mutate \"{{target}}\"", "build": "vite build" }

// Go
"commands": { "lint": "go vet ./...", "test": "go test ./...",
              "mutate": "gremlins unleash --threshold-efficacy {{threshold_pct}}" }

// Rust
"commands": { "lint": "cargo clippy -- -D warnings", "test": "cargo test",
              "mutate": "cargo mutants -f {{target}}" }

// Java
"commands": { "lint": "mvn -q checkstyle:check", "test": "mvn -q test",
              "mutate": "mvn test-compile org.pitest:pitest-maven:mutationCoverage -DmutationThreshold={{threshold_pct}} -DtargetClasses=\"{{target}}\"" }
```

Para Python, [Cosmic Ray](https://cosmic-ray.readthedocs.io/en/latest/reference/cli.html) es la herramienta que puede hacer de puerta por sí sola; `mutmut` no. `python.md` tiene el comando completo.

## Portar a un stack nuevo

1. Copia `harness.config.json` y rellena `commands` con los de tu stack.
2. Asegura que `commands.test` sale con código 0 solo si todos los tests pasan.
3. Elige un mutador y ponlo en `commands.mutate` (debe salir != 0 bajo umbral).
4. Pon `require_tests_to_close` y `require_mutation_to_close` a `true` si quieres que `verify` exija el comando de tests y ejecute la mutación (con `false`, `verify` no ejecuta la mutación).
5. Ajusta `paths` si tu layout no usa `src/`/`tests/`.
6. `bin/harness init` en verde → listo.
