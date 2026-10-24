# Instrucciones y palancas de usuario (fuera del repo)

> Consultado el **2026-10-17**. Son preferencias de la persona, no del proyecto: van en el fichero personal de cada
> herramienta, fuera del repo; lo del proyecto vive en `AGENTS.md`. Esta página guarda la plantilla de instrucciones,
> dice dónde se instala y, al final, recoge las palancas de coste que también viven fuera del repo; **no instala
> nada**.
>
> Procedencia: **[R]** leído en la documentación oficial (URL en *Fuentes*) · **[O]** observado en una sesión real,
> no documentado · **[M]** medición local sobre transcripciones de una persona (jul–oct 2026; no reproducible desde el
> repo) · **sin verificar** = no hay dato fiable y no se inventa uno.

## Qué va dónde

| Fichero | Lo escribe | Alcance |
| --- | --- | --- |
| `AGENTS.md` del repo | el proyecto | ese repo; cada herramienta lo lee sola o lo importa desde su propio fichero |
| Fichero personal de la herramienta | tú | todos tus repos, solo tú |

Claude Code, Codex y Copilot en VS Code cargan los dos y los suman, y el orden no es el mismo en todas: Claude Code
coloca las instrucciones del proyecto después de las de usuario [R]; Codex junta primero el fichero global y luego los
del proyecto, de la raíz hacia abajo [R]; Copilot los trata como «aditivos» y avisa de que no hay que fiarse del orden
[R]. Por eso la plantilla lo dice con palabras: **si chocan, gana el `AGENTS.md` del repo**. Es una petición al modelo,
no algo que garantice la herramienta.

## La plantilla

Copia el bloque tal cual en el fichero personal de tu herramienta (siguiente apartado). Es texto plano, sin imports,
para que valga igual en todas. La regla de que mande el `AGENTS.md` del repo está en la cabecera, y el aviso de
sesión nueva cuando lo que pides se sale del objetivo, en el paso 7.

```markdown
# Instrucciones personales (todos los proyectos)

Basadas en el vídeo «7 pasos para programar mejor con coding agents» (https://youtu.be/dhkiC4Iq1eM). Mandan después del `AGENTS.md` del repo: si chocan, gana el del repo.

## 1. Conoce el proyecto antes de pedir nada
Lee el `AGENTS.md` del repo, arranca el proyecto y mira su interfaz o su salida real antes de planificar. Si no hay `AGENTS.md`, propón crearlo corto: resumen del proyecto, ficheros clave, comandos de validación, guardarraíles y definición de hecho (menos de 200 líneas).

## 2. Un `AGENTS.md` en la raíz sirve a todas las herramientas
Las instrucciones del proyecto van ahí y no en ficheros por herramienta; si una herramienta pide el suyo, que se limite a importar el `AGENTS.md`.

## 3. Planifica antes de actuar
Usa el modo plan. Conversa: hazme preguntas hasta afinar el plan y espera mi aprobación antes de implementar. Planifica con el modelo más capaz y, si el cambio es crítico, propón una segunda lectura de otro modelo.

## 4. Implementa solo después del plan, con el modelo justo
Delega la implementación en un modelo menos capaz y más barato; tú revisas y reasignas si no termina. En el plan, recomienda modelo y esfuerzo por tarea sin fijar un nombre concreto.

## 5. Revisa antes de subir
Pasa una revisión propia del diff (`/review` o equivalente) y déjame revisarlo en local. No hagas `git push` hasta entonces.

## 6. Pull request de cuatro bloques
Qué, por qué, cómo se probó y pendiente. Pequeña y fácil de revisar: un tema y pocas líneas. Si el cambio es visual, adjunta imágenes o vídeo de antes y después. Para explicar un diff, usa el skill `show-me` (https://github.com/humanlayer/skills) si está instalado.

## 7. Tarea nueva, sesión nueva
Una tarea, una sesión: el traspaso es el issue y el PR, no el chat. Si lo que te pido se sale del objetivo de esta sesión, avísame y sugiere abrir una sesión nueva con un título; no la sigas aquí. Gasta poco contexto: lee solo lo necesario, resume en vez de pegar y delega las búsquedas amplias en subagentes. Si la sesión se alarga o acumula varias tareas, propón cerrarla.

## Complementos
- Crea un issue con el plan, los pasos y etiquetas adaptadas al proyecto.
- Trabaja en una rama nueva desde la rama por defecto y usa commits convencionales.
```

## Dónde se instala

`~` es tu carpeta personal.

