# Convenciones de código

> Homogeneidad extrema: la IA predice mejor cuando el repositorio se parece a sí mismo en todas partes. Define aquí las convenciones de TU stack; los agentes las siguen al pie de la letra.

## Principios (agnósticos)

- **Un formateador y un linter fijos**, declarados en `harness.config.json` (`commands.lint`). El código se entrega formateado; el linter no da avisos.
- **Nombres consistentes** por tipo (módulos, tipos, funciones, constantes, privados). Elige una convención por categoría y no la mezcles.
- **Estructura de archivo homogénea**: mismo orden de imports, mismas cabeceras, mismos patrones de export.
- **Manejo de errores uniforme**: un tipo/base de error de dominio; la capa de interfaz captura, informa por el canal de error y sale con código != 0. Nunca propagar stack traces crudos al usuario.
- **Comentarios: solo el *porqué* no obvio.** Los nombres hacen el resto.
- **Tests co-locados o en `tests/`**, uno por módulo, con nombres que digan qué comportamiento verifican.

## Referencia por stack

| Stack | Formato / lint | Tests |
| --- | --- | --- |
| Python | PEP 8, líneas ≤ 100 | `unittest` |
| Node/TS | ESLint + Prettier | `node --test` |
| Node/TS (web) | ESLint 9 flat + Prettier | Vitest + Testing Library |
| Go | `gofmt` + `go vet` | `go test ./...` |
| Rust | `cargo fmt` + clippy | `cargo test` |

## Rellena: convenciones de tu proyecto

- **Lenguaje / versión:** …
- **Formato / línea máxima:** …
- **Convención de nombres:** …
- **Orden de imports:** …
- **Errores de dominio:** …
