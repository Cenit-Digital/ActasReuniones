# Modelos por nivel de capacidad (capa 1)

> Consultado el **2026-10-18**. La política (capa 0) está en `AGENTS.md` y no nombra modelos: aquí está
> la única tabla que sí lo hace. Los alias y las versiones cambian; actualiza esta tabla **en la
> plantilla** (con fecha y fuente), no en cada proyecto.
>
> Procedencia: **[R]** leído en la documentación oficial (URL en *Fuentes*) · **[D]** propuesta del
> arnés o derivado de otro dato, no un dato · **[NV]** sin verificar: no hay dato fiable y no se inventa uno.
> El reparto de IDs entre niveles es siempre **[D]**; un **[R]** en una celda significa que el ID y su
> descripción oficial están leídos. Lo de Codex, Copilot y OpenCode está *verificado contra la
> documentación el 2026-10-18, no ejecutado*: desde este repo solo se puede correr Claude Code.

| Herramienta | Dónde se fija el modelo [R] | `frontier` | `balanced` | `fast` |
| --- | --- | --- | --- | --- |
| Claude Code | `model` en `.claude/settings.json` (aquí `opusplan`: plan con `opus`, ejecución con `sonnet`); `model:` en el agente (alias, ID completo o `inherit`); `/model` | `opus` [D]; `best` si quieres el más capaz de tu cuenta (cae a `opus` si no hay `fable`) [R] | `sonnet` [D] | `haiku` [D] |
| Codex | `model` en `.codex/agents/<agente>.toml`; `agents.default_subagent_model` en `config.toml` para el resto de subagentes | `gpt-6-astra` [R] | `gpt-6.1-sol` [R] | `gpt-6-luna` [R] |
| Copilot (VS Code; CLI [NV]) | `model` en `.github/agents/<agente>.agent.md`: nombre o lista de respaldo; en un `handoff`, formato `Nombre (vendor)` | `Claude Opus 5.5`, `GPT-6 Astra` [R] | `Claude Sonnet 5.5`, `GPT-6.1 Sol` [R] | `Claude Haiku 5.5`, `GPT-6 Luna` [R] |
| OpenCode | `model` por agente, formato `proveedor/modelo` (`.opencode/agents/<agente>.md` o la clave `agent` de `opencode.json`); sin él, hereda el del agente que lo invoca | `anthropic/claude-opus-5-5`, `openai/gpt-6-astra` [D] | `anthropic/claude-sonnet-5-5`, `openai/gpt-6.1-sol` [D] | `anthropic/claude-haiku-5-5`, `openai/gpt-6-luna` [D] |
| Gemini CLI | Solo compatibilidad mínima: `GEMINI.md` importa `AGENTS.md`; no se asignan niveles | — | — | — |

Notas: **[R]** los alias de Claude Code resuelven en la API de Anthropic a Opus 5.5 (`opus`), Sonnet 5.5
(`sonnet`) y Haiku 5.5 (`haiku`); en otras plataformas pueden ser otra versión. **[R]** La página de modelos
de Codex y la comparación de modelos de GitHub Docs describen cada ID con una orientación de uso (el más
capaz, el equilibrado, el eficiente). **[D]** El reparto en tres niveles es del arnés.

## Agentes por herramienta

Los tres agentes de nivel existen en cuatro herramientas. El **cuerpo y la descripción son los mismos**
(los de `.claude/agents/`, y una prueba lo vigila); lo propio de cada herramienta es la cabecera.

| Agente | Claude Code | Copilot (VS Code; CLI [NV]) | Codex | OpenCode |
| --- | --- | --- | --- | --- |
| `worker_fast` | `.claude/agents/worker_fast.md` | `.github/agents/worker_fast.agent.md` | `.codex/agents/worker_fast.toml` | `.opencode/agents/worker_fast.md` |
| `worker_balanced` | `.claude/agents/worker_balanced.md` | `.github/agents/worker_balanced.agent.md` | `.codex/agents/worker_balanced.toml` | `.opencode/agents/worker_balanced.md` |
| `reviewer_frontier` | `.claude/agents/reviewer_frontier.md` | `.github/agents/reviewer_frontier.agent.md` | `.codex/agents/reviewer_frontier.toml` | `.opencode/agents/reviewer_frontier.md` |

El **esfuerzo de razonamiento no se fija en ningún adaptador**: lo decide cada tarea, en la tabla
«Delegación» del plan. Los especialistas (`security_reviewer`, `a11y_seo_auditor`, `mentor`) solo tienen
adaptador en Claude Code.

### Claude Code

