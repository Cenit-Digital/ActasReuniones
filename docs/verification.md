# Verificación — cómo demostrar que el trabajo funciona

> El agente no dice «funciona»: lo demuestra con evidencia ejecutable. Los comandos salen de `harness.config.json`; aquí, qué evidencia exige cada nivel de tarea (la política está en la «Política de trabajo» de `AGENTS.md`).

## Definición de hecho

En todos los niveles: `bin/harness test` y `bin/harness init` en verde antes de cerrar, **un test por criterio de aceptación** y, en un bugfix, el test de regresión escrito primero y visto fallar. El nivel **crítico** añade TDD estricto (`docs/tdd.md`) y mutación sobre los módulos que fija el plan.

## Qué se prueba

1. **Unitarios (siempre).** Toda función pública nueva tiene un test del camino feliz y, si puede fallar, de un camino de error. Deben comprobar el resultado concreto, no solo que no lance.
2. **Integración de la interfaz (features de UI/CLI).** Se ejecuta la interfaz real contra un entorno aislado (directorio temporal, base de datos efímera…), nunca con mocks del sistema de ficheros.
3. **Smoke manual (recomendado).** Antes de cerrar, un flujo de punta a punta con datos desechables, y límpialo.

## Trazabilidad criterio → test

Cada criterio de aceptación tiene al menos un test cuyo nombre lo refleja. El PR declara en «Cómo se probó» qué test cubre cada criterio, con los comandos y los resultados reales; quien revisa rechaza si falta uno.

## Mutación (nivel crítico)

Una suite verde no basta: hay que demostrar que los tests **muerden**. Se corre `bin/harness mutate <módulo>` sobre los módulos que fija el plan; la mutación completa (`bin/harness mutate` sin módulo, o `bin/harness verify`, que añade `init`) solo antes de una entrega.

- Umbral: se declara en `mutation.threshold` (**0,8** por defecto; 1,0 solo por excepción justificada y registrada) y lo aplica el comando `commands.mutate`: el motor solo mira su código de salida.
- `bin/harness verify` aborta si `commands.mutate` está vacío mientras `rules.require_mutation_to_close` sea `true`: si tu proyecto no corre mutación, ponla a `false` (`docs/configuration.md`).
- Un mutante superviviente se mata con un test nuevo o se justifica como equivalente en el issue o el PR; tope de 2 iteraciones.
- Principios y adaptadores por stack: `docs/mutation-testing.md` y `.harness/adapters/`.

## Anti-patrones

- ❌ «He añadido el comando, debería funcionar.» → falta test ejecutable.
- ❌ Un test que solo comprueba que la función no lanza.
- ❌ Mockear el sistema de ficheros en vez de aislarlo de verdad.
- ❌ Dar la tarea por hecha sin pasar `bin/harness init`.

## El motor del arnés

`.harness/harness.mjs` se mantiene en la plantilla (sus pruebas, `.harness/test/`, no se propagan): un derivado no lo edita; un fallo se reporta en la plantilla.
