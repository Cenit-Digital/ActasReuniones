# Prueba de mutación — validar que los tests muerden

## El problema que resuelve

Una suite verde dice "el código no explota con estas entradas". **No** dice
"los tests fallarían si el código estuviera mal". Un test sin asserts fuertes
pasa siempre y no protege nada.

La prueba de mutación lo mide al revés: introduce un defecto pequeño en el
código (un *mutante*) y observa la suite.

- Si **algún test falla** → el mutante está **muerto** (killed). Bien: la red
  atrapó el defecto.
- Si **todos los tests pasan** → el mutante **sobrevive** (survived). Mal: hay
  un agujero. Falta un assert o un caso.

**Puntuación de mutación** = `muertos / total`. Cuanto más alta, más muerden
los tests.

## Cuándo se corre

- **Solo en nivel crítico** (seguridad, datos, dinero o contrato público). El
  nivel lo fija el plan. En trivial, pequeño y estándar no se corre: un test por
  criterio y, en un bugfix, el test de regresión primero.
- **Sobre los módulos que fija el plan:** `bin/harness mutate <módulo>` por cada
  uno. Basta mientras se trabaja y es lo barato donde la herramienta acota por
  módulo (StrykerJS, cargo-mutants, PIT con Maven). En gremlins, Cosmic Ray y PIT
  con Gradle el alcance se fija en su configuración y `mutate <módulo>` no acota
  nada: ver el adaptador.
- **Completa, solo antes de una entrega:** `bin/harness mutate` sin módulo
  recorre `mutation.targets` (o el proyecto entero si la lista está vacía).
  `bin/harness verify` también la lanza mientras `rules.require_mutation_to_close`
  sea `true` (el valor por defecto): no es el cierre de cada tarea.

## Cómo se corre

```bash
bin/harness mutate                # todos los mutation.targets (o el proyecto entero)
bin/harness mutate src/pricing.py # un módulo: el token {{target}} recibe este argumento
```

La puerta es **determinista y sin LLM**: el motor ejecuta `commands.mutate` y
propaga su código de salida (0 = supera el umbral, distinto de 0 = falla). **El
motor no mide nada**: el umbral lo aplica la herramienta de mutación de cada
proyecto. Cada stack declara la suya en `commands.mutate`; los adaptadores de
`.harness/adapters/` traen el comando de cada una.

## El umbral

- `mutation.threshold` en `harness.config.json`: proporción de mutantes muertos,
  de 0 a 1. Por defecto **0,8**. **1,0 solo por excepción justificada**, escrita
  en el plan.
- Para que llegue a la herramienta, el motor ofrece dos tokens opcionales en
  cualquier `commands.*`: `{{threshold}}` (`0.8`) y `{{threshold_pct}}` (`80`,
  entero más próximo; usa umbrales de dos decimales como máximo), porque unas
  herramientas lo esperan en 0–1 y otras en 0–100. Ejemplo con PIT:

  ```json
  { "commands": { "mutate": "mvn test-compile org.pitest:pitest-maven:mutationCoverage -DmutationThreshold={{threshold_pct}} -DtargetClasses=\"{{target}}\"" } }
  ```

- Si el comando no usa los tokens, manda el umbral que tenga la propia
  herramienta (p. ej. StrykerJS solo lo admite en su fichero de configuración):
  mantenlo alineado a mano con `mutation.threshold`.
- «80 %» no significa lo mismo en todas las herramientas: el denominador cambia
  (gremlins excluye los mutantes sin cobertura, `cr-rate` cuenta supervivientes
  sobre mutantes completados, PIT usa «percentage detected»).

## Herramientas estándar por stack

Verificado el 2026-10-17 en la documentación oficial de cada herramienta; el
detalle, las URL y lo que no se pudo verificar están en cada adaptador.

| Stack | Herramienta | Cómo llega el umbral | Falla con |
| ----- | ----------- | -------------------- | --------- |
| Node/TS | [StrykerJS](https://stryker-mutator.io/docs/stryker-js/configuration/) | `thresholds.break` en su config (0–100); sin flag de línea de comandos | exit 1 |
| JVM | [PIT](https://pitest.org/quickstart/maven/) | `-DmutationThreshold` (0–100, entero) | falla la build (código exacto sin verificar) |
| Go | [gremlins](https://gremlins.dev/latest/usage/commands/unleash/) | `--threshold-efficacy` | exit 10 (11 si falla el mínimo de cobertura de mutantes) |
| Rust | [cargo-mutants](https://mutants.rs/exit-codes.html) | sin porcentaje: binaria, equivale a umbral 1,0 | exit 2 si queda un mutante sin detectar |
| Python | [Cosmic Ray](https://cosmic-ray.readthedocs.io/en/latest/reference/cli.html) | `cr-rate --fail-over`: máximo de supervivencia en % (100 − umbral) | exit 1 |

mutmut 3.x (Python) no tiene umbral nativo y no sale con error por
supervivientes: no sirve como puerta por sí solo. go-mutesting tampoco (imprime
la puntuación y sale con 0). Otros stacks (.NET, PHP, Ruby): `.harness/adapters/generic.md`.

## Supervivientes: tope de dos iteraciones

Un mutante superviviente es un hueco en los tests:

1. Se añade el test que lo mata (no se toca el código de producción para
   esquivarlo) y se vuelve a correr `mutate` sobre ese módulo.
2. **Máximo dos iteraciones.** Si tras la segunda siguen sobreviviendo mutantes,
   se para: quien aprueba decide si se acepta el resto, se baja el umbral con
   justificación o se replantea el diseño. Es una regla del proceso, no la hace
   cumplir el motor: lo registra el plan o el PR.

## Mutantes equivalentes

Un mutante **equivalente** (no cambia el comportamiento observable) puede
excluirse, pero solo con el mecanismo nativo de la herramienta (p. ej.
`#[mutants::skip]` en cargo-mutants) y con la justificación escrita en el PR.
Abusar de esta vía es hacer trampa a la puerta.
