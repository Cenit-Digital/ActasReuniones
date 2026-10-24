<!-- harness:begin — bloque gestionado por la plantilla: no lo edites aquí; lo reemplaza scripts/harness-upgrade.mjs al aplicar -->
## Arnés SSD (gestionado por la plantilla)

- Entorno y arnés: `bin/harness init` · tests: `bin/harness test` · mutación: `bin/harness mutate [target]`.
- ¿Al día con la plantilla? `node scripts/harness-upgrade.mjs --check` (solo lectura); `--diff` enseña los cambios.
- Qué es de la plantilla y qué del proyecto: `harness.manifest.json`.

### Política de trabajo

**Niveles.** El planificador clasifica cada tarea por juicio (las pistas no son exhaustivas; ante la duda, el nivel superior) y escribe el nivel y su motivo en el plan; la persona lo corrige al aprobarlo.
- **trivial:** cambio local y evidente. Un solo contexto, sin subagentes obligatorios.
- **pequeño:** acotado a pocos ficheros y sin decisiones de diseño. Se planifica con `frontier` y se implementa con `balanced`, en la misma sesión.
- **estándar:** varias piezas o un comportamiento nuevo. Mismo mecanismo; el plan fija los artefactos que exige.
- **crítico:** seguridad, datos, dinero o un contrato público. El planificador sigue como orquestador y revisor: delega, puede reasignar y revisa. Exige además TDD estricto y mutación sobre los módulos que fija el plan (`docs/verification.md`); en los demás niveles no se corre mutación.

**Puerta humana (dos puntos, todos los niveles).** 1) La persona aprueba el plan antes de implementar (en trivial basta uno de 1-2 líneas con el nivel y el motivo). 2) La persona revisa el diff en local antes de cualquier `git push`; un agente interactivo no empuja sin esa revisión.

**Delegación.** Por capacidad, no por proveedor: `frontier` (planificar, revisar, lo crítico), `balanced` (implementar), `fast` (tareas mecánicas y exploración). Salvo en trivial, el plan lleva una tabla «Delegación»: ejecutor, nivel, esfuerzo, motivo, «escalar si…» y verificación automática. Qué modelo es cada nivel en cada herramienta: `docs/modelos.md`.

**Issues y PR.** Plantillas en `.github/`. Toda tarea tiene su issue (objetivo, nivel, criterios Given/When/Then, plan en casillas, tareas relacionadas, resultados); en trivial es mínimo: objetivo y plan de 1-2 líneas con el nivel y el motivo. El PR lo enlaza con `Closes #N`, lleva siempre cuatro bloques (qué, por qué, cómo se probó, pendiente), «Impacto en tareas anteriores» y la casilla de revisión local; el workflow «Plantilla del PR» comprueba esas secciones y la casilla (`node .harness/pr-body.mjs`).

**Bucle de aprendizaje (fase de cierre).** Una tarea nueva puede dejar obsoletas otras anteriores; el nivel trivial no ejecuta esta fase.
- Al planificar, anota en «Tareas relacionadas» del issue las anteriores que tocan lo mismo: `node .harness/impacto-tareas.mjs --files <rutas del plan>` da los candidatos.
- Al cerrar, `node .harness/impacto-tareas.mjs` sobre la rama lista, con tope fijo y sin LLM, los PR e issues previos que tocaron los mismos ficheros. Alimenta «Impacto en tareas anteriores»: cada candidato se marca «afecta» o «no afecta», con el motivo en una línea.
- Cada tarea afectada (su issue; si solo existe el PR, el PR) recibe la etiqueta `revisit` y un comentario con el motivo y el enlace al PR. Si el impacto exige cambiar algo, un agente en modo plan abre un issue `revisit` nuevo con el plan de enmienda ya redactado; se enlaza desde el comentario, desde «Resultados de la ejecución» y desde el bloque del PR, y la persona lo aprueba como cualquier plan. Comentar, etiquetar, crear la etiqueta si falta y abrir ese issue se hace con el OK de la persona; ningún issue se reabre por su cuenta.
- Lo aprendido que valga para tareas futuras va a `AGENTS.md` en el mismo PR. No hay bot retrospectivo.
- «Todo criterio de aceptación tiene un test» es la mitad determinista del bucle.
<!-- harness:end -->