Cada agente de `.claude/agents/` fija su propio modelo, que manda sobre el de la sesión (orden: parámetro
de la llamada, `model:` del agente, `CLAUDE_CODE_SUBAGENT_MODEL`, modelo de la sesión) [R]. La asignación de
nivel a alias es [D]:

| Agente | Modelo | Para qué |
| --- | --- | --- |
| `worker_fast` | `haiku` | tareas mecánicas y exploración |
| `worker_balanced` | `sonnet` | implementar lo que el plan delega |
| `reviewer_frontier` | `opus` | revisión independiente, solo lectura |
| `security_reviewer` | `opus` | fronteras de confianza (opcional) |
| `a11y_seo_auditor` | `sonnet` | accesibilidad y SEO (opcional) |
| `mentor` | `sonnet` | explicar el porqué (opcional) |

**Nivel crítico.** Con `opusplan` la sesión corre en `sonnet` fuera del modo plan. En crítico, cambia la
sesión a `opus` (`/model opus`): el planificador orquesta y delega en `worker_balanced` y `worker_fast`,
que conservan su propio modelo, y `reviewer_frontier` hace la revisión independiente.

El `model` de `.claude/settings.json` se reaplica en cada arranque aunque elijas otro con `/model` [R]; para
anularlo de forma persistente ponlo en `.claude/settings.local.json`, que tiene precedencia [R]. La
documentación indica que `opusplan[1m]` se puede fijar con el ajuste `model`; que `opusplan` a secas sea
válido ahí se infiere de eso: comprueba con `/model` en una sesión nueva.

### Codex

- Los agentes son ficheros TOML en `.codex/agents/` (o `~/.codex/agents/`). Obligatorios: `name`,
  `description` y `developer_instructions`; opcionales: `model` y `model_reasoning_effort` [R]. El cuerpo va
  en una cadena literal `'''…'''` para que una barra invertida no sea un escape.
- El `model` del fichero manda sobre el valor resuelto en el lanzamiento [R]. La página describe además el
  orden lanzamiento → `[agents]` → padre sin precisar cómo encaja con el fichero, así que que el nivel fije
  el modelo en todos los casos es **[NV]**. Un fichero que solo fija `model` conserva el esfuerzo ya
  resuelto [R]: por eso estos no fijan `model_reasoning_effort`.
- `sandbox_mode`, `approval_policy`, `model_provider` y `mcp_servers` no se pueden fijar en el fichero [R]:
  `reviewer_frontier` es de solo lectura por instrucción, no por permiso.
- Confianza: Codex omite las capas `.codex/` de un proyecto que no es de confianza
  (`projects.<ruta>.trust_level`) [R]. La página cita la configuración, los hooks y las reglas y no nombra
  `agents/`: que también los omita es una inferencia [NV].
- `gpt-6.1-sol` está en Plus, Pro, Business, Enterprise y Edu, no en Free ni Go, y en Enterprise y Edu viene
  desactivado hasta que un administrador lo active [R]. **Si tu cuenta no lo muestra, cambia el `model` de
  `worker_balanced.toml`** (en un derivado es una edición local: `harness-upgrade --check` la marcará como
  deriva y `--apply` pide confirmación antes de revertirla). En Codex el `model` es una sola cadena, sin
  lista de respaldo; un modelo que tu cuenta no tenga probablemente haga fallar la delegación **[NV]**. Los
  `gpt-5.x` figuran como retirados o en retirada [R]: no se usan.

### Copilot (VS Code y CLI)

- Los agentes son `.github/agents/<agente>.agent.md` [R]. Se usan `name`, `description`, `tools` (alias
  `read`, `edit`, `search`, `execute`) y `model`; este último admite una lista y se usa el primer modelo
  disponible [R]. No se tocan `user-invocable`, `disable-model-invocation`, `agents` ni `handoffs`.
- Los nombres son los de la lista de modelos admitidos de GitHub Docs [R]. Los ejemplos de VS Code usan el
  nombre sin sufijo en el `model` de un agente (`Claude Opus 4.5`) y el formato `Nombre (vendor)` solo en el
  `model` de un `handoff` [R]. Que el nombre exacto del selector de tu cuenta coincida con el de GitHub Docs
  es **[NV]**, y qué ocurre si ningún nombre de la lista casa tampoco está documentado **[NV]**.
- La CLI lee `.github/agents/` [R], pero su documentación no menciona `model`: que lo respete es **[NV]**. De
  los modelos usados, solo Haiku 5.5 consta como disponible en la CLI y en VS Code [R]; el resto, **[NV]**.
