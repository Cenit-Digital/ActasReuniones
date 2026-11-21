# Diseño con Impeccable

> Toda interfaz del proyecto (web, componentes y pantallas nativas) se diseña y se revisa con la skill **Impeccable**
> (<https://github.com/pbakaus/impeccable>, Apache-2.0). Claude Design y la skill `frontend-design` están retirados.

## Qué trae la plantilla

| Ruta | Qué es |
| --- | --- |
| `.claude/skills/impeccable/` | La skill para Claude Code (`/impeccable …`), con su `LICENSE` y su `NOTICE.md` |
| `.agents/skills/impeccable/` | La misma skill para Codex |
| `.claude/agents/impeccable-*.md` | Los subagentes que la skill delega (revisión final, movimiento, documentación, recursos y ediciones manuales) |
| `.harness/impeccable-gate.mjs` | La puerta de la CI: el detector sobre las rutas web del proyecto |
| `.github/workflows/impeccable.yml` | El workflow «Diseño (Impeccable)», con su gemelo para los runners propios |

Todo es de plantilla en `harness.manifest.json`: `scripts/harness-upgrade.mjs --apply` lo pone al día. La versión está
fijada (la 4.10.0) en la puerta y en el front matter de los dos `SKILL.md`; se sube en la plantilla, nunca en un derivado.
Se instaló con:

```bash
npx impeccable@4.10.0 install -y --scope=project --providers=claude,codex --no-hooks
```

## Cómo se trabaja

1. **`/impeccable init`** una vez por proyecto: escribe `PRODUCT.md` (para quién es y qué tiene que conseguir) y
   `DESIGN.md` (el sistema de diseño: color, tipografía, espaciado, componentes). Los dos son del proyecto y se versionan.
   Las webs de una misma marca comparten su `DESIGN.md`; la web de un cliente usa el de su marca.
2. **`/impeccable shape`** antes de construir una pantalla nueva: deja el diseño acordado antes del código.
3. **`/impeccable critique`** y **`/impeccable audit`** al revisar: puntúan el resultado y listan lo que falla.
4. **`/impeccable polish`** antes de entregar. Si el cambio es visual, el PR lleva capturas de antes y después.

## La puerta de la CI

`.harness/impeccable-gate.mjs` lee `ui` de `harness.config.json`:

```json
"ui": { "paths": ["web/src"], "routes": ["/", "/reservar"], "themes": ["light", "dark"] }
```

- **`ui` es obligatorio.** Sin la clave la puerta sale con 2: no se sabe si hay web.
- **`"paths": []`:** el proyecto declara que no tiene web. La puerta comprueba que la skill está instalada, lo dice y sale
  con 0.
- **Con `ui.paths`:** `ui.routes` es obligatorio, porque el detector aplica reglas distintas según lo que analiza:
  - **Código** (`node .harness/impeccable-gate.mjs`, workflow «Diseño (Impeccable)» de la plantilla): ejecuta
    `npx impeccable@4.10.0 detect --json --report-unused-ignores -- <ficheros>` con la lista exacta de ficheros de
    `ui.paths` (sin `node_modules` ni `.git`), porque con una carpeta el detector se salta por su cuenta `dist/`, `build/`
    y otras. Sobre el código solo corren las reglas por patrón; el propio detector avisa de que el resultado se queda
    corto.
  - **Renderizado** (`node .harness/impeccable-gate.mjs --rendered <url base>`): analiza cada ruta de `ui.routes` con un
    navegador, en escritorio (1280x800) y en móvil (390x844), y en cada tema de `ui.themes` (por defecto `["light"]`;
    con `["light", "dark"]` también el oscuro). El tema se fuerza en Chromium con `--blink-settings=preferredColorScheme`
    (0 oscuro, 1 claro), así que `prefers-color-scheme` responde igual en local y en la CI. Una web con tema oscuro lo
    declara, porque si no la CI solo mide el claro. **Límite:** solo se mide el oscuro que la web activa con
    `prefers-color-scheme` (o `light-dark()`); un tema oscuro que solo se enciende con una clase, un `data-theme` o
    `localStorage` sin mirar la preferencia del sistema no se ve, y esa web tiene que seguir la preferencia del sistema
    por defecto para que la puerta lo mida. Aquí corren las reglas de página: contraste, tamaño del
    texto, jerarquía tipográfica, tarjetas anidadas, etiquetas sobre los títulos… Lo cablea **cada proyecto en su CI**,
    en el job que ya construye y sirve la app (normalmente el de e2e, con la imagen oficial de Playwright), después de
    arrancar el servidor. El navegador sale de `IMPECCABLE_BROWSER`, de Chrome o Chromium en el `PATH` o del Chromium de
    Playwright (`/ms-playwright` o `~/.cache/ms-playwright`); la puerta lo envuelve con `--no-sandbox`, porque en los
    contenedores de la CI no arranca con el sandbox. Sin navegador sale con 2: nunca se salta.
  - **Cableado obligatorio:** con web, la puerta de código suspende si ningún workflow de `.github/workflows/` ejecuta
    `impeccable-gate.mjs --rendered`.
  - **Rutas:** empiezan por `/`; con enrutado por hash, `/#/reservar`. Antes de analizar, la puerta pide cada ruta sin
    seguir redirecciones y suspende si no responde 2xx: un 302 a `/login` haría analizar otra página. Una redirección
    que hace el enrutador de la app en el navegador no se ve así, de modo que las rutas con sesión se sirven en la CI
    con las simulaciones de API y el usuario de prueba del e2e.
  - **Límite medido:** el detector espera a que la red quede quieta. Lo que llega por `fetch` se analiza, pero lo que se
    pinta más tarde con un temporizador (animaciones de entrada largas, cargas diferidas por tiempo) puede quedar
    fuera. En esos casos el estado final tiene que verse en la ruta sin esperar.
- **Qué exige**, en los dos modos: que no salga **ninguna** entrada y que el detector no escriba nada por stderr.
  - Cuentan los hallazgos y los avisos («advisory», que el detector deja salir con 0).
  - En código cuentan también los comentarios de excepción que ya no ignoran nada. `--report-unused-ignores` solo mira
    los comentarios, no las entradas de `ignoreValues` que ya no hacen falta: esas se repasan al revisar el PR.
  - Un aviso por stderr (por ejemplo, una hoja de estilos que no pudo leer) significa que el análisis quedó incompleto y
    suspende. Antes de analizar el código, cada ruta tiene que existir y tener algo que analizar, porque una carpeta
    vacía sale limpia sin mirar nada.
- **Códigos del detector**, comprobados con la 4.10.0:
  - **0:** sin hallazgos, aunque haya avisos.
  - **2:** con hallazgos o con ignorados sin uso.
  - **1:** no pudo escanear una ruta o una URL.
- **Salida de la puerta:**
  - **0:** limpio o sin web.
  - **1:** hay hallazgos o falla una comprobación.
  - **2:** el detector no pudo escanear o avisó por stderr, falta el navegador o la configuración es ilegible.

## Hooks apagados

Los hooks de Impeccable (detector tras cada edición) van **apagados**: se instala con `--no-hooks`, la puerta falla si
`.claude/settings.json` o `.codex/hooks.json` traen uno, y `.impeccable/config.json`, si existe, lleva
`"hook": { "enabled": false }` (`/impeccable hooks off`). En Codex un hook exige aprobación manual y los agentes sin
interfaz no pueden darla; la verificación es la puerta de la CI. `.impeccable/config.local.json` es personal: va en
`.gitignore`.

## Excepciones

La regla es corregir. Una excepción solo vale para algo que no se puede cambiar, como la marca de un cliente, y lleva
su motivo escrito:

- **De valor, en `.impeccable/config.json`:** `detector.ignoreValues` con `--reason`
  (`/impeccable hooks ignore-value <regla> <valor> --reason "…"`), por ejemplo la tipografía corporativa del cliente.
  Es la única que vale en los dos modos.
- **En el fichero** (`impeccable-disable-next-line <regla>: <motivo>`, `impeccable-disable-line` o
  `impeccable-disable <regla>` en el comentario del lenguaje) y **acotada a un fichero** (`ignore-value … --file`): solo
  cuentan en el análisis del código. En una URL, el detector no ve los comentarios ni sabe de qué fichero sale cada
  elemento (comprobado con la 4.10.0). La puerta rechaza el comentario sin motivo, y el detector, el que ya no ignora nada.
- **No se admiten**, porque silencian una regla o un fichero entero, incluidas las reglas que aún no existen:
  - `detector.ignoreRules` y `detector.ignoreFiles`.
  - Un `ignoreValues` con el valor `*`.
  - Un comentario sin reglas o con `*`.
  - `detector.designSystem.enabled: false`.
  - Un `.impeccable/config.local.json` en el repo: es personal y el detector también lo aplica.

## Adoptarla en un derivado

`harness-upgrade --apply` trae la skill, la puerta y su workflow. Lo demás es del proyecto y va en el mismo PR:

1. **`harness.config.json`:** el bloque `ui`, con `paths` y `routes`, o con las dos listas vacías si no hay web.
2. **`.gitattributes`:** `*.cmd text eol=crlf`, para que `scripts/impeccable.cmd` funcione en Windows. Con
   `* text=auto eol=lf` se guarda en LF y `harness-upgrade` no lo ve como deriva.
3. **`.gitignore`:** `.impeccable/config.local.json`.
4. **Fuera** la skill `frontend-design` y cualquier instrucción de Claude Design: `--apply` nunca borra.
5. **`/impeccable init`** (`PRODUCT.md` y `DESIGN.md`) y `/impeccable hooks off`.
6. **Con web:**
   - Corrige hasta 0 en los dos modos.
   - Añade el paso `node .harness/impeccable-gate.mjs --rendered <url>` al job de la CI que sirve la app.
   - Adjunta al PR las capturas de antes y después.
