# TemplateSSDUncleBob — plantilla de arnés SSD para trabajar con agentes de IA

Plantilla **agnóstica al lenguaje** para desarrollar con agentes de IA (Claude Code, Codex, GitHub Copilot, OpenCode…) de forma proporcional al riesgo, verificable y barata. Adapta el método que divulga [BettaTech](https://github.com/betta-tech/harness-sdd) y las prácticas del vídeo [«7 pasos para programar mejor con coding agents»](https://youtu.be/dhkiC4Iq1eM).

Lo que fija la plantilla es **cómo se trabaja**, no tu aplicación: planificar, aprobar el plan, implementar con el modelo justo, revisar el diff en local y abrir un PR pequeño. Lo único que cambia por proyecto son los comandos de tu stack, en `harness.config.json`.

## La política en cuatro líneas

Texto completo: la «Política de trabajo» del final de `AGENTS.md`.

- **Niveles:** trivial, pequeño, estándar y crítico. Quien planifica los clasifica por juicio y escribe el nivel y su motivo en el plan; la persona lo corrige al aprobarlo.
- **Puerta humana, en dos puntos:** la persona aprueba el plan antes de implementar y revisa el diff en local antes de cualquier `git push`.
- **Delegación por capacidad, no por proveedor:** `frontier` planifica y revisa, `balanced` implementa, `fast` hace lo mecánico. Qué modelo es cada uno en cada herramienta: `docs/modelos.md` (Claude Code usa `opusplan` por defecto).
- **Pruebas proporcionales:** un test por criterio de aceptación; TDD estricto y mutación solo en el nivel crítico.

## Usar la plantilla

1. En GitHub, pulsa **«Use this template»** (o clona el repo). Requisito del arnés: **Node.js ≥ 18**; tu proyecto usa el runtime que quiera.
2. Edita `harness.config.json` con los comandos de tu stack (`docs/configuration.md`, adaptadores en `.harness/adapters/`).
3. Verifica el entorno: `./init.sh` (POSIX), `pwsh ./init.ps1` (Windows) o `node .harness/harness.mjs init`.
4. Abre tu agente en la raíz (`CLAUDE.md` y `GEMINI.md` importan `AGENTS.md`), pide la tarea y aprueba el plan que te proponga.

| Comando | Qué hace |
| --- | --- |
| `bin/harness init` | Verifica entorno, ficheros base y tests |
| `bin/harness test` | La suite de tests declarada |
| `bin/harness mutate [módulo]` | La prueba de mutación |
| `bin/harness verify` | `init` + mutación completa (antes de una entrega) |

En Windows: `bin\harness.ps1 <comando>`. `verify` aborta si `commands.mutate` está vacío mientras `rules.require_mutation_to_close` sea `true` (`docs/configuration.md`).

## Cómo se propaga a los derivados

Los repos creados desde la plantilla reciben sus cambios con `scripts/harness-upgrade.mjs` (modelo pull, 0 tokens; requiere Node ≥ 18 y git). `harness.manifest.json` dice qué es de la plantilla (se reemplaza), qué es del proyecto (nunca se toca) y qué se queda solo aquí. La política de `AGENTS.md` viaja en un bloque entre marcadores `harness:begin/end`: se reemplaza ese bloque y el resto del fichero es del proyecto. Lo que cada proyecto rellena (`docs/architecture.md` y `docs/conventions.md`) es del proyecto y `--apply` no lo toca.

Desde la raíz del derivado y en una rama:

```bash
node scripts/harness-upgrade.mjs --check   # solo lectura: lista la deriva
node scripts/harness-upgrade.mjs --diff    # lo mismo, y enseña el diff de cada fichero
node scripts/harness-upgrade.mjs --apply   # reemplaza tras mostrar el diff y pedir confirmación (--yes la omite)
```

Sin `--ref` toma el último tag `vX.Y.Z` de la plantilla (sin tags, sale con error): cada cambio que quieras propagar necesita un tag nuevo. Los JSON mixtos (`harness.config.json`, `.claude/settings.json`) solo se reemplazan si los nombras con `--replace-json <ruta>`, y `--apply` rechaza pisar ediciones sin confirmar. El diseño y sus porqués: `docs/decisiones/0001-rediseno-arnes.md`, que solo vive en la plantilla.

## Mapa del repo

| Dónde | Qué hay |
| --- | --- |
| `AGENTS.md` | Instrucciones para cualquier agente: las cinco secciones del proyecto y, al final, la política de trabajo de la plantilla (bloque gestionado) |
| `CLAUDE.md` · `GEMINI.md` | Importan `AGENTS.md`; son de la plantilla y lo del proyecto va en `AGENTS.md` |
| `harness.config.json` · `harness.schema.json` | El único punto que depende del stack |
| `.harness/` | Motor agnóstico (cero dependencias), adaptadores por lenguaje, comprobador del PR e `impacto-tareas.mjs` (candidatos de «Impacto en tareas anteriores») |
| `.claude/agents/` | 3 agentes de nivel y 3 especialistas opcionales (`docs/tooling.md`) |
| `.github/agents/` · `.codex/agents/` · `.opencode/agents/` | Los 3 agentes de nivel para Copilot, Codex y OpenCode (`docs/tooling.md`, modelos en `docs/modelos.md`) |
| `scripts/` | `harness-upgrade.mjs` (propagación) |
| `docs/` | Guías cortas: TDD, criterios en Gherkin, verificación, arquitectura, convenciones, configuración, modelos y palancas de usuario |
| `.github/` | Plantillas de issue y de PR (cuatro bloques y «Impacto en tareas anteriores»), CI y guardián de rutas sensibles |

## Opcional, hoy en pausa

- **Evolución autónoma:** un workflow (`.github/workflows/autonomous-evolve.yml`) puede mejorar el propio arnés abriendo PR que una persona revisa. Su cron está retirado; solo se lanza a mano. Mandato en `.github/AUTONOMOUS.md`, puesta en marcha en `docs/autonomous.md`.
- **Memoria organizacional:** patrones validados que se sincronizan al empezar una tarea (paso de `AGENTS.md`, no bloqueante). El bot que la alimenta está en pausa (decisión D11 del ADR). Detalles: `docs/memoria-organizacional.md`.

## Créditos

Esta plantilla es una adaptación del método de **BettaTech** ([playlist](https://www.youtube.com/playlist?list=PLJkcleqxxobX8POJ0sMoG62VyyZGrvhM2), [repo](https://github.com/betta-tech/harness-sdd/tree/uncle-bob-harness)) y de las prácticas del vídeo citado arriba. Generalización agnóstica y plantilla por **Cenit Digital**. Licencia MIT.

**Qué se le debe a Uncle Bob.** De Robert C. Martin solo consta una fuente primaria verificada: su [post del 12-feb-2026](https://x.com/unclebobmartin/status/2021998958579794052). Parafraseado: el desarrollo guiado por especificaciones aporta valor con IA, pero diseñarlo todo por adelantado arriesga volver al diseño grande previo; conviene mantener el carácter iterativo, con especificaciones justas para lo que se va a construir, que se modifican sobre la marcha, que coescriben persona e IA y que aprueba una persona. De ahí las specs vivas por capacidad y la aprobación humana de esta plantilla. El nombre «Uncle Bob» (también en la rama `uncle-bob-harness` del repo de BettaTech) no implica autoría ni aval suyo, y no se le atribuye nada más.
