# Adaptador genérico (cualquier stack)

El arnés no sabe de tu lenguaje: solo ejecuta los comandos que declaras. Para
cualquier stack no cubierto por un adaptador específico (los hay para Python,
Node, Go, Rust y Java: `python.md`, `node.md`, `go.md`, `rust.md`, `java.md`):

1. Copia `harness.config.json` y rellena `commands`:
   - `test` — debe salir con código 0 **solo** si todos los tests pasan.
   - `mutate` — la herramienta de mutación estándar de tu stack; debe salir != 0
     si no supera el umbral. El motor no mide nada: ejecuta el comando y propaga
     su código de salida.
   - `lint`, `build`, `install` — opcionales.
2. Pasa `mutation.threshold` a la herramienta con `{{threshold}}` (0–1, p. ej.
   `0.8`) o `{{threshold_pct}}` (entero 0–100, p. ej. `80`). `{{target}}` recibe
   el módulo de `mutate <módulo>` o cada entrada de `mutation.targets`.
3. Ajusta `paths` si tu layout no usa `src/` / `tests/`.
4. `bin/harness init` en verde → listo.

Los comandos se ejecutan en una shell (cmd en Windows, sh en POSIX): usa comillas
dobles, nunca simples. Sin scripts envoltorio.

## Herramientas por stack

| Stack   | test           | mutación: comando con umbral | El umbral viaja por | ¿Puerta por sí sola? |
| ------- | -------------- | ---------------------------- | ------------------- | -------------------- |
| Node/TS | `vitest run`   | StrykerJS: `stryker run --mutate "{{target}}"` | fichero de config (`thresholds.break`), no por token | sí (exit 1); ver `node.md` |
| Python  | `pytest -q`    | Cosmic Ray: `cr-rate --fail-over <100 − umbral>` (3 pasos, ver `python.md`) | a mano (máximo de supervivencia) | sí (exit 1); mutmut 3.x no: ver `python.md` |
| Go      | `go test ./...` | gremlins: `gremlins unleash --threshold-efficacy {{threshold_pct}}` | token (flag) | sí (exit 10 u 11); ver `go.md` |
| Rust    | `cargo test`   | cargo-mutants: `cargo mutants -f {{target}}` | ninguna: binaria, equivale a umbral 1.0 | sí; ver `rust.md` |
| Java    | `mvn test`     | PIT: `-DmutationThreshold={{threshold_pct}}` (comando completo en `java.md`) | token (Maven); fichero (Gradle) | sí; exit code NO VERIFICADO |
| C#/.NET | `dotnet test`  | Stryker.NET: `dotnet stryker --break-at {{threshold_pct}} --threshold-low {{threshold_pct}} --threshold-high {{threshold_pct}} --mutate "**/Foo*.cs"` | token (flags) | sí; ≠ 0 (código exacto sin verificar) |
| PHP     | `phpunit`      | Infection: `infection --min-msi={{threshold_pct}} src/Service/Mailer.php` | token (flag) | exit code NO VERIFICADO |
| Ruby    | `rspec`        | mutant: NO VERIFICADO (no consultado) | NO VERIFICADO | NO VERIFICADO |

- Stryker.NET (`dotnet-stryker` 5.0.0): flags `-b`/`--break-at`, `--threshold-low`,
  `--threshold-high`, `-m`/`--mutate`; escala 0–100 entera. Su doc exige
  `break` ≤ `low` ≤ `high` (por defecto `break` 0, `low` 60, `high` 80) y su código
  lanza error si `break` > `low`: por eso los tres reciben el mismo valor. Qué
  ocurre si `low` > `high`: NO VERIFICADO (la doc solo enuncia la restricción).
- Infection 0.35.8: la doc habla de «percentage» para `--min-msi`. `--filter` está
  deprecated desde 0.34.0: el alcance son argumentos posicionales.

## Los porcentajes no son idénticos entre herramientas

Los denominadores difieren: gremlins excluye NOT COVERED de la eficacia, `cr-rate`
mide supervivientes sobre mutantes completados y PIT usa «percentage detected».
Un «80 %» no significa exactamente lo mismo en todas: lee la definición de tu
herramienta antes de fijar o comparar umbrales.

## Si tu stack no está en la tabla

Busca su herramienta estándar y comprueba, en su documentación oficial, tres
cosas: cómo recibe el umbral (token, fichero o ninguno), qué código de salida da
al incumplirlo y cómo se acota el alcance. Lo que no puedas confirmar, anótalo
como «NO VERIFICADO». Si no admite umbral, dilo tal cual: «sin umbral nativo: no
sirve como puerta por sí sola».

Verificado el 2026-10-17 en: https://gremlins.dev/latest/usage/commands/unleash/ · https://mutants.rs/exit-codes.html · https://cosmic-ray.readthedocs.io/en/latest/reference/cli.html · https://pitest.org/quickstart/maven/ · https://stryker-mutator.io/docs/stryker-net/configuration/ · https://infection.github.io/guide/command-line-options.html
