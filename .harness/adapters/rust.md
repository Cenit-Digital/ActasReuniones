# Adaptador: Rust

Mapea el arnés a un proyecto Rust. El runner de tests es Cargo (`cargo test`); la
mutación usa [cargo-mutants](https://mutants.rs/ci.html) (27.1.0). Ver también
`generic.md`.

## `harness.config.json`

```json
{
  "language": "rust",
  "commands": {
    "lint": "cargo clippy -- -D warnings",
    "test": "cargo test",
    "mutate": "cargo mutants -f {{target}}"
  },
  "paths": { "src": "src", "tests": "tests" },
  "mutation": { "threshold": 1.0, "targets": ["src/notes.rs"] }
}
```

- Sin `{{py}}`: Rust no necesita intérprete.
- `-f` filtra por fichero (`-e`/`--exclude` excluye), así que los `targets` son
  rutas de fichero. Como el comando usa `{{target}}`, no dejes `targets` vacío.

## Mutación: binaria, equivale a umbral 1.0

cargo-mutants **no tiene umbral porcentual** (no figura en su book ni en su
`NEWS.md`; la inexistencia se deduce de esa ausencia). Es una puerta binaria:
equivale a `threshold: 1.0`, y por eso el JSON lo declara así: es la excepción
(de la herramienta, no del proyecto) a la regla general de 0,8. Otro valor de
`mutation.threshold` no llega a la herramienta.

Códigos de salida oficiales (https://mutants.rs/exit-codes.html): 0 todos los
mutantes viables detectados · 1 error de uso · 2 mutantes no cubiertos por los
tests · 3 timeouts · 4 falla el baseline · 5 y 6 error de `--in-diff` · 70 error
interno. Cualquier ≠ 0 dispara la puerta del motor.

Mutantes equivalentes: márcalos con `#[mutants::skip]` (o
`#[cfg_attr(test, mutants::skip)]`) y documenta por qué. El atributo requiere el
crate `mutants` (≥ 0.0.3) como dependencia **normal**, no `dev-dependency`:
añade una línea a tu `Cargo.toml`.

```rust
#[mutants::skip] // equivalente: el orden de estos dos writes no es observable
fn flush(&mut self) { /* ... */ }
```

Instalación y `.cargo/mutants.toml`: NO VERIFICADO; ver https://mutants.rs.

## Layout típico

Rust **coloca los tests unitarios junto al código**, en un módulo `#[cfg(test)]`
dentro del mismo `.rs`; los de integración van aparte, en `tests/`:

```
Cargo.toml
src/lib.rs      src/notes.rs      (cada uno con su  #[cfg(test)] mod tests)
src/main.rs
tests/cli.rs                      (tests de integración)
```

Verificado el 2026-10-17 en: https://mutants.rs/exit-codes.html · https://mutants.rs/skip_files.html · https://mutants.rs/attrs.html · https://mutants.rs/ci.html
