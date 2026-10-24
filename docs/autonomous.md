# Evolución autónoma del arnés

> Cómo el propio arnés se mejora solo, de forma acotada y verificable, abriendo
> Pull Requests que **un humano siempre revisa y fusiona a mano**.
>
> El mandato que sigue el bot vive en `.github/AUTONOMOUS.md`. Esta página es la
> cara humana: qué es, cómo se pone en marcha, qué cuesta y por qué es seguro.

> **Estado: PAUSADO.** El `cron` está retirado: el bot solo corre si lo lanzas a
> mano (Actions → "Evolución autónoma del arnés" → *Run workflow*). Cada sesión
> consume cuota de la suscripción y la mayoría de sus PRs eran endurecimiento de
> entradas malformadas. Para reactivar la cadencia diaria, restaura el bloque
> `schedule` comentado al inicio de `autonomous-evolve.yml`. Lo que sigue describe
> el diseño cuando está activo.
>
> Su futuro (eliminarlo, dejar un mandato mínimo o reactivarlo) es una decisión
> abierta (`docs/decisiones/0001-rediseno-arnes.md`). Antes de lanzarlo o
> reactivarlo, comprueba que el modelo fijado en el workflow (`--model
> claude-opus-4-8`) sigue disponible, que el secret `CLAUDE_CODE_OAUTH_TOKEN` sigue
> vigente y que el backlog de `.github/AUTONOMOUS.md` es el que quieres que trabaje.

## Qué es

