# Adaptador: Node / TypeScript

Mapea el arnés a un proyecto Node/TS. La mutación usa
[StrykerJS](https://stryker-mutator.io/docs/stryker-js/configuration/) (10.0.0).

## `harness.config.json`

```json
{
  "language": "node",
  "commands": {
    "test": "vitest run",
    "mutate": "stryker run --mutate \"{{target}}\""
  },
  "mutation": { "threshold": 0.8, "targets": ["src/notes.ts"] }
}
```

- Las comillas dobles de `--mutate` van escapadas por ser JSON; en la shell
  protegen los globs.
- `--mutate` **sustituye** (no suma) la lista de `mutate` del fichero de config;
  admite globs y rangos (`fichero:5-10`). Como el comando usa `{{target}}`, no
  dejes `targets` vacío.
- Qué plugin de runner de tests necesita Stryker para tu runner: NO VERIFICADO
  aquí; ver su documentación.

## El umbral va solo en el fichero de config

Stryker **no tiene flag de línea de comandos para los umbrales** (su doc:
«Command line: none»; tampoco el código de su CLI). Se fijan en el fichero de
config, en escala 0–100, y hay que dar los tres valores («all or nothing»;
`high >= low`):

```json
{ "thresholds": { "high": 90, "low": 80, "break": 80 } }
```

`break` es la puerta: `stryker run` sale con 1 si la puntuación queda por debajo.
Como no puede recibir `{{threshold_pct}}`, **mantén `break` alineado a mano con
`mutation.threshold`** (0.8 → `80`). El fichero de config también puede pasarse
como argumento posicional (`stryker run fichero.json`). Leer el umbral de
`process.env` desde un `.mjs`: NO VERIFICADO. Stryker no estaba instalado al
verificar: nada de esto se ha ejecutado, solo leído en su doc y su código.

## Layout típico

```
src/*.ts      tests/      (más el fichero de config de Stryker)
```

Exclusión de mutantes equivalentes: NO VERIFICADO en esta pasada.

Verificado el 2026-10-17 en: https://stryker-mutator.io/docs/stryker-js/configuration/ · https://stryker-mutator.io/docs/stryker-js/config-file/
