# Adaptador: Python

Mapea el arnés a un proyecto Python. El runner de tests puede ser la stdlib o
`pytest -q`; la mutación usa una herramienta externa. Ver también `generic.md`.

## `harness.config.json`

```json
{
  "language": "python",
  "commands": {
    "test": "{{py}} -m unittest discover -s tests -q",
    "mutate": "cosmic-ray init cosmic-ray.toml cosmic-ray.sqlite && cosmic-ray exec cosmic-ray.toml cosmic-ray.sqlite && cr-rate cosmic-ray.sqlite --fail-over 20"
  },
  "mutation": { "threshold": 0.8, "targets": [] }
}
```

- `{{py}}` lo resuelve el motor a `python3` o `python`.
- `mutate` usa [Cosmic Ray](https://cosmic-ray.readthedocs.io/en/latest/reference/cli.html) (8.7.0), la única
  herramienta Python de este adaptador que puede ser puerta por sí sola.
- `cr-rate --fail-over N` sale con 1 cuando el porcentaje de **supervivencia**
  supera N: con un 80 % de mutantes muertos, `--fail-over 20`. Ese valor es
  `100 − umbral·100` y **no puede viajar por token** (`{{threshold_pct}}` daría
  80, no 20): se calcula a mano y debe mantenerse alineado con
  `mutation.threshold`. Excepción, según su código fuente: con N = 0 no comprueba
  nada, así que un umbral de 1.0 no se puede expresar con `cr-rate`.
- El alcance se fija con `module-path` en el TOML; por línea de comandos, NO
  VERIFICADO. Por eso el comando no usa `{{target}}`, `targets` va vacío y
  `mutate <módulo>` no acota nada. Qué hace `cosmic-ray init` si el `.sqlite` ya
  existe: NO VERIFICADO.

## Layout típico

```
src/*.py          tests/test_*.py     cosmic-ray.toml
```

## Alternativa: mutmut (no sirve como puerta por sí sola)

[mutmut](https://github.com/boxed/mutmut) 3.8.0 **no tiene umbral nativo** y no
sale con código ≠ 0 por mutantes supervivientes (solo con 1 si fallan los tests
sin mutar). Alcance con `mutmut run "modulo*"` (o `only_mutate`/`source_paths`
en `setup.cfg`); `mutmut export-cicd-stats` escribe
`mutants/mutmut-cicd-stats.json` (killed, survived, total, no_tests, skipped,
suspicious, timeout), pero aplicar un umbral sobre ese fichero exigiría un
script aparte. Su README exige un sistema con soporte de `fork` (en Windows,
WSL). El CLI cambió mucho entre 2.x y 3.x: no mezcles documentación de ambas.

Exclusión de mutantes equivalentes en Cosmic Ray y en mutmut: NO VERIFICADO.

Verificado el 2026-10-17 en: https://cosmic-ray.readthedocs.io/en/latest/reference/cli.html · https://github.com/boxed/mutmut