| Herramienta | Fichero personal | Notas |
| --- | --- | --- |
| Claude Code (CLI y app de escritorio) | `~/.claude/CLAUDE.md` | [R] Se carga al inicio de cada sesión, para todos los proyectos, y sigue cargándose junto al `AGENTS.md` del repo; este se lee solo si el proyecto no tiene `CLAUDE.md`, así que si lo tiene, ha de importarlo con `@AGENTS.md`. [O] La app de escritorio lo carga (visto el 2026-10-17). |
| Codex | `~/.codex/AGENTS.md` | [R] En el directorio de Codex (`CODEX_HOME` lo cambia) manda `AGENTS.override.md` si existe y no está vacío; se usa solo el primer fichero no vacío de ese nivel. Tope combinado de 32 KiB por defecto (`project_doc_max_bytes`). |
| Copilot (VS Code) | `~/.copilot/copilot-instructions.md` | [R] Instrucciones personales siempre activas en las sesiones de Copilot; también `~/.copilot/instructions/*.instructions.md` (con `applyTo`). Esos ficheros no viajan con Settings Sync; los que guarda el perfil de VS Code, sí. |
| OpenCode | `~/.config/opencode/AGENTS.md` | [R] Si no existe, usa `~/.claude/CLAUDE.md`; `OPENCODE_DISABLE_CLAUDE_CODE_PROMPT` desactiva solo ese fichero. Si ya instalaste el de Claude Code, no hace falta duplicarlo. |
| Gemini CLI | `~/.gemini/GEMINI.md` | [R] Instrucciones por defecto para todos tus proyectos. La página avisa de que para los usuarios del nivel gratuito y de Google One, Antigravity CLI sustituyó a Gemini CLI el 2026-06-18; el fichero personal de Antigravity queda **sin verificar**. |

## Cómo mantenerla

- El texto se mantiene en la plantilla (este fichero). En un derivado llega con `node scripts/harness-upgrade.mjs --apply` y no se edita a mano: `--check` lo marcaría como deriva.
- Para cambiar tus preferencias, edita el bloque en la plantilla, no en un derivado, y vuelve a copiarlo en cada herramienta; no lo retoques a mano en cada máquina.
- Para comprobar que Claude Code la cargó, ejecuta `/context` en una sesión nueva y mira la lista de *Memory files* [R].

## Palancas de coste fuera del repo

Lo que más pesa en la factura de tokens no está en este repo: la plantilla solo puede recortar su parte. Estas palancas
son de la persona y viven en la configuración de su herramienta (`~/.claude` en Claude Code). **El repo no las toca ni
las instala**: solo las documenta. Las cifras [M] salen de 659 transcripciones de una sola persona (jul–oct 2026, octubre
parcial): son un orden de magnitud, mide las tuyas.

| Palanca | Qué mueve | Cómo actuar |
| --- | --- | --- |
| Modelo | Opus fue ≈ 70 % de la salida medida [M]. | Reserva el modelo más capaz para planificar y lo crítico; el proyecto ya fija `opusplan` (`docs/modelos.md`). Si cambias de modelo con `/model`, hazlo al empezar: cada modelo tiene su propia caché y el primer mensaje tras el cambio relee toda la conversación sin caché [R]. |
| Longitud de la sesión | ~445 K tokens de contexto por llamada en la sesión principal [M]; cada llamada vuelve a leer lo acumulado. | Una tarea, una sesión (paso 7 de la plantilla); delega las búsquedas amplias en subagentes; cierra o reinicia las sesiones que acumulan varias tareas. |
| Línea base | Lo que ya pesa una sesión recién abierta: instrucciones de usuario y de proyecto, plugins, skills, herramientas. Lo que aporta el arranque de este repo ronda 4,3 K tokens [M]. | Mídela con `/context` en una sesión nueva, antes y después de tocar nada [R]. |
| Plugins globales | Sus descripciones entran en cada sesión, uses o no el plugin. | Deja activados solo los que usa el proyecto: el ajuste `enabledPlugins` activa o desactiva cada plugin por ámbito (usuario, proyecto o local) [R]; su formato exacto, en la página de ajustes. |

### Hoy no es palanca: el esfuerzo de usuario

El `effortLevel` de `~/.claude/settings.json` solo rige en Opus 5, Fable 5.1 y modelos anteriores; Opus 5.5 y los
posteriores lo **ignoran** y arrancan en su propio defecto hasta que guardes un nivel para ellos con `/effort` (que lo
guarda por modelo) [R]. Se había contado como palanca de coste y es una corrección: con los modelos actuales no lo
es. En la configuración de proyecto o local, en cambio, `effortLevel` aplica a todos los modelos, y por eso la plantilla
no lo fija.

## Fuentes

- Ajustes, precedencia, `model`, `effortLevel` y `enabledPlugins`: https://code.claude.com/docs/en/settings · https://code.claude.com/docs/en/settings-reference
- Ventana de contexto y `/context`: https://code.claude.com/docs/en/context-window
- Claude Code: https://code.claude.com/docs/en/memory (sin fecha visible)
- Codex: https://learn.chatgpt.com/docs/agent-configuration/agents-md (sin fecha visible)
- Copilot en VS Code: https://code.visualstudio.com/docs/agent-customization/custom-instructions (página fechada 2026-10-14)
- OpenCode: https://opencode.ai/docs/rules/ (actualizada el 2026-10-16)
- Gemini CLI: https://geminicli.com/docs/cli/gemini-md (actualizada el 2026-06-18)
