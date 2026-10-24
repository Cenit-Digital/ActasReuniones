# TDD — la disciplina, proporcional al riesgo

> En nivel **crítico** se aplica TDD estricto: un test a la vez. En los demás niveles basta **un test por criterio de aceptación**, y en un bugfix el test de regresión se escribe **antes** del arreglo y se ve fallar. La técnica de abajo vale para ambos casos. Nunca se escribe la batería entera por adelantado.

## Las Tres Leyes del TDD

1. **No escribes código de producción** salvo para hacer pasar un test que está fallando.
2. **No escribes más de un test del necesario para fallar** — y que no compile o no importe cuenta como fallar.
3. **No escribes más código de producción del necesario** para pasar el único test que falla.

El efecto: nunca hay código sin un test que lo justifique ni un test que no empuje código real. El alcance no se infla.

## El ciclo, en pequeño y repetido

```
 ROJO            VERDE                 REFACTOR
 escribe UN  →   mínimo código    →    limpia con   ─┐
 test que        para ponerlo          la barra       │ (y vuelta
 falla           verde                 verde         ─┘  a ROJO)
```

- **ROJO** — el test deriva del siguiente criterio de aceptación (`docs/gherkin.md`). Verifica que falla de verdad (`bin/harness test`). Un test que pasa a la primera no demuestra nada: ajústalo o sospecha del montaje.
- **VERDE** — la implementación **mínima**. Está permitido hacer trampa (devolver una constante) si aún no hay test que lo desmienta; el siguiente ciclo forzará la generalización.
- **REFACTOR** — solo en verde: elimina duplicación, mejora nombres, parte funciones largas. Si algo se pone rojo, no estás refactorizando: estás cambiando comportamiento.

Un criterio con varias aristas («lista vacía imprime 0», «tres notas imprime 3») puede necesitar dos ciclos para forzar la generalización.

## Trazabilidad

Al cerrar, cada criterio está cubierto por al menos un test concreto cuyo nombre lo refleja (`test_count_archivo_vacio`). El PR lo cuenta en «Cómo se probó». Quien revisa rechaza si un criterio queda sin test.

## Olores que busca quien revisa

- Código de producción que ningún test rojo pidió (viola la Ley 1; solo en nivel crítico).
- Tests escritos «a futuro» para criterios que aún no tocan (solo en nivel crítico).
- Refactors hechos en rojo.
- Funciones largas o nombres opacos que sobrevivieron al REFACTOR.

> El runner concreto (unittest, Vitest, `node --test`, go test…) lo declara `harness.config.json` → `commands.test`. La disciplina es la misma en todos los stacks.
