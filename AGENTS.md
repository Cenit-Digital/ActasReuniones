# AGENTS.md — instrucciones para agentes de IA

> Punto de entrada para cualquier agente (Claude Code, Codex, Copilot, OpenCode, Gemini). Corto a propósito (menos de 200 líneas):
> lo detallado vive en `docs/`, léelo solo cuando lo necesites. Las cinco secciones son del proyecto; el bloque final lo gestiona la plantilla.

## 1. Resumen del proyecto

**Actas de las reuniones de socios de Cenit Digital**, F1 de la [decisión 0015 de KubernetesInfrastructure](https://github.com/Cenit-Digital/KubernetesInfrastructure/blob/main/docs/infraestructura/decisiones/0015-actas-de-reuniones.md) (issue KubernetesInfrastructure#223). Un supervisor en Python atiende las peticiones de grabar y parar que llegan por PostgreSQL. Controla por CDP un Chromium sin cabeza con una página espectadora de VDO.Ninja por socio conforme. Al parar, envía las pistas a la plataforma de transcripción (decisión 0017 de KubernetesInfrastructure, apartado de actas) y guarda el texto en el archivo de actas. El despliegue (espacio `actas`, red, Secrets) vive en KubernetesInfrastructure, `kubernetes/apps/actas/`.

Reglas que no se negocian:
- Son datos personales (voz y palabras de los socios).
- Ningún secreto ni texto de la reunión en los registros: la contraseña de la sala y el token se redactan.
- Solo se graba a los socios conformes de cada reunión.
- El audio vive en un tmpfs y se borra en cuanto el texto está guardado, o como mucho a los 7 días.
- Chromium nunca recibe el token ni las credenciales de la base.

## 2. Ficheros clave

| Ruta | Qué contiene |
| --- | --- |
| `src/actas/` | Módulos puros (`pistas`, `conformidad`, `estados`, `purga`, `sondeo`, `registro`, `aviso`, `transcripcion`, `salas` y `enlaces` y, del panel, `origen`, `formulario`, `busqueda`, `presentacion`) y adaptadores (`cdp`, `grabador`, `base`, `plataforma`, `metricas`), el bucle del supervisor (`supervisor`, `__main__`), las órdenes de `actas.sh` (`cli`) y el panel de F2 (`panel/`, Starlette con plantillas Jinja2) |
| `textos/` | Textos informativos versionados (`informativo-<versión>.md`) que muestra «Grabar»; la versión queda en `conformidades` |
| `migraciones/` | Esquema del inquilino `actas` del PostgreSQL compartido (lo aplica `actas_owner` en el initContainer, `python -m actas.migrar`) |
| `tests/unit/` · `tests/integracion/` | Unitarios (objetivo de la mutación) e integración con PostgreSQL (`ACTAS_DSN_PRUEBAS`, `scripts/pg-pruebas.sh`) y con Chromium (`ACTAS_CHROMIUM`) |
| `cosmic-ray.toml` | Módulos que se mutan (umbral 0,8) |
| `Dockerfile` · `.github/workflows/imagen.yml` | Imagen `ghcr.io/cenit-digital/actas-supervisor`, publicada por `:sha-<commit>` y desplegada por digest |
| `features/actas.feature` | Spec viva de la captura y la transcripción |
| `harness.config.json` | Conecta `lint`, `test` y `mutate` del arnés con uv |

## 3. Desarrollo y validación

**Cómo se ejecuta.** Empieza siempre por el entorno: `./init.sh` (POSIX), `pwsh ./init.ps1` (Windows) o `bin/harness init` (`bin\harness.ps1 init` en Windows). Si falla, **para** y resuelve el entorno antes de tocar código. Los comandos de tu stack viven en `harness.config.json` y se invocan siempre a través del arnés, nunca copiados aquí.

| Comando | Para qué |
| --- | --- |
| `bin/harness init` | Verifica el entorno y el arnés |
| `bin/harness test` | La suite de tests |
| `bin/harness mutate [objetivo]` | Prueba de mutación; solo nivel crítico, sobre los módulos que fija el plan |
| `bin/harness verify` | `init` + mutación completa; solo antes de una entrega (el cierre ordinario es `init` + `test`) |

**Al empezar una tarea.** Lee el issue (objetivo, criterios y plan) o lo que pida la persona, y la «Política de trabajo» del final de este fichero. Opcional y no bloqueante, para cualquier herramienta y si tu repo conserva `scripts/sync-memoria.*`: sincroniza la memoria de la organización con `scripts/sync-memoria.sh` (`pwsh scripts/sync-memoria.ps1` en Windows) y revisa en `.memoria-cache/patterns/` los patrones de la categoría de tu tarea antes de diseñar desde cero, respetando su «Cuándo NO aplica»; si falla (sin red o sin acceso), sigue sin ella y anótalo en el PR (`docs/memoria-organizacional.md`).

**Flujo.**
- Trabaja en una **rama nueva** desde la rama por defecto y usa **commits convencionales** (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`).
- Antes de pedir revisión, **revisa tu propio diff**: `/code-review` (Claude Code), `/review` (Codex y Copilot CLI) o, si tu herramienta no trae un comando de revisión, pide el diff a otro agente (`reviewer_frontier` o el equivalente).
- El PR sigue la plantilla de `.github/`; si el cambio es visual, adjunta imágenes o vídeo de antes y después.

## 4. Guardarraíles

- **No saltes la puerta humana:** plan aprobado antes de implementar y diff revisado en local antes de cualquier `git push`.
- **Un test por criterio** del issue; TDD estricto (`docs/tdd.md`) y mutación solo en nivel crítico.
- **Un tema por tarea y por PR**, pequeño y fácil de revisar.
- **Una tarea, una sesión:** el traspaso es el issue y el PR, no el chat. Si lo que te piden se sale del objetivo de la sesión, avisa y propón abrir una sesión nueva con un título; no la sigas aquí. Gasta poco contexto: lee solo lo necesario y resume en vez de pegar.
- **Si no sabes algo, busca en `docs/`** antes de inventarlo.
- **Si te bloqueas** (una herramienta no hace lo que esperas), no inventes un workaround: documenta el bloqueo en el issue o en el PR y para.

## 5. Definición de hecho

Una tarea está hecha cuando se cumple todo esto:

- `bin/harness init` y `bin/harness test` en verde; en nivel crítico, además, la mutación sobre los módulos del plan por encima de `mutation.threshold` (0,8 por defecto).
- Cada criterio del issue tiene su test; si cambió una capacidad, su `features/<capacidad>.feature` está actualizado en el mismo diff.
- El diff está revisado (por ti y, en local, por la persona) y el PR rellena sus bloques y marca la casilla de revisión local.
- El issue tiene las casillas del plan marcadas y «Resultados de la ejecución» rellena.
- El repo queda limpio: sin logs de debug, sin ficheros temporales, sin TODOs sin contexto.

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
