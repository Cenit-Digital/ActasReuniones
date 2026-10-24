# CHECKPOINTS — Evaluación del estado final

> En sistemas multi-agente no se evalúa el camino, se evalúa el destino.
> Estos son los checkpoints objetivos que un juez (humano o IA) puede usar
> para decidir si el proyecto está sano. Son **agnósticos al lenguaje**: los
> comandos concretos salen de `harness.config.json`.

## C1 — El arnés está completo

- [ ] Existen los ficheros base: `AGENTS.md`, `CLAUDE.md`, `CHECKPOINTS.md`,
      `harness.config.json`.
- [ ] Existen los docs: `docs/architecture.md`, `docs/conventions.md`,
      `docs/verification.md`.
- [ ] `bin/harness init` termina con exit code 0.

## C2 — El estado es coherente

- [ ] Toda tarea terminada tiene tests asociados que pasan.

## C3 — El código respeta la arquitectura

- [ ] `src/` solo contiene los módulos previstos en `docs/architecture.md`.
- [ ] No hay dependencias externas no justificadas.
- [ ] No hay logs de debug sueltos, ni TODOs sin contexto.

## C4 — La verificación es real

- [ ] Hay al menos un test por módulo de `src/`.
- [ ] Los tests usan aislamiento real (p. ej. directorios temporales), no
      mocks de sistema de ficheros.
- [ ] `bin/harness test` muestra > 0 tests y todos verdes.

## C5 — La sesión se cerró bien

- [ ] No hay archivos sin trackear sospechosos (temporales, cachés fuera del
      `.gitignore`).
- [ ] La última tarea trabajada está reflejada en su issue (casillas y
      «Resultados de la ejecución»).

## C6 — Criterios Given/When/Then y spec viva

- [ ] Cada criterio de aceptación (Given/When/Then, en el issue)
      está cubierto por al menos un test concreto cuyo nombre lo refleja, y el
      PR declara en «Cómo se probó» cuál (ver `docs/verification.md`). En un
      bugfix, el test de regresión se escribió antes del arreglo y se vio fallar.
- [ ] Si la capacidad tiene su spec viva `features/<capacidad>.feature`
      (opcional, ver `docs/gherkin.md`): el mismo PR que cambia el
      comportamiento la actualiza, usa Gherkin con escenarios tagueados
      `@s1`, `@s2`, …, cada `Then` afirma algo medible y cada escenario `@s`
      está cubierto por al menos un test (mapa `@s → test` en el issue o en el PR).
- [ ] Solo nivel crítico: TDD estricto; no hay código de producción que ningún
      test rojo haya pedido (ver `docs/tdd.md`).

## C7 — Prueba de mutación (solo nivel crítico)

Solo aplica si el plan clasificó la tarea como **crítica**; en los demás
niveles no se corre (política en `docs/verification.md`).

- [ ] La tarea crítica superó la prueba de mutación
      (`bin/harness mutate <módulo>`) sobre los módulos que fija el plan, con
      la puntuación por encima del umbral de `harness.config.json`
      (`mutation.threshold`, 0,8 por defecto).
- [ ] Cualquier mutante sobreviviente queda documentado en el issue o en
      el PR (matado con un test nuevo, o justificado como equivalente).

---

**Cómo usar este archivo:** quien revisa el trabajo
recorre C1-C6 y, si la tarea es crítica, C7 (`bin/harness mutate <módulo>`).
Se rechaza el cierre de sesión si quedan boxes vacíos; los que solo aplican en
nivel crítico o con spec viva se marcan «n/a» cuando no corresponden.