- **Duplicados en VS Code [NV].** VS Code también lee `.claude/agents/` (en ese formato solo
  `name`, `description`, `tools` y `disallowedTools`; el `model` no se documenta) [R]. No dice qué pasa con el
  mismo `name` en las dos carpetas ni ofrece un ajuste para ignorar `.claude/agents/` **[NV]**. Por eso los
  adaptadores repiten el `name` y no ocultan nada. Para comprobarlo en un proyecto de confianza:
  1. despliega el selector de agentes en el chat de VS Code;
  2. ¿sale `reviewer_frontier` una vez o dos? Al pasar el ratón se ve la ruta de origen de cada una;
  3. lanza uno y mira qué modelo usa: ¿gana la copia con `model` (`.github/agents/`) o la que no lo tiene?;
  4. repite con `/agent` en la CLI de Copilot;
  5. comunica el resultado para anotarlo en la plantilla (esta página se actualiza allí, no en cada
     proyecto); si gana la copia sin `model`, la plantilla aún no ofrece salida y habrá que decidir una.

### OpenCode

- Los agentes son `.opencode/agents/<agente>.md` (el nombre del fichero es el del agente) o la clave `agent`
  de `opencode.json` [R]. Se usan `description` y `mode: subagent`; el revisor lleva además `permission` con
  `edit: deny` [R].
- `model` va en formato `proveedor/modelo`; sin él, el subagente usa el modelo del agente que lo invoca [R].
  **Los adaptadores no lo fijan, a propósito:** un proveedor fijado en la plantilla falla (modelo o
  credencial no encontrados) a quien use otro. **Hasta que descomentes una línea `# model:`, los tres
  agentes corren con el modelo del agente que los invoca**: `worker_fast` y `worker_balanced` no escalan el
  coste y `reviewer_frontier` hace la revisión con un modelo que puede ser más barato y menos capaz. Cada
  fichero trae las líneas de Anthropic y de OpenAI (los IDs son los de sus API: [D]). Para GitHub Copilot
  conéctalo con `/connect` y elige el ID en `/models` [R]; qué IDs expone OpenCode para ese proveedor es
  **[NV]**.
- Elegir el modelo es una edición local de un fichero de la plantilla: `harness-upgrade --check` la marcará
  como deriva y `--apply` pide confirmación antes de revertirla. Alternativa **[NV]**: ponerlo en el
  `opencode.json` del proyecto o en el global (`agent.<nombre>.model`), que no se propagan; la
  documentación dice que las configuraciones se combinan, pero no precisa si eso alcanza a un agente
  definido en Markdown.
- La sustitución `{env:…}` y `{file:…}` solo está documentada para `opencode.json`, no para el Markdown de
  los agentes [R]: no se usa.
- Cualquier otra clave del agente pasa al proveedor (`reasoningEffort` en OpenAI; en Anthropic el esfuerzo
  va por `thinking`) [R]: no se fija. Tampoco `steps`, que no tiene base para un número.
- Plan → Build con otro modelo (el equivalente de `opusplan`) no se incluye: sería config del proyecto. Si lo
  quieres, ponlo en tu `opencode.json`; la documentación muestra un modelo distinto para `plan` y `build`, y
  usarlo como cambio de modelo es una inferencia [D]:

  ```json
  { "agent": { "plan": { "model": "anthropic/claude-opus-5-5" }, "build": { "model": "anthropic/claude-sonnet-5-5" } } }
  ```

## Fuentes

- Claude Code: modelos y `opusplan` https://code.claude.com/docs/en/model-config · agentes https://code.claude.com/docs/en/subagents · ajustes y precedencia https://code.claude.com/docs/en/settings
- Codex: modelos https://learn.chatgpt.com/codex/models · agentes personalizados https://learn.chatgpt.com/docs/agent-configuration/subagents · configuración https://learn.chatgpt.com/docs/config-file/config-reference
- VS Code Copilot: https://code.visualstudio.com/docs/agent-customization/custom-agents · GitHub Docs: configuración de agentes https://docs.github.com/en/copilot/reference/custom-agents-configuration · modelos admitidos https://docs.github.com/en/copilot/reference/ai-models/supported-models · comparación https://docs.github.com/en/copilot/reference/ai-models/model-comparison · agentes en la CLI https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/create-custom-agents-for-cli
- OpenCode: agentes https://opencode.ai/docs/agents/ · configuración https://opencode.ai/docs/config/ · modelos https://opencode.ai/docs/models/ · proveedores https://opencode.ai/docs/providers/
- Gemini CLI: https://geminicli.com/docs/cli/gemini-md
