# ADR 0002 — Resultados del piloto en un derivado y de la prueba A/B de coste

- **Estado:** Aceptado al fusionarse este PR (la fecha es la de la fusión en el historial de git). Cierra la decisión abierta A7 del ADR 0001 y da por cumplido el incremento 10 de D13 (piloto y prueba A/B).
- **Alcance:** recoge qué se midió, qué se encontró y qué cambió en la plantilla. Es un registro de resultados con una decisión mínima, no una guía de uso.
- **Procedencia:** **[R]** re-verificado el 2026-10-18 contra el repo o GitHub · **[M]** medido en los ensayos del 2026-10-17 y 18; las copias, los scripts y los informes de origen son notas de sesión no versionadas, así que no es reproducible desde este repo · **[NV]** no verificado.

## Contexto

D13 cerraba el rediseño con un piloto en un derivado real (incremento 10) y con la prueba A/B de coste (A7): sin ellas, el ahorro del arnés nuevo era una hipótesis. La prueba A/B y el ensayo del piloto se hicieron el 2026-10-17 contra `main` de la plantilla, todavía sin `v0.3.0`; el PR real del piloto, con `v0.3.0`, se abrió y se fusionó el 2026-10-18. Los resultados solo constaban en notas fuera del repo. El piloto fue el derivado Galapavet (público), cuya suite propia tiene 2 388 tests.

## Resultados del piloto

**Fase A: ensayo en un clon desechable (2026-10-17).** Contra `main` de la plantilla (4a7dca1, aún sin `v0.3.0`) el resultado fue «pasa con condiciones» **[M]**: `--apply` aplicó unos 30 cambios, `--check` quedó sin deriva salvo el aviso esperado de `harness.config.json` (es del proyecto) y `init` salió en verde (90 ficheros, 2 388 tests, unos 4 minutos) solo tras ignorar `scripts/harness-upgrade.mjs` en el linter del derivado.