Un workflow (`.github/workflows/autonomous-evolve.yml`) que, cuando está
programado —siempre que no haya ya un PR suyo esperando revisión—, lanza
[Claude Code](https://github.com/anthropics/claude-code-action) dentro de GitHub
Actions con un único encargo: **elegir una tarea del backlog, completarla con
verificación real y abrir un Pull Request**. Nunca fusiona, nunca empuja a
`main`.

Es la misma idea que el bot de `DocsTemplateSSDUncleBob`, pero con una diferencia
deliberada: allí el bot reescribe prosa y hace auto-merge; aquí toca el motor de
la metodología y una plantilla pública, así que **la fusión es siempre manual**.

## Arquitectura (los ficheros)

| Fichero | Rol |
| --- | --- |
| `.github/workflows/autonomous-evolve.yml` | El disparador. Deliberadamente "tonto": hoy solo `workflow_dispatch` (el cron está retirado y comentado), permisos mínimos, apunta al mandato y para. |
| `.github/AUTONOMOUS.md` | El mandato. Alcance, **límites duros**, política de fusión, formato del PR y **backlog por niveles de riesgo**. Es la fuente de verdad. |
| `.github/workflows/guard-sensitive-paths.yml` | Guardián. En cada PR, si se tocan rutas sensibles (el propio workflow, el mandato, la CI o el motor) etiqueta el PR con `permissions-change` para que la revisión no lo pase por alto. |
| `.github/CODEOWNERS` | Marca al dueño sobre esas mismas rutas sensibles; solo fuerza su revisión si la protección de rama exige "review from Code Owners", y hoy no lo exige. |

## Requisitos previos

1. **Node.js ≥ 18** — ya es requisito del arnés; el runner lo trae.
2. **Secret `CLAUDE_CODE_OAUTH_TOKEN`** en este repo
   (*Settings → Secrets and variables → Actions → New repository secret*). Es el
   mismo token de `claude setup-token` que usa el bot de docs: está ligado a tu
   cuenta, no al repo, pero **los secrets no se heredan entre repos**, así que
   hay que darlo de alta aquí también. (Usa el mismo valor en ambos repos; si
   regeneras el token, actualiza los dos.)
3. **La GitHub App de Claude instalada** en la organización o el repo
   (<https://github.com/apps/claude>). Es lo que permite que el push y el PR del
   bot se creen con el token de la App y que, por tanto, `harness-ci.yml` corra
   sobre sus PRs. Si ya está instalada "para todos los repos" del org, esto ya
   está cubierto.
4. **Protección de rama sobre `main`** — es lo que hace REAL la política de
   "solo abre PR" (ver el paso obligatorio de la checklist, abajo). Sin ella, un
   bot con `contents: write` podría técnicamente empujar a `main`; con ella, no.

Las etiquetas `autonomous`, `needs-human-review` y `permissions-change` **no hace
falta crearlas a mano**: se crean de forma idempotente antes de usarse.

## Puesta en marcha (checklist del dueño)

- [ ] Añadir el secret `CLAUDE_CODE_OAUTH_TOKEN`.
- [ ] Confirmar que la GitHub App de Claude está instalada en el repo.
- [ ] **OBLIGATORIO — Proteger `main`.** Esta es la barrera que convierte "solo
      abre PR" de promesa en garantía estructural. En *Settings → Branches → Add
      branch protection rule* (o *Settings → Rules → Rulesets*) sobre `main`:
    - ✅ *Require a pull request before merging* → *Require approvals: 1*.
    - ☐ *Require review from Code Owners* — opcional y **hoy desactivado** en este
      repo (`require_code_owner_reviews: false`, comprobado el 2026-10-18): mientras
      lo esté, `.github/CODEOWNERS` solo informa. Actívalo si quieres que las rutas
      sensibles exijan además la aprobación del dueño.
    - ✅ *Require status checks to pass before merging* y añade los checks de la
      CI: `Arnés raíz (init)` y `Motor (tests)` (los dos jobs de `harness-ci.yml`).
    - ☐ *Allow force pushes* y ☐ *Allow deletions* — **sin marcar**: así es como
      quedan bloqueados. Estas dos aplican a todo el mundo, admins incluidos.
    - ☐ *Do not allow bypassing the above settings* — **déjalo SIN marcar**, que
      es como está configurado este repo. Por defecto *"the restrictions of a
      branch protection rule don't apply to people with admin permissions to the
      repository"*: tú sigues pudiendo actuar directo en una urgencia y fusionar
      tus propios PRs, mientras que el bot —que no es admin— sí queda sujeto a la
      regla, que es de quien queremos protegernos.
      Referencia oficial: <https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches>.
    - ⚠️ *Si eres el único mantenedor, no marques esa casilla.* La doc oficial dice
      que *"Pull request authors cannot approve their own pull requests"*: con el
      bypass desactivado y sin nadie más que te apruebe, no podrías fusionar nada
      en tu propio repo. Lo **imprescindible contra el bot** es más simple: *exigir
      PR* (le impide empujar a `main`) y *exigir 1 aprobación* (le impide fusionar
      lo suyo). Las aprobaciones humanas y el review de Code Owners son calidad de
      revisión añadida para ti.
- [ ] Probar sin esperar a mañana: *Actions → «Evolución autónoma del arnés» →
      Run workflow* (`workflow_dispatch`); marca **`forzar`** si quieres saltarte
      la guarda de PR abierto. Requiere que el workflow ya esté en la rama por
      defecto.
- [ ] Revisar el PR que abra, leer el diff con calma (con especial atención si
      lleva la etiqueta `permissions-change`) y fusionar —o pedir cambios— a mano.

## Activar / desactivar

- **Repositorio canónico** (`Cenit-Digital/TemplateSSDUncleBob`): el job corre
  siempre que se lanza (hoy, solo a mano); no hay que hacer nada más que los
  requisitos de arriba.
- **Consumidores de la plantilla** (quien haga "Use this template"): el workflow
  se copia, pero el job **no corre** salvo que se opte explícitamente creando la
  variable de repo `ENABLE_AUTONOMOUS_EVOLVE=true`
  (*Settings → Secrets and variables → Actions → Variables*). Con el cron retirado
  no hay runs programados; si alguien lo lanzara a mano sin optar, el job saldría
  *skipped*, y con el cron restaurado verías uno diario así. Es inofensivo (un job
  saltado no consume minutos ni hace fallar nada). Así ningún proyecto nuevo
  hereda un bot programado que no pidió.
- **Desactivarlo del todo**: borra `.github/workflows/autonomous-evolve.yml` (y,
  si quieres, `.github/AUTONOMOUS.md` y `.github/workflows/guard-sensitive-paths.yml`),
  o desactiva el workflow desde la pestaña *Actions*.

## Cadencia

> Decisión de arquitectura: **`DE-003`** en Confluence (espacio DDS) — por qué la
> cadencia la protege una guarda y no un cron largo, y qué se descartó.

Con el cron restaurado, la cadencia es **diaria**, 06:23 UTC — pero eso **no**
significa un PR al día. La guarda
del workflow no deja que haya más de un PR del bot esperando revisión: si el
anterior sigue abierto, el ciclo se salta y sale en verde sin gastar nada.

**El ritmo lo marcas tú al fusionar (o cerrar), no el calendario.** Fusionas hoy,
mañana hay tarea nueva; no lo lees en dos semanas, el bot te espera dos semanas.

Antes era semanal (lunes) con este argumento: "con alcance total, cada PR puede
tocar el motor o los agentes y merece lectura humana sin prisa". El argumento
sigue siendo cierto — lo que era falso es que un cron lo garantizara. Esperar
siete días no hace que nadie lea el diff con más calma; solo retrasa la tarea
siguiente cuando el PR anterior ya se fusionó el martes. La lectura sin prisa la
protege ahora un **mecanismo** (la guarda: nunca dos PRs sin leer), no una espera.

> Tres avisos sobre workflows programados, de la doc oficial de GitHub:
>
> - Solo se disparan desde la **rama por defecto** ("Scheduled workflows will
>   only run on the default branch"). Hasta que este fichero no esté en `main`,
>   ni el cron ni `workflow_dispatch` estarán activos.
> - Pueden retrasarse en horas de carga alta, y con carga suficiente "some queued
>   jobs may be dropped". Por eso el cron va a las **06:23** y no en punto: la doc
>   recomienda literalmente programar "at a different time of the hour".
> - En un repositorio **público** como este, GitHub **desactiva automáticamente**
>   los workflows programados tras **60 días sin actividad** en el repo ("In a
>   public repository, scheduled workflows are automatically disabled when no
>   repository activity has occurred in 60 days"). Si dejas de ver PRs, revisa la
>   pestaña *Actions* por si el workflow quedó desactivado y reactívalo. (Los
>   fallos de runs programadas se notifican por email al último que tocó el
>   fichero del workflow.)

## Modelo de seguridad

El diseño no acota al bot restringiéndole el alcance, sino **poniendo el filtro
en el sitio correcto** y respaldándolo con mecanismos que no dependen de la buena
fe del bot:

- **Alcance total, fusión manual — y ahora mecánica.** El bot puede tocar
  cualquier cosa; nada llega a `main` sin que un humano lea el diff y pulse
  *merge*. Con la **protección de rama** de la checklist, esa garantía deja de ser
  una instrucción de prompt y pasa a estar impuesta por GitHub: push directo y
  auto-merge quedan bloqueados sin aprobación.
- **Alarma de auto-permisos, con respaldo mecánico.** Si el bot toca su workflow,
  su mandato, `permissions:`/secrets, `CODEOWNERS`, **o la cadena de verificación
  (`harness-ci.yml`, `.harness/harness.mjs`)**, debe avisarlo en la primera línea
  del PR (límite 1 de `AUTONOMOUS.md`). Además, el guardián
  `guard-sensitive-paths.yml` etiqueta automáticamente esos PRs con
  `permissions-change`, y `CODEOWNERS` exige tu revisión sobre esas rutas: la
  autodeclaración deja de ser el único mecanismo.
- **Sin trampas para la CI.** Prohibido borrar/relajar tests o bajar el umbral de
  mutación para forzar el verde (límite 2). Marcar los jobs de `harness-ci.yml`
  como *required checks* (checklist) cierra el hueco de que un PR borre la CI y se
  presente en verde: si el check desaparece, el merge queda bloqueado.
- **El umbral de mutación no baja para forzar el verde.** `mutation.threshold`
  vale 0,8 por defecto; rebajarlo o recortar los módulos a mutar para que un PR
  pase queda prohibido (límite 3).
- **Permisos y herramientas acotados.** El workflow concede solo `contents`,
  `pull-requests`, `issues` (write) e `id-token` (que la acción usa en su flujo
  de auth OIDC; los ejemplos oficiales lo incluyen y el bot hermano lo necesitó
  en cron). Y `claude_args` corta con `--disallowedTools` las herramientas de
  exfiltración de red más obvias (`curl`, `wget`).
- **Riesgo residual honesto (exfiltración durante el run).** Con alcance total,
  `Bash` queda ampliamente disponible, así que el corte de `curl`/`wget` es
  defensa en profundidad, no una barrera hermética (un actor decidido podría usar
  otras vías). Lo que de verdad acota el daño: (a) la guarda hace que solo corra
  en el repo canónico, (b) el token es de **suscripción, ámbito solo-inferencia**
  y revocable regenerándolo, y (c) nada aterriza sin tu merge. Para una postura
  más estricta, restringe `--allowedTools` a prefijos concretos
  (`Bash(git:*),Bash(gh:*),Bash(node:*),…`) aceptando algo más de fricción.

## Controles de coste

Tres cortafuegos van de serie en el workflow:

- `--max-turns 100` — acota las iteraciones del agente.
- `timeout-minutes: 90` — corta cualquier run desbocado por reloj de pared.
- `--max-budget-usd 15` — techo de gasto por ejecución. La
  [referencia oficial del CLI](https://code.claude.com/docs/en/cli-reference)
  lo documenta ("Maximum dollar amount to spend on API calls before stopping",
  *print mode only* — que es como corre la acción).

Matiz importante según cómo autentiques:

- Con el **token de suscripción** (`claude_code_oauth_token`, que es tu caso), un
  run desbocado consume **cuota de tu plan**, no una factura en dólares; los tres
  cortafuegos actúan como cortes de ejecución, y `--max-budget-usd` como límite
  adicional de trabajo por run.
- Si un consumidor de la plantilla usa `anthropic_api_key` (facturación por API),
  `--max-budget-usd` sí es un **techo de dólares real** por ejecución.

Ajusta los tres valores a tu gusto en `claude_args` / `timeout-minutes`. Recuerda
además los costes de **minutos de GitHub Actions** (runner), aparte de los del
modelo.

> Sobre el modelo: `--model claude-opus-4-8` está fijado a propósito
> (reproducible). Cuando Anthropic retire Opus 4.8, el run empezará a fallar a
> diario: actualiza el ID en el workflow y aquí. La alternativa es el alias `opus`
> (siempre el Opus vigente), a cambio de posible deriva de comportamiento.

## Cómo se crean los PRs (detalle técnico)

La GitHub Action **no** abre PRs por su cuenta: en modo automatización deja un
enlace de creación. Por eso el prompt instruye al bot a abrirlo él mismo con
`gh pr create` (tiene la herramienta Bash y `gh` autenticado en el runner). Para
que `harness-ci.yml` (que dispara en `pull_request`) corra sobre ese PR, el push
y el PR deben crearse con el token de la **GitHub App de Claude**, no con el
`GITHUB_TOKEN` por defecto (los eventos del `GITHUB_TOKEN` no disparan otros
workflows). No es cuestión de la *firma* del commit, sino de qué token crea el
evento. Con la App instalada, ese es el caso. Si alguna vez la CI no arrancara,
el bot lo indica en el PR para que la relances a mano.

## Referencias oficiales

- Claude Code GitHub Action — guía: <https://code.claude.com/docs/en/github-actions>
- Referencia de flags del CLI: <https://code.claude.com/docs/en/cli-reference>
- Autenticación y `claude setup-token`: <https://code.claude.com/docs/en/authentication>
- Repositorio de la acción: <https://github.com/anthropics/claude-code-action>
- Seguridad de la acción: <https://github.com/anthropics/claude-code-action/blob/main/docs/security.md>
- Protección de ramas en GitHub: <https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches>
