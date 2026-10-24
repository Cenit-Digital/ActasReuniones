# Adaptador: Go

Mapea el arnés a un proyecto Go. El runner de tests es la stdlib (`go test`); la
mutación usa [gremlins](https://gremlins.dev/latest/usage/commands/unleash/)
(v0.6.0; su README dice que solo se mantiene la última minor). Ver también
`generic.md`.

## `harness.config.json`

```json
{
  "language": "go",
  "commands": {
    "lint": "go vet ./...",
    "test": "go test ./...",
    "mutate": "gremlins unleash --threshold-efficacy {{threshold_pct}}"
  },
  "paths": { "src": ".", "tests": "." },
  "mutation": { "threshold": 0.8, "targets": [] }
}
```

- Sin `{{py}}`: Go no necesita intérprete.
- `--threshold-efficacy` recibe el porcentaje (`{{threshold_pct}}`, 0.8 → `80`).
  Eficacia = KILLED / (KILLED + LIVED): **excluye NOT COVERED**. Umbral 0 =
  desactivado. `--threshold-mcover` fija además un mínimo de cobertura de
  mutantes.
- Sale con 10 si no alcanza la eficacia y con 11 si no alcanza la cobertura de
  mutantes: cualquier ≠ 0 es fallo para el motor.
- La misma clave en `.gremlins.yaml` es `unleash.threshold.efficacy` (no
  `thresholds.efficacy`); con el flag en `commands.mutate` no hace falta.
- Alcance: `gremlins unleash [path]` recibe la raíz del módulo, no un filtro de
  paquete; acotar por paquete: NO VERIFICADO. Opciones documentadas para acotar
  (`--coverpkg`, `--exclude-files`/`-E`, `--diff <ref>`): su semántica exacta, NO
  VERIFICADA. Por eso el comando no usa `{{target}}`, `targets` va vacío y
  `mutate <módulo>` no acota nada.

## Layout típico

Go **coloca los tests junto al código**, no en un `tests/` aparte:

```
go.mod
pkg/notes/notes.go      pkg/notes/notes_test.go
pkg/storage/storage.go  pkg/storage/storage_test.go
cmd/notes/main.go
```

Por eso `paths.src` y `paths.tests` pueden apuntar ambos a `.`.

## Alternativa: go-mutesting (no sirve como puerta por sí sola)

El original (zimmski) está sin mantenimiento desde 2021-06-10; el fork vivo es
[avito-tech/go-mutesting](https://github.com/avito-tech/go-mutesting) (v2.3.1).
**No tiene umbral**: imprime «The mutation score is 0.750000» (escala 0–1) y sale
con 0 aunque queden mutantes vivos (≠ 0 solo por error de ejecución; el valor
exacto de `returnError`: NO VERIFICADO).

Exclusión de mutantes equivalentes en gremlins: NO VERIFICADO.

Verificado el 2026-10-17 en: https://gremlins.dev/latest/usage/commands/unleash/ · https://github.com/go-gremlins/gremlins/blob/main/docs/docs/usage/configuration.md · https://github.com/avito-tech/go-mutesting
