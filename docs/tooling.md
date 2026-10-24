# Tooling — agentes y verificación

> Refuerzan el arnés, no lo reemplazan. Los agentes de nivel ejecutan y revisan lo que delega el plan; los especialistas son **opcionales y de solo lectura**: los convoca el planificador cuando aportan valor y no sustituyen a la revisión del cambio.

## Agentes de nivel (`.claude/agents/`)

La política de niveles está en `AGENTS.md`; el modelo de cada uno, en `docs/modelos.md`.

| Agente              | Nivel     | Para qué                                                   |
| ------------------- | --------- | ---------------------------------------------------------- |
| `worker_fast`       | fast      | Tareas mecánicas y de exploración con salida comprobable   |
| `worker_balanced`   | balanced  | Implementa lo que el plan delega, con un test por criterio |
| `reviewer_frontier` | frontier  | Revisión independiente, solo lectura                       |

Sirven para todo el repositorio, `src/` y sus tests incluidos.

Los tres existen también, con el mismo cuerpo, para las demás herramientas: `.github/agents/*.agent.md` (Copilot, con una lista de modelos de respaldo), `.codex/agents/*.toml` (Codex) y `.opencode/agents/*.md` (OpenCode, con la línea `model:` comentada hasta que elijas proveedor). Cada uno lleva el modelo de su herramienta según `docs/modelos.md`, que dice qué se leyó en la documentación y qué no se ha ejecutado. Los especialistas solo existen en `.claude/agents/`.

## Especialistas (opt-in, solo lectura)

| Agente              | Cuándo usarlo                                                        | Qué devuelve                      |
| ------------------- | -------------------------------------------------------------------- | --------------------------------- |
| `security_reviewer` | Cambios que tocan entrada de usuario, auth, IO, red o terceros       | Veredicto por severidad           |
| `a11y_seo_auditor`  | Features con UI web (accesibilidad y SEO)                            | Veredicto por impacto             |
| `mentor`            | Cuando la persona quiere una explicación didáctica de un cambio      | Responde en el chat, no bloquea   |

Revisan y reportan; no editan `src/`. Son `optional` en `harness.manifest.json`: si tu proyecto no los necesita (p. ej. `a11y_seo_auditor` sin UI web), bórralos y `harness-upgrade` no los repone; los que conserves se actualizan con el resto. Para recuperar uno que borraste (o adoptar uno nuevo de la plantilla), cópialo de su tag: `git show vX.Y.Z:.claude/agents/mentor.md`.

## Verificación: sin hooks de tests

`.claude/settings.json` no trae hooks que corran los tests ni `init` tras cada edición o cada turno. Un hook es síncrono (Claude espera a que acabe) y, si sale con 1 en rojo como `harness test`, no condiciona nada: solo sale un aviso con la primera línea de stderr. Con una suite de minutos son minutos de espera por edición sin que nada se haga cumplir. La verificación vive en tres sitios:

- **Cierre de tarea:** `bin/harness init` y `bin/harness test` en verde (`AGENTS.md` §5); en nivel crítico, además, la mutación que fija el plan.
- **Revisión local del diff** antes de cualquier `git push`, a cargo de la persona (`AGENTS.md`, «Política de trabajo»).
- **CI:** el workflow `harness-ci.yml` ejecuta `init` y los tests en cada PR; conviene que la protección de `main` exija esos checks.

Si un proyecto quiere un hook, que sea barato (p. ej. el lint del fichero tocado) y, si tarda, `async: true`; nunca la suite completa en cada edición.

## Permisos y modelo

`.claude/settings.json` incluye una allowlist mínima (`bin/harness …`, `node .harness/harness.mjs …`) para que los comandos del arnés no pidan confirmación en cada invocación; amplíala con los de tu stack. También fija `model: opusplan` (ver `docs/modelos.md`).