**Fase B: el PR real.** [Cenit-Digital/GalapavetClinicaVeterinaria#1](https://github.com/Cenit-Digital/GalapavetClinicaVeterinaria/pull/1) actualizó el derivado a `v0.3.0` con `harness-upgrade --apply --ref v0.3.0 --replace-json .claude/settings.json`: 46 ficheros, +1492 −1864, abierto a las 10:59 UTC con la casilla de revisión local marcada y fusionado por el titular el 2026-10-18 a las 11:01 UTC **[R]**. El `main` del derivado quedó en verde (CI del arnés y despliegue de Pages) **[R]**. Los 6 agentes del pipeline antiguo se borraron a mano, porque `--apply` nunca borra.

**Hallazgos y qué cambió en la plantilla:**

| Hallazgo | Cómo se vio | Arreglo en la plantilla |
|---|---|---|
| `bin/harness.ps1` e `init.ps1` fallaban en Windows PowerShell 5.1 (`Join-Path` con más de dos argumentos); el derivado tenía arreglado a mano solo `bin/harness.ps1` y el upgrade lo revertía (`init.ps1` ya fallaba) | Fase A, reproducido en el clon | #58, en `v0.3.0` |
| El check «Cuerpo del PR» (`pr-body.yml`) fallaba en derivados con pnpm: `setup-node` cacheaba por `packageManager` antes de que pnpm estuviera instalado | En el propio PR de la fase B, con ese check (no requerido) en rojo **[R]** | #60, en `v0.3.1`. Lo confirmó el PR de actualización a `v0.3.2` del mismo derivado ([#2](https://github.com/Cenit-Digital/GalapavetClinicaVeterinaria/pull/2), fusionado el 2026-10-18 a las 12:05 UTC), con todos sus checks en verde **[R]** |
| `.claude/settings.json` traía hooks que corrían la suite tras cada edición y `init` al cerrar cada turno. En el derivado costaban unos 264,5 s por edición y unos 274 s por turno (clon limpio, n = 1) **[M]** | Medición posterior al piloto | #61, en `v0.3.2`; el mismo PR #2 del derivado los quitó **[R]** |
| Las «Reglas duras» del `AGENTS.md` del arnés nuevo, aún sin alinear con el nivel trivial, pedían mutación para dar algo por hecho; con Opus se ejecutó en una tarea trivial | Prueba A/B | #59 |

**Hallazgos sin arreglo de plantilla.** El script de propagación cae dentro del linter estricto de un derivado (hubo que ignorarlo a mano), y el reemplazo de una doc de plantilla borra sin avisar el texto que el derivado le hubiera añadido (solo se ve leyendo `--diff`). Ni `docs/configuration.md` ni `docs/tooling.md` lo mencionan **[R]**, y el PR del derivado lo resolvió a mano.

**Restos en el derivado** (según el cuerpo del PR; limpieza aparte y con OK, ver Seguimiento del ADR 0001): `examples/` y sus dos jobs de CI, el cron diario de su bot, las secciones de su `AGENTS.md` que aún describen el pipeline antiguo, una copia vieja de los tests del motor que su CI no ejecuta, y su umbral de mutación propio (1,0). Tampoco tenía protección de rama.

## Resultados de la prueba A/B

**Diseño.** La misma tarea trivial (cambiar el texto de salida de un comando y su test) en un proyecto de juguete de 29 tests, con el mismo prompt, en sesiones limpias de `claude -p`, con el arnés antiguo (commit anterior al rediseño) y el nuevo (4a7dca1), cada uno con Sonnet y con Opus. Cuatro celdas, **n = 1 por celda**, 2,216 USD en total contando una prueba de humo previa **[M]**. Los costes son los que informa el CLI.

| Celda | Coste (USD) | Llamadas | Contextos | Subagentes |
|---|---|---|---|---|
| Antiguo · Sonnet | 0,271 | 12 | 2 | 1 |
| Nuevo · Sonnet | 0,228 (−16 %) | 7 | 1 | 0 |
| Antiguo · Opus | 0,906 | 32 | 4 | 3 |
| Nuevo · Opus | 0,628 (−31 %) | 15 | 1 | 0 |

**Lectura.**
- El nuevo cuesta menos con los dos modelos y cumple la meta del nivel trivial: un contexto y ningún subagente. El diff de producto fue el mismo en las cuatro celdas.
- El ahorro depende de cuánto siga el modelo el arnés antiguo. Con Sonnet recorrió 1 de las 6 fases del diagnóstico (se saltó 5); con Opus, 3 de 6 (TDD, juez y mutación, más el ritual de cierre), y omitió spec y Gherkin por no ser una feature con `sdd`. El diagnóstico «trivial = 6 fases» solo se reproduce a medias, y ningún mecanismo del arnés antiguo lo hacía cumplir: era política de prompt.
- El coste fijo del nuevo es de unos 2,5 K tokens por llamada (`CLAUDE.md` importa `AGENTS.md`), que compensa: con Opus procesa un 21 % menos de tokens de contexto en la tarea; con Sonnet, un 0,2 % menos, es decir, prácticamente lo mismo pese a esos 2,5 K tokens más por llamada.
- Cambiar de Opus a Sonnet ahorró más (−64 % a −70 %) que cambiar de arnés (−16 % a −31 %), aunque esa comparación mezcla modelo y longitud del camino.
- La línea base de una sesión recién abierta fue de 62–65 K tokens, de los que el arnés explica una parte pequeña (≈ 95 % es entorno de usuario, calculado sobre la línea base medida **[M]**). Bajar la factura absoluta pasa más por el modelo y los plugins (A3) que por el arnés.
- Los subagentes del arnés antiguo corrieron en Sonnet aun con la sesión en Opus. La causa no se aisló **[NV]** (probablemente un ajuste de usuario) y matiza la fila 2 del Diagnóstico del ADR 0001, que daba por hecho que heredaban el modelo de la sesión.

**Cautelas.**
- n = 1 por celda con un modelo no determinista: sin varianza medida, una diferencia de 0,04 USD (Sonnet) cae dentro del ruido esperable y el −31 % de Opus tampoco está replicado.
- Juguete de una línea de cambio, no un repo real.
- El modo `-p` no tiene modo plan: no ejercita `opusplan`, el plan con nivel ni la tabla «Delegación».
- Los hooks de usuario y la lista de permisos del ensayo provocaron reintentos (en las celdas de Opus, una de cada tres llamadas siguió a un bloqueo, en proporción parecida en los dos brazos). La línea base depende del entorno de usuario.
- El nuevo se midió antes de la dieta del motor (#57), de la alineación de textos (#59) y de las etiquetas `v0.3.x`.

## Decisión

Se cierra A7 y se da por cumplido el incremento 10 de D13. Nada más se decide aquí. Quedan como **opciones abiertas que solo activa el titular** (D2: nada se ejecuta sin su OK expreso): repetir la prueba con réplicas (unos 6 USD con tres por celda), una variante con una tarea declarada como feature, y una prueba interactiva con `opusplan` y plan aprobado a mano. Los ajustes que salieron de los dos ensayos ya están en la plantilla (#58, #59, #60 y #61).

## Consecuencias

- **Positivas:** la meta del nivel trivial está medida, no supuesta; el piloto demostró la propagación de punta a punta y permitió ver o medir tres defectos reales del arnés (#58, #60 y #61), ya corregidos, y dos más sin corregir.
- **Negativas y riesgos:** con n = 1 y un juguete, las cifras indican una dirección, no una magnitud fiable; la parte interactiva (plan aprobado, tabla «Delegación», `opusplan`) sigue sin medirse. Los datos no piden por sí solos un cambio de rumbo, pero tampoco lo descartan.
- **Observación:** en ambos arneses, Sonnet se saltó el arranque (`init`) que `AGENTS.md` pide en prosa; no hay mecanismo que lo haga cumplir.

## Fuentes

Notas de sesión del 2026-10-17 y 18, no versionadas: informe de la prueba A/B y notas de las dos fases del piloto. En el repo: ADR 0001; los PR #57, #58, #59, #60 y #61 de esta plantilla; el PR del derivado enlazado arriba.
